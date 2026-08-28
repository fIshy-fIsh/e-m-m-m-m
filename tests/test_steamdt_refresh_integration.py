import ast
import asyncio
import os
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import NoReturn

import pytest

from app.clients.steamdt_client import SteamDTPlatformPrice
from app.services.steamdt_price_refresh_service import SteamDTFetchedPriceSnapshot
from scripts import steamdt_refresh_integration as command


class CandidateClient:
    def __init__(
        self,
        candidates: list[SteamDTPlatformPrice] | None = None,
        *,
        error: Exception | None = None,
        blocker: asyncio.Event | None = None,
    ) -> None:
        self.candidates = candidates or _candidates()
        self.error = error
        self.blocker = blocker
        self.calls: list[str] = []
        self.cancelled = False

    async def get_price_single_candidates(
        self,
        market_hash_name: str,
    ) -> list[SteamDTPlatformPrice]:
        self.calls.append(market_hash_name)
        try:
            if self.blocker is not None:
                await self.blocker.wait()
            if self.error is not None:
                raise self.error
            return self.candidates
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class FakeRuntime:
    def __init__(
        self,
        client: CandidateClient | None = None,
        *,
        request_count: object = 0,
        close_error: Exception | None = None,
    ) -> None:
        self.client = client or CandidateClient()
        self._request_count = request_count
        self.close_error = close_error
        self.closed = 0

    @property
    def request_count(self) -> int:
        if isinstance(self._request_count, Exception):
            raise self._request_count
        return self._request_count  # type: ignore[return-value]

    async def aclose(self) -> None:
        self.closed += 1
        if self.close_error is not None:
            raise self.close_error


class SnapshotSource:
    def __init__(
        self,
        candidates: tuple[SteamDTPlatformPrice, ...],
        *,
        error: Exception | None = None,
        blocker: asyncio.Event | None = None,
    ) -> None:
        self.candidates = candidates
        self.error = error
        self.blocker = blocker
        self.calls: list[str] = []
        self.cancelled = False

    async def fetch_price_snapshot(
        self,
        market_hash_name: str,
    ) -> SteamDTFetchedPriceSnapshot:
        self.calls.append(market_hash_name)
        try:
            if self.blocker is not None:
                await self.blocker.wait()
            if self.error is not None:
                raise self.error
            return SteamDTFetchedPriceSnapshot(
                market_hash_name=market_hash_name,
                source="steamdt",
                candidates=self.candidates,
                observed_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            )
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def _candidates(
    *,
    second_platform: str = "second",
) -> list[SteamDTPlatformPrice]:
    return [
        SteamDTPlatformPrice(
            platform="first",
            sell_price_cny=Decimal("12.50"),
            sell_count=10,
        ),
        SteamDTPlatformPrice(
            platform=second_platform,
            sell_price_cny=Decimal("10.25"),
            sell_count=8,
        ),
    ]


def _run(
    *args: str,
    environ: Mapping[str, str] | None = None,
    **kwargs: object,
) -> tuple[int, list[str]]:
    lines: list[str] = []
    exit_code = asyncio.run(
        command.async_main(
            list(args),
            environ if environ is not None else {},
            printer=lines.append,
            **kwargs,  # type: ignore[arg-type]
        )
    )
    return exit_code, lines


def _live_args(*items: str) -> tuple[str, ...]:
    args = ["--mode", "live"]
    for item in items or ("A",):
        args.extend(("--item", item))
    return tuple(args)


def test_import_has_no_environment_or_runtime_side_effects() -> None:
    assert command.RUN_GATE_ENV == "STEAMDT_RUN_REFRESH_INTEGRATION"
    assert command.DEFAULT_CHUNK_SIZE == 5
    assert command.DEFAULT_MAX_CONCURRENCY == 2


def test_parse_options_preserves_raw_repeated_items_and_defaults() -> None:
    options = command.parse_options(["--item", " A ", "--item", "A"])

    assert options.mode == "fake"
    assert options.items == (" A ", "A")
    assert options.chunk_size == 5
    assert options.max_concurrency == 2


def test_parse_options_accepts_explicit_values() -> None:
    options = command.parse_options(
        [
            "--mode",
            "live",
            "--item",
            "A",
            "--chunk-size",
            "3",
            "--max-concurrency",
            "4",
        ]
    )

    assert options == command.SteamDTRefreshIntegrationOptions(
        mode="live",
        items=("A",),
        chunk_size=3,
        max_concurrency=4,
    )


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("--item", "A", "--mode", "unknown"),
        ("--item", "A", "--chunk-size", "0"),
        ("--item", "A", "--chunk-size", "-1"),
        ("--item", "A", "--chunk-size", "1.5"),
        ("--item", "A", "--max-concurrency", "0"),
        ("--item", "A", "--unknown"),
    ],
)
def test_cli_validation_returns_two(args: tuple[str, ...]) -> None:
    exit_code, lines = _run(*args)

    assert exit_code == 2
    assert lines[-2:] == ["SteamDT requests sent: 0", "Redis used: no"]
    assert not any("Traceback" in line for line in lines)


def test_blank_item_is_rejected_by_real_planner() -> None:
    exit_code, lines = _run("--item", "   ")

    assert exit_code == 2
    assert "SteamDTRefreshPlannerValidationError" in lines[0]


def test_fake_single_item_runs_complete_real_chain() -> None:
    exit_code, lines = _run("--item", "A")
    output = "\n".join(lines)

    assert exit_code == 0
    assert "Mode: fake" in output
    assert "Synthetic data: yes" in output
    assert "Refresh success: 1" in output
    assert "Selected quotes: 1" in output
    assert 'Selected platform: "synthetic-beta"' in output
    assert "Selected price: 99.50" in output
    assert "SteamDT requests sent: 0" in output
    assert "Redis used: no" in output


def test_fake_duplicate_chain_uses_planner_canonical_order_and_counts() -> None:
    exit_code, lines = _run(
        "--item",
        " A ",
        "--item",
        "B",
        "--item",
        "A",
        "--chunk-size",
        "1",
    )
    output = "\n".join(lines)

    assert exit_code == 0
    assert "Input items: 3" in output
    assert "Unique items: 2" in output
    assert "Duplicates removed: 1" in output
    assert "Chunks: 2" in output
    assert output.index('Canonical item: "A"') < output.index('Canonical item: "B"')
    assert "Occurrence count: 2" in output


def test_fake_mode_does_not_read_environment_or_create_live_runtime() -> None:
    class NoReadMapping(Mapping[str, str]):
        def __getitem__(self, key: str) -> str:
            raise AssertionError(key)

        def __iter__(self):  # type: ignore[no-untyped-def]
            return iter(())

        def __len__(self) -> int:
            return 0

        def get(self, key: str, default: str | None = None) -> str | None:
            raise AssertionError(key)

    async def forbidden_runtime(
        _environ: Mapping[str, str],
    ) -> FakeRuntime:
        raise AssertionError("live runtime must not be created")

    exit_code, _lines = _run(
        "--item",
        "A",
        environ=NoReadMapping(),
        live_runtime_factory=forbidden_runtime,
    )

    assert exit_code == 0


def test_fake_source_uses_decimal_candidates_and_real_cached_selector() -> None:
    source = SnapshotSource(tuple(_candidates()))

    exit_code, lines = _run(
        "--item",
        "A",
        fake_source_factory=lambda: source,
    )
    output = "\n".join(lines)

    assert exit_code == 0
    assert source.calls == ["A"]
    assert 'Selected platform: "second"' in output
    assert "Selected price: 10.25" in output


def test_no_candidates_is_normal_success_and_cache_miss() -> None:
    source = SnapshotSource(())

    exit_code, lines = _run(
        "--item",
        "A",
        fake_source_factory=lambda: source,
    )
    output = "\n".join(lines)

    assert exit_code == 0
    assert "No candidates: 1" in output
    assert "Refresh status: no_candidates" in output
    assert "Cache lookup hit: False" in output
    assert "Resolution status: miss" in output
    assert "Selected quotes: 0" in output


def test_item_failure_is_isolated_resolved_as_miss_and_exits_one() -> None:
    source = SnapshotSource((), error=RuntimeError("secret-message"))

    exit_code, lines = _run(
        "--item",
        "A",
        "--item",
        "B",
        fake_source_factory=lambda: source,
    )
    output = "\n".join(lines)

    assert exit_code == 1
    assert source.calls == ["A", "B"]
    assert "Refresh failure: 2" in output
    assert output.count("Execution status: failed") == 2
    assert output.count("Resolution status: miss") == 2
    assert "Safe error type: RuntimeError" in output
    assert "secret-message" not in output


def test_external_text_is_redacted_and_control_characters_are_escaped() -> None:
    secret = "api-key-value"
    item = f"A\n\x1bAuthorization: Bearer {secret}"
    source = SnapshotSource(tuple(_candidates(second_platform=item)))

    exit_code, lines = _run(
        "--item",
        item,
        fake_source_factory=lambda: source,
    )
    output = "\n".join(lines)

    assert exit_code == 0
    assert secret not in output
    assert "Authorization: Bearer" not in output
    assert "\\n" in output
    assert "\\u001b" in output
    assert "\x1b" not in output


def test_unsafe_error_class_name_uses_internal_error() -> None:
    unsafe_error_type = type("Bad\nInjected\x1b", (RuntimeError,), {})
    source = SnapshotSource((), error=unsafe_error_type("secret"))

    exit_code, lines = _run(
        "--item",
        "A",
        fake_source_factory=lambda: source,
    )

    assert exit_code == 1
    assert "  Safe error type: InternalError" in lines
    assert not any("Injected" in line for line in lines)


@pytest.mark.parametrize("gate_value", [None, "", "false", "1", "yes"])
def test_live_gate_false_returns_two_without_key_or_runtime(
    gate_value: str | None,
) -> None:
    environ: dict[str, str] = {"STEAMDT_API_KEY": "must-not-be-read"}
    if gate_value is not None:
        environ[command.RUN_GATE_ENV] = gate_value
    called = False

    async def forbidden_runtime(
        _environ: Mapping[str, str],
    ) -> FakeRuntime:
        nonlocal called
        called = True
        raise AssertionError

    exit_code, lines = _run(
        *_live_args(),
        environ=environ,
        live_runtime_factory=forbidden_runtime,
    )

    assert exit_code == 2
    assert called is False
    assert lines[-2:] == ["SteamDT requests sent: 0", "Redis used: no"]
    assert "must-not-be-read" not in "\n".join(lines)


def test_live_gate_is_checked_before_api_key_lookup() -> None:
    class GateOnlyMapping(Mapping[str, str]):
        def __getitem__(self, key: str) -> str:
            if key == command.RUN_GATE_ENV:
                return "false"
            raise AssertionError(key)

        def __iter__(self):  # type: ignore[no-untyped-def]
            return iter((command.RUN_GATE_ENV,))

        def __len__(self) -> int:
            return 1

        def get(self, key: str, default: str | None = None) -> str | None:
            if key == command.RUN_GATE_ENV:
                return "false"
            raise AssertionError(key)

    exit_code, _lines = _run(*_live_args(), environ=GateOnlyMapping())

    assert exit_code == 2


@pytest.mark.parametrize("gate_value", ["true", " TRUE ", "TrUe"])
def test_live_true_gate_with_injected_runtime_runs_and_closes(
    gate_value: str,
) -> None:
    runtime = FakeRuntime(request_count=1)

    async def create_runtime(
        _environ: Mapping[str, str],
    ) -> FakeRuntime:
        return runtime

    exit_code, lines = _run(
        *_live_args(),
        environ={
            command.RUN_GATE_ENV: gate_value,
            "STEAMDT_API_KEY": "dummy-key",
        },
        live_runtime_factory=create_runtime,
    )
    output = "\n".join(lines)

    assert exit_code == 0
    assert runtime.closed == 1
    assert runtime.client.calls == ["A"]
    assert "Mode: live" in output
    assert "Synthetic data: no" in output
    assert "SteamDT requests sent: 1" in output
    assert "dummy-key" not in output


@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_live_missing_api_key_returns_two_before_runtime(
    api_key: str | None,
) -> None:
    environ = {command.RUN_GATE_ENV: "true"}
    if api_key is not None:
        environ["STEAMDT_API_KEY"] = api_key
    called = False

    async def forbidden_runtime(
        _environ: Mapping[str, str],
    ) -> FakeRuntime:
        nonlocal called
        called = True
        raise AssertionError

    exit_code, lines = _run(
        *_live_args(),
        environ=environ,
        live_runtime_factory=forbidden_runtime,
    )

    assert exit_code == 2
    assert called is False
    assert "SteamDT requests sent: 0" in lines


@pytest.mark.parametrize("invalid", [True, -1, 1.5, "1", None])
def test_invalid_live_request_count_is_unavailable_and_exit_one(
    invalid: object,
) -> None:
    runtime = FakeRuntime(request_count=invalid)

    async def create_runtime(
        _environ: Mapping[str, str],
    ) -> FakeRuntime:
        return runtime

    exit_code, lines = _run(
        *_live_args(),
        environ={
            command.RUN_GATE_ENV: "true",
            "STEAMDT_API_KEY": "dummy-key",
        },
        live_runtime_factory=create_runtime,
    )
    output = "\n".join(lines)

    assert exit_code == 1
    assert runtime.closed == 1
    assert "SteamDT requests sent: unavailable" in output
    assert "SteamDT refresh integration failed: TypeError" in output


def test_raising_request_counter_is_safe_and_unavailable() -> None:
    runtime = FakeRuntime(request_count=RuntimeError("api-key-value"))

    async def create_runtime(
        _environ: Mapping[str, str],
    ) -> FakeRuntime:
        return runtime

    exit_code, lines = _run(
        *_live_args(),
        environ={
            command.RUN_GATE_ENV: "true",
            "STEAMDT_API_KEY": "api-key-value",
        },
        live_runtime_factory=create_runtime,
    )
    output = "\n".join(lines)

    assert exit_code == 1
    assert "SteamDT requests sent: unavailable" in output
    assert "api-key-value" not in output


def test_live_runtime_factory_failure_is_safe_and_does_not_fallback() -> None:
    async def fail_runtime(
        _environ: Mapping[str, str],
    ) -> NoReturn:
        raise RuntimeError("Authorization: Bearer api-key-value")

    exit_code, lines = _run(
        *_live_args(),
        environ={
            command.RUN_GATE_ENV: "true",
            "STEAMDT_API_KEY": "api-key-value",
        },
        live_runtime_factory=fail_runtime,
    )
    output = "\n".join(lines)

    assert exit_code == 1
    assert "SteamDT refresh integration failed: RuntimeError" in output
    assert "api-key-value" not in output
    assert "Mode: fake" not in output


def test_runtime_close_failure_is_reported_safely_and_exits_one() -> None:
    runtime = FakeRuntime(
        request_count=1,
        close_error=RuntimeError("redis://user:password@localhost/15"),
    )

    async def create_runtime(
        _environ: Mapping[str, str],
    ) -> FakeRuntime:
        return runtime

    exit_code, lines = _run(
        *_live_args(),
        environ={
            command.RUN_GATE_ENV: "true",
            "STEAMDT_API_KEY": "dummy-key",
        },
        live_runtime_factory=create_runtime,
    )
    output = "\n".join(lines)

    assert exit_code == 1
    assert runtime.closed == 1
    assert "SteamDT refresh integration close failed: RuntimeError" in output
    assert "password" not in output


def test_cancellation_propagates_closes_runtime_and_prints_no_partial_summary() -> None:
    blocker = asyncio.Event()
    client = CandidateClient(blocker=blocker)
    runtime = FakeRuntime(client)
    lines: list[str] = []
    resolver_created = False

    async def create_runtime(
        _environ: Mapping[str, str],
    ) -> FakeRuntime:
        return runtime

    def forbidden_resolver(_cache):  # type: ignore[no-untyped-def]
        nonlocal resolver_created
        resolver_created = True
        raise AssertionError

    async def scenario() -> None:
        baseline_tasks = asyncio.all_tasks()
        task = asyncio.create_task(
            command.async_main(
                list(_live_args("A", "B")),
                {
                    command.RUN_GATE_ENV: "true",
                    "STEAMDT_API_KEY": "dummy-key",
                },
                printer=lines.append,
                live_runtime_factory=create_runtime,
                resolver_factory=forbidden_resolver,
            )
        )
        while not client.calls:
            await asyncio.sleep(0)
        task.cancel("stop")
        with pytest.raises(asyncio.CancelledError):
            await task
        assert asyncio.all_tasks() == baseline_tasks

    asyncio.run(scenario())

    assert runtime.closed == 1
    assert client.cancelled is True
    assert resolver_created is False
    assert lines == []


def test_printer_runs_only_after_live_runtime_close() -> None:
    runtime = FakeRuntime(request_count=1)

    async def create_runtime(
        _environ: Mapping[str, str],
    ) -> FakeRuntime:
        return runtime

    def printer(_line: str) -> None:
        assert runtime.closed == 1

    exit_code = asyncio.run(
        command.async_main(
            list(_live_args()),
            {
                command.RUN_GATE_ENV: "true",
                "STEAMDT_API_KEY": "dummy-key",
            },
            printer=printer,
            live_runtime_factory=create_runtime,
        )
    )

    assert exit_code == 0


def test_main_maps_keyboard_interrupt_to_130(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(_awaitable: object) -> NoReturn:
        if hasattr(_awaitable, "close"):
            _awaitable.close()  # type: ignore[attr-defined]
        raise KeyboardInterrupt

    monkeypatch.setattr(command.asyncio, "run", interrupt)

    with pytest.raises(SystemExit) as exc_info:
        command.main()

    assert exc_info.value.code == 130


@pytest.mark.parametrize(
    "entrypoint",
    [
        ("-m", "scripts.steamdt_refresh_integration"),
        ("scripts/steamdt_refresh_integration.py",),
    ],
)
def test_direct_and_module_fake_entrypoints_are_offline(
    entrypoint: tuple[str, ...],
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    for name in list(environment):
        if name.startswith("STEAMDT_") or "REDIS" in name:
            environment.pop(name)
    completed = subprocess.run(
        [sys.executable, *entrypoint, "--item", "A"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    output = completed.stdout + completed.stderr

    assert completed.returncode == 0
    assert "Mode: fake" in output
    assert "SteamDT requests sent: 0" in output
    assert "Redis used: no" in output
    assert "Traceback" not in output


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module.casefold())
    return imports


def test_command_has_manual_single_item_architecture_boundaries() -> None:
    project_root = Path(__file__).resolve().parents[1]
    command_path = project_root / "scripts" / "steamdt_refresh_integration.py"
    source = command_path.read_text(encoding="utf-8").casefold()
    imports = _imported_names(command_path)
    forbidden = {
        "redis",
        "price_cache_factory",
        "price_provider",
        "valuation",
        "pipeline",
        "scheduler",
        "fastapi",
        "discord",
        "buff",
    }

    assert not any(fragment in name for name in imports for fragment in forbidden)
    assert "get_price_batch" not in source
    assert "/price/batch" not in source
    assert "create_task" not in source
    assert "steamdtpricecache" not in source
    assert "redis://" not in source
    assert "postgresql" not in source


def test_pipeline_scheduler_and_main_do_not_reverse_import_command() -> None:
    project_root = Path(__file__).resolve().parents[1]
    paths = [
        project_root / "app" / "services" / "pipeline_service.py",
        project_root / "app" / "jobs" / "scheduler.py",
        project_root / "app" / "main.py",
    ]

    for path in paths:
        imports = _imported_names(path)
        assert "scripts.steamdt_refresh_integration" not in imports
        assert "steamdt_refresh_integration" not in imports
