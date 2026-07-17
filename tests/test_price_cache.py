import asyncio
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.price_cache import (
    PRICE_CACHE_SCHEMA_VERSION,
    CachedPriceSnapshot,
    InMemoryPriceCache,
    NormalizedPriceCandidate,
    PriceCacheKey,
    PriceCachePolicy,
    PriceCacheReadPolicy,
    PriceCacheState,
    PriceCacheWriteResult,
)

BASE_TIME = datetime(2026, 7, 16, 12, tzinfo=UTC)


class ManualClock:
    def __init__(self, now: datetime = BASE_TIME) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def set(self, now: datetime) -> None:
        self.now = now


class MutableSequence:
    def __init__(self, values: list[NormalizedPriceCandidate]) -> None:
        self.values = values

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.values)


def _key(
    name: str = "AK-47 | Redline (Field-Tested)",
    *,
    source: str = "steamdt",
    currency: str = "CNY",
) -> PriceCacheKey:
    return PriceCacheKey(
        market_hash_name=name,
        source=source,
        currency=currency,
    )


def _candidate(
    *,
    platform: str = "buff",
    sell_price: str = "123.4500",
    sell_count: int = 20,
) -> NormalizedPriceCandidate:
    return NormalizedPriceCandidate(
        platform=platform,
        platform_item_id="item-1",
        sell_price_cny=Decimal(sell_price),
        sell_count=sell_count,
        bidding_price_cny=Decimal("120.0100"),
        bidding_count=9,
        source_update_time=1_752_665_600,
    )


def _policy(
    *,
    fresh: timedelta = timedelta(minutes=5),
    stale: timedelta = timedelta(minutes=3),
    grace: timedelta = timedelta(minutes=2),
) -> PriceCachePolicy:
    return PriceCachePolicy(
        fresh_ttl=fresh,
        stale_ttl=stale,
        stale_grace_ttl=grace,
    )


def _snapshot(
    *,
    key: PriceCacheKey | None = None,
    observed_at: datetime = BASE_TIME,
    stored_at: datetime | None = None,
    policy: PriceCachePolicy | None = None,
    candidates: tuple[NormalizedPriceCandidate, ...] | None = None,
) -> CachedPriceSnapshot:
    return CachedPriceSnapshot(
        key=key or _key(),
        candidates=candidates or (_candidate(),),
        observed_at=observed_at,
        stored_at=stored_at or observed_at,
        policy=policy or _policy(),
    )


def _run(coroutine):  # type: ignore[no-untyped-def]
    return asyncio.run(coroutine)


@pytest.mark.parametrize("fresh", [timedelta(0), timedelta(microseconds=-1)])
def test_policy_rejects_non_positive_fresh_ttl(fresh: timedelta) -> None:
    with pytest.raises(ValueError, match="fresh_ttl"):
        _policy(fresh=fresh)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stale", timedelta(microseconds=-1)),
        ("grace", timedelta(microseconds=-1)),
    ],
)
def test_policy_rejects_negative_optional_ttls(field: str, value: timedelta) -> None:
    kwargs = {field: value}
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        _policy(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["observed_at", "stored_at"])
def test_snapshot_rejects_naive_datetimes(field: str) -> None:
    kwargs = {
        "observed_at": BASE_TIME,
        "stored_at": BASE_TIME,
    }
    kwargs[field] = datetime(2026, 7, 16, 12)

    with pytest.raises(ValueError, match=f"{field} must be timezone-aware"):
        _snapshot(**kwargs)  # type: ignore[arg-type]


def test_snapshot_rejects_observation_later_than_storage() -> None:
    with pytest.raises(ValueError, match="observed_at cannot be later"):
        _snapshot(
            observed_at=BASE_TIME + timedelta(seconds=1),
            stored_at=BASE_TIME,
        )


def test_snapshot_normalizes_aware_datetimes_to_utc() -> None:
    east = timezone(timedelta(hours=8))
    snapshot = _snapshot(
        observed_at=datetime(2026, 7, 16, 20, tzinfo=east),
        stored_at=datetime(2026, 7, 16, 20, 1, tzinfo=east),
    )

    assert snapshot.observed_at == BASE_TIME
    assert snapshot.observed_at.tzinfo is UTC
    assert snapshot.stored_at == BASE_TIME + timedelta(minutes=1)


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (timedelta(minutes=4, seconds=59), PriceCacheState.FRESH),
        (timedelta(minutes=5), PriceCacheState.STALE),
        (timedelta(minutes=7, seconds=59), PriceCacheState.STALE),
        (timedelta(minutes=8), PriceCacheState.STALE_GRACE),
        (timedelta(minutes=9, seconds=59), PriceCacheState.STALE_GRACE),
        (timedelta(minutes=10), PriceCacheState.EXPIRED),
    ],
)
def test_exact_state_boundaries(offset: timedelta, expected: PriceCacheState) -> None:
    clock = ManualClock(BASE_TIME + offset)
    cache = InMemoryPriceCache(clock=clock)
    snapshot = _snapshot()
    _run(cache.put(snapshot))

    result = _run(
        cache.get(
            snapshot.key,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE_GRACE,
        )
    )

    assert result.state == expected
    if expected == PriceCacheState.EXPIRED:
        assert result.hit is False
        assert result.snapshot is None
        assert result.expired is True
    else:
        assert result.hit is True


def test_zero_stale_ttl_skips_stale_interval() -> None:
    clock = ManualClock(BASE_TIME + timedelta(minutes=5))
    cache = InMemoryPriceCache(clock=clock)
    snapshot = _snapshot(policy=_policy(stale=timedelta(0)))
    _run(cache.put(snapshot))

    result = _run(
        cache.get(
            snapshot.key,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE_GRACE,
        )
    )

    assert result.state == PriceCacheState.STALE_GRACE


def test_zero_grace_ttl_skips_grace_interval() -> None:
    clock = ManualClock(BASE_TIME + timedelta(minutes=8))
    cache = InMemoryPriceCache(clock=clock)
    snapshot = _snapshot(policy=_policy(grace=timedelta(0)))
    _run(cache.put(snapshot))

    result = _run(
        cache.get(
            snapshot.key,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE_GRACE,
        )
    )

    assert result.state == PriceCacheState.EXPIRED
    assert result.snapshot is None


def test_zero_stale_and_grace_ttls_expire_at_fresh_boundary() -> None:
    clock = ManualClock(BASE_TIME + timedelta(minutes=5))
    cache = InMemoryPriceCache(clock=clock)
    snapshot = _snapshot(
        policy=_policy(stale=timedelta(0), grace=timedelta(0))
    )
    _run(cache.put(snapshot))

    result = _run(cache.get(snapshot.key))

    assert result.state == PriceCacheState.EXPIRED
    assert result.hit is False


@pytest.mark.parametrize(
    ("state_offset", "read_policy", "hit"),
    [
        (timedelta(minutes=1), PriceCacheReadPolicy.FRESH_ONLY, True),
        (timedelta(minutes=6), PriceCacheReadPolicy.FRESH_ONLY, False),
        (timedelta(minutes=9), PriceCacheReadPolicy.FRESH_ONLY, False),
        (timedelta(minutes=1), PriceCacheReadPolicy.ALLOW_STALE, True),
        (timedelta(minutes=6), PriceCacheReadPolicy.ALLOW_STALE, True),
        (timedelta(minutes=9), PriceCacheReadPolicy.ALLOW_STALE, False),
        (timedelta(minutes=1), PriceCacheReadPolicy.ALLOW_STALE_GRACE, True),
        (timedelta(minutes=6), PriceCacheReadPolicy.ALLOW_STALE_GRACE, True),
        (timedelta(minutes=9), PriceCacheReadPolicy.ALLOW_STALE_GRACE, True),
    ],
)
def test_read_policy_matrix(
    state_offset: timedelta,
    read_policy: PriceCacheReadPolicy,
    hit: bool,
) -> None:
    clock = ManualClock(BASE_TIME + state_offset)
    cache = InMemoryPriceCache(clock=clock)
    snapshot = _snapshot()
    _run(cache.put(snapshot))

    result = _run(cache.get(snapshot.key, read_policy=read_policy))

    assert result.hit is hit
    assert (result.snapshot is not None) is hit
    assert result.policy_blocked is not hit
    assert result.needs_refresh is (state_offset >= timedelta(minutes=5))


def test_default_read_policy_is_fresh_only() -> None:
    clock = ManualClock(BASE_TIME + timedelta(minutes=6))
    cache = InMemoryPriceCache(clock=clock)
    snapshot = _snapshot()
    _run(cache.put(snapshot))

    result = _run(cache.get(snapshot.key))

    assert result.state == PriceCacheState.STALE
    assert result.hit is False
    assert result.snapshot is None
    assert result.policy_blocked is True


def test_allow_stale_policy_blocks_grace_without_payload() -> None:
    cache = InMemoryPriceCache(clock=ManualClock(BASE_TIME + timedelta(minutes=9)))
    snapshot = _snapshot()
    _run(cache.put(snapshot))

    result = _run(
        cache.get(snapshot.key, read_policy=PriceCacheReadPolicy.ALLOW_STALE)
    )

    assert result.state == PriceCacheState.STALE_GRACE
    assert result.hit is False
    assert result.snapshot is None
    assert result.policy_blocked is True


def test_missing_key_returns_plain_miss() -> None:
    result = _run(InMemoryPriceCache(clock=ManualClock()).get(_key()))

    assert result.hit is False
    assert result.state is None
    assert result.snapshot is None
    assert result.age is None
    assert result.needs_refresh is False
    assert result.policy_blocked is False
    assert result.expired is False


def test_fresh_hit_does_not_need_refresh() -> None:
    cache = InMemoryPriceCache(clock=ManualClock(BASE_TIME + timedelta(minutes=1)))
    snapshot = _snapshot()
    _run(cache.put(snapshot))

    result = _run(cache.get(snapshot.key))

    assert result.needs_refresh is False
    assert result.age == timedelta(minutes=1)
    assert result.snapshot is not None
    assert result.snapshot.observed_at == snapshot.observed_at
    assert result.snapshot.stored_at == BASE_TIME + timedelta(minutes=1)


def test_stale_and_grace_hits_need_refresh() -> None:
    for offset, policy in (
        (timedelta(minutes=6), PriceCacheReadPolicy.ALLOW_STALE),
        (timedelta(minutes=9), PriceCacheReadPolicy.ALLOW_STALE_GRACE),
    ):
        cache = InMemoryPriceCache(clock=ManualClock(BASE_TIME + offset))
        snapshot = _snapshot()
        _run(cache.put(snapshot))

        result = _run(cache.get(snapshot.key, read_policy=policy))

        assert result.hit is True
        assert result.needs_refresh is True


def test_expired_lookup_deletes_entry_without_returning_payload() -> None:
    clock = ManualClock(BASE_TIME + timedelta(minutes=10))
    cache = InMemoryPriceCache(clock=clock)
    snapshot = _snapshot()
    _run(cache.put(snapshot))

    expired = _run(cache.get(snapshot.key, read_policy=PriceCacheReadPolicy.ALLOW_STALE_GRACE))
    missing = _run(cache.get(snapshot.key))

    assert expired.state == PriceCacheState.EXPIRED
    assert expired.expired is True
    assert expired.hit is False
    assert expired.snapshot is None
    assert missing.hit is False
    assert missing.state is None
    assert missing.snapshot is None
    assert missing.expired is False


def test_put_uses_cache_clock_as_authoritative_stored_at() -> None:
    clock = ManualClock(BASE_TIME + timedelta(minutes=2))
    cache = InMemoryPriceCache(clock=clock)
    snapshot = _snapshot(stored_at=BASE_TIME + timedelta(minutes=1))

    assert _run(cache.put(snapshot)) == PriceCacheWriteResult.CREATED
    lookup = _run(cache.get(snapshot.key))

    assert lookup.snapshot is not None
    assert lookup.snapshot.stored_at == clock.now
    assert snapshot.stored_at == BASE_TIME + timedelta(minutes=1)


def test_put_rejects_future_observation_even_with_future_declared_storage() -> None:
    clock = ManualClock(BASE_TIME)
    cache = InMemoryPriceCache(clock=clock)
    snapshot = _snapshot(
        observed_at=BASE_TIME + timedelta(minutes=1),
        stored_at=BASE_TIME + timedelta(minutes=2),
    )

    with pytest.raises(ValueError, match="later than cache storage time"):
        _run(cache.put(snapshot))

    assert _run(cache.get(snapshot.key)).state is None


def test_lookup_age_is_never_negative() -> None:
    clock = ManualClock(BASE_TIME)
    cache = InMemoryPriceCache(clock=clock)
    future = _snapshot(
        observed_at=BASE_TIME + timedelta(microseconds=1),
        stored_at=BASE_TIME + timedelta(microseconds=1),
    )

    with pytest.raises(ValueError, match="later than cache storage time"):
        _run(cache.put(future))

    valid = _snapshot(observed_at=BASE_TIME, stored_at=BASE_TIME)
    _run(cache.put(valid))
    lookup = _run(cache.get(valid.key))

    assert lookup.age == timedelta(0)
    assert lookup.age >= timedelta(0)


def test_lookup_rejects_clock_rollback_instead_of_returning_negative_age() -> None:
    clock = ManualClock(BASE_TIME)
    cache = InMemoryPriceCache(clock=clock)
    snapshot = _snapshot()
    _run(cache.put(snapshot))
    clock.set(BASE_TIME - timedelta(microseconds=1))

    with pytest.raises(ValueError, match="clock cannot be earlier"):
        _run(cache.get(snapshot.key))


def test_new_key_is_created() -> None:
    cache = InMemoryPriceCache(clock=ManualClock())

    result = _run(cache.put(_snapshot()))

    assert result == PriceCacheWriteResult.CREATED


def test_newer_observation_replaces_existing_entry() -> None:
    cache = InMemoryPriceCache(clock=ManualClock(BASE_TIME + timedelta(minutes=2)))
    original = _snapshot(stored_at=BASE_TIME + timedelta(minutes=1))
    newer = _snapshot(
        observed_at=BASE_TIME + timedelta(minutes=1),
        stored_at=BASE_TIME + timedelta(minutes=2),
        candidates=(_candidate(sell_price="130.00"),),
    )
    _run(cache.put(original))

    result = _run(cache.put(newer))
    lookup = _run(cache.get(newer.key))

    assert result == PriceCacheWriteResult.REPLACED
    assert lookup.snapshot is not None
    assert lookup.snapshot.observed_at == newer.observed_at
    assert lookup.snapshot.candidates == newer.candidates
    assert lookup.snapshot.stored_at == BASE_TIME + timedelta(minutes=2)


def test_older_observation_cannot_replace_newer_entry() -> None:
    cache = InMemoryPriceCache(clock=ManualClock(BASE_TIME + timedelta(minutes=2)))
    newer = _snapshot(
        observed_at=BASE_TIME + timedelta(minutes=1),
        stored_at=BASE_TIME + timedelta(minutes=2),
        candidates=(_candidate(sell_price="130.00"),),
    )
    older = _snapshot(
        observed_at=BASE_TIME,
        stored_at=BASE_TIME + timedelta(minutes=2),
        candidates=(_candidate(sell_price="1.00"),),
    )
    _run(cache.put(newer))

    result = _run(cache.put(older))
    lookup = _run(cache.get(newer.key))

    assert result == PriceCacheWriteResult.IGNORED_OLDER
    assert lookup.snapshot is not None
    assert lookup.snapshot.observed_at == newer.observed_at
    assert lookup.snapshot.candidates == newer.candidates
    assert lookup.snapshot.stored_at == BASE_TIME + timedelta(minutes=2)


def test_equal_observation_is_stable_and_keeps_existing_entry() -> None:
    cache = InMemoryPriceCache(clock=ManualClock(BASE_TIME + timedelta(minutes=1)))
    original = _snapshot(
        stored_at=BASE_TIME + timedelta(seconds=1),
        candidates=(_candidate(sell_price="100.00"),),
    )
    equal = _snapshot(
        stored_at=BASE_TIME + timedelta(minutes=1),
        candidates=(_candidate(sell_price="999.00"),),
    )
    _run(cache.put(original))

    result = _run(cache.put(equal))
    lookup = _run(cache.get(original.key))

    assert result == PriceCacheWriteResult.UNCHANGED_EQUAL
    assert lookup.snapshot is not None
    assert lookup.snapshot.candidates == original.candidates
    assert lookup.snapshot.stored_at == BASE_TIME + timedelta(minutes=1)


def test_later_stored_at_does_not_refresh_or_override_equal_observation() -> None:
    clock = ManualClock(BASE_TIME + timedelta(minutes=6))
    cache = InMemoryPriceCache(clock=clock)
    original = _snapshot(stored_at=BASE_TIME)
    rewritten = _snapshot(stored_at=BASE_TIME + timedelta(minutes=6))
    _run(cache.put(original))
    _run(cache.put(rewritten))

    result = _run(cache.get(original.key, read_policy=PriceCacheReadPolicy.ALLOW_STALE))

    assert result.state == PriceCacheState.STALE
    assert result.age == timedelta(minutes=6)
    assert result.snapshot is not None
    assert result.snapshot.candidates == original.candidates
    assert result.snapshot.stored_at == BASE_TIME + timedelta(minutes=6)


def test_different_keys_do_not_overwrite_each_other() -> None:
    cache = InMemoryPriceCache(clock=ManualClock())
    keys = [
        _key("item-a"),
        _key("item-b"),
        _key("item-a", source="other-provider"),
        PriceCacheKey(
            market_hash_name="item-a",
            snapshot_type="price_average",
        ),
    ]
    for index, key in enumerate(keys):
        result = _run(
            cache.put(
                _snapshot(
                    key=key,
                    candidates=(_candidate(sell_price=str(index + 1)),),
                )
            )
        )
        assert result == PriceCacheWriteResult.CREATED

    prices = [
        _run(cache.get(key)).snapshot.candidates[0].sell_price_cny  # type: ignore[union-attr]
        for key in keys
    ]
    assert prices == [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]


def test_delete_removes_only_requested_key() -> None:
    cache = InMemoryPriceCache(clock=ManualClock())
    first = _snapshot(key=_key("first"))
    second = _snapshot(key=_key("second"))
    _run(cache.put(first))
    _run(cache.put(second))

    assert _run(cache.delete(first.key)) is True
    assert _run(cache.delete(first.key)) is False
    assert _run(cache.get(first.key)).hit is False
    assert _run(cache.get(second.key)).hit is True


def test_clear_empties_only_current_instance() -> None:
    first_cache = InMemoryPriceCache(clock=ManualClock())
    second_cache = InMemoryPriceCache(clock=ManualClock())
    snapshot = _snapshot()
    _run(first_cache.put(snapshot))
    _run(second_cache.put(snapshot))

    _run(first_cache.clear())

    assert _run(first_cache.get(snapshot.key)).hit is False
    assert _run(second_cache.get(snapshot.key)).hit is True


def test_purge_expired_removes_only_expired_entries() -> None:
    clock = ManualClock(BASE_TIME + timedelta(minutes=10))
    cache = InMemoryPriceCache(clock=clock)
    expired = _snapshot(key=_key("expired"))
    fresh = _snapshot(
        key=_key("fresh"),
        observed_at=BASE_TIME + timedelta(minutes=9),
        stored_at=BASE_TIME + timedelta(minutes=9),
    )
    _run(cache.put(expired))
    _run(cache.put(fresh))

    removed = _run(cache.purge_expired())

    assert removed == 1
    assert _run(cache.get(expired.key)).state is None
    assert _run(cache.get(fresh.key)).hit is True


def test_snapshot_copies_mutable_candidate_sequence_on_construction() -> None:
    original = [_candidate(sell_price="100")]
    snapshot = _snapshot(candidates=tuple(original))

    original.append(_candidate(sell_price="200"))

    assert len(snapshot.candidates) == 1


def test_models_are_deeply_immutable_for_core_payload() -> None:
    candidate = _candidate()
    snapshot = _snapshot(candidates=(candidate,))

    with pytest.raises(FrozenInstanceError):
        candidate.sell_count = 999  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        snapshot.candidates = ()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        snapshot.candidates.append(candidate)  # type: ignore[attr-defined]


def test_serializable_dump_is_a_detached_copy() -> None:
    snapshot = _snapshot()
    dumped = snapshot.to_serializable()
    candidate_data = dumped["candidates"]
    assert isinstance(candidate_data, list)
    assert isinstance(candidate_data[0], dict)

    candidate_data[0]["sell_price_cny"] = "0"

    assert snapshot.candidates[0].sell_price_cny == Decimal("123.4500")


def test_concurrent_writes_always_keep_newest_observation() -> None:
    cache = InMemoryPriceCache(clock=ManualClock(BASE_TIME + timedelta(minutes=10)))
    snapshots = [
        _snapshot(
            observed_at=BASE_TIME + timedelta(minutes=index),
            stored_at=BASE_TIME + timedelta(minutes=10),
            candidates=(_candidate(sell_price=str(index)),),
        )
        for index in range(10)
    ]

    async def write_all() -> None:
        await asyncio.gather(*(cache.put(snapshot) for snapshot in reversed(snapshots)))

    _run(write_all())
    result = _run(cache.get(snapshots[-1].key))

    assert result.snapshot is not None
    assert result.snapshot.observed_at == snapshots[-1].observed_at
    assert result.snapshot.candidates == snapshots[-1].candidates
    assert result.snapshot.stored_at == BASE_TIME + timedelta(minutes=10)


def test_concurrent_get_and_put_do_not_mutate_dictionary_unsafely() -> None:
    cache = InMemoryPriceCache(clock=ManualClock(BASE_TIME + timedelta(minutes=50)))
    keys = [_key(f"item-{index}") for index in range(50)]

    async def exercise() -> list[object]:
        operations = []
        for index, key in enumerate(keys):
            snapshot = _snapshot(
                key=key,
                observed_at=BASE_TIME + timedelta(minutes=index),
                stored_at=BASE_TIME + timedelta(minutes=50),
            )
            operations.extend((cache.put(snapshot), cache.get(key), cache.delete(key)))
        return await asyncio.gather(*operations)

    results = _run(exercise())

    assert len(results) == 150


def test_two_cache_instances_do_not_share_state() -> None:
    first = InMemoryPriceCache(clock=ManualClock())
    second = InMemoryPriceCache(clock=ManualClock())
    snapshot = _snapshot()

    _run(first.put(snapshot))

    assert _run(first.get(snapshot.key)).hit is True
    assert _run(second.get(snapshot.key)).hit is False


@pytest.mark.parametrize(
    "field",
    ["market_hash_name", "game", "currency", "source", "snapshot_type"],
)
def test_key_rejects_identity_field_empty_after_strip(field: str) -> None:
    values = {
        "market_hash_name": "item",
        "game": "cs2",
        "currency": "CNY",
        "source": "steamdt",
        "snapshot_type": "platform_prices",
    }
    values[field] = "   "

    with pytest.raises(ValueError, match=field):
        PriceCacheKey(**values)


def test_key_rejects_bool_schema_version() -> None:
    with pytest.raises(ValueError, match="schema_version must be 1"):
        PriceCacheKey(market_hash_name="item", schema_version=True)


def test_candidate_rejects_invalid_platform_and_platform_item_id_types() -> None:
    with pytest.raises(TypeError, match="platform must be a string"):
        NormalizedPriceCandidate(platform=123)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="platform_item_id must be a string"):
        NormalizedPriceCandidate(
            platform="buff",
            platform_item_id=123,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("field", ["sell_price_cny", "bidding_price_cny"])
def test_candidate_rejects_negative_price(field: str) -> None:
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        NormalizedPriceCandidate(platform="buff", **{field: Decimal("-0.01")})


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
@pytest.mark.parametrize("field", ["sell_price_cny", "bidding_price_cny"])
def test_candidate_rejects_non_finite_price(field: str, value: Decimal) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        NormalizedPriceCandidate(platform="buff", **{field: value})


@pytest.mark.parametrize("field", ["sell_price_cny", "bidding_price_cny"])
def test_candidate_rejects_non_decimal_price(field: str) -> None:
    with pytest.raises(TypeError, match="must be a Decimal"):
        NormalizedPriceCandidate(platform="buff", **{field: 1.25})


@pytest.mark.parametrize("field", ["sell_count", "bidding_count"])
def test_candidate_rejects_negative_count(field: str) -> None:
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        NormalizedPriceCandidate(platform="buff", **{field: -1})


@pytest.mark.parametrize("value", [True, False, 1.5, "1"])
@pytest.mark.parametrize("field", ["sell_count", "bidding_count"])
def test_candidate_rejects_ambiguous_count_types(field: str, value: object) -> None:
    with pytest.raises(TypeError, match="must be an int"):
        NormalizedPriceCandidate(platform="buff", **{field: value})


def test_duplicate_candidates_preserve_provider_response_order() -> None:
    candidate = _candidate()
    snapshot = _snapshot(candidates=(candidate, candidate))

    assert snapshot.candidates == (candidate, candidate)
    assert snapshot.to_serializable()["candidates"] == [
        candidate.to_serializable(),
        candidate.to_serializable(),
    ]


def test_candidate_rejects_mutable_or_ambiguous_source_update_time() -> None:
    with pytest.raises(TypeError, match="source_update_time"):
        NormalizedPriceCandidate(
            platform="buff",
            source_update_time=["mutable"],  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="source_update_time"):
        NormalizedPriceCandidate(platform="buff", source_update_time=True)


def test_key_rejects_currency_that_conflicts_with_cny_payload_fields() -> None:
    with pytest.raises(ValueError, match="currency must be CNY"):
        PriceCacheKey(market_hash_name="item", currency="USD")


def test_key_normalizes_identity_whitespace_before_hashing() -> None:
    normalized = _key()
    padded = PriceCacheKey(
        market_hash_name=f"  {normalized.market_hash_name}  ",
        game=" cs2 ",
        currency=" CNY ",
        source=" steamdt ",
        snapshot_type=" platform_prices ",
    )

    assert padded == normalized
    assert padded.serialize() == normalized.serialize()
    assert padded.stable_digest() == normalized.stable_digest()


def test_key_serialization_is_stable_and_process_hash_independent() -> None:
    key = _key()

    first = key.serialize()
    second = PriceCacheKey(
        schema_version=PRICE_CACHE_SCHEMA_VERSION,
        snapshot_type="platform_prices",
        source="steamdt",
        currency="CNY",
        game="cs2",
        market_hash_name="AK-47 | Redline (Field-Tested)",
    ).serialize()

    assert first == second
    assert key.stable_digest() == _key().stable_digest()
    assert json.loads(first)["market_hash_name"] == key.market_hash_name


def test_unsupported_schema_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="schema_version must be 1"):
        PriceCacheKey(market_hash_name="item", schema_version=2)


def test_snapshot_schema_version_is_stable_and_matches_key() -> None:
    snapshot = _snapshot()

    assert PRICE_CACHE_SCHEMA_VERSION == 1
    assert snapshot.schema_version == 1
    assert snapshot.key.schema_version == 1
    assert snapshot.to_serializable()["schema_version"] == 1


def test_snapshot_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValueError, match="schema_version must be 1"):
        CachedPriceSnapshot(
            key=_key(),
            candidates=(_candidate(),),
            observed_at=BASE_TIME,
            stored_at=BASE_TIME,
            policy=_policy(),
            schema_version=2,
        )


def test_serialization_preserves_decimal_without_float() -> None:
    snapshot = _snapshot(
        candidates=(
            NormalizedPriceCandidate(
                platform="buff",
                sell_price_cny=Decimal("0.12345678901234567890"),
                bidding_price_cny=Decimal("0.10000000000000000001"),
            ),
        )
    )

    dumped = snapshot.to_serializable()
    encoded = json.dumps(dumped, sort_keys=True)
    candidate = dumped["candidates"]
    assert isinstance(candidate, list)
    assert isinstance(candidate[0], dict)

    assert candidate[0]["sell_price_cny"] == "0.12345678901234567890"
    assert candidate[0]["bidding_price_cny"] == "0.10000000000000000001"
    assert "0.12345678901234567890" in encoded


def test_utc_datetime_serialization_round_trip() -> None:
    snapshot = _snapshot(stored_at=BASE_TIME + timedelta(microseconds=123456))
    dumped = snapshot.to_serializable()

    observed = datetime.fromisoformat(str(dumped["observed_at"]).replace("Z", "+00:00"))
    stored = datetime.fromisoformat(str(dumped["stored_at"]).replace("Z", "+00:00"))

    assert observed == snapshot.observed_at
    assert stored == snapshot.stored_at
    assert observed.tzinfo == UTC


def test_core_snapshot_contains_no_secret_or_runtime_objects() -> None:
    snapshot = _snapshot()
    dumped = snapshot.to_serializable()
    encoded = json.dumps(dumped, sort_keys=True)

    assert "api_key" not in encoded.lower()
    assert "authorization" not in encoded.lower()
    assert "redis_url" not in encoded.lower()
    assert "httpx" not in encoded.lower()
    assert "callback" not in encoded.lower()
    assert all(not asyncio.iscoroutine(value) for value in dumped.values())


def test_clock_must_return_aware_datetime() -> None:
    cache = InMemoryPriceCache(clock=lambda: datetime(2026, 7, 16, 12))

    with pytest.raises(ValueError, match="clock result must be timezone-aware"):
        _run(cache.get(_key()))
