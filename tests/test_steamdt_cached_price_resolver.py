import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.clients.steamdt_client import SteamDTPlatformPrice, SteamDTPriceQuote
from app.clients.steamdt_price_selection import (
    SteamDTPriceSelectionConfig,
    SteamDTPriceSelectionResult,
    SteamDTPriceSelectionStrategy,
    select_steamdt_price_quote,
)
from app.services.price_cache import (
    CachedPriceSnapshot,
    InMemoryPriceCache,
    NormalizedPriceCandidate,
    PriceCacheKey,
    PriceCacheLookup,
    PriceCachePolicy,
    PriceCacheReadPolicy,
    PriceCacheState,
    PriceCacheWriteResult,
)
from app.services.price_cache_codec import PriceCacheCodecError
from app.services.redis_price_cache import PriceCacheBackendError
from app.services.steamdt_cached_price_resolver import (
    SteamDTCachedPriceResolutionStatus,
    SteamDTCachedPriceResolver,
    SteamDTCachedPriceResolverError,
)
from app.services.steamdt_price_cache_adapter import (
    SteamDTPriceCacheAdapterError,
    SteamDTPriceCacheAdapterErrorReason,
)

BASE_TIME = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
MARKET_HASH_NAME = "AK-47 | Redline"


class ManualClock:
    def __init__(self, now: datetime = BASE_TIME) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def set(self, now: datetime) -> None:
        self.now = now


class RecordingPriceCache:
    def __init__(
        self,
        *,
        lookup: PriceCacheLookup | None = None,
        error: Exception | None = None,
    ) -> None:
        self.lookup = lookup
        self.error = error
        self.get_calls: list[tuple[PriceCacheKey, PriceCacheReadPolicy]] = []
        self.write_calls = 0

    async def get(
        self,
        key: PriceCacheKey,
        *,
        read_policy: PriceCacheReadPolicy = PriceCacheReadPolicy.FRESH_ONLY,
    ) -> PriceCacheLookup:
        self.get_calls.append((key, read_policy))
        if self.error is not None:
            raise self.error
        if self.lookup is None:
            return PriceCacheLookup.missing(key)
        return self.lookup

    async def put(self, snapshot: CachedPriceSnapshot) -> PriceCacheWriteResult:
        self.write_calls += 1
        raise AssertionError("resolver must not write the price cache")

    async def delete(self, key: PriceCacheKey) -> bool:
        self.write_calls += 1
        raise AssertionError("resolver must not delete price-cache records")

    async def clear(self) -> None:
        self.write_calls += 1
        raise AssertionError("resolver must not clear the price cache")

    async def purge_expired(self) -> int:
        self.write_calls += 1
        raise AssertionError("resolver must not purge the price cache")


class FixedSelector:
    def __init__(self, result: object) -> None:
        self.result = result

    def __call__(
        self,
        market_hash_name: str,
        platform_prices: list[SteamDTPlatformPrice],
        *,
        config: SteamDTPriceSelectionConfig | None = None,
        avg_price_cny: Decimal | None = None,
        original_payload: dict[str, Any] | None = None,
    ) -> Any:
        return self.result


class RecordingSelector:
    def __init__(self) -> None:
        self.calls: list[
            tuple[
                str,
                list[SteamDTPlatformPrice],
                SteamDTPriceSelectionConfig | None,
                Decimal | None,
                dict[str, Any] | None,
            ]
        ] = []

    def __call__(
        self,
        market_hash_name: str,
        platform_prices: list[SteamDTPlatformPrice],
        *,
        config: SteamDTPriceSelectionConfig | None = None,
        avg_price_cny: Decimal | None = None,
        original_payload: dict[str, Any] | None = None,
    ) -> SteamDTPriceSelectionResult:
        self.calls.append(
            (
                market_hash_name,
                platform_prices,
                config,
                avg_price_cny,
                original_payload,
            )
        )
        return select_steamdt_price_quote(
            market_hash_name,
            platform_prices,
            config=config,
            avg_price_cny=avg_price_cny,
            original_payload=original_payload,
        )


def _run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def _key() -> PriceCacheKey:
    return PriceCacheKey(market_hash_name=MARKET_HASH_NAME)


def _candidate(
    platform: str,
    sell_price: str,
    *,
    sell_count: int | None = 10,
    bidding_count: int | None = 5,
) -> NormalizedPriceCandidate:
    return NormalizedPriceCandidate(
        platform=platform,
        platform_item_id=f"{platform}-item",
        sell_price_cny=Decimal(sell_price),
        sell_count=sell_count,
        bidding_price_cny=Decimal(sell_price) - Decimal("0.50"),
        bidding_count=bidding_count,
        source_update_time="opaque-source-time",
    )


def _policy() -> PriceCachePolicy:
    return PriceCachePolicy(
        fresh_ttl=timedelta(minutes=1),
        stale_ttl=timedelta(minutes=1),
        stale_grace_ttl=timedelta(minutes=1),
    )


def _snapshot(
    *,
    candidates: tuple[NormalizedPriceCandidate, ...] | None = None,
) -> CachedPriceSnapshot:
    return CachedPriceSnapshot(
        key=_key(),
        candidates=(
            candidates
            if candidates is not None
            else (
                _candidate("buff", "10.00"),
                _candidate("steam", "11.00"),
            )
        ),
        observed_at=BASE_TIME,
        stored_at=BASE_TIME,
        policy=_policy(),
    )


def _cache_with_snapshot(
    clock: ManualClock,
    *,
    candidates: tuple[NormalizedPriceCandidate, ...] | None = None,
) -> InMemoryPriceCache:
    cache = InMemoryPriceCache(clock=clock)
    result = _run(cache.put(_snapshot(candidates=candidates)))
    assert result == PriceCacheWriteResult.CREATED
    return cache


def test_resolution_rejects_unknown_status_values() -> None:
    from app.services.steamdt_cached_price_resolver import (
        SteamDTCachedPriceResolution,
    )

    with pytest.raises(TypeError, match="status"):
        SteamDTCachedPriceResolution(
            status="unexpected",  # type: ignore[arg-type]
            lookup=PriceCacheLookup.missing(_key()),
        )


def test_resolution_status_must_agree_with_retained_lookup() -> None:
    from app.services.steamdt_cached_price_resolver import (
        SteamDTCachedPriceResolution,
    )

    with pytest.raises(ValueError, match="expired cache lookup"):
        SteamDTCachedPriceResolution(
            status=SteamDTCachedPriceResolutionStatus.EXPIRED,
            lookup=PriceCacheLookup.missing(_key()),
        )


def test_fresh_hit_selects_existing_quote_and_preserves_lookup() -> None:
    clock = ManualClock(BASE_TIME + timedelta(seconds=30))
    cache = _cache_with_snapshot(clock)
    resolver = SteamDTCachedPriceResolver(cache)

    result = _run(resolver.resolve(MARKET_HASH_NAME))

    assert result.status == SteamDTCachedPriceResolutionStatus.SELECTED
    assert result.lookup.hit is True
    assert result.lookup.state == PriceCacheState.FRESH
    assert result.lookup.age == timedelta(seconds=30)
    assert result.lookup.needs_refresh is False
    assert result.quote is not None
    assert result.quote.price_cny == Decimal("10.00")
    assert result.selection_result is not None
    assert result.selection_result.selected_platform == "buff"


def test_allowed_stale_hit_selects_and_keeps_refresh_advice() -> None:
    clock = ManualClock(BASE_TIME + timedelta(minutes=1))
    cache = _cache_with_snapshot(clock)

    result = _run(
        SteamDTCachedPriceResolver(cache).resolve(
            MARKET_HASH_NAME,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE,
        )
    )

    assert result.status == SteamDTCachedPriceResolutionStatus.SELECTED
    assert result.lookup.state == PriceCacheState.STALE
    assert result.lookup.age == timedelta(minutes=1)
    assert result.lookup.needs_refresh is True
    assert result.quote is not None


def test_stale_is_blocked_by_fresh_only_without_selector_call() -> None:
    clock = ManualClock(BASE_TIME + timedelta(minutes=1))
    cache = _cache_with_snapshot(clock)
    selector = RecordingSelector()

    result = _run(
        SteamDTCachedPriceResolver(cache, selector=selector).resolve(MARKET_HASH_NAME)
    )

    assert result.status == SteamDTCachedPriceResolutionStatus.POLICY_BLOCKED
    assert result.lookup.state == PriceCacheState.STALE
    assert result.lookup.policy_blocked is True
    assert result.lookup.needs_refresh is True
    assert result.quote is None
    assert selector.calls == []


def test_stale_grace_requires_explicit_allow_stale_grace() -> None:
    clock = ManualClock(BASE_TIME + timedelta(minutes=2))
    cache = _cache_with_snapshot(clock)
    selector = RecordingSelector()
    resolver = SteamDTCachedPriceResolver(cache, selector=selector)

    blocked = _run(
        resolver.resolve(
            MARKET_HASH_NAME,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE,
        )
    )
    allowed = _run(
        resolver.resolve(
            MARKET_HASH_NAME,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE_GRACE,
        )
    )

    assert blocked.status == SteamDTCachedPriceResolutionStatus.POLICY_BLOCKED
    assert blocked.lookup.state == PriceCacheState.STALE_GRACE
    assert blocked.quote is None
    assert allowed.status == SteamDTCachedPriceResolutionStatus.SELECTED
    assert allowed.lookup.state == PriceCacheState.STALE_GRACE
    assert allowed.lookup.needs_refresh is True
    assert allowed.quote is not None
    assert len(selector.calls) == 1


def test_missing_is_a_normal_no_quote_result() -> None:
    cache = RecordingPriceCache()
    selector = RecordingSelector()

    result = _run(
        SteamDTCachedPriceResolver(cache, selector=selector).resolve(MARKET_HASH_NAME)
    )

    assert result.status == SteamDTCachedPriceResolutionStatus.MISS
    assert result.lookup.state is None
    assert result.lookup.hit is False
    assert result.lookup.needs_refresh is False
    assert result.quote is None
    assert selector.calls == []
    assert cache.get_calls == [(_key(), PriceCacheReadPolicy.FRESH_ONLY)]
    assert cache.write_calls == 0


def test_expired_is_a_normal_no_quote_result_and_is_not_selected() -> None:
    clock = ManualClock(BASE_TIME + timedelta(minutes=3))
    cache = _cache_with_snapshot(clock)
    selector = RecordingSelector()

    result = _run(
        SteamDTCachedPriceResolver(cache, selector=selector).resolve(
            MARKET_HASH_NAME,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE_GRACE,
        )
    )

    assert result.status == SteamDTCachedPriceResolutionStatus.EXPIRED
    assert result.lookup.state == PriceCacheState.EXPIRED
    assert result.lookup.expired is True
    assert result.lookup.needs_refresh is True
    assert result.quote is None
    assert selector.calls == []


def test_empty_candidate_snapshot_is_a_selection_failure_not_a_miss() -> None:
    clock = ManualClock(BASE_TIME + timedelta(seconds=1))
    cache = _cache_with_snapshot(clock, candidates=())

    result = _run(
        SteamDTCachedPriceResolver(cache).resolve(MARKET_HASH_NAME)
    )

    assert result.status == SteamDTCachedPriceResolutionStatus.SELECTION_FAILURE
    assert result.lookup.hit is True
    assert result.selection_failure_reason_codes == ("NO_ACCEPTED_LIQUID_PRICE",)


def test_selector_no_candidate_is_a_typed_selection_failure() -> None:
    candidates = (_candidate("buff", "10.00", sell_count=0),)
    clock = ManualClock(BASE_TIME + timedelta(seconds=1))
    cache = _cache_with_snapshot(clock, candidates=candidates)
    config = SteamDTPriceSelectionConfig(
        min_sell_count=5,
        fallback_to_lowest_positive=False,
    )

    result = _run(
        SteamDTCachedPriceResolver(cache).resolve(
            MARKET_HASH_NAME,
            selection_config=config,
        )
    )

    assert result.status == SteamDTCachedPriceResolutionStatus.SELECTION_FAILURE
    assert result.quote is None
    assert result.selection_failure_reason_codes == ("NO_ACCEPTED_LIQUID_PRICE",)
    assert result.selection_result is not None
    assert result.selection_result.candidate_decisions[0].accepted is False
    assert "SELL_COUNT_BELOW_MINIMUM" in (
        result.selection_result.candidate_decisions[0].reason_codes
    )


def test_current_policy_reselects_same_snapshot_without_new_cache_key() -> None:
    candidates = (
        _candidate("buff", "9.00", sell_count=0),
        _candidate("steam", "10.00", sell_count=20),
    )
    clock = ManualClock(BASE_TIME + timedelta(seconds=1))
    cache = _cache_with_snapshot(clock, candidates=candidates)
    resolver = SteamDTCachedPriceResolver(cache)

    liquidity_result = _run(
        resolver.resolve(
            MARKET_HASH_NAME,
            selection_config=SteamDTPriceSelectionConfig(
                min_sell_count=5,
                fallback_to_lowest_positive=False,
            ),
        )
    )
    lowest_result = _run(
        resolver.resolve(
            MARKET_HASH_NAME,
            selection_config=SteamDTPriceSelectionConfig(
                strategy=SteamDTPriceSelectionStrategy.LOWEST_POSITIVE_SELL_PRICE
            ),
        )
    )

    assert liquidity_result.lookup.key == lowest_result.lookup.key == _key()
    assert liquidity_result.lookup.snapshot is lowest_result.lookup.snapshot
    assert liquidity_result.selection_result is not None
    assert liquidity_result.selection_result.selected_platform == "steam"
    assert lowest_result.selection_result is not None
    assert lowest_result.selection_result.selected_platform == "buff"


def test_selector_receives_order_duplicates_current_config_and_known_avg() -> None:
    duplicate = _candidate("buff", "10.12345678")
    snapshot = _snapshot(candidates=(duplicate, duplicate, _candidate("steam", "11")))
    lookup = PriceCacheLookup(
        key=snapshot.key,
        hit=True,
        state=PriceCacheState.FRESH,
        snapshot=snapshot,
        age=timedelta(seconds=3),
        needs_refresh=False,
        policy_blocked=False,
        expired=False,
    )
    cache = RecordingPriceCache(lookup=lookup)
    selector = RecordingSelector()
    config = SteamDTPriceSelectionConfig(max_price_to_avg_ratio=Decimal("2"))
    avg_price = Decimal("9.87654321")

    result = _run(
        SteamDTCachedPriceResolver(cache, selector=selector).resolve(
            MARKET_HASH_NAME,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE,
            selection_config=config,
            avg_price_cny=avg_price,
        )
    )

    assert result.status == SteamDTCachedPriceResolutionStatus.SELECTED
    assert cache.get_calls == [(_key(), PriceCacheReadPolicy.ALLOW_STALE)]
    assert cache.write_calls == 0
    assert len(selector.calls) == 1
    name, prices, actual_config, actual_avg, original_payload = selector.calls[0]
    assert name == MARKET_HASH_NAME
    assert [price.platform for price in prices] == ["buff", "buff", "steam"]
    assert prices[0] == prices[1]
    assert all(price.raw is None for price in prices)
    assert actual_config is config
    assert actual_avg is avg_price
    assert original_payload is None


@pytest.mark.parametrize(
    "error",
    [
        PriceCacheBackendError("get", "unavailable"),
        PriceCacheCodecError("payload_json", "corrupt"),
    ],
)
def test_backend_and_codec_errors_propagate_by_identity(error: Exception) -> None:
    cache = RecordingPriceCache(error=error)

    with pytest.raises(type(error)) as exc_info:
        _run(SteamDTCachedPriceResolver(cache).resolve(MARKET_HASH_NAME))

    assert exc_info.value is error
    assert cache.write_calls == 0


def test_mismatched_snapshot_key_is_rejected_before_selection() -> None:
    snapshot = _snapshot()
    other_snapshot = CachedPriceSnapshot(
        key=PriceCacheKey(market_hash_name="M4A4 | Asiimov"),
        candidates=snapshot.candidates,
        observed_at=snapshot.observed_at,
        stored_at=snapshot.stored_at,
        policy=snapshot.policy,
    )
    lookup = PriceCacheLookup(
        key=_key(),
        hit=True,
        state=PriceCacheState.FRESH,
        snapshot=other_snapshot,
        age=timedelta(seconds=1),
        needs_refresh=False,
        policy_blocked=False,
        expired=False,
    )

    with pytest.raises(SteamDTCachedPriceResolverError, match="different key"):
        _run(
            SteamDTCachedPriceResolver(RecordingPriceCache(lookup=lookup)).resolve(
                MARKET_HASH_NAME
            )
        )


def test_inconsistent_lookup_flags_are_rejected() -> None:
    snapshot = _snapshot()
    lookup = PriceCacheLookup(
        key=_key(),
        hit=True,
        state=PriceCacheState.FRESH,
        snapshot=snapshot,
        age=timedelta(seconds=1),
        needs_refresh=True,
        policy_blocked=False,
        expired=False,
    )

    with pytest.raises(SteamDTCachedPriceResolverError, match="inconsistent"):
        _run(
            SteamDTCachedPriceResolver(RecordingPriceCache(lookup=lookup)).resolve(
                MARKET_HASH_NAME
            )
        )


def test_lookup_state_must_match_snapshot_age() -> None:
    snapshot = _snapshot()
    lookup = PriceCacheLookup(
        key=_key(),
        hit=True,
        state=PriceCacheState.FRESH,
        snapshot=snapshot,
        age=timedelta(minutes=10),
        needs_refresh=False,
        policy_blocked=False,
        expired=False,
    )

    with pytest.raises(SteamDTCachedPriceResolverError, match="snapshot age"):
        _run(
            SteamDTCachedPriceResolver(RecordingPriceCache(lookup=lookup)).resolve(
                MARKET_HASH_NAME
            )
        )


def test_reader_cannot_return_stale_hit_blocked_by_requested_policy() -> None:
    snapshot = _snapshot()
    lookup = PriceCacheLookup(
        key=_key(),
        hit=True,
        state=PriceCacheState.STALE,
        snapshot=snapshot,
        age=timedelta(minutes=1),
        needs_refresh=True,
        policy_blocked=False,
        expired=False,
    )

    with pytest.raises(SteamDTCachedPriceResolverError, match="read policy"):
        _run(
            SteamDTCachedPriceResolver(RecordingPriceCache(lookup=lookup)).resolve(
                MARKET_HASH_NAME,
                read_policy=PriceCacheReadPolicy.FRESH_ONLY,
            )
        )


def test_reader_cannot_block_stale_data_allowed_by_requested_policy() -> None:
    lookup = PriceCacheLookup(
        key=_key(),
        hit=False,
        state=PriceCacheState.STALE,
        snapshot=None,
        age=timedelta(minutes=1),
        needs_refresh=True,
        policy_blocked=True,
        expired=False,
    )

    with pytest.raises(SteamDTCachedPriceResolverError, match="allowed"):
        _run(
            SteamDTCachedPriceResolver(RecordingPriceCache(lookup=lookup)).resolve(
                MARKET_HASH_NAME,
                read_policy=PriceCacheReadPolicy.ALLOW_STALE,
            )
        )


def test_invalid_selector_result_is_rejected_explicitly() -> None:
    snapshot = _snapshot()
    lookup = PriceCacheLookup(
        key=_key(),
        hit=True,
        state=PriceCacheState.FRESH,
        snapshot=snapshot,
        age=timedelta(seconds=1),
        needs_refresh=False,
        policy_blocked=False,
        expired=False,
    )

    with pytest.raises(SteamDTCachedPriceResolverError, match="invalid selection"):
        _run(
            SteamDTCachedPriceResolver(
                RecordingPriceCache(lookup=lookup),
                selector=FixedSelector(None),  # type: ignore[arg-type]
            ).resolve(MARKET_HASH_NAME)
        )


def test_selector_quote_for_another_item_is_rejected() -> None:
    snapshot = _snapshot()
    lookup = PriceCacheLookup(
        key=_key(),
        hit=True,
        state=PriceCacheState.FRESH,
        snapshot=snapshot,
        age=timedelta(seconds=1),
        needs_refresh=False,
        policy_blocked=False,
        expired=False,
    )
    selection_result = SteamDTPriceSelectionResult(
        market_hash_name=MARKET_HASH_NAME,
        quote=SteamDTPriceQuote(
            market_hash_name="M4A4 | Asiimov",
            price_cny=Decimal("10"),
        ),
        selected_platform="buff",
        selected_strategy="test",
        reason_codes=["TEST"],
        candidate_decisions=[],
    )

    with pytest.raises(SteamDTCachedPriceResolverError, match="different market"):
        _run(
            SteamDTCachedPriceResolver(
                RecordingPriceCache(lookup=lookup),
                selector=FixedSelector(selection_result),
            ).resolve(MARKET_HASH_NAME)
        )


def test_adapter_error_from_corrupt_cached_candidate_remains_distinct() -> None:
    candidate = _candidate("buff", "10.00")
    object.__setattr__(candidate, "source_update_time", True)
    snapshot = _snapshot(candidates=(candidate,))
    lookup = PriceCacheLookup(
        key=snapshot.key,
        hit=True,
        state=PriceCacheState.FRESH,
        snapshot=snapshot,
        age=timedelta(seconds=1),
        needs_refresh=False,
        policy_blocked=False,
        expired=False,
    )
    cache = RecordingPriceCache(lookup=lookup)
    selector = RecordingSelector()

    with pytest.raises(SteamDTPriceCacheAdapterError) as exc_info:
        _run(
            SteamDTCachedPriceResolver(cache, selector=selector).resolve(
                MARKET_HASH_NAME
            )
        )

    assert exc_info.value.reason == SteamDTPriceCacheAdapterErrorReason.INVALID_TYPE
    assert exc_info.value.field == "candidates[0].candidate.source_update_time"
    assert selector.calls == []
    assert cache.write_calls == 0


def test_existing_runtime_boundaries_do_not_import_adapter_or_resolver() -> None:
    paths = [
        Path("app/services/price_provider.py"),
        Path("app/services/valuation_service.py"),
        Path("app/services/pipeline_service.py"),
        Path("app/services/pipeline_alert_service.py"),
        Path("app/jobs/scheduler.py"),
        Path("app/main.py"),
    ]

    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "steamdt_cached_price_resolver" not in source
        assert "steamdt_price_cache_adapter" not in source


def test_resolver_source_has_no_forbidden_runtime_dependencies() -> None:
    source = Path(
        "app/services/steamdt_cached_price_resolver.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "SteamDTHttpClient",
        "RedisPriceCache",
        "Redis.from_url",
        "get_avg_price",
        "asyncio.create_task",
        "app.config",
        "os.environ",
        "price_provider",
        "pipeline_service",
        "scheduler",
        "fastapi",
        "._cache.put(",
        "._cache.delete(",
        "._cache.clear(",
        "._cache.purge_expired(",
    ]
    for value in forbidden:
        assert value not in source