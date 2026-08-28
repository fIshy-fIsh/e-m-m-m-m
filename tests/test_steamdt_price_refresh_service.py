import asyncio
from collections.abc import Coroutine
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.clients.steamdt_client import SteamDTPlatformPrice
from app.clients.steamdt_errors import (
    SteamDTApiError,
    SteamDTHttpStatusError,
    SteamDTRateLimitError,
    SteamDTResponseParseError,
    SteamDTTransportError,
)
from app.services.price_cache import (
    CachedPriceSnapshot,
    InMemoryPriceCache,
    PriceCacheKey,
    PriceCacheLookup,
    PriceCachePolicy,
    PriceCacheReadPolicy,
    PriceCacheWriteResult,
)
from app.services.price_cache_codec import PriceCacheCodecError
from app.services.redis_price_cache import PriceCacheBackendError
from app.services.steamdt_price_cache_adapter import (
    SteamDTPriceCacheAdapterError,
    SteamDTPriceCacheAdapterErrorReason,
)
from app.services.steamdt_price_refresh_service import (
    SteamDTFetchedPriceSnapshot,
    SteamDTPriceRefreshResult,
    SteamDTPriceRefreshService,
    SteamDTPriceRefreshStatus,
    SteamDTPriceRefreshValidationError,
)

BASE_TIME = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
MARKET_HASH_NAME = "AK-47 | Redline"


class ManualClock:
    def __init__(self, now: datetime = BASE_TIME) -> None:
        self.now = now
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return self.now


class FakeSnapshotSource:
    def __init__(
        self,
        fetched: object | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.fetched = fetched
        self.error = error
        self.calls: list[str] = []

    async def fetch_price_snapshot(self, market_hash_name: str) -> Any:
        self.calls.append(market_hash_name)
        if self.error is not None:
            raise self.error
        return self.fetched


class SpyPriceCache:
    def __init__(
        self,
        write_result: object = PriceCacheWriteResult.CREATED,
        *,
        error: Exception | None = None,
    ) -> None:
        self.write_result = write_result
        self.error = error
        self.put_calls: list[CachedPriceSnapshot] = []
        self.forbidden_calls: list[str] = []

    async def put(self, snapshot: CachedPriceSnapshot) -> Any:
        self.put_calls.append(snapshot)
        if self.error is not None:
            raise self.error
        return self.write_result

    async def get(
        self,
        key: PriceCacheKey,
        *,
        read_policy: PriceCacheReadPolicy = PriceCacheReadPolicy.FRESH_ONLY,
    ) -> PriceCacheLookup:
        self.forbidden_calls.append("get")
        raise AssertionError("refresh service must not read the cache")

    async def delete(self, key: PriceCacheKey) -> bool:
        self.forbidden_calls.append("delete")
        raise AssertionError("refresh service must not delete cache entries")

    async def clear(self) -> None:
        self.forbidden_calls.append("clear")
        raise AssertionError("refresh service must not clear the cache")

    async def purge_expired(self) -> int:
        self.forbidden_calls.append("purge_expired")
        raise AssertionError("refresh service must not purge cache entries")


class CoordinatedSnapshotSource:
    def __init__(
        self,
        newer: SteamDTFetchedPriceSnapshot,
        older: SteamDTFetchedPriceSnapshot,
    ) -> None:
        self.newer = newer
        self.older = older
        self.calls = 0
        self.older_started = asyncio.Event()
        self.release_older = asyncio.Event()

    async def fetch_price_snapshot(
        self,
        market_hash_name: str,
    ) -> SteamDTFetchedPriceSnapshot:
        self.calls += 1
        if self.calls == 1:
            self.older_started.set()
            await self.release_older.wait()
            return self.older
        return self.newer


def _run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def _platform_price(
    platform: str = "buff",
    sell_price: str = "12.34000001",
    *,
    raw: dict[str, object] | None = None,
) -> SteamDTPlatformPrice:
    return SteamDTPlatformPrice(
        platform=platform,
        platform_item_id=f"{platform}-item",
        sell_price_cny=Decimal(sell_price),
        sell_count=17,
        bidding_price_cny=Decimal("11.98765432"),
        bidding_count=9,
        update_time="opaque-source-time",
        raw=raw,
    )


def _fetched(
    *,
    candidates: list[SteamDTPlatformPrice] | tuple[SteamDTPlatformPrice, ...] | None = None,
    observed_at: datetime = BASE_TIME,
    market_hash_name: str = MARKET_HASH_NAME,
    source: str = "steamdt",
) -> SteamDTFetchedPriceSnapshot:
    return SteamDTFetchedPriceSnapshot(
        market_hash_name=market_hash_name,
        source=source,
        candidates=(candidates if candidates is not None else [_platform_price()]),
        observed_at=observed_at,
    )


def _policy() -> PriceCachePolicy:
    return PriceCachePolicy(
        fresh_ttl=timedelta(minutes=1),
        stale_ttl=timedelta(minutes=2),
        stale_grace_ttl=timedelta(minutes=3),
    )


def test_fetched_snapshot_defensively_clones_candidates_without_raw() -> None:
    raw: dict[str, object] = {"Authorization": "Bearer dummy-secret"}
    original = _platform_price(raw=raw)
    candidates = [original, original, _platform_price("steam", "13.00000009")]

    fetched = _fetched(candidates=candidates)
    candidates.clear()
    raw["Authorization"] = "changed"

    assert isinstance(fetched.candidates, tuple)
    assert [candidate.platform for candidate in fetched.candidates] == [
        "buff",
        "buff",
        "steam",
    ]
    assert fetched.candidates[0] == fetched.candidates[1]
    assert fetched.candidates[0] is not original
    assert all(candidate.raw is None for candidate in fetched.candidates)
    assert fetched.candidates[0].sell_price_cny == Decimal("12.34000001")
    assert fetched.candidates[0].update_time == "opaque-source-time"
    assert "dummy-secret" not in repr(fetched)


def test_fetched_snapshot_is_frozen_and_normalizes_aware_time_to_utc() -> None:
    offset_time = datetime.fromisoformat("2026-07-21T20:00:00+08:00")
    fetched = _fetched(observed_at=offset_time)

    assert fetched.observed_at == BASE_TIME
    with pytest.raises(FrozenInstanceError):
        fetched.source = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "error_type"),
    [
        ({"market_hash_name": " "}, ValueError),
        ({"market_hash_name": " padded "}, ValueError),
        ({"source": ""}, ValueError),
        ({"source": " steamdt "}, ValueError),
        ({"observed_at": datetime(2026, 7, 21, 12, 0)}, ValueError),
    ],
)
def test_fetched_snapshot_rejects_invalid_identity_or_time(
    kwargs: dict[str, object],
    error_type: type[Exception],
) -> None:
    values: dict[str, object] = {
        "market_hash_name": MARKET_HASH_NAME,
        "source": "steamdt",
        "candidates": [_platform_price()],
        "observed_at": BASE_TIME,
    }
    values.update(kwargs)

    with pytest.raises(error_type):
        SteamDTFetchedPriceSnapshot(**values)  # type: ignore[arg-type]


def test_refresh_result_enforces_status_contract() -> None:
    key = PriceCacheKey(market_hash_name=MARKET_HASH_NAME)

    with pytest.raises(ValueError):
        SteamDTPriceRefreshResult(
            status=SteamDTPriceRefreshStatus.NO_CANDIDATES,
            key=key,
            observed_at=BASE_TIME,
            candidate_count=1,
            write_result=None,
        )
    with pytest.raises(ValueError):
        SteamDTPriceRefreshResult(
            status=SteamDTPriceRefreshStatus.CACHE_PUT_COMPLETED,
            key=key,
            observed_at=BASE_TIME,
            candidate_count=0,
            write_result=PriceCacheWriteResult.CREATED,
        )
    with pytest.raises(TypeError):
        SteamDTPriceRefreshResult(
            status="written",  # type: ignore[arg-type]
            key=key,
            observed_at=BASE_TIME,
            candidate_count=1,
            write_result=PriceCacheWriteResult.CREATED,
        )


@pytest.mark.parametrize("write_result", list(PriceCacheWriteResult))
def test_nonempty_refresh_preserves_exact_write_result_and_snapshot(
    write_result: PriceCacheWriteResult,
) -> None:
    fetched = _fetched(
        candidates=[
            _platform_price("buff", "12.34000001"),
            _platform_price("buff", "12.34000001"),
            _platform_price("steam", "13.00000009"),
        ]
    )
    source = FakeSnapshotSource(fetched)
    cache = SpyPriceCache(write_result)
    clock = ManualClock(BASE_TIME + timedelta(seconds=5))
    policy = _policy()

    result = _run(
        SteamDTPriceRefreshService(source, cache, clock=clock).refresh_one(
            f"  {MARKET_HASH_NAME}  ",
            policy,
        )
    )

    assert source.calls == [MARKET_HASH_NAME]
    assert len(cache.put_calls) == 1
    assert cache.forbidden_calls == []
    assert clock.calls == 1
    snapshot = cache.put_calls[0]
    assert snapshot.key == PriceCacheKey(market_hash_name=MARKET_HASH_NAME)
    assert [candidate.platform for candidate in snapshot.candidates] == [
        "buff",
        "buff",
        "steam",
    ]
    assert snapshot.candidates[0] == snapshot.candidates[1]
    assert snapshot.candidates[0].sell_price_cny == Decimal("12.34000001")
    assert snapshot.candidates[0].source_update_time == "opaque-source-time"
    assert snapshot.observed_at == BASE_TIME
    assert snapshot.stored_at == BASE_TIME + timedelta(seconds=5)
    assert snapshot.policy is policy
    assert result.status == SteamDTPriceRefreshStatus.CACHE_PUT_COMPLETED
    assert result.key == snapshot.key
    assert result.observed_at == BASE_TIME
    assert result.candidate_count == 3
    assert result.write_result is write_result


def test_empty_candidates_return_no_candidates_without_clock_or_cache() -> None:
    fetched = _fetched(candidates=[])
    source = FakeSnapshotSource(fetched)
    cache = SpyPriceCache()
    clock = ManualClock(BASE_TIME)

    result = _run(
        SteamDTPriceRefreshService(source, cache, clock=clock).refresh_one(
            MARKET_HASH_NAME,
            _policy(),
        )
    )

    assert result.status == SteamDTPriceRefreshStatus.NO_CANDIDATES
    assert result.candidate_count == 0
    assert result.write_result is None
    assert result.observed_at == BASE_TIME
    assert source.calls == [MARKET_HASH_NAME]
    assert clock.calls == 0
    assert cache.put_calls == []
    assert cache.forbidden_calls == []


@pytest.mark.parametrize(
    ("fetched", "message"),
    [
        (object(), "invalid result"),
        (_fetched(market_hash_name="M4A4 | Asiimov"), "different item"),
        (_fetched(source="other"), "different source"),
    ],
)
def test_source_contract_mismatch_fails_before_clock_or_cache(
    fetched: object,
    message: str,
) -> None:
    source = FakeSnapshotSource(fetched)
    cache = SpyPriceCache()
    clock = ManualClock(BASE_TIME)

    with pytest.raises(SteamDTPriceRefreshValidationError, match=message):
        _run(
            SteamDTPriceRefreshService(source, cache, clock=clock).refresh_one(
                MARKET_HASH_NAME,
                _policy(),
            )
        )

    assert clock.calls == 0
    assert cache.put_calls == []


def test_invalid_cache_write_result_is_a_refresh_validation_error() -> None:
    cache = SpyPriceCache("created")

    with pytest.raises(SteamDTPriceRefreshValidationError, match="cache writer"):
        _run(
            SteamDTPriceRefreshService(
                FakeSnapshotSource(_fetched()),
                cache,
                clock=ManualClock(BASE_TIME),
            ).refresh_one(MARKET_HASH_NAME, _policy())
        )

    assert len(cache.put_calls) == 1


@pytest.mark.parametrize(
    "error",
    [
        SteamDTTransportError("transport", endpoint="price_single"),
        SteamDTHttpStatusError(
            "status",
            endpoint="price_single",
            status_code=503,
        ),
        SteamDTApiError(
            "api",
            endpoint="price_single",
            error_code=5001,
        ),
        SteamDTRateLimitError(
            "limited",
            endpoint="price_single",
            status_code=429,
        ),
        SteamDTResponseParseError("parse", endpoint="price_single"),
    ],
)
def test_source_typed_errors_propagate_by_identity_without_retry(
    error: Exception,
) -> None:
    source = FakeSnapshotSource(error=error)
    cache = SpyPriceCache()
    clock = ManualClock(BASE_TIME)

    with pytest.raises(type(error)) as exc_info:
        _run(
            SteamDTPriceRefreshService(source, cache, clock=clock).refresh_one(
                MARKET_HASH_NAME,
                _policy(),
            )
        )

    assert exc_info.value is error
    assert source.calls == [MARKET_HASH_NAME]
    assert clock.calls == 0
    assert cache.put_calls == []


def test_adapter_error_propagates_without_cache_write() -> None:
    candidate = _platform_price()
    object.__setattr__(candidate, "update_time", True)
    fetched = _fetched(candidates=[candidate])
    cache = SpyPriceCache()

    with pytest.raises(SteamDTPriceCacheAdapterError) as exc_info:
        _run(
            SteamDTPriceRefreshService(
                FakeSnapshotSource(fetched),
                cache,
                clock=ManualClock(BASE_TIME),
            ).refresh_one(MARKET_HASH_NAME, _policy())
        )

    assert exc_info.value.reason == SteamDTPriceCacheAdapterErrorReason.INVALID_TYPE
    assert cache.put_calls == []


@pytest.mark.parametrize(
    "error",
    [
        PriceCacheBackendError("put", "unavailable"),
        PriceCacheCodecError("payload_json", "corrupt"),
    ],
)
def test_cache_errors_propagate_by_identity_after_one_put(error: Exception) -> None:
    cache = SpyPriceCache(error=error)

    with pytest.raises(type(error)) as exc_info:
        _run(
            SteamDTPriceRefreshService(
                FakeSnapshotSource(_fetched()),
                cache,
                clock=ManualClock(BASE_TIME),
            ).refresh_one(MARKET_HASH_NAME, _policy())
        )

    assert exc_info.value is error
    assert len(cache.put_calls) == 1


def test_service_clock_lag_does_not_preempt_authoritative_cache_validation() -> None:
    cache = SpyPriceCache()
    observed_at = BASE_TIME + timedelta(seconds=1)

    result = _run(
        SteamDTPriceRefreshService(
            FakeSnapshotSource(_fetched(observed_at=observed_at)),
            cache,
            clock=ManualClock(BASE_TIME),
        ).refresh_one(MARKET_HASH_NAME, _policy())
    )

    assert result.write_result == PriceCacheWriteResult.CREATED
    assert len(cache.put_calls) == 1
    assert cache.put_calls[0].observed_at == observed_at
    assert cache.put_calls[0].stored_at == observed_at


def test_cache_backend_stamps_authoritative_stored_at() -> None:
    service_clock = ManualClock(BASE_TIME + timedelta(seconds=3))
    cache_clock = ManualClock(BASE_TIME + timedelta(seconds=10))
    cache = InMemoryPriceCache(clock=cache_clock)

    result = _run(
        SteamDTPriceRefreshService(
            FakeSnapshotSource(_fetched()),
            cache,
            clock=service_clock,
        ).refresh_one(MARKET_HASH_NAME, _policy())
    )
    lookup = _run(cache.get(PriceCacheKey(market_hash_name=MARKET_HASH_NAME)))

    assert result.write_result == PriceCacheWriteResult.CREATED
    assert lookup.snapshot is not None
    assert lookup.snapshot.observed_at == BASE_TIME
    assert lookup.snapshot.stored_at == cache_clock.now
    assert lookup.snapshot.stored_at != service_clock.now


def test_cache_authoritative_clock_can_reject_future_observation() -> None:
    cache = InMemoryPriceCache(clock=ManualClock(BASE_TIME))
    service_clock = ManualClock(BASE_TIME + timedelta(seconds=2))
    fetched = _fetched(observed_at=BASE_TIME + timedelta(seconds=1))

    with pytest.raises(ValueError, match="later than cache storage time"):
        _run(
            SteamDTPriceRefreshService(
                FakeSnapshotSource(fetched),
                cache,
                clock=service_clock,
            ).refresh_one(MARKET_HASH_NAME, _policy())
        )

    missing = _run(cache.get(PriceCacheKey(market_hash_name=MARKET_HASH_NAME)))
    assert missing.hit is False


def test_inmemory_write_results_preserve_observed_at_ordering() -> None:
    cache_clock = ManualClock(BASE_TIME + timedelta(minutes=4))
    cache = InMemoryPriceCache(clock=cache_clock)
    service = lambda fetched: SteamDTPriceRefreshService(  # noqa: E731
        FakeSnapshotSource(fetched),
        cache,
        clock=ManualClock(BASE_TIME + timedelta(minutes=9)),
    )

    created = _run(
        service(_fetched(observed_at=BASE_TIME + timedelta(minutes=2))).refresh_one(
            MARKET_HASH_NAME,
            _policy(),
        )
    )
    replaced = _run(
        service(
            _fetched(
                observed_at=BASE_TIME + timedelta(minutes=3),
                candidates=[_platform_price("steam", "20")],
            )
        ).refresh_one(MARKET_HASH_NAME, _policy())
    )
    older = _run(
        service(
            _fetched(
                observed_at=BASE_TIME + timedelta(minutes=1),
                candidates=[_platform_price("market", "5")],
            )
        ).refresh_one(MARKET_HASH_NAME, _policy())
    )
    equal = _run(
        service(
            _fetched(
                observed_at=BASE_TIME + timedelta(minutes=3),
                candidates=[_platform_price("other", "1")],
            )
        ).refresh_one(MARKET_HASH_NAME, _policy())
    )
    lookup = _run(
        cache.get(
            PriceCacheKey(market_hash_name=MARKET_HASH_NAME),
            read_policy=PriceCacheReadPolicy.ALLOW_STALE_GRACE,
        )
    )

    assert created.write_result == PriceCacheWriteResult.CREATED
    assert replaced.write_result == PriceCacheWriteResult.REPLACED
    assert older.write_result == PriceCacheWriteResult.IGNORED_OLDER
    assert equal.write_result == PriceCacheWriteResult.UNCHANGED_EQUAL
    assert lookup.snapshot is not None
    assert lookup.snapshot.observed_at == BASE_TIME + timedelta(minutes=3)
    assert lookup.snapshot.candidates[0].platform == "steam"


def test_concurrent_refreshes_fetch_independently_and_cache_keeps_newer() -> None:
    async def scenario() -> tuple[
        SteamDTPriceRefreshResult,
        SteamDTPriceRefreshResult,
        PriceCacheLookup,
        int,
    ]:
        newer = _fetched(
            observed_at=BASE_TIME + timedelta(minutes=2),
            candidates=[_platform_price("newer", "20")],
        )
        older = _fetched(
            observed_at=BASE_TIME + timedelta(minutes=1),
            candidates=[_platform_price("older", "10")],
        )
        source = CoordinatedSnapshotSource(newer, older)
        shared_clock = ManualClock(BASE_TIME + timedelta(minutes=3))
        cache = InMemoryPriceCache(clock=shared_clock)
        service = SteamDTPriceRefreshService(source, cache, clock=shared_clock)

        older_task = asyncio.create_task(service.refresh_one(MARKET_HASH_NAME, _policy()))
        await source.older_started.wait()
        newer_result = await service.refresh_one(MARKET_HASH_NAME, _policy())
        source.release_older.set()
        older_result = await older_task
        lookup = await cache.get(
            PriceCacheKey(market_hash_name=MARKET_HASH_NAME),
            read_policy=PriceCacheReadPolicy.ALLOW_STALE_GRACE,
        )
        return newer_result, older_result, lookup, source.calls

    newer_result, older_result, lookup, source_calls = _run(scenario())

    assert source_calls == 2
    assert newer_result.write_result == PriceCacheWriteResult.CREATED
    assert older_result.write_result == PriceCacheWriteResult.IGNORED_OLDER
    assert lookup.snapshot is not None
    assert lookup.snapshot.observed_at == BASE_TIME + timedelta(minutes=2)
    assert lookup.snapshot.candidates[0].platform == "newer"


def test_runtime_boundaries_do_not_import_refresh_service() -> None:
    paths = [
        Path("app/services/price_provider.py"),
        Path("app/services/steamdt_cached_price_resolver.py"),
        Path("app/services/price_cache_factory.py"),
        Path("app/services/valuation_service.py"),
        Path("app/services/pipeline_service.py"),
        Path("app/services/pipeline_alert_service.py"),
        Path("app/jobs/scheduler.py"),
        Path("app/main.py"),
        Path("app/config.py"),
    ]

    for path in paths:
        assert "steamdt_price_refresh_service" not in path.read_text(encoding="utf-8")


def test_refresh_service_has_no_forbidden_runtime_dependencies() -> None:
    source = Path(
        "app/services/steamdt_price_refresh_service.py"
    ).read_text(encoding="utf-8")
    forbidden = [
        "SteamDTHttpClient",
        "SteamDTPriceProvider",
        "select_steamdt_price_quote",
        "steamdt_price_selection",
        "SteamDTPriceQuote",
        "SteamDTCachedPriceResolver",
        "RedisPriceCache",
        "Redis.from_url",
        "price_cache_factory",
        "app.config",
        "os.environ",
        "asyncio.create_task",
        "get_price_single",
        "pipeline_service",
        "scheduler",
        "fastapi",
        "._cache.get(",
        "._cache.delete(",
        "._cache.clear(",
        "._cache.purge_expired(",
    ]

    for value in forbidden:
        assert value not in source
