from __future__ import annotations

import ast
import asyncio
import dataclasses
import json
import os
import subprocess
import sys
from collections.abc import Coroutine, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Never

import pytest

from app.services.buff_listing import (
    BuffListingObservation,
    BuffTradableCandidate,
    normalize_buff_listing,
)
from app.services.buff_listing_eligibility import (
    BuffListingEligibilityPolicy,
    BuffListingIneligibilityReason,
)
from app.services.buff_listing_facts import (
    BuffListingFactsRecord,
    OfflineBuffListingFactsProvider,
)
from app.services.buff_listing_qualification import (
    BuffListingQualificationResult,
    BuffListingQualificationService,
    BuffListingQualificationStatus,
)
from scripts import buff_listing_qualification_integration as command

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "buff_listing_qualification_integration.py"


def _run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def _observation(
    *,
    listing_id: str = "test-listing",
    market_hash_name: str = "Synthetic Test Item",
) -> BuffListingObservation:
    return BuffListingObservation(
        listing_id=listing_id,
        market_hash_name=market_hash_name,
        price_cny=Decimal("10.00"),
        quantity=1,
        float_value=Decimal("0.10"),
        wear_name="Factory New",
        paint_seed=1,
        observed_at=datetime(2026, 7, 25, tzinfo=UTC),
    )


def _candidate(
    *,
    listing_id: str = "test-listing",
    market_hash_name: str = "Synthetic Test Item",
) -> BuffTradableCandidate:
    return normalize_buff_listing(
        _observation(
            listing_id=listing_id,
            market_hash_name=market_hash_name,
        )
    )


async def _qualified_result(
    candidate: BuffTradableCandidate,
) -> BuffListingQualificationResult:
    provider = OfflineBuffListingFactsProvider(
        (
            BuffListingFactsRecord(
                listing_id=candidate.listing_id,
                market_hash_name=candidate.market_hash_name,
                is_stattrak=False,
                is_souvenir=False,
                has_special_seed=False,
            ),
        )
    )
    return await BuffListingQualificationService(provider).qualify(
        candidate,
        BuffListingEligibilityPolicy(),
    )


def _write_fixture(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _listing_payload(*, name: str = "Synthetic Test Item") -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": "buff",
        "observed_at": "2026-07-25T12:00:00Z",
        "listings": [
            {
                "listing_id": "test-listing",
                "market_hash_name": name,
                "price_cny": "10.00",
                "quantity": 1,
                "float_value": "0.10",
                "wear_name": "Factory New",
                "paint_seed": 1,
                "sticker_metadata": None,
            }
        ],
    }


def _facts_payload(*, name: str = "Synthetic Test Item") -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": "buff",
        "records": [
            {
                "listing_id": "test-listing",
                "market_hash_name": name,
                "is_stattrak": False,
                "is_souvenir": False,
                "has_special_seed": False,
            }
        ],
    }


def test_parse_options_uses_repository_anchored_default_fixtures() -> None:
    options = command.parse_options([])

    assert options.listings_fixture == command.DEFAULT_LISTINGS_FIXTURE
    assert options.facts_fixture == command.DEFAULT_FACTS_FIXTURE
    assert options.listings_fixture.is_absolute()
    assert options.facts_fixture.is_absolute()


def test_parse_options_accepts_explicit_fixture_paths(tmp_path: Path) -> None:
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
def test_parse_options_rejects_invalid_cli_without_reflecting_input(
    argv: list[str],
) -> None:
    with pytest.raises(command.BuffListingQualificationIntegrationCliError) as exc_info:
        command.parse_options(argv)

    assert str(exc_info.value) == ""
    assert repr(argv) not in repr(exc_info.value)


@pytest.mark.parametrize("missing", ["listings", "facts"])
def test_async_main_returns_two_for_missing_fixture_path(
    tmp_path: Path,
    missing: str,
) -> None:
    listings = tmp_path / "listings.json"
    facts = tmp_path / "facts.json"
    if missing != "listings":
        _write_fixture(listings, _listing_payload())
    if missing != "facts":
        _write_fixture(facts, _facts_payload())
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
    assert lines[0] == "Offline BUFF qualification failed: input"
    assert str(tmp_path) not in "\n".join(lines)


def test_async_main_returns_two_for_directory_path(tmp_path: Path) -> None:
    lines: list[str] = []

    exit_code = _run(
        command.async_main(
            [
                "--listings-fixture",
                str(tmp_path),
                "--facts-fixture",
                str(command.DEFAULT_FACTS_FIXTURE),
            ],
            printer=lines.append,
        )
    )

    assert exit_code == 2
    assert not any(line.startswith("Mode:") for line in lines)


def test_real_integration_preserves_expected_status_order() -> None:
    result = _run(
        command.run_qualification_integration(
            command.DEFAULT_LISTINGS_FIXTURE,
            command.DEFAULT_FACTS_FIXTURE,
        )
    )

    assert tuple(item.status for item in result.ordered_qualification_results) == (
        BuffListingQualificationStatus.QUALIFIED,
        BuffListingQualificationStatus.REJECTED,
        BuffListingQualificationStatus.QUALIFIED,
        BuffListingQualificationStatus.MISSING_FACTS,
    )


def test_real_integration_preserves_duplicate_identity_and_input_order() -> None:
    result = _run(
        command.run_qualification_integration(
            command.DEFAULT_LISTINGS_FIXTURE,
            command.DEFAULT_FACTS_FIXTURE,
        )
    )

    assert len(result.ordered_candidates) == 4
    assert result.ordered_candidates[0].listing_id == result.ordered_candidates[2].listing_id
    assert result.ordered_candidates[0].market_hash_name == (
        result.ordered_candidates[2].market_hash_name
    )
    assert result.ordered_candidates[0].buy_price_cny == Decimal("100.25")
    assert result.ordered_candidates[2].buy_price_cny == Decimal("99.75")


def test_run_result_counts_are_derived_from_ordered_results() -> None:
    result = _run(
        command.run_qualification_integration(
            command.DEFAULT_LISTINGS_FIXTURE,
            command.DEFAULT_FACTS_FIXTURE,
        )
    )

    assert result.total_count == 4
    assert result.qualified_count == 2
    assert result.rejected_count == 1
    assert result.missing_facts_count == 1
    assert [field.name for field in dataclasses.fields(result)] == [
        "ordered_candidates",
        "ordered_qualification_results",
    ]


def test_run_result_is_frozen_keyword_only_tuple_backed_and_repr_safe() -> None:
    candidate = _candidate()
    qualification = _run(_qualified_result(candidate))
    result = command.BuffListingQualificationRunResult(
        ordered_candidates=(candidate,),
        ordered_qualification_results=(qualification,),
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.ordered_candidates = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        command.BuffListingQualificationRunResult((candidate,), (qualification,))  # type: ignore[misc]
    assert type(result.ordered_candidates) is tuple
    assert "test-listing" not in repr(result)


def test_run_result_rejects_length_mismatch() -> None:
    with pytest.raises(command.BuffListingQualificationIntegrationError) as exc_info:
        command.BuffListingQualificationRunResult(
            ordered_candidates=(_candidate(),),
            ordered_qualification_results=(),
        )

    assert exc_info.value.stage == "run_result"


def test_run_result_rejects_positional_candidate_mismatch() -> None:
    first = _candidate(listing_id="first")
    second = _candidate(listing_id="second")
    qualification = _run(_qualified_result(first))

    with pytest.raises(command.BuffListingQualificationIntegrationError):
        command.BuffListingQualificationRunResult(
            ordered_candidates=(second,),
            ordered_qualification_results=(qualification,),
        )


def test_rejected_result_preserves_existing_canonical_reason() -> None:
    result = _run(
        command.run_qualification_integration(
            command.DEFAULT_LISTINGS_FIXTURE,
            command.DEFAULT_FACTS_FIXTURE,
        )
    )
    rejected = result.ordered_qualification_results[1]

    assert rejected.decision is not None
    assert rejected.decision.reasons == (
        BuffListingIneligibilityReason.STATTRAK_DISALLOWED,
    )


def test_missing_result_never_manufactures_false_facts() -> None:
    result = _run(
        command.run_qualification_integration(
            command.DEFAULT_LISTINGS_FIXTURE,
            command.DEFAULT_FACTS_FIXTURE,
        )
    )
    missing = result.ordered_qualification_results[3]

    assert missing.status is BuffListingQualificationStatus.MISSING_FACTS
    assert missing.lookup_result.facts is None
    assert missing.decision is None


def test_repeated_real_runs_are_deterministic_and_fresh() -> None:
    first = _run(
        command.run_qualification_integration(
            command.DEFAULT_LISTINGS_FIXTURE,
            command.DEFAULT_FACTS_FIXTURE,
        )
    )
    second = _run(
        command.run_qualification_integration(
            command.DEFAULT_LISTINGS_FIXTURE,
            command.DEFAULT_FACTS_FIXTURE,
        )
    )

    assert first == second
    assert first is not second
    assert first.ordered_candidates is not second.ordered_candidates
    assert first.ordered_qualification_results is not second.ordered_qualification_results


def test_orchestration_uses_required_order_and_one_call_per_candidate() -> None:
    events: list[str] = []
    observations = (_observation(listing_id="one"), _observation(listing_id="two"))
    records = (
        BuffListingFactsRecord(
            listing_id="one",
            market_hash_name="Synthetic Test Item",
            is_stattrak=False,
            is_souvenir=False,
            has_special_seed=False,
        ),
        BuffListingFactsRecord(
            listing_id="two",
            market_hash_name="Synthetic Test Item",
            is_stattrak=False,
            is_souvenir=False,
            has_special_seed=False,
        ),
    )

    def load_listings(path: Path) -> tuple[BuffListingObservation, ...]:
        events.append("load_listings")
        return observations

    def normalize(observation: BuffListingObservation) -> BuffTradableCandidate:
        events.append(f"normalize:{observation.listing_id}")
        return normalize_buff_listing(observation)

    def load_facts(path: Path) -> tuple[BuffListingFactsRecord, ...]:
        events.append("load_facts")
        return records

    def build_provider(
        values: Sequence[BuffListingFactsRecord],
    ) -> OfflineBuffListingFactsProvider:
        events.append("provider")
        return OfflineBuffListingFactsProvider(values)

    def build_policy() -> BuffListingEligibilityPolicy:
        events.append("policy")
        return BuffListingEligibilityPolicy()

    class Service:
        async def qualify(
            self,
            candidate: BuffTradableCandidate,
            policy: BuffListingEligibilityPolicy,
        ) -> BuffListingQualificationResult:
            events.append(f"qualify:{candidate.listing_id}")
            provider = OfflineBuffListingFactsProvider(records)
            return await BuffListingQualificationService(provider).qualify(
                candidate,
                policy,
            )

    def build_service(provider: OfflineBuffListingFactsProvider) -> Service:
        events.append("service")
        return Service()

    result = _run(
        command.run_qualification_integration(
            Path("unused-listings"),
            Path("unused-facts"),
            listing_loader=load_listings,
            normalizer=normalize,
            facts_loader=load_facts,
            provider_factory=build_provider,
            policy_factory=build_policy,
            service_factory=build_service,
        )
    )

    assert result.total_count == 2
    assert events == [
        "load_listings",
        "normalize:one",
        "normalize:two",
        "load_facts",
        "provider",
        "policy",
        "service",
        "qualify:one",
        "qualify:two",
    ]


def test_real_service_performs_one_lookup_per_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    original = OfflineBuffListingFactsProvider.lookup_facts
    queried_ids: list[str] = []

    async def counted_lookup(
        self: OfflineBuffListingFactsProvider,
        candidate: BuffTradableCandidate,
    ) -> object:
        queried_ids.append(candidate.listing_id)
        return await original(self, candidate)

    monkeypatch.setattr(OfflineBuffListingFactsProvider, "lookup_facts", counted_lookup)

    result = _run(
        command.run_qualification_integration(
            command.DEFAULT_LISTINGS_FIXTURE,
            command.DEFAULT_FACTS_FIXTURE,
        )
    )

    assert result.total_count == 4
    assert queried_ids == [
        "qualification-synthetic-001",
        "qualification-synthetic-002",
        "qualification-synthetic-001",
        "qualification-synthetic-003",
    ]


def test_normalization_failure_stops_before_facts_loading() -> None:
    events: list[str] = []

    def fail_normalization(observation: BuffListingObservation) -> BuffTradableCandidate:
        events.append("normalization")
        raise ValueError("unsafe nested message")

    def unexpected_facts(path: Path) -> tuple[BuffListingFactsRecord, ...]:
        events.append("facts")
        return ()

    with pytest.raises(command.BuffListingQualificationIntegrationError) as exc_info:
        _run(
            command.run_qualification_integration(
                Path("unused"),
                Path("unused"),
                listing_loader=lambda path: (_observation(),),
                normalizer=fail_normalization,
                facts_loader=unexpected_facts,
            )
        )

    assert exc_info.value.stage == "normalization"
    assert events == ["normalization"]
    assert "unsafe nested message" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("fixture_name", "payload", "expected_stage"),
    [
        ("listings", {"invalid": True}, "listing_fixture"),
        ("facts", {"invalid": True}, "facts_fixture"),
    ],
)
def test_malformed_fixture_content_returns_one_without_partial_summary(
    tmp_path: Path,
    fixture_name: str,
    payload: object,
    expected_stage: str,
) -> None:
    listings = _write_fixture(tmp_path / "listings.json", _listing_payload())
    facts = _write_fixture(tmp_path / "facts.json", _facts_payload())
    _write_fixture(listings if fixture_name == "listings" else facts, payload)
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

    assert exit_code == 1
    assert lines[0] == f"Offline BUFF qualification failed: {expected_stage}"
    assert not any(line.startswith("Listings:") for line in lines)
    assert not any(line.startswith("Listing 0:") for line in lines)
    assert "Traceback" not in "\n".join(lines)


def test_qualification_failure_stops_without_publishing_partial_result() -> None:
    calls: list[str] = []

    class Service:
        async def qualify(
            self,
            candidate: BuffTradableCandidate,
            policy: BuffListingEligibilityPolicy,
        ) -> BuffListingQualificationResult:
            calls.append(candidate.listing_id)
            if len(calls) == 2:
                raise RuntimeError("secret second failure")
            return await _qualified_result(candidate)

    with pytest.raises(command.BuffListingQualificationIntegrationError) as exc_info:
        _run(
            command.run_qualification_integration(
                Path("unused"),
                Path("unused"),
                listing_loader=lambda path: (
                    _observation(listing_id="one"),
                    _observation(listing_id="two"),
                    _observation(listing_id="three"),
                ),
                facts_loader=lambda path: (),
                service_factory=lambda provider: Service(),
            )
        )

    assert exc_info.value.stage == "qualification"
    assert calls == ["one", "two"]
    assert "secret second failure" not in str(exc_info.value)


def test_invalid_service_result_stops_before_later_candidates() -> None:
    calls: list[str] = []

    class Service:
        async def qualify(
            self,
            candidate: BuffTradableCandidate,
            policy: BuffListingEligibilityPolicy,
        ) -> object:
            calls.append(candidate.listing_id)
            return object()

    with pytest.raises(command.BuffListingQualificationIntegrationError) as exc_info:
        _run(
            command.run_qualification_integration(
                Path("unused"),
                Path("unused"),
                listing_loader=lambda path: (
                    _observation(listing_id="one"),
                    _observation(listing_id="two"),
                ),
                facts_loader=lambda path: (),
                service_factory=lambda provider: Service(),  # type: ignore[arg-type]
            )
        )

    assert exc_info.value.stage == "qualification"
    assert calls == ["one"]


@pytest.mark.parametrize("failure", [MemoryError(), asyncio.CancelledError()])
def test_resource_and_cancellation_failures_propagate_by_identity(
    failure: BaseException,
) -> None:
    class Service:
        async def qualify(
            self,
            candidate: BuffTradableCandidate,
            policy: BuffListingEligibilityPolicy,
        ) -> BuffListingQualificationResult:
            raise failure

    with pytest.raises(type(failure)) as exc_info:
        _run(
            command.run_qualification_integration(
                Path("unused"),
                Path("unused"),
                listing_loader=lambda path: (_observation(),),
                facts_loader=lambda path: (),
                service_factory=lambda provider: Service(),
            )
        )

    assert exc_info.value is failure


def test_async_main_complete_business_outcomes_return_zero() -> None:
    lines: list[str] = []

    exit_code = _run(command.async_main([], printer=lines.append))

    assert exit_code == 0
    assert "Rejected: 1" in lines
    assert "Missing facts: 1" in lines


def test_success_output_contains_required_safe_summary() -> None:
    lines: list[str] = []

    assert _run(command.async_main([], printer=lines.append)) == 0

    assert lines[:5] == [
        "Mode: offline-fixture",
        "Listings: 4",
        "Qualified: 2",
        "Rejected: 1",
        "Missing facts: 1",
    ]
    assert "  Qualification status: qualified" in lines
    assert "  Qualification status: rejected" in lines
    assert "  Qualification status: missing_facts" in lines
    assert "  Rejection reasons: stattrak_disallowed" in lines
    assert lines[-3:] == [
        "BUFF requests sent: 0",
        "SteamDT requests sent: 0",
        "Redis used: no",
    ]


def test_safe_external_text_escapes_control_characters() -> None:
    rendered = command._safe_external_text(
        _candidate(market_hash_name="line one\nline two\t\x1b[31m")
    )

    assert rendered == '"line one\\nline two\\t\\u001b[31m"'
    assert "\n" not in rendered
    assert "\x1b" not in rendered


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "Cookie=session-secret",
        "Authorization: Bearer credential-secret",
        "X-API-Key sk-live-credential-secret",
        "api_key=credential-secret",
        "Authorization: Basic dXNlcjpwYXNz",
        "Basic dGVzdDp0ZXN0",
        "Bearer credential-secret",
        "sessionid=abc; locale=en-US",
        "token=credential-secret",
        "access_token=credential-secret",
        "password=credential-secret",
        "https://secret.example/path",
        "redis://user:credential-secret@host/0",
        "prefix_https://user:credential-secret@example.com/path",
        "mailto:user:credential-secret@example.com",
        "www.example.com/path",
        "//example.com/path",
        "https%3A%2F%2Fexample.com%2Fpath",
    ],
)
def test_safe_external_text_redacts_prohibited_segments(unsafe_value: str) -> None:
    rendered = command._safe_external_text(
        _candidate(market_hash_name=f"Synthetic {unsafe_value} Item")
    )

    assert rendered == '"[REDACTED]"'


def test_safe_external_text_redacts_embedded_listing_id() -> None:
    candidate = _candidate(
        listing_id="private-listing-7f4c9",
        market_hash_name="Synthetic private-listing-7f4c9 Item",
    )

    assert command._safe_external_text(candidate) == '"[REDACTED]"'


def test_output_does_not_include_listing_ids_or_fixture_paths() -> None:
    lines: list[str] = []

    assert _run(command.async_main([], printer=lines.append)) == 0
    output = "\n".join(lines)

    assert "qualification-synthetic-001" not in output
    assert str(command.DEFAULT_LISTINGS_FIXTURE) not in output
    assert str(command.DEFAULT_FACTS_FIXTURE) not in output
    assert "BuffTradableCandidate" not in output
    assert "BuffListingEligibilityFacts" not in output


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
        ["-m", "scripts.buff_listing_qualification_integration"],
    ],
)
def test_direct_and_module_entrypoints_succeed(entrypoint: list[str]) -> None:
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
    assert "Mode: offline-fixture" in completed.stdout
    assert "Qualified: 2" in completed.stdout
    assert "Rejected: 1" in completed.stdout
    assert "Missing facts: 1" in completed.stdout
    assert "BUFF requests sent: 0" in completed.stdout
    assert "SteamDT requests sent: 0" in completed.stdout
    assert "Redis used: no" in completed.stdout
    assert completed.stderr == ""


def test_default_paths_are_independent_of_process_working_directory(
    tmp_path: Path,
) -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(PROJECT_ROOT)
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.buff_listing_qualification_integration"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0
    assert "Listings: 4" in completed.stdout
    assert completed.stderr == ""


def test_import_has_no_fixture_environment_or_runtime_side_effects() -> None:
    probe = """
import os
from pathlib import Path
Path.read_text = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('read'))
os.getenv = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('env'))
import scripts.buff_listing_qualification_integration
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


def test_dedicated_fixtures_are_synthetic_and_secret_free() -> None:
    serialized = (
        command.DEFAULT_LISTINGS_FIXTURE.read_text(encoding="utf-8")
        + command.DEFAULT_FACTS_FIXTURE.read_text(encoding="utf-8")
    ).lower()

    assert "synthetic" in serialized
    for forbidden in (
        "seller",
        "cookie",
        "authorization",
        "bearer",
        "token",
        "password",
        "http://",
        "https://",
        "inspect_link",
        "endpoint",
    ):
        assert forbidden not in serialized


def _imported_modules(source: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_command_imports_only_offline_buff_boundaries() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    imported = _imported_modules(source)
    forbidden_fragments = {
        "httpx",
        "requests",
        "redis",
        "steamdt",
        "config",
        "scanner",
        "solver",
        "risk",
        "valuation",
        "pipeline",
        "scheduler",
        "fastapi",
        "discord",
        "database",
        "clients",
    }

    assert not {
        module
        for module in imported
        if any(fragment in module.lower() for fragment in forbidden_fragments)
    }
    assert not any(module == "os" or module.startswith("os.") for module in imported)


def test_command_has_no_network_background_or_environment_calls() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    forbidden_calls = {
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
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called_names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called_names.add(node.func.attr)

    assert called_names.isdisjoint(forbidden_calls)


def test_application_modules_do_not_reverse_import_integration_command() -> None:
    references: list[Path] = []
    for path in (PROJECT_ROOT / "app").rglob("*.py"):
        if "buff_listing_qualification_integration" in path.read_text(encoding="utf-8"):
            references.append(path)

    assert references == []
