from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from app.services.price_cache import (
    CachedPriceSnapshot,
    PriceCacheKey,
    PriceCacheLookup,
    PriceCacheReadPolicy,
    PriceCacheWriteResult,
)
from app.services.recipe_solver import RecipeEnumerationConfig
from app.services.scanner_cached_buff_price_resolver import (
    ScannerCachedBuffPriceResolver,
)
from app.services.scanner_orchestrator import (
    ScannerRunDiagnostics,
    ScannerRunResult,
    ScannerRunStageCounters,
)
from scripts.run_live_scan_once import (
    LiveScanSettings,
    LiveValuationConfigurationError,
    _build_market_universe_spec,
    _to_jsonable,
    build_parser,
    build_steamdt_http_client,
    print_human,
    run_live_scan_once,
    validate_live_valuation_config,
)


def _empty_run_result(
    *,
    counters: ScannerRunStageCounters | None = None,
) -> ScannerRunResult:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    return ScannerRunResult(
        started_at=now,
        completed_at=now,
        goods_ids=("34279",),
        counters=counters or ScannerRunStageCounters(),
        diagnostics=ScannerRunDiagnostics(),
        recipe_evaluations=(),
        opportunities=(),
    )


class ReadOnlyRecordingCache:
    def __init__(self) -> None:
        self.get_calls: list[tuple[PriceCacheKey, PriceCacheReadPolicy]] = []

    async def get(
        self,
        key: PriceCacheKey,
        *,
        read_policy: PriceCacheReadPolicy = PriceCacheReadPolicy.FRESH_ONLY,
    ) -> PriceCacheLookup:
        self.get_calls.append((key, read_policy))
        return PriceCacheLookup.missing(key)

    async def put(self, snapshot: CachedPriceSnapshot) -> PriceCacheWriteResult:
        raise AssertionError("scanner CLI must not write cache snapshots")

    async def delete(self, key: PriceCacheKey) -> bool:
        raise AssertionError("scanner CLI must not delete cache entries")

    async def clear(self) -> None:
        raise AssertionError("scanner CLI must not clear the cache")

    async def purge_expired(self) -> int:
        raise AssertionError("scanner CLI must not purge the cache")



def _settings(
    *,
    dry_run: bool,
    api_key: str,
    cache_backend: str = "inmemory",
    redis_url: str = "",
    cache_namespace: str = "steamdt-price-cache-v1",
) -> LiveScanSettings:
    return LiveScanSettings(
        _env_file=None,
        steamdt_dry_run=dry_run,
        steamdt_api_key=api_key,
        steamdt_price_cache_backend=cache_backend,
        steamdt_price_cache_redis_namespace=cache_namespace,
        redis_url=redis_url,
    )


def _capture_orchestrator_kwargs(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    *,
    settings: LiveScanSettings | None = None,
) -> dict[str, Any]:
    from scripts import run_live_scan_once

    class FakeHttpClient:
        async def aclose(self) -> None:
            return None

    class FakeCacheRuntime:
        def __init__(self) -> None:
            self.cache = Mock(name="price_cache")
            self.close_calls = 0

        async def __aenter__(self) -> FakeCacheRuntime:
            return self

        async def __aexit__(
            self,
            exc_type: object,
            exc: BaseException | None,
            traceback: object,
        ) -> None:
            self.close_calls += 1

    captured: dict[str, Any] = {}
    runtime = FakeCacheRuntime()

    async def create_cache_runtime(_settings: LiveScanSettings) -> FakeCacheRuntime:
        captured["cache_settings"] = _settings
        captured["cache_runtime"] = runtime
        return runtime

    monkeypatch.setattr(
        run_live_scan_once,
        "create_steamdt_price_cache_runtime",
        create_cache_runtime,
    )

    class CapturingOrchestrator:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        async def run_once(self, goods_ids: list[str]) -> object:
            captured["run_once_calls"] = captured.get("run_once_calls", 0) + 1
            captured["goods_ids"] = tuple(goods_ids)
            return object()

    settings = settings or _settings(dry_run=False, api_key="present")
    monkeypatch.setattr(run_live_scan_once, "LiveScanSettings", lambda: settings)
    identity_resolver = Mock(name="identity_resolver")
    metadata_resolver = Mock(name="metadata_resolver")
    monkeypatch.setattr(
        run_live_scan_once.BuffCommunityIdentityResolver,
        "from_snapshot_path",
        lambda _path: identity_resolver,
    )
    monkeypatch.setattr(
        run_live_scan_once.PinnedSkinMetadataResolver,
        "from_snapshot_path",
        lambda _path: metadata_resolver,
    )
    monkeypatch.setattr(
        run_live_scan_once.httpx,
        "AsyncClient",
        lambda *args, **kwargs: FakeHttpClient(),
    )
    monkeypatch.setattr(
        run_live_scan_once,
        "build_steamdt_http_client",
        lambda _settings: FakeHttpClient(),
    )
    monkeypatch.setattr(
        run_live_scan_once,
        "BuffAnonymousListingHttpClient",
        lambda _http: object(),
    )
    monkeypatch.setattr(
        run_live_scan_once,
        "BuffListingProvider",
        lambda _client: object(),
    )
    monkeypatch.setattr(
        run_live_scan_once,
        "SteamDTHttpClient",
        lambda _config, _http: object(),
    )
    monkeypatch.setattr(
        run_live_scan_once,
        "SteamDTBuffPriceProvider",
        lambda _client: object(),
    )
    monkeypatch.setattr(
        run_live_scan_once,
        "ValuationService",
        lambda _provider, _config: object(),
    )
    monkeypatch.setattr(
        run_live_scan_once,
        "LiveScannerOrchestrator",
        CapturingOrchestrator,
    )
    monkeypatch.setattr(
        run_live_scan_once,
        "print_effective_config",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        run_live_scan_once,
        "print_human",
        lambda _result: None,
    )

    assert run_live_scan_once.main(argv) == 0
    assert runtime.close_calls == 1
    captured["runtime_cache"] = runtime.cache
    return captured


def test_live_gate_refuses_dry_run_true() -> None:
    with pytest.raises(
        LiveValuationConfigurationError,
        match="STEAMDT_DRY_RUN must be false",
    ):
        validate_live_valuation_config(
            _settings(dry_run=True, api_key="present"),
            max_valuation_requests=5,
        )


def test_live_gate_refuses_missing_api_key() -> None:
    with pytest.raises(
        LiveValuationConfigurationError,
        match="STEAMDT_API_KEY is required",
    ):
        validate_live_valuation_config(
            _settings(dry_run=False, api_key=""),
            max_valuation_requests=5,
        )


def test_live_gate_accepts_explicit_live_configuration() -> None:
    validate_live_valuation_config(
        _settings(dry_run=False, api_key="present"),
        max_valuation_requests=5,
    )


@pytest.mark.parametrize("cap", [0, -1, 61, True])
def test_live_gate_rejects_invalid_valuation_cap(cap: object) -> None:
    with pytest.raises(
        LiveValuationConfigurationError,
        match="max valuation requests",
    ):
        validate_live_valuation_config(
            _settings(dry_run=False, api_key="present"),
            max_valuation_requests=cap,  # type: ignore[arg-type]
        )


def test_steamdt_borrowed_http_client_has_configured_base_url() -> None:
    import asyncio

    settings = _settings(dry_run=False, api_key="present")
    client = build_steamdt_http_client(settings)
    try:
        assert str(client.base_url) == "https://open.steamdt.com"
    finally:
        asyncio.run(client.aclose())


def test_default_cache_runtime_injects_strict_scanner_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_orchestrator_kwargs(
        monkeypatch,
        ["--goods-id", "34279"],
    )
    settings = captured["cache_settings"]
    assert settings.steamdt_price_cache_backend == "inmemory"
    resolver = captured["cached_price_resolver"]
    assert type(resolver) is ScannerCachedBuffPriceResolver
    assert resolver._resolver._cache is captured["runtime_cache"]
    assert captured["run_once_calls"] == 1


def test_redis_settings_reach_existing_cache_factory_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(
        dry_run=False,
        api_key="present",
        cache_backend="redis",
        redis_url="redis://user:secret@cache.test:6379/4",
        cache_namespace="scanner-cache-v1",
    )

    captured = _capture_orchestrator_kwargs(
        monkeypatch,
        ["--goods-id", "34279"],
        settings=settings,
    )

    assert captured["cache_settings"] is settings
    assert settings.steamdt_price_cache_backend == "redis"
    assert settings.steamdt_price_cache_redis_namespace == "scanner-cache-v1"
    assert type(captured["cached_price_resolver"]) is ScannerCachedBuffPriceResolver


def test_scanner_cache_wrapper_reads_fresh_only_without_write_methods() -> None:
    cache = ReadOnlyRecordingCache()
    resolver = ScannerCachedBuffPriceResolver(cache)

    resolution = asyncio.run(resolver.resolve("Exact Name"))

    assert resolution.lookup.hit is False
    assert cache.get_calls == [
        (PriceCacheKey(market_hash_name="Exact Name"), PriceCacheReadPolicy.FRESH_ONLY)
    ]


def test_human_output_includes_phase14_counter_groups(
    capsys: pytest.CaptureFixture[str],
) -> None:
    counters = ScannerRunStageCounters(
        valuation_requests_attempted=1,
        valuation_requests_succeeded=2,
        valuation_requests_failed=3,
        valuation_requests_blocked=4,
        run_reuse_hits=5,
        run_reuse_successes=6,
        run_reuse_failures=7,
        cache_hits_fresh_selected=8,
        cache_misses=9,
        cache_policy_blocked=10,
        cache_expired=11,
        cache_selection_failures=12,
        live_demand=13,
        live_attempted=14,
        live_succeeded=15,
        live_failed=16,
        live_atomically_blocked=17,
    )

    print_human(_empty_run_result(counters=counters))

    output = capsys.readouterr().out
    expected_lines = (
        "logical valuation requests attempted: 1",
        "logical valuation requests succeeded: 2",
        "logical valuation requests failed:    3",
        "logical valuation requests blocked:   4",
        "run reuse hits:              5",
        "run reuse successes:         6",
        "run reuse failures:          7",
        "cache fresh hits:            8",
        "cache misses:                9",
        "cache policy blocked:        10",
        "cache expired:               11",
        "cache selection failures:    12",
        "live demand:                 13",
        "live attempted:              14",
        "live succeeded:              15",
        "live failed:                 16",
        "live atomically blocked:     17",
    )
    for line in expected_lines:
        assert line in output


def test_json_shape_preserves_phase14_counters() -> None:
    payload = _to_jsonable(
        _empty_run_result(
            counters=ScannerRunStageCounters(
                cache_hits_fresh_selected=2,
                live_demand=3,
            )
        )
    )

    assert set(payload) == {
        "started_at",
        "completed_at",
        "goods_ids",
        "counters",
        "diagnostics",
        "recipe_evaluations",
        "opportunities",
    }
    assert payload["counters"]["cache_hits_fresh_selected"] == 2
    assert payload["counters"]["live_demand"] == 3
    assert "steamdt_price_cache_backend" not in payload


@pytest.mark.parametrize(
    ("backend", "redis_url", "namespace"),
    [
        ("filesystem", "", "steamdt-price-cache-v1"),
        ("redis", "", "steamdt-price-cache-v1"),
        ("redis", "not-a-url", "steamdt-price-cache-v1"),
        ("redis", "redis://cache.test:6379/0", "bad namespace"),
    ],
)
def test_invalid_cache_config_fails_before_live_client_work(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    backend: str,
    redis_url: str,
    namespace: str,
) -> None:
    from scripts import run_live_scan_once as script

    secret = "super-secret-password"
    settings = _settings(
        dry_run=False,
        api_key="present",
        cache_backend=backend,
        redis_url=(
            f"redis://user:{secret}@cache.test:6379/0"
            if redis_url.startswith("redis://")
            else redis_url
        ),
        cache_namespace=namespace,
    )
    monkeypatch.setattr(script, "LiveScanSettings", lambda: settings)
    constructed: list[str] = []

    def fail_live_constructor(*args: object, **kwargs: object) -> None:
        constructed.append("live")
        raise AssertionError("live dependencies must not be constructed")

    monkeypatch.setattr(script.httpx, "AsyncClient", fail_live_constructor)
    monkeypatch.setattr(script, "build_steamdt_http_client", fail_live_constructor)
    monkeypatch.setattr(script, "LiveScannerOrchestrator", fail_live_constructor)

    assert script.main(["--goods-id", "34279"]) == 2
    output = capsys.readouterr().out
    assert "LIVE_PRICE_CACHE_BLOCKED_BY_CONFIGURATION" in output
    assert secret not in output
    assert constructed == []


@pytest.mark.parametrize(
    "error",
    [RuntimeError("scan failed"), MemoryError("oom"), asyncio.CancelledError()],
)
def test_cache_runtime_closes_when_scan_raises(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    from scripts import run_live_scan_once as script

    class Runtime:
        def __init__(self) -> None:
            self.cache = ReadOnlyRecordingCache()
            self.close_calls = 0

        async def __aenter__(self) -> Runtime:
            return self

        async def __aexit__(
            self,
            exc_type: object,
            exc: BaseException | None,
            traceback: object,
        ) -> None:
            self.close_calls += 1

    runtime = Runtime()

    async def create_runtime(_settings: LiveScanSettings) -> Runtime:
        return runtime

    async def fail_scan(*args: object, **kwargs: object) -> ScannerRunResult:
        raise error

    settings = _settings(dry_run=False, api_key="present")
    monkeypatch.setattr(script, "LiveScanSettings", lambda: settings)
    monkeypatch.setattr(script, "create_steamdt_price_cache_runtime", create_runtime)
    monkeypatch.setattr(script, "run_live_scan_once", fail_scan)

    with pytest.raises(type(error)) as info:
        asyncio.run(script.main(["--goods-id", "34279", "--json"]))

    assert info.value is error
    assert runtime.close_calls == 1


def test_http_clients_close_when_orchestrator_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import run_live_scan_once as script

    events: list[str] = []

    class HttpClient:
        def __init__(self, name: str) -> None:
            self.name = name

        async def aclose(self) -> None:
            events.append(f"close:{self.name}")

    failure = MemoryError("sentinel")

    class FailingOrchestrator:
        def __init__(self, **kwargs: object) -> None:
            return None

        async def run_once(self, goods_ids: list[str]) -> ScannerRunResult:
            raise failure

    monkeypatch.setattr(
        script.BuffCommunityIdentityResolver,
        "from_snapshot_path",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        script.PinnedSkinMetadataResolver,
        "from_snapshot_path",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        script.httpx,
        "AsyncClient",
        lambda *args, **kwargs: HttpClient("buff"),
    )
    monkeypatch.setattr(
        script,
        "build_steamdt_http_client",
        lambda _settings: HttpClient("steamdt"),
    )
    monkeypatch.setattr(script, "BuffAnonymousListingHttpClient", lambda _http: object())
    monkeypatch.setattr(script, "BuffListingProvider", lambda _client: object())
    monkeypatch.setattr(script, "SteamDTHttpClient", lambda _config, _http: object())
    monkeypatch.setattr(script, "SteamDTBuffPriceProvider", lambda _client: object())
    monkeypatch.setattr(script, "ValuationService", lambda _provider, _config: object())
    monkeypatch.setattr(script, "LiveScannerOrchestrator", FailingOrchestrator)

    args = build_parser().parse_args(["--goods-id", "34279"])
    with pytest.raises(MemoryError) as info:
        asyncio.run(
            run_live_scan_once(
                args,
                settings=_settings(dry_run=False, api_key="present"),
                price_cache=ReadOnlyRecordingCache(),
                enumeration_config=RecipeEnumerationConfig(),
            )
        )

    assert info.value is failure
    assert events == ["close:steamdt", "close:buff"]


def test_partial_http_construction_closes_buff_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import run_live_scan_once as script

    events: list[str] = []

    class BuffHttpClient:
        async def aclose(self) -> None:
            events.append("close:buff")

    failure = RuntimeError("steamdt construction failed")
    monkeypatch.setattr(
        script.BuffCommunityIdentityResolver,
        "from_snapshot_path",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        script.PinnedSkinMetadataResolver,
        "from_snapshot_path",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        script.httpx,
        "AsyncClient",
        lambda *args, **kwargs: BuffHttpClient(),
    )

    def fail_steamdt_http(_settings: LiveScanSettings) -> None:
        raise failure

    monkeypatch.setattr(script, "build_steamdt_http_client", fail_steamdt_http)
    args = build_parser().parse_args(["--goods-id", "34279"])

    with pytest.raises(RuntimeError) as info:
        asyncio.run(
            run_live_scan_once(
                args,
                settings=_settings(dry_run=False, api_key="present"),
                price_cache=ReadOnlyRecordingCache(),
                enumeration_config=RecipeEnumerationConfig(),
            )
        )

    assert info.value is failure
    assert events == ["close:buff"]


def test_parser_defaults_to_conservative_valuation_cap() -> None:
    args = build_parser().parse_args(["--goods-id", "34279"])
    assert args.max_valuation_requests == 5


def test_parser_defaults_recipe_enumeration_bounds() -> None:
    args = build_parser().parse_args(["--goods-id", "34279"])
    assert args.max_recipe_candidates_returned == 2
    assert args.max_candidate_states_explored == 256


def test_default_recipe_enumeration_config_reaches_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_orchestrator_kwargs(
        monkeypatch,
        ["--goods-id", "34279"],
    )
    config = captured["enumeration_config"]
    assert isinstance(config, RecipeEnumerationConfig)
    assert config.max_recipe_candidates_returned == 2
    assert config.max_candidate_states_explored == 256


@pytest.mark.parametrize(
    ("candidates", "states"),
    [(4, 512), (1, 1), (6, 1024), (4, 4)],
)
def test_explicit_recipe_enumeration_config_reaches_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
    candidates: int,
    states: int,
) -> None:
    captured = _capture_orchestrator_kwargs(
        monkeypatch,
        [
            "--goods-id",
            "34279",
            "--max-recipe-candidates-returned",
            str(candidates),
            "--max-candidate-states-explored",
            str(states),
        ],
    )
    config = captured["enumeration_config"]
    assert isinstance(config, RecipeEnumerationConfig)
    assert config.max_recipe_candidates_returned == candidates
    assert config.max_candidate_states_explored == states


@pytest.mark.parametrize(
    ("flag", "value", "message"),
    [
        (
            "--max-recipe-candidates-returned",
            "0",
            "max_recipe_candidates_returned must be an integer in [1, 6]",
        ),
        (
            "--max-recipe-candidates-returned",
            "7",
            "max_recipe_candidates_returned must be an integer in [1, 6]",
        ),
        (
            "--max-candidate-states-explored",
            "0",
            "max_candidate_states_explored must be an integer in [1, 1024]",
        ),
        (
            "--max-candidate-states-explored",
            "1025",
            "max_candidate_states_explored must be an integer in [1, 1024]",
        ),
    ],
)
def test_invalid_recipe_enumeration_domain_config_fails_before_settings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    flag: str,
    value: str,
    message: str,
) -> None:
    from scripts import run_live_scan_once

    def fail_settings(*args: object, **kwargs: object) -> None:
        raise AssertionError("LiveScanSettings must not be constructed")

    monkeypatch.setattr(run_live_scan_once, "LiveScanSettings", fail_settings)
    assert run_live_scan_once.main(["--goods-id", "34279", flag, value]) == 2
    output = capsys.readouterr().out
    assert "RECIPE_ENUMERATION_BLOCKED_BY_CONFIGURATION" in output
    assert message in output


def test_recipe_state_budget_below_candidate_budget_fails_before_settings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import run_live_scan_once

    def fail_settings(*args: object, **kwargs: object) -> None:
        raise AssertionError("LiveScanSettings must not be constructed")

    monkeypatch.setattr(run_live_scan_once, "LiveScanSettings", fail_settings)
    assert (
        run_live_scan_once.main(
            [
                "--goods-id",
                "34279",
                "--max-recipe-candidates-returned",
                "4",
                "--max-candidate-states-explored",
                "3",
            ]
        )
        == 2
    )
    output = capsys.readouterr().out
    assert "RECIPE_ENUMERATION_BLOCKED_BY_CONFIGURATION" in output
    assert (
        "max_candidate_states_explored must be greater than or equal to "
        "max_recipe_candidates_returned"
    ) in output


@pytest.mark.parametrize(
    "flag",
    [
        "--max-recipe-candidates-returned",
        "--max-candidate-states-explored",
    ],
)
def test_recipe_enumeration_non_integer_fails_parser(
    flag: str,
) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--goods-id", "34279", flag, "not-an-int"])


def test_recipe_enumeration_flags_leave_other_config_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _capture_orchestrator_kwargs(
        monkeypatch,
        ["--goods-id", "34279"],
    )
    explicit = _capture_orchestrator_kwargs(
        monkeypatch,
        [
            "--goods-id",
            "34279",
            "--max-recipe-candidates-returned",
            "4",
            "--max-candidate-states-explored",
            "512",
        ],
    )
    assert explicit["solver_config"] == baseline["solver_config"]
    assert explicit["risk_config"] == baseline["risk_config"]
    assert (
        explicit["max_valuation_requests_per_run"]
        == baseline["max_valuation_requests_per_run"]
        == 5
    )
    assert explicit["goods_ids"] == baseline["goods_ids"] == ("34279",)


def test_parser_preserves_repeatable_goods_ids() -> None:
    args = build_parser().parse_args(
        ["--goods-id", "34279", "--goods-id", "34420"]
    )
    assert args.goods_id == ["34279", "34420"]


def test_parser_requires_one_source() -> None:
    import pytest

    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_parser_rejects_mixed_sources() -> None:
    import pytest

    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "--goods-id",
                "34279",
                "--auto-universe",
            ]
        )


def test_parser_auto_universe_defaults() -> None:
    args = build_parser().parse_args(["--auto-universe"])
    assert args.auto_universe is True
    assert args.rarity == "Restricted"
    assert args.stattrak_mode == "normal"
    assert args.souvenir == "include"
    assert args.max_goods_ids == 10
    assert args.allocation is None
    assert args.target_cohorts is None


def test_auto_universe_effective_defaults_preserve_breadth() -> None:
    from app.services.market_universe_builder import UniverseAllocationStrategy

    args = build_parser().parse_args(["--auto-universe"])
    spec = _build_market_universe_spec(args)
    assert spec.allocation_strategy is UniverseAllocationStrategy.BREADTH
    assert spec.target_cohort_count == 3


def test_parser_maps_explicit_cohort_depth_configuration() -> None:
    from app.services.market_universe_builder import UniverseAllocationStrategy

    args = build_parser().parse_args(
        [
            "--auto-universe",
            "--allocation",
            "cohort-depth",
            "--target-cohorts",
            "2",
        ]
    )
    spec = _build_market_universe_spec(args)
    assert spec.allocation_strategy is UniverseAllocationStrategy.COHORT_DEPTH
    assert spec.target_cohort_count == 2


def test_explicit_target_with_breadth_fails_closed() -> None:
    from app.services.market_universe_builder import (
        BoundedMarketUniverseBuilderError,
    )

    args = build_parser().parse_args(
        [
            "--auto-universe",
            "--allocation",
            "breadth",
            "--target-cohorts",
            "3",
        ]
    )
    with pytest.raises(BoundedMarketUniverseBuilderError) as info:
        _build_market_universe_spec(args)
    assert info.value.reason == "invalid_target_cohort_count"


def test_manual_mode_rejects_explicit_auto_allocation_before_settings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import run_live_scan_once

    def fail_settings(*args: object, **kwargs: object) -> None:
        raise AssertionError("LiveScanSettings must not be constructed")

    monkeypatch.setattr(run_live_scan_once, "LiveScanSettings", fail_settings)
    exit_code = run_live_scan_once.main(
        ["--goods-id", "34279", "--allocation", "breadth"]
    )
    assert exit_code == 2
    assert "AUTO_UNIVERSE_OPTION_REQUIRES_AUTO_UNIVERSE" in capsys.readouterr().out


def test_manual_mode_rejects_explicit_target_before_settings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import run_live_scan_once

    def fail_settings(*args: object, **kwargs: object) -> None:
        raise AssertionError("LiveScanSettings must not be constructed")

    monkeypatch.setattr(run_live_scan_once, "LiveScanSettings", fail_settings)
    exit_code = run_live_scan_once.main(
        ["--goods-id", "34279", "--target-cohorts", "3"]
    )
    assert exit_code == 2
    assert "AUTO_UNIVERSE_OPTION_REQUIRES_AUTO_UNIVERSE" in capsys.readouterr().out


def test_parser_rejects_unsupported_rarity() -> None:
    import pytest

    with pytest.raises(SystemExit):
        build_parser().parse_args(["--auto-universe", "--rarity", "Covert"])


def test_parser_accepts_max_goods_ids_then_validates() -> None:
    """Argparse accepts the integer; the builder rejects values outside [1, 10]."""
    from app.services.market_universe_builder import (
        BoundedMarketUniverseBuilderError,
        MarketUniverseSpec,
        SouvenirInclusion,
        StatTrakMode,
    )

    args = build_parser().parse_args(["--auto-universe", "--max-goods-ids", "0"])
    with pytest.raises(BoundedMarketUniverseBuilderError):
        MarketUniverseSpec(
            rarity=args.rarity,
            stattrak_mode=StatTrakMode.NORMAL,
            souvenir_inclusion=SouvenirInclusion.INCLUDE,
            cap=args.max_goods_ids,
        )
    args = build_parser().parse_args(["--auto-universe", "--max-goods-ids", "11"])
    with pytest.raises(BoundedMarketUniverseBuilderError):
        MarketUniverseSpec(
            rarity=args.rarity,
            stattrak_mode=StatTrakMode.NORMAL,
            souvenir_inclusion=SouvenirInclusion.INCLUDE,
            cap=args.max_goods_ids,
        )


def test_parser_accepts_repeatable_collection() -> None:
    args = build_parser().parse_args(
        [
            "--auto-universe",
            "--collection",
            "The Cobblestone Collection",
            "--collection",
            "The Ancient Collection",
        ]
    )
    assert args.collection == [
        "The Cobblestone Collection",
        "The Ancient Collection",
    ]


def test_successful_depth_preview_is_structured_and_no_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json

    from scripts import run_live_scan_once

    metadata_items: list[dict[str, object]] = []
    identities: dict[str, str] = {}
    for collection_index, collection_name in enumerate(
        ("Collection A", "Collection B", "Collection C")
    ):
        for input_index in range(4):
            name = f"{collection_name} Input {input_index}"
            metadata_items.append(
                {
                    "market_hash_name": name,
                    "collection_name": collection_name,
                    "rarity": "Restricted",
                    "min_float": 0.0,
                    "max_float": 1.0,
                    "stattrak": False,
                    "souvenir": False,
                }
            )
            identities[name] = str(collection_index * 10 + input_index + 1)
        metadata_items.append(
            {
                "market_hash_name": f"{collection_name} Output",
                "collection_name": collection_name,
                "rarity": "Classified",
                "min_float": 0.0,
                "max_float": 1.0,
                "stattrak": False,
                "souvenir": False,
            }
        )
    identity_payload = {
        "schema_version": 1,
        "catalog_kind": "community_catalog",
        "source": {
            "repository": "example/repo",
            "file": "x.json",
            "commit": "abc",
            "sha256": "deadbeef" * 8,
            "license": "CC-BY-4.0",
            "attribution": "test",
        },
        "counts": {
            "source": len(identities),
            "accepted": len(identities),
            "rejected": 0,
        },
        "items": identities,
    }
    identity_path = tmp_path / "identity.json"
    metadata_path = tmp_path / "metadata.json"
    identity_path.write_text(json.dumps(identity_payload), encoding="utf-8")
    metadata_path.write_text(
        json.dumps({"items": metadata_items}), encoding="utf-8"
    )

    failures: list[str] = []

    def fail_constructor(*args: object, **kwargs: object) -> None:
        failures.append("live-constructor")

    async def fail_cache_factory(*args: object, **kwargs: object) -> None:
        failures.append("cache-factory")

    monkeypatch.setattr(run_live_scan_once, "LiveScanSettings", fail_constructor)
    monkeypatch.setattr(
        run_live_scan_once,
        "create_steamdt_price_cache_runtime",
        fail_cache_factory,
    )
    monkeypatch.setattr("httpx.AsyncClient", fail_constructor)
    monkeypatch.setattr(
        run_live_scan_once, "BuffAnonymousListingHttpClient", fail_constructor
    )
    monkeypatch.setattr(run_live_scan_once, "SteamDTHttpClient", fail_constructor)
    monkeypatch.setattr(run_live_scan_once, "ValuationService", fail_constructor)
    monkeypatch.setattr(run_live_scan_once, "LiveScannerOrchestrator", fail_constructor)

    exit_code = run_live_scan_once.main(
        [
            "--auto-universe",
            "--allocation",
            "cohort-depth",
            "--target-cohorts",
            "3",
            "--max-goods-ids",
            "10",
            "--universe-preview",
            "--identity-snapshot",
            str(identity_path),
            "--metadata-snapshot",
            str(metadata_path),
            "--json",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["spec"]["allocation_strategy"] == "cohort-depth"
    assert payload["spec"]["target_cohort_count"] == 3
    diagnostics = payload["catalog_diagnostics"]
    assert diagnostics["selected_cohort_count"] == 3
    assert [
        cohort["allocated_slots"] for cohort in diagnostics["selected_cohorts"]
    ] == [4, 3, 3]
    assert payload["http_clients_constructed"] is False
    assert payload["http_requests_sent"] == 0
    assert failures == []


def test_universe_preview_does_not_construct_clients(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--universe-preview` runs before settings/client construction."""
    import json

    from scripts import run_live_scan_once

    identity_payload = {
        "schema_version": 1,
        "catalog_kind": "community_catalog",
        "source": {
            "repository": "example/repo",
            "file": "x.json",
            "commit": "abc",
            "sha256": "deadbeef" * 8,
            "license": "CC-BY-4.0",
            "attribution": "test",
        },
        "counts": {"source": 0, "accepted": 0, "rejected": 0},
        "items": {},
    }
    metadata_payload = {"items": []}
    identity_path = tmp_path / "identity.json"
    metadata_path = tmp_path / "metadata.json"
    identity_path.write_bytes(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )
    metadata_path.write_bytes(
        json.dumps(metadata_payload, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )

    failures: list[str] = []

    def fail_httpx_client(*args: object, **kwargs: object) -> None:
        failures.append("httpx.AsyncClient")

    def fail_steamdt(*args: object, **kwargs: object) -> None:
        failures.append("SteamDTHttpClient")

    def fail_buff(*args: object, **kwargs: object) -> None:
        failures.append("BuffAnonymousListingHttpClient")

    def fail_provider(*args: object, **kwargs: object) -> None:
        failures.append("BuffListingProvider")

    def fail_valuation(*args: object, **kwargs: object) -> None:
        failures.append("ValuationService")

    def fail_orchestrator(*args: object, **kwargs: object) -> None:
        failures.append("LiveScannerOrchestrator")

    async def fail_cache_factory(*args: object, **kwargs: object) -> None:
        failures.append("create_steamdt_price_cache_runtime")

    monkeypatch.setattr("httpx.AsyncClient", fail_httpx_client)
    monkeypatch.setattr(
        "scripts.run_live_scan_once.build_steamdt_http_client", fail_steamdt
    )
    monkeypatch.setattr(
        "scripts.run_live_scan_once.BuffAnonymousListingHttpClient", fail_buff
    )
    monkeypatch.setattr(
        "scripts.run_live_scan_once.BuffListingProvider", fail_provider
    )
    monkeypatch.setattr(
        "scripts.run_live_scan_once.ValuationService", fail_valuation
    )
    monkeypatch.setattr(
        "scripts.run_live_scan_once.LiveScannerOrchestrator", fail_orchestrator
    )
    monkeypatch.setattr(
        "scripts.run_live_scan_once.create_steamdt_price_cache_runtime",
        fail_cache_factory,
    )

    # Empty catalogs produce empty universe -> builder fails closed.
    # The preview path surfaces that before any settings/client work.
    exit_code = run_live_scan_once.main(
        [
            "--auto-universe",
            "--rarity",
            "Restricted",
            "--max-goods-ids",
            "5",
            "--universe-preview",
            "--identity-snapshot",
            str(identity_path),
            "--metadata-snapshot",
            str(metadata_path),
        ]
    )
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "MARKET_UNIVERSE_BUILDER_BLOCKED" in captured.out
    assert failures == []
