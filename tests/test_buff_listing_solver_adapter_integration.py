from __future__ import annotations

import ast
import asyncio
import dataclasses
import os
import subprocess
import sys
from collections.abc import Coroutine
from dataclasses import replace
from pathlib import Path
from typing import Any, Never

import pytest

from app.services.buff_listing_qualification import (
    BuffListingQualificationResult,
    BuffListingQualificationStatus,
)
from app.services.market_scan_service import CandidateListing
from scripts import buff_listing_solver_adapter_integration as command
from scripts.buff_listing_qualification_integration import (
    BuffListingQualificationRunResult,
    run_qualification_integration,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "buff_listing_solver_adapter_integration.py"
V1_LISTINGS_FIXTURE = (
    PROJECT_ROOT / "tests" / "fixtures" / "buff" / "qualification_listings_v1.json"
)


def _run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def _qualification_run() -> BuffListingQualificationRunResult:
    return _run(
        run_qualification_integration(
            command.DEFAULT_LISTINGS_FIXTURE,
            command.DEFAULT_FACTS_FIXTURE,
        )
    )


def _integration_result() -> command.BuffListingSolverAdapterIntegrationResult:
    return _run(
        command.run_solver_adapter_integration(
            command.DEFAULT_LISTINGS_FIXTURE,
            command.DEFAULT_FACTS_FIXTURE,
        )
    )


def test_parse_options_reuses_repository_anchored_defaults() -> None:
    options = command.parse_options([])

    assert options.listings_fixture == command.DEFAULT_LISTINGS_FIXTURE
    assert options.facts_fixture == command.DEFAULT_FACTS_FIXTURE
    assert options.listings_fixture.name == "qualification_listings_v2.json"
    assert options.listings_fixture.is_absolute()
    assert options.facts_fixture.is_absolute()


def test_parse_options_accepts_only_explicit_fixture_paths(tmp_path: Path) -> None:
    options = command.parse_options(
        [
            "--listings-fixture",
            str(tmp_path / "listings.json"),
            "--facts-fixture",
            str(tmp_path / "facts.json"),
        ]
    )

    assert options.listings_fixture == tmp_path / "listings.json"
    assert options.facts_fixture == tmp_path / "facts.json"


@pytest.mark.parametrize(
    "argv",
    [
        ["--unknown"],
        ["--listings-fixture"],
        ["--listings", "x", "--facts", "y"],
    ],
)
def test_parse_options_rejects_invalid_cli_without_reflection(
    argv: list[str],
) -> None:
    with pytest.raises(
        command.BuffListingSolverAdapterIntegrationCliError
    ) as exc_info:
        command.parse_options(argv)

    assert str(exc_info.value) == ""
    assert repr(argv) not in repr(exc_info.value)


@pytest.mark.parametrize("missing", ["listings", "facts"])
def test_async_main_returns_two_for_invalid_fixture_path(
    tmp_path: Path,
    missing: str,
) -> None:
    listings = command.DEFAULT_LISTINGS_FIXTURE
    facts = command.DEFAULT_FACTS_FIXTURE
    if missing == "listings":
        listings = tmp_path / "private-listings-secret.json"
    else:
        facts = tmp_path / "private-facts-secret.json"
    lines: list[str] = []

    exit_code = _run(
        command.async_main(
            [
                "--listings-fixture",
                str(listings),
                "--facts-fixture",
                str(facts),
            ],
            printer=lines.append,
        )
    )

    assert exit_code == 2
    assert lines[0] == "Offline BUFF solver adapter integration failed: input"
    assert not any(line.startswith("Mode:") for line in lines)
    assert str(tmp_path) not in "\n".join(lines)


def test_default_integration_adapts_only_qualified_results_in_order() -> None:
    result = _integration_result()
    statuses = tuple(
        item.status
        for item in result.qualification_run_result.ordered_qualification_results
    )

    assert statuses == (
        BuffListingQualificationStatus.QUALIFIED,
        BuffListingQualificationStatus.REJECTED,
        BuffListingQualificationStatus.QUALIFIED,
        BuffListingQualificationStatus.MISSING_FACTS,
    )
    assert [candidate.price_cny for candidate in result.ordered_solver_candidates] == [
        result.qualification_run_result.ordered_candidates[0].buy_price_cny,
        result.qualification_run_result.ordered_candidates[2].buy_price_cny,
    ]
    assert result.ordered_solver_candidates[0].listing_id == (
        result.ordered_solver_candidates[1].listing_id
    )
    assert result.ordered_solver_candidates[0] is not result.ordered_solver_candidates[1]


def test_runner_calls_qualification_once_and_adapter_once_per_qualified() -> None:
    qualification_run = _qualification_run()
    qualification_calls: list[tuple[Path, Path]] = []
    adapted_results: list[BuffListingQualificationResult] = []

    async def qualification_runner(
        listings_fixture: Path,
        facts_fixture: Path,
    ) -> BuffListingQualificationRunResult:
        qualification_calls.append((listings_fixture, facts_fixture))
        return qualification_run

    from app.services.buff_listing_solver_adapter import adapt_qualified_buff_listing

    def adapter(result: BuffListingQualificationResult) -> CandidateListing:
        adapted_results.append(result)
        return adapt_qualified_buff_listing(result)

    output = _run(
        command.run_solver_adapter_integration(
            Path("unused-listings"),
            Path("unused-facts"),
            qualification_runner=qualification_runner,
            adapter=adapter,
        )
    )

    expected = (
        qualification_run.ordered_qualification_results[0],
        qualification_run.ordered_qualification_results[2],
    )
    assert qualification_calls == [(Path("unused-listings"), Path("unused-facts"))]
    assert tuple(adapted_results) == expected
    assert output.adapted_candidate_count == 2


def test_rejected_and_missing_results_never_reach_adapter() -> None:
    qualification_run = _qualification_run()
    seen_statuses: list[BuffListingQualificationStatus] = []

    from app.services.buff_listing_solver_adapter import adapt_qualified_buff_listing

    def adapter(result: BuffListingQualificationResult) -> CandidateListing:
        seen_statuses.append(result.status)
        return adapt_qualified_buff_listing(result)

    _run(
        command.run_solver_adapter_integration(
            Path("unused"),
            Path("unused"),
            qualification_runner=lambda _listings, _facts: _return(qualification_run),
            adapter=adapter,
        )
    )

    assert seen_statuses == [
        BuffListingQualificationStatus.QUALIFIED,
        BuffListingQualificationStatus.QUALIFIED,
    ]


async def _return[T](value: T) -> T:
    return value


def test_result_counts_are_derived_and_store_only_two_fields() -> None:
    result = _integration_result()

    assert result.qualification_total_count == 4
    assert result.qualified_result_count == 2
    assert result.adapted_candidate_count == 2
    assert result.skipped_rejected_count == 1
    assert result.skipped_missing_facts_count == 1
    assert [field.name for field in dataclasses.fields(result)] == [
        "qualification_run_result",
        "ordered_solver_candidates",
    ]


def test_result_is_frozen_keyword_only_tuple_backed_and_repr_safe() -> None:
    result = _integration_result()

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.ordered_solver_candidates = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        command.BuffListingSolverAdapterIntegrationResult(  # type: ignore[misc]
            result.qualification_run_result,
            result.ordered_solver_candidates,
        )
    assert type(result.ordered_solver_candidates) is tuple
    assert "qualification-synthetic" not in repr(result)
    assert "Synthetic Qualification" not in repr(result)


@pytest.mark.parametrize("invalid", [None, object(), "run-result"])
def test_result_rejects_wrong_qualification_run_type(invalid: object) -> None:
    with pytest.raises(
        command.BuffListingSolverAdapterIntegrationError
    ) as exc_info:
        command.BuffListingSolverAdapterIntegrationResult(
            qualification_run_result=invalid,  # type: ignore[arg-type]
            ordered_solver_candidates=(),
        )

    assert exc_info.value.stage == "run_result"
    assert repr(invalid) not in str(exc_info.value)


def test_result_rejects_non_tuple_and_wrong_candidate_type() -> None:
    run = _qualification_run()
    candidate = _integration_result().ordered_solver_candidates[0]

    for invalid in ([candidate, candidate], (candidate, object())):
        with pytest.raises(command.BuffListingSolverAdapterIntegrationError):
            command.BuffListingSolverAdapterIntegrationResult(
                qualification_run_result=run,
                ordered_solver_candidates=invalid,  # type: ignore[arg-type]
            )


def test_result_rejects_count_and_order_mapping_mismatch() -> None:
    result = _integration_result()

    with pytest.raises(command.BuffListingSolverAdapterIntegrationError):
        command.BuffListingSolverAdapterIntegrationResult(
            qualification_run_result=result.qualification_run_result,
            ordered_solver_candidates=result.ordered_solver_candidates[:1],
        )
    with pytest.raises(command.BuffListingSolverAdapterIntegrationError):
        command.BuffListingSolverAdapterIntegrationResult(
            qualification_run_result=result.qualification_run_result,
            ordered_solver_candidates=tuple(reversed(result.ordered_solver_candidates)),
        )


def test_runner_rejects_malformed_adapter_output() -> None:
    qualification_run = _qualification_run()

    with pytest.raises(
        command.BuffListingSolverAdapterIntegrationError
    ) as exc_info:
        _run(
            command.run_solver_adapter_integration(
                Path("unused"),
                Path("unused"),
                qualification_runner=lambda _listings, _facts: _return(
                    qualification_run
                ),
                adapter=lambda _result: object(),  # type: ignore[arg-type,return-value]
            )
        )

    assert exc_info.value.stage == "adaptation"


def test_repeated_runs_are_deterministic_and_fresh() -> None:
    first = _integration_result()
    second = _integration_result()

    assert first == second
    assert first is not second
    assert first.qualification_run_result is not second.qualification_run_result
    assert first.ordered_solver_candidates is not second.ordered_solver_candidates
    assert all(
        left is not right
        for left, right in zip(
            first.ordered_solver_candidates,
            second.ordered_solver_candidates,
            strict=True,
        )
    )


def test_second_adapter_failure_aborts_without_returning_partial_result() -> None:
    qualification_run = _qualification_run()
    calls = 0

    from app.services.buff_listing_solver_adapter import adapt_qualified_buff_listing

    def adapter(result: BuffListingQualificationResult) -> CandidateListing:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Cookie: private-secret")
        return adapt_qualified_buff_listing(result)

    with pytest.raises(
        command.BuffListingSolverAdapterIntegrationError
    ) as exc_info:
        _run(
            command.run_solver_adapter_integration(
                Path("unused"),
                Path("unused"),
                qualification_runner=lambda _listings, _facts: _return(
                    qualification_run
                ),
                adapter=adapter,
            )
        )

    assert calls == 2
    assert exc_info.value.stage == "adaptation"
    assert "private-secret" not in str(exc_info.value)


def test_v1_qualified_null_goods_id_exits_one_without_partial_summary() -> None:
    lines: list[str] = []

    exit_code = _run(
        command.async_main(
            [
                "--listings-fixture",
                str(V1_LISTINGS_FIXTURE),
                "--facts-fixture",
                str(command.DEFAULT_FACTS_FIXTURE),
            ],
            printer=lines.append,
        )
    )

    assert exit_code == 1
    assert lines[0].endswith(": adaptation")
    assert not any(line.startswith("Mode:") for line in lines)
    assert not any(line.startswith("Adapted solver candidates:") for line in lines)
    assert lines[-4:] == [
        "Recipe solver executed: no",
        "BUFF requests sent: 0",
        "SteamDT requests sent: 0",
        "Redis used: no",
    ]


@pytest.mark.parametrize("failure", [MemoryError(), asyncio.CancelledError()])
@pytest.mark.parametrize("failure_site", ["qualification", "adapter"])
def test_resource_and_cancellation_failures_propagate_by_identity(
    failure: BaseException,
    failure_site: str,
) -> None:
    qualification_run = _qualification_run()

    async def qualification_runner(
        _listings: Path,
        _facts: Path,
    ) -> BuffListingQualificationRunResult:
        if failure_site == "qualification":
            raise failure
        return qualification_run

    def adapter(_result: BuffListingQualificationResult) -> CandidateListing:
        if failure_site == "adapter":
            raise failure
        raise AssertionError("adapter should not run")

    with pytest.raises(type(failure)) as exc_info:
        _run(
            command.run_solver_adapter_integration(
                Path("unused"),
                Path("unused"),
                qualification_runner=qualification_runner,
                adapter=adapter,
            )
        )

    assert exc_info.value is failure


def test_keyboard_interrupt_from_adapter_propagates_unchanged() -> None:
    qualification_run = _qualification_run()
    expected = KeyboardInterrupt()

    def adapter(_result: BuffListingQualificationResult) -> CandidateListing:
        raise expected

    with pytest.raises(KeyboardInterrupt) as exc_info:
        _run(
            command.run_solver_adapter_integration(
                Path("unused"),
                Path("unused"),
                qualification_runner=lambda _listings, _facts: _return(
                    qualification_run
                ),
                adapter=adapter,
            )
        )

    assert exc_info.value is expected


def test_success_output_contains_only_required_safe_candidate_fields() -> None:
    lines: list[str] = []

    assert _run(command.async_main([], printer=lines.append)) == 0

    assert lines[:6] == [
        "Mode: offline-fixture",
        "Qualification results: 4",
        "Qualified results: 2",
        "Adapted solver candidates: 2",
        "Skipped rejected: 1",
        "Skipped missing facts: 1",
    ]
    assert lines.count("  Source: buff") == 2
    assert lines.count("  Float present: yes") == 2
    assert lines[-4:] == [
        "Recipe solver executed: no",
        "BUFF requests sent: 0",
        "SteamDT requests sent: 0",
        "Redis used: no",
    ]


def test_output_omits_candidate_values_paths_and_transport_data() -> None:
    result = _integration_result()
    lines: list[str] = []

    assert _run(command.async_main([], printer=lines.append)) == 0
    output = "\n".join(lines)

    forbidden = {
        str(command.DEFAULT_LISTINGS_FIXTURE),
        str(command.DEFAULT_FACTS_FIXTURE),
        "qualification-synthetic-001",
        "qualification-synthetic-goods-001",
        "100.25",
        "99.75",
        "0.10",
        "0.20",
        "CandidateListing",
        "inspect_link",
        "raw",
        "paint_seed",
        "Traceback",
    }
    forbidden.update(
        candidate.listing_id for candidate in result.ordered_solver_candidates
    )
    forbidden.update(candidate.goods_id for candidate in result.ordered_solver_candidates)
    assert all(value not in output for value in forbidden)


def test_safe_renderer_redacts_secret_and_url_shaped_market_name() -> None:
    qualification_run = _qualification_run()
    first = qualification_run.ordered_candidates[0]
    unsafe = replace(
        first,
        market_hash_name="Cookie=private-secret https://private.example/path",
    )
    tampered_run = object.__new__(BuffListingQualificationRunResult)
    object.__setattr__(tampered_run, "ordered_candidates", (unsafe,))
    qualified = qualification_run.ordered_qualification_results[0]
    object.__setattr__(qualified, "candidate", unsafe)
    object.__setattr__(tampered_run, "ordered_qualification_results", (qualified,))
    adapted = _integration_result().ordered_solver_candidates[0]
    object.__setattr__(adapted, "market_hash_name", unsafe.market_hash_name)
    integration = object.__new__(command.BuffListingSolverAdapterIntegrationResult)
    object.__setattr__(integration, "qualification_run_result", tampered_run)
    object.__setattr__(integration, "ordered_solver_candidates", (adapted,))

    output = "\n".join(command._build_summary_lines(integration))

    assert '"[REDACTED]"' in output
    assert "private-secret" not in output
    assert "private.example" not in output


def test_main_maps_keyboard_interrupt_to_130(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(coroutine: object) -> Never:
        if hasattr(coroutine, "close"):
            coroutine.close()  # type: ignore[attr-defined]
        raise KeyboardInterrupt

    monkeypatch.setattr(command.asyncio, "run", interrupt)

    with pytest.raises(SystemExit) as exc_info:
        command.main()

    assert exc_info.value.code == 130


@pytest.mark.parametrize(
    "entrypoint",
    [
        [str(SCRIPT_PATH)],
        ["-m", "scripts.buff_listing_solver_adapter_integration"],
    ],
)
def test_direct_and_module_entrypoints_succeed_with_same_output(
    entrypoint: list[str],
) -> None:
    completed = subprocess.run(
        [sys.executable, *entrypoint],
        cwd=PROJECT_ROOT,
        env={key: value for key, value in os.environ.items() if "SECRET" not in key},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0
    assert "Adapted solver candidates: 2" in completed.stdout
    assert "Recipe solver executed: no" in completed.stdout
    assert "BUFF requests sent: 0" in completed.stdout
    assert "SteamDT requests sent: 0" in completed.stdout
    assert "Redis used: no" in completed.stdout
    assert "qualification-synthetic" not in completed.stdout
    assert completed.stderr == ""


def test_direct_and_module_entrypoint_outputs_are_identical() -> None:
    environment = {
        key: value for key, value in os.environ.items() if "SECRET" not in key
    }
    direct = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    module = subprocess.run(
        [sys.executable, "-m", "scripts.buff_listing_solver_adapter_integration"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert direct.returncode == module.returncode == 0
    assert direct.stdout == module.stdout
    assert direct.stderr == module.stderr == ""


def test_import_has_no_fixture_environment_or_runtime_side_effects() -> None:
    probe = """
import asyncio
import os
from pathlib import Path
Path.read_text = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('read'))
os.getenv = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('env'))
asyncio.create_task = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('task'))
import scripts.buff_listing_solver_adapter_integration
print('imported')
"""
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "imported"
    assert completed.stderr == ""


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_command_has_no_direct_recipe_metadata_runtime_or_external_imports() -> None:
    imported = _imported_modules(SCRIPT_PATH)
    forbidden = {
        "recipe_solver",
        "metadata",
        "pipeline",
        "scheduler",
        "fastapi",
        "httpx",
        "requests",
        "steamdt",
        "redis",
        "config",
        "discord",
        "database",
        "clients",
        "risk",
        "valuation",
    }

    assert not {
        module
        for module in imported
        if any(fragment in module.casefold() for fragment in forbidden)
    }
    assert not any(module == "os" or module.startswith("os.") for module in imported)


def test_command_has_no_solver_network_or_background_calls() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)

    assert called.isdisjoint(
        {
            "solve_recipes",
            "lookup_metadata",
            "get_sell_orders",
            "create_task",
            "gather",
            "sleep",
            "to_thread",
            "run_in_executor",
            "Thread",
            "start",
            "getenv",
            "environ",
            "urlopen",
            "request",
            "connect",
        }
    )


def test_application_modules_do_not_reverse_import_integration_command() -> None:
    references = [
        path
        for path in (PROJECT_ROOT / "app").rglob("*.py")
        if "buff_listing_solver_adapter_integration" in path.read_text(
            encoding="utf-8"
        )
    ]

    assert references == []
