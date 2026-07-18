import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest
from redis.exceptions import ConnectionError, ResponseError

from app.services.price_cache import (
    PRICE_CACHE_SCHEMA_VERSION,
    CachedPriceSnapshot,
    NormalizedPriceCandidate,
    PriceCacheKey,
    PriceCachePolicy,
    PriceCacheReadPolicy,
    PriceCacheState,
    PriceCacheWriteResult,
)
from app.services.price_cache_codec import (
    REDIS_PRICE_CACHE_CODEC_VERSION,
    PriceCacheCodecError,
    RedisPriceCacheRecordCodec,
)
from app.services.redis_price_cache import (
    DEFAULT_REDIS_PRICE_CACHE_NAMESPACE,
    REDIS_PRICE_CACHE_GET_SCRIPT,
    REDIS_PRICE_CACHE_PHYSICAL_CLEANUP_GRACE_MILLISECONDS,
    REDIS_PRICE_CACHE_PURGE_SCRIPT,
    REDIS_PRICE_CACHE_PUT_SCRIPT,
    PriceCacheBackendError,
    RedisPriceCache,
)

BASE_TIME = datetime(2026, 7, 17, 12, 0, 0, 123456, tzinfo=UTC)


def _parts(value: datetime) -> tuple[int, int]:
    delta = value - datetime(1970, 1, 1, tzinfo=UTC)
    return delta.days * 86_400 + delta.seconds, delta.microseconds


def _key(
    name: str = "AK-47 | Redline (Field-Tested)",
    *,
    source: str = "steamdt",
) -> PriceCacheKey:
    return PriceCacheKey(market_hash_name=name, source=source)


def _candidate(
    platform: str = "buff",
    *,
    sell_price: str = "123.4500",
    source_update_time: int | str | None = 1_752_765_600,
) -> NormalizedPriceCandidate:
    return NormalizedPriceCandidate(
        platform=platform,
        platform_item_id="item-1",
        sell_price_cny=Decimal(sell_price),
        sell_count=20,
        bidding_price_cny=Decimal("120.0100"),
        bidding_count=9,
        source_update_time=source_update_time,
    )


def _snapshot(
    *,
    key: PriceCacheKey | None = None,
    observed_at: datetime = BASE_TIME,
    stored_at: datetime | None = None,
    candidates: tuple[NormalizedPriceCandidate, ...] | None = None,
    fresh: timedelta = timedelta(minutes=5, microseconds=7),
    stale: timedelta = timedelta(minutes=3, microseconds=11),
    grace: timedelta = timedelta(minutes=2, microseconds=13),
) -> CachedPriceSnapshot:
    return CachedPriceSnapshot(
        key=key or _key(),
        candidates=candidates or (_candidate(),),
        observed_at=observed_at,
        stored_at=stored_at or observed_at,
        policy=PriceCachePolicy(
            fresh_ttl=fresh,
            stale_ttl=stale,
            stale_grace_ttl=grace,
        ),
    )


def _stored_record(
    snapshot: CachedPriceSnapshot,
    *,
    stored_at: datetime,
    codec: RedisPriceCacheRecordCodec | None = None,
) -> dict[str, str]:
    codec = codec or RedisPriceCacheRecordCodec()
    record = dict(codec.encode_for_put(snapshot).fields)
    stored_seconds, stored_microseconds = _parts(stored_at)
    record["stored_seconds"] = str(stored_seconds)
    record["stored_microseconds"] = str(stored_microseconds)
    return record


def _flat(record: dict[str, str]) -> list[str]:
    values: list[str] = []
    for name, value in record.items():
        values.extend((name, value))
    return values


def _run(coroutine):  # type: ignore[no-untyped-def]
    return asyncio.run(coroutine)


class ScriptedRedis:
    def __init__(self) -> None:
        self.eval_responses: list[object] = []
        self.scan_responses: list[object] = []
        self.delete_responses: list[object] = []
        self.eval_calls: list[tuple[str, int, tuple[object, ...]]] = []
        self.scan_calls: list[tuple[object, str | None, int | None]] = []
        self.delete_calls: list[tuple[str | bytes, ...]] = []
        self.closed_count = 0
        self.ping_count = 0

    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> object:
        self.eval_calls.append((script, numkeys, keys_and_args))
        response = self.eval_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def scan(
        self,
        cursor: int = 0,
        *,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[bytes | str]]:
        self.scan_calls.append((cursor, match, count))
        response = self.scan_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return cast(tuple[int, list[bytes | str]], response)

    async def delete(self, *names: str | bytes) -> object:
        self.delete_calls.append(names)
        response = self.delete_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def aclose(self) -> None:
        self.closed_count += 1

    async def ping(self) -> bool:
        self.ping_count += 1
        return True


@pytest.mark.parametrize(
    "namespace",
    ["steamdt-price-cache-v1", "cache.prod_1", "tenant:cache"],
)
def test_default_and_explicit_namespace_are_valid(namespace: str) -> None:
    redis = ScriptedRedis()
    cache = RedisPriceCache(redis, namespace=namespace)

    assert cache.namespace == namespace
    assert redis.eval_calls == []
    assert redis.scan_calls == []
    assert redis.ping_count == 0


@pytest.mark.parametrize(
    "namespace",
    ["", "   ", "bad\nname", "bad\x00name", "bad*name", "bad?name", "bad[name", "bad{name"],
)
def test_invalid_namespace_is_rejected(namespace: str) -> None:
    with pytest.raises(ValueError, match="namespace"):
        RedisPriceCache(ScriptedRedis(), namespace=namespace)


def test_non_string_namespace_is_rejected() -> None:
    with pytest.raises(TypeError, match="namespace must be a string"):
        RedisPriceCache(ScriptedRedis(), namespace=123)  # type: ignore[arg-type]


def test_redis_key_is_stable_opaque_and_namespace_scoped() -> None:
    cache = RedisPriceCache(ScriptedRedis())
    padded = PriceCacheKey(market_hash_name="  AK-47 | Redline (Field-Tested)  ")
    different = _key("M4A4 | Asiimov (Field-Tested)")

    first = cache.key_for(_key())

    assert first == cache.key_for(padded)
    assert first != cache.key_for(different)
    assert first.startswith(f"{{{DEFAULT_REDIS_PRICE_CACHE_NAMESPACE}:")
    assert first.endswith("}:snapshot")
    assert "AK-47" not in first
    assert "Redline" not in first
    assert "steamdt-rate-limit-v1" not in first
    assert "secret" not in first.lower()


def test_codec_round_trip_preserves_all_values_and_candidate_order() -> None:
    codec = RedisPriceCacheRecordCodec()
    east = datetime(2026, 7, 17, 20, 0, 0, 123456, tzinfo=UTC)
    snapshot = _snapshot(
        candidates=(
            _candidate("buff", sell_price="0.12345678901234567890"),
            NormalizedPriceCandidate(
                platform="steam",
                platform_item_id=None,
                sell_price_cny=None,
                sell_count=None,
                bidding_price_cny=Decimal("0.10000000000000000001"),
                bidding_count=0,
                source_update_time="2026-07-17T12:00:00Z",
            ),
        ),
    )
    record = _stored_record(snapshot, stored_at=east, codec=codec)

    decoded = codec.decode(snapshot.key, record)
    decoded_from_bytes = codec.decode(
        snapshot.key,
        {name.encode(): value.encode() for name, value in record.items()},
    )

    assert decoded == decoded_from_bytes
    assert decoded.candidates == snapshot.candidates
    assert decoded.observed_at == BASE_TIME
    assert decoded.stored_at == east
    assert decoded.policy == snapshot.policy
    assert decoded.candidates[0].sell_price_cny == Decimal("0.12345678901234567890")


def test_codec_encode_is_deterministic_and_omits_caller_stored_at() -> None:
    codec = RedisPriceCacheRecordCodec()
    first = _snapshot(stored_at=BASE_TIME)
    second = _snapshot(stored_at=BASE_TIME + timedelta(hours=1))

    first_record = codec.encode_for_put(first)
    second_record = codec.encode_for_put(second)

    assert first_record == second_record
    assert "stored_seconds" not in dict(first_record.fields)
    assert "stored_microseconds" not in dict(first_record.fields)
    payload = first_record.value_for("payload_json")
    assert payload == json.dumps(
        json.loads(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert "123.4500" in payload


def test_codec_preserves_datetime_and_duration_microseconds() -> None:
    codec = RedisPriceCacheRecordCodec()
    snapshot = _snapshot()
    record = _stored_record(
        snapshot,
        stored_at=BASE_TIME + timedelta(microseconds=654321),
    )

    decoded = codec.decode(snapshot.key, record)

    assert decoded.observed_at.microsecond == 123456
    assert decoded.stored_at.microsecond == 777777
    assert decoded.policy.fresh_ttl == timedelta(minutes=5, microseconds=7)
    assert decoded.policy.stale_ttl == timedelta(minutes=3, microseconds=11)
    assert decoded.policy.stale_grace_ttl == timedelta(minutes=2, microseconds=13)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda record: record.pop("payload_json"), "missing fields"),
        (lambda record: record.__setitem__("extra", "value"), "unexpected fields"),
        (lambda record: record.__setitem__("codec_version", "2"), "unsupported version"),
        (lambda record: record.__setitem__("schema_version", "2"), "unsupported version"),
        (lambda record: record.__setitem__("observed_seconds", "1.5"), "canonical"),
        (lambda record: record.__setitem__("observed_microseconds", "1000000"), "0..999999"),
        (lambda record: record.__setitem__("fresh_ttl_microseconds", "0"), "greater than 0"),
        (lambda record: record.__setitem__("stale_ttl_microseconds", "-1"), "canonical"),
        (lambda record: record.__setitem__("expires_seconds", "0"), "does not match"),
        (lambda record: record.__setitem__("payload_json", "not-json"), "malformed JSON"),
    ],
)
def test_codec_rejects_corrupt_metadata(mutation, match: str) -> None:  # type: ignore[no-untyped-def]
    snapshot = _snapshot()
    record = _stored_record(snapshot, stored_at=BASE_TIME)
    mutation(record)

    with pytest.raises(PriceCacheCodecError, match=match):
        RedisPriceCacheRecordCodec().decode(snapshot.key, record)


def test_codec_rejects_expected_key_and_digest_mismatch() -> None:
    snapshot = _snapshot()
    record = _stored_record(snapshot, stored_at=BASE_TIME)

    with pytest.raises(PriceCacheCodecError, match="expected cache key"):
        RedisPriceCacheRecordCodec().decode(_key("different"), record)

    record["key_digest"] = "0" * 64
    with pytest.raises(PriceCacheCodecError, match="key_digest"):
        RedisPriceCacheRecordCodec().decode(snapshot.key, record)


def test_codec_rejects_metadata_payload_version_mismatch() -> None:
    snapshot = _snapshot()
    record = _stored_record(snapshot, stored_at=BASE_TIME)
    payload = json.loads(record["payload_json"])
    payload["schema_version"] = 2
    record["payload_json"] = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    with pytest.raises(PriceCacheCodecError, match="schema_version"):
        RedisPriceCacheRecordCodec().decode(snapshot.key, record)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "invalid", "-0.01"])
def test_codec_rejects_invalid_decimal(value: str) -> None:
    snapshot = _snapshot()
    record = _stored_record(snapshot, stored_at=BASE_TIME)
    payload = json.loads(record["payload_json"])
    payload["candidates"][0]["sell_price_cny"] = value
    record["payload_json"] = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    with pytest.raises(PriceCacheCodecError, match="candidates"):
        RedisPriceCacheRecordCodec().decode(snapshot.key, record)


@pytest.mark.parametrize("value", [True, -1, 1.5, "1"])
def test_codec_rejects_invalid_count(value: object) -> None:
    snapshot = _snapshot()
    record = _stored_record(snapshot, stored_at=BASE_TIME)
    payload = json.loads(record["payload_json"])
    payload["candidates"][0]["sell_count"] = value
    record["payload_json"] = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    with pytest.raises(PriceCacheCodecError, match="candidates"):
        RedisPriceCacheRecordCodec().decode(snapshot.key, record)


def test_codec_rejects_duplicate_json_key_and_non_object_root() -> None:
    snapshot = _snapshot()
    record = _stored_record(snapshot, stored_at=BASE_TIME)
    record["payload_json"] = '{"candidates":[],"candidates":[],"key":{},"schema_version":1}'
    with pytest.raises(PriceCacheCodecError, match="malformed JSON"):
        RedisPriceCacheRecordCodec().decode(snapshot.key, record)

    record["payload_json"] = "[]"
    with pytest.raises(PriceCacheCodecError, match="JSON object"):
        RedisPriceCacheRecordCodec().decode(snapshot.key, record)


def test_codec_error_does_not_include_payload_or_secret() -> None:
    snapshot = _snapshot()
    record = _stored_record(snapshot, stored_at=BASE_TIME)
    secret = "Authorization: Bearer super-secret-token"
    record["payload_json"] = secret

    with pytest.raises(PriceCacheCodecError) as exc_info:
        RedisPriceCacheRecordCodec().decode(snapshot.key, record)

    assert secret not in str(exc_info.value)
    assert "super-secret-token" not in str(exc_info.value)


def _put_response(
    tag: str,
    snapshot: CachedPriceSnapshot,
    *,
    stored_at: datetime,
) -> list[object]:
    seconds, microseconds = _parts(stored_at)
    return [tag, seconds, microseconds, *_flat(_stored_record(snapshot, stored_at=stored_at))]


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("created", PriceCacheWriteResult.CREATED),
        ("replaced", PriceCacheWriteResult.REPLACED),
        ("ignored_older", PriceCacheWriteResult.IGNORED_OLDER),
        ("unchanged_equal", PriceCacheWriteResult.UNCHANGED_EQUAL),
    ],
)
def test_put_maps_all_write_results(tag: str, expected: PriceCacheWriteResult) -> None:
    redis = ScriptedRedis()
    snapshot = _snapshot()
    redis.eval_responses.append(_put_response(tag, snapshot, stored_at=BASE_TIME))
    cache = RedisPriceCache(redis)

    assert _run(cache.put(snapshot)) == expected
    assert len(redis.eval_calls) == 1
    script, numkeys, args = redis.eval_calls[0]
    assert script == REDIS_PRICE_CACHE_PUT_SCRIPT
    assert numkeys == 1
    assert args[0] == cache.key_for(snapshot.key)
    assert "AK-47" not in str(args[0])
    assert args[1:5] == (*_parts(snapshot.observed_at), *_parts(snapshot.expires_at))
    assert args[5] == REDIS_PRICE_CACHE_PHYSICAL_CLEANUP_GRACE_MILLISECONDS
    assert "stored_seconds" not in args
    assert "stored_microseconds" not in args


def test_put_uses_redis_stored_at_not_caller_value() -> None:
    redis = ScriptedRedis()
    snapshot = _snapshot(stored_at=BASE_TIME + timedelta(hours=1))
    authoritative = BASE_TIME + timedelta(seconds=2)
    stored_snapshot = _snapshot(stored_at=authoritative)
    redis.eval_responses.append(_put_response("created", stored_snapshot, stored_at=authoritative))

    assert _run(RedisPriceCache(redis).put(snapshot)) == PriceCacheWriteResult.CREATED


def test_put_rejects_future_observation_from_redis_time() -> None:
    redis = ScriptedRedis()
    now_seconds, now_microseconds = _parts(BASE_TIME)
    redis.eval_responses.append(["future", now_seconds, now_microseconds])

    with pytest.raises(ValueError, match="Redis server time"):
        _run(RedisPriceCache(redis).put(_snapshot()))


def test_put_corruption_and_malformed_response_fail_closed() -> None:
    redis = ScriptedRedis()
    seconds, microseconds = _parts(BASE_TIME)
    redis.eval_responses.extend(
        [
            ["corrupt", seconds, microseconds, "wrong_type"],
            ["unknown", seconds, microseconds],
        ]
    )
    cache = RedisPriceCache(redis)

    with pytest.raises(PriceCacheCodecError):
        _run(cache.put(_snapshot()))
    with pytest.raises(PriceCacheBackendError):
        _run(cache.put(_snapshot()))


def test_put_eval_error_becomes_safe_backend_error_without_fallback() -> None:
    redis = ScriptedRedis()
    redis.eval_responses.append(
        ConnectionError("redis://user:password@redis/0 Authorization: Bearer secret-token")
    )

    with pytest.raises(PriceCacheBackendError) as exc_info:
        _run(RedisPriceCache(redis).put(_snapshot()))

    text = str(exc_info.value)
    assert "password" not in text
    assert "secret-token" not in text
    assert "ConnectionError" in text
    assert redis.closed_count == 0


def _get_response(
    snapshot: CachedPriceSnapshot,
    *,
    now: datetime,
    state: PriceCacheState,
) -> list[object]:
    seconds, microseconds = _parts(now)
    return [
        "record",
        seconds,
        microseconds,
        state.value,
        *_flat(_stored_record(snapshot, stored_at=snapshot.stored_at)),
    ]


def test_eval_list_bytes_and_string_responses_parse_like_redis_py() -> None:
    snapshot = _snapshot()
    stored = _stored_record(snapshot, stored_at=BASE_TIME)
    seconds, microseconds = _parts(BASE_TIME)
    flat_bytes = [value.encode() for value in _flat(stored)]

    redis = ScriptedRedis()
    redis.eval_responses.extend(
        [
            [b"created", seconds, microseconds, *flat_bytes],
            ["record", seconds, microseconds, "fresh", *_flat(stored)],
            [b"deleted", 1],
        ]
    )
    cache = RedisPriceCache(redis)
    redis.scan_responses.append((0, [cache.key_for(snapshot.key).encode()]))

    assert _run(cache.put(snapshot)) == PriceCacheWriteResult.CREATED
    assert _run(cache.get(snapshot.key)).state == PriceCacheState.FRESH
    assert _run(cache.purge_expired()) == 1


def test_redis_time_integer_and_text_replies_are_supported() -> None:
    redis = ScriptedRedis()
    seconds, microseconds = _parts(BASE_TIME)
    redis.eval_responses.extend(
        [
            ["missing", str(seconds), str(microseconds)],
            [b"missing", str(seconds).encode(), str(microseconds).encode()],
        ]
    )
    cache = RedisPriceCache(redis)

    assert _run(cache.get(_key())).hit is False
    assert _run(cache.get(_key())).hit is False


def test_redis_time_integer_replies_reject_bool() -> None:
    redis = ScriptedRedis()
    redis.eval_responses.append(["missing", True, 0])

    with pytest.raises(PriceCacheBackendError, match="nonnegative integer"):
        _run(RedisPriceCache(redis).get(_key()))


def test_equal_and_older_flat_hgetall_bytes_records_are_decoded() -> None:
    snapshot = _snapshot()
    record = _stored_record(snapshot, stored_at=BASE_TIME)
    seconds, microseconds = _parts(BASE_TIME)
    flat_bytes = [value.encode() for value in _flat(record)]
    redis = ScriptedRedis()
    redis.eval_responses.extend(
        [
            [b"unchanged_equal", seconds, microseconds, *flat_bytes],
            [b"ignored_older", seconds, microseconds, *flat_bytes],
        ]
    )
    cache = RedisPriceCache(redis)

    assert _run(cache.put(snapshot)) == PriceCacheWriteResult.UNCHANGED_EQUAL
    assert _run(cache.put(snapshot)) == PriceCacheWriteResult.IGNORED_OLDER


def test_put_rejects_extra_elements_for_fixed_length_tags() -> None:
    seconds, microseconds = _parts(BASE_TIME)
    redis = ScriptedRedis()
    redis.eval_responses.extend(
        [
            ["future", seconds, microseconds, "extra"],
            ["invalid_args", seconds, microseconds, "extra"],
            ["corrupt", seconds, microseconds, "wrong_type", "extra"],
        ]
    )
    cache = RedisPriceCache(redis)

    for _ in range(3):
        with pytest.raises(PriceCacheBackendError, match="malformed"):
            _run(cache.put(_snapshot()))


def test_get_missing_uses_redis_time_and_returns_plain_miss() -> None:
    redis = ScriptedRedis()
    redis.eval_responses.append(["missing", *_parts(BASE_TIME)])
    cache = RedisPriceCache(redis)

    lookup = _run(cache.get(_key()))

    assert lookup.hit is False
    assert lookup.state is None
    assert lookup.snapshot is None
    assert lookup.expired is False
    assert redis.eval_calls[0][0] == REDIS_PRICE_CACHE_GET_SCRIPT
    assert len(redis.eval_calls) == 1


@pytest.mark.parametrize(
    ("offset", "state", "policy", "hit", "blocked"),
    [
        (timedelta(minutes=1), PriceCacheState.FRESH, PriceCacheReadPolicy.FRESH_ONLY, True, False),
        (timedelta(minutes=6), PriceCacheState.STALE, PriceCacheReadPolicy.FRESH_ONLY, False, True),
        (
            timedelta(minutes=6),
            PriceCacheState.STALE,
            PriceCacheReadPolicy.ALLOW_STALE,
            True,
            False,
        ),
        (
            timedelta(minutes=9),
            PriceCacheState.STALE_GRACE,
            PriceCacheReadPolicy.ALLOW_STALE,
            False,
            True,
        ),
        (
            timedelta(minutes=9),
            PriceCacheState.STALE_GRACE,
            PriceCacheReadPolicy.ALLOW_STALE_GRACE,
            True,
            False,
        ),
    ],
)
def test_get_read_policy_matches_d1(
    offset: timedelta,
    state: PriceCacheState,
    policy: PriceCacheReadPolicy,
    hit: bool,
    blocked: bool,
) -> None:
    snapshot = _snapshot(stored_at=BASE_TIME)
    redis = ScriptedRedis()
    redis.eval_responses.append(_get_response(snapshot, now=BASE_TIME + offset, state=state))

    lookup = _run(RedisPriceCache(redis).get(snapshot.key, read_policy=policy))

    assert lookup.hit is hit
    assert (lookup.snapshot is not None) is hit
    assert lookup.policy_blocked is blocked
    assert lookup.needs_refresh is (state != PriceCacheState.FRESH)
    assert lookup.age == offset


def test_get_expired_never_returns_snapshot() -> None:
    snapshot = _snapshot(stored_at=BASE_TIME)
    redis = ScriptedRedis()
    now = snapshot.expires_at
    redis.eval_responses.append(_get_response(snapshot, now=now, state=PriceCacheState.EXPIRED))

    lookup = _run(
        RedisPriceCache(redis).get(
            snapshot.key,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE_GRACE,
        )
    )

    assert lookup.hit is False
    assert lookup.state == PriceCacheState.EXPIRED
    assert lookup.snapshot is None
    assert lookup.expired is True


def test_get_state_mismatch_is_backend_error() -> None:
    snapshot = _snapshot(stored_at=BASE_TIME)
    redis = ScriptedRedis()
    redis.eval_responses.append(
        _get_response(snapshot, now=BASE_TIME + timedelta(minutes=1), state=PriceCacheState.STALE)
    )

    with pytest.raises(PriceCacheBackendError, match="state mismatch"):
        _run(RedisPriceCache(redis).get(snapshot.key))


def test_get_corrupt_payload_is_codec_error_not_miss() -> None:
    snapshot = _snapshot(stored_at=BASE_TIME)
    record = _stored_record(snapshot, stored_at=BASE_TIME)
    record["payload_json"] = "not-json"
    redis = ScriptedRedis()
    redis.eval_responses.append(
        ["record", *_parts(BASE_TIME), PriceCacheState.FRESH.value, *_flat(record)]
    )

    with pytest.raises(PriceCacheCodecError):
        _run(RedisPriceCache(redis).get(snapshot.key))


def test_get_eval_failure_is_backend_error_and_does_not_close_client() -> None:
    redis = ScriptedRedis()
    redis.eval_responses.append(ResponseError("bad response with secret-token"))

    with pytest.raises(PriceCacheBackendError) as exc_info:
        _run(RedisPriceCache(redis).get(_key()))

    assert "secret-token" not in str(exc_info.value)
    assert redis.closed_count == 0


def test_delete_uses_one_exact_key_and_strict_count() -> None:
    redis = ScriptedRedis()
    redis.delete_responses.extend([1, 0])
    cache = RedisPriceCache(redis)
    key = _key()

    assert _run(cache.delete(key)) is True
    assert _run(cache.delete(key)) is False
    assert redis.delete_calls == [(cache.key_for(key),), (cache.key_for(key),)]


@pytest.mark.parametrize("response", [True, -1, 2, "1", b"1", 1.0, []])
def test_delete_rejects_malformed_count(response: object) -> None:
    redis = ScriptedRedis()
    redis.delete_responses.append(response)

    with pytest.raises(PriceCacheBackendError, match="delete count"):
        _run(RedisPriceCache(redis).delete(_key()))


def test_clear_scans_multiple_pages_and_deletes_only_exact_namespace_keys() -> None:
    redis = ScriptedRedis()
    cache = RedisPriceCache(redis, scan_count=2)
    first = cache.key_for(_key("first"))
    second = cache.key_for(_key("second"))
    other = RedisPriceCache(redis, namespace="other-cache").key_for(_key("first"))
    redis.scan_responses.extend(
        [
            (1, [first.encode(), other.encode(), b"malformed"]),
            (0, [second]),
        ]
    )
    redis.delete_responses.extend([1, 1])

    _run(cache.clear())

    assert redis.scan_calls == [
        (0, cache.scan_pattern(), 2),
        (1, cache.scan_pattern(), 2),
    ]
    assert redis.delete_calls == [(first.encode(),), (second,)]
    assert all(other not in str(call) for call in redis.delete_calls)
    assert redis.closed_count == 0


def test_clear_accepts_compatibility_text_cursors_after_normalizing_to_int() -> None:
    redis = ScriptedRedis()
    cache = RedisPriceCache(redis)
    redis.scan_responses.extend([(b"2", []), ("0", [])])

    _run(cache.clear())

    assert redis.scan_calls == [
        (0, cache.scan_pattern(), cache.scan_count),
        (2, cache.scan_pattern(), cache.scan_count),
    ]


@pytest.mark.parametrize("cursor", [True, False, -1, b"-1", "-1", 1.5, b"bad", " 1"])
def test_clear_rejects_invalid_scan_cursor(cursor: object) -> None:
    redis = ScriptedRedis()
    redis.scan_responses.append((cursor, []))

    with pytest.raises(PriceCacheBackendError, match="SCAN cursor"):
        _run(RedisPriceCache(redis).clear())


@pytest.mark.parametrize(
    "response",
    [None, (), (0,), (0, [], "extra"), (0, b"single-key"), (0, [object()])],
)
def test_clear_rejects_malformed_scan_page(response: object) -> None:
    redis = ScriptedRedis()
    redis.scan_responses.append(response)

    with pytest.raises(PriceCacheBackendError, match="SCAN"):
        _run(RedisPriceCache(redis).clear())


def test_clear_scan_or_delete_error_becomes_backend_error() -> None:
    redis = ScriptedRedis()
    redis.scan_responses.append(ConnectionError("scan failed"))
    with pytest.raises(PriceCacheBackendError):
        _run(RedisPriceCache(redis).clear())

    redis = ScriptedRedis()
    cache = RedisPriceCache(redis)
    redis.scan_responses.append((0, [cache.key_for(_key())]))
    redis.delete_responses.append(ConnectionError("delete failed"))
    with pytest.raises(PriceCacheBackendError):
        _run(cache.clear())


def test_purge_expired_sums_only_actual_atomic_deletes() -> None:
    redis = ScriptedRedis()
    cache = RedisPriceCache(redis)
    keys = [cache.key_for(_key(name)) for name in ("expired", "live", "gone")]
    redis.scan_responses.append((0, keys))
    redis.eval_responses.extend(
        [
            ["deleted", 1],
            ["live", 0],
            ["missing", 0],
        ]
    )

    assert _run(cache.purge_expired()) == 1
    assert [call[0] for call in redis.eval_calls] == [
        REDIS_PRICE_CACHE_PURGE_SCRIPT,
        REDIS_PRICE_CACHE_PURGE_SCRIPT,
        REDIS_PRICE_CACHE_PURGE_SCRIPT,
    ]


def test_purge_scans_multiple_pages_with_redis_py_integer_cursors() -> None:
    redis = ScriptedRedis()
    cache = RedisPriceCache(redis, scan_count=1)
    first = cache.key_for(_key("expired-first"))
    second = cache.key_for(_key("expired-second"))
    redis.scan_responses.extend([(7, [first]), (0, [second])])
    redis.eval_responses.extend([["deleted", 1], ["deleted", 1]])

    assert _run(cache.purge_expired()) == 2
    assert redis.scan_calls == [
        (0, cache.scan_pattern(), 1),
        (7, cache.scan_pattern(), 1),
    ]


def test_purge_corruption_and_malformed_count_fail_closed() -> None:
    redis = ScriptedRedis()
    cache = RedisPriceCache(redis)
    redis.scan_responses.append((0, [cache.key_for(_key())]))
    redis.eval_responses.append(["corrupt", 0, "wrong_type"])
    with pytest.raises(PriceCacheCodecError):
        _run(cache.purge_expired())

    redis = ScriptedRedis()
    cache = RedisPriceCache(redis)
    redis.scan_responses.append((0, [cache.key_for(_key())]))
    redis.eval_responses.append(["live", 1])
    with pytest.raises(PriceCacheBackendError):
        _run(cache.purge_expired())


def test_cache_never_closes_or_pings_injected_redis_client() -> None:
    redis = ScriptedRedis()
    cache = RedisPriceCache(redis)
    redis.eval_responses.append(["missing", *_parts(BASE_TIME)])
    redis.delete_responses.append(0)
    redis.scan_responses.extend([(0, []), (0, [])])

    _run(cache.get(_key()))
    _run(cache.delete(_key()))
    _run(cache.clear())
    _run(cache.purge_expired())

    assert redis.closed_count == 0
    assert redis.ping_count == 0


def test_lua_scripts_have_atomic_server_time_and_expiry_contracts() -> None:
    scripts = "\n".join(
        [
            REDIS_PRICE_CACHE_PUT_SCRIPT,
            REDIS_PRICE_CACHE_GET_SCRIPT,
            REDIS_PRICE_CACHE_PURGE_SCRIPT,
        ]
    )

    assert REDIS_PRICE_CACHE_PUT_SCRIPT.count('redis.call("TIME")') == 1
    assert 'redis.call("TYPE", key)["ok"]' in REDIS_PRICE_CACHE_PUT_SCRIPT
    assert 'redis.call("PEXPIREAT", key, physical_expires_at_ms)' in (
        REDIS_PRICE_CACHE_PUT_SCRIPT
    )
    assert 'redis.call("HSET"' in REDIS_PRICE_CACHE_PUT_SCRIPT
    assert "math.ceil(expires_microseconds / 1000)" in REDIS_PRICE_CACHE_PUT_SCRIPT
    assert "cleanup_grace_ms" in REDIS_PRICE_CACHE_PUT_SCRIPT
    assert 'redis.call("EXPIRE"' not in REDIS_PRICE_CACHE_PUT_SCRIPT
    assert 'redis.call("PEXPIRE"' not in REDIS_PRICE_CACHE_PUT_SCRIPT
    assert "existing_seconds > observed_seconds" in REDIS_PRICE_CACHE_PUT_SCRIPT
    assert "existing_microseconds > observed_microseconds" in REDIS_PRICE_CACHE_PUT_SCRIPT
    assert 'return {"ignored_older"' in REDIS_PRICE_CACHE_PUT_SCRIPT
    assert 'return {"unchanged_equal"' in REDIS_PRICE_CACHE_PUT_SCRIPT
    assert REDIS_PRICE_CACHE_GET_SCRIPT.count('redis.call("TIME")') == 1
    assert 'redis.call("TYPE", key)["ok"]' in REDIS_PRICE_CACHE_GET_SCRIPT
    assert 'redis.call("HGETALL", key)' in REDIS_PRICE_CACHE_GET_SCRIPT
    assert 'redis.call("DEL", key)' in REDIS_PRICE_CACHE_GET_SCRIPT
    assert REDIS_PRICE_CACHE_PURGE_SCRIPT.count('redis.call("TIME")') == 1
    assert 'redis.call("TYPE", key)["ok"]' in REDIS_PRICE_CACHE_PURGE_SCRIPT
    assert "HGETALL" not in REDIS_PRICE_CACHE_PURGE_SCRIPT
    assert "redis.call(\"GET\"" not in scripts
    assert "cjson" not in scripts.lower()
    assert "KEYS *" not in scripts
    assert "FLUSHDB" not in scripts.upper()
    assert "FLUSHALL" not in scripts.upper()
    assert "Authorization" not in scripts
    assert "api_key" not in scripts.lower()


def test_codec_versions_are_explicit_and_stable() -> None:
    assert REDIS_PRICE_CACHE_CODEC_VERSION == 1
    assert PRICE_CACHE_SCHEMA_VERSION == 1
