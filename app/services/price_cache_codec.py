from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from app.services.price_cache import (
    PRICE_CACHE_SCHEMA_VERSION,
    CachedPriceSnapshot,
    NormalizedPriceCandidate,
    PriceCacheKey,
    PriceCachePolicy,
)

REDIS_PRICE_CACHE_CODEC_VERSION = 1

type RedisValue = bytes | str
type RedisHashRecord = Mapping[RedisValue, RedisValue] | Sequence[RedisValue]

_RECORD_FIELDS = frozenset(
    {
        "codec_version",
        "schema_version",
        "key_json",
        "key_digest",
        "observed_seconds",
        "observed_microseconds",
        "stored_seconds",
        "stored_microseconds",
        "fresh_ttl_microseconds",
        "stale_ttl_microseconds",
        "stale_grace_ttl_microseconds",
        "fresh_until_seconds",
        "fresh_until_microseconds",
        "stale_until_seconds",
        "stale_until_microseconds",
        "expires_seconds",
        "expires_microseconds",
        "payload_json",
    }
)
_KEY_FIELDS = frozenset(
    {
        "currency",
        "game",
        "market_hash_name",
        "schema_version",
        "snapshot_type",
        "source",
    }
)
_PAYLOAD_FIELDS = frozenset({"candidates", "key", "schema_version"})
_CANDIDATE_FIELDS = frozenset(
    {
        "bidding_count",
        "bidding_price_cny",
        "platform",
        "platform_item_id",
        "sell_count",
        "sell_price_cny",
        "source_update_time",
    }
)
_CANONICAL_NONNEGATIVE_INTEGER = re.compile(r"0|[1-9][0-9]*")


class PriceCacheCodecError(ValueError):
    """Stored Redis price-cache data violates the versioned codec contract."""

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"invalid Redis price-cache record field {field}: {reason}")


@dataclass(frozen=True)
class RedisPriceCacheWriteRecord:
    """Caller-independent fields passed to the atomic Redis put script."""

    fields: tuple[tuple[str, str], ...]
    observed_seconds: int
    observed_microseconds: int
    expires_seconds: int
    expires_microseconds: int

    def value_for(self, name: str) -> str:
        for field_name, value in self.fields:
            if field_name == name:
                return value
        raise KeyError(name)


class RedisPriceCacheRecordCodec:
    """Strict deterministic codec for version-1 Redis price-cache hash records."""

    def encode_for_put(self, snapshot: CachedPriceSnapshot) -> RedisPriceCacheWriteRecord:
        observed_seconds, observed_microseconds = _datetime_parts(snapshot.observed_at)
        fresh_until_seconds, fresh_until_microseconds = _datetime_parts(
            snapshot.fresh_until
        )
        stale_until_seconds, stale_until_microseconds = _datetime_parts(
            snapshot.stale_until
        )
        expires_seconds, expires_microseconds = _datetime_parts(snapshot.expires_at)
        key_json = snapshot.key.serialize()
        payload_json = _canonical_json(
            {
                "candidates": [
                    candidate.to_serializable() for candidate in snapshot.candidates
                ],
                "key": _load_json_object(key_json, field="key_json"),
                "schema_version": snapshot.schema_version,
            }
        )
        fields = (
            ("codec_version", str(REDIS_PRICE_CACHE_CODEC_VERSION)),
            ("schema_version", str(snapshot.schema_version)),
            ("key_json", key_json),
            ("key_digest", snapshot.key.stable_digest()),
            ("observed_seconds", str(observed_seconds)),
            ("observed_microseconds", str(observed_microseconds)),
            (
                "fresh_ttl_microseconds",
                str(_timedelta_microseconds(snapshot.policy.fresh_ttl)),
            ),
            (
                "stale_ttl_microseconds",
                str(_timedelta_microseconds(snapshot.policy.stale_ttl)),
            ),
            (
                "stale_grace_ttl_microseconds",
                str(_timedelta_microseconds(snapshot.policy.stale_grace_ttl)),
            ),
            ("fresh_until_seconds", str(fresh_until_seconds)),
            ("fresh_until_microseconds", str(fresh_until_microseconds)),
            ("stale_until_seconds", str(stale_until_seconds)),
            ("stale_until_microseconds", str(stale_until_microseconds)),
            ("expires_seconds", str(expires_seconds)),
            ("expires_microseconds", str(expires_microseconds)),
            ("payload_json", payload_json),
        )
        return RedisPriceCacheWriteRecord(
            fields=fields,
            observed_seconds=observed_seconds,
            observed_microseconds=observed_microseconds,
            expires_seconds=expires_seconds,
            expires_microseconds=expires_microseconds,
        )

    def decode(
        self,
        expected_key: PriceCacheKey,
        record: RedisHashRecord,
    ) -> CachedPriceSnapshot:
        fields = _decode_hash_record(record)
        actual_fields = frozenset(fields)
        if actual_fields != _RECORD_FIELDS:
            missing = sorted(_RECORD_FIELDS - actual_fields)
            unexpected = sorted(actual_fields - _RECORD_FIELDS)
            if missing:
                raise PriceCacheCodecError("record", f"missing fields: {', '.join(missing)}")
            raise PriceCacheCodecError(
                "record",
                f"unexpected fields: {', '.join(unexpected)}",
            )

        codec_version = _parse_canonical_int(fields["codec_version"], "codec_version")
        if codec_version != REDIS_PRICE_CACHE_CODEC_VERSION:
            raise PriceCacheCodecError("codec_version", "unsupported version")
        schema_version = _parse_canonical_int(fields["schema_version"], "schema_version")
        if schema_version != PRICE_CACHE_SCHEMA_VERSION:
            raise PriceCacheCodecError("schema_version", "unsupported version")

        key = _decode_key(fields["key_json"])
        if key != expected_key:
            raise PriceCacheCodecError("key_json", "does not match expected cache key")
        if fields["key_json"] != key.serialize():
            raise PriceCacheCodecError("key_json", "is not canonical")
        if fields["key_digest"] != expected_key.stable_digest():
            raise PriceCacheCodecError("key_digest", "does not match expected cache key")

        observed_at = _datetime_from_parts(
            fields["observed_seconds"],
            fields["observed_microseconds"],
            field="observed_at",
        )
        stored_at = _datetime_from_parts(
            fields["stored_seconds"],
            fields["stored_microseconds"],
            field="stored_at",
        )
        fresh_microseconds = _parse_canonical_int(
            fields["fresh_ttl_microseconds"],
            "fresh_ttl_microseconds",
        )
        stale_microseconds = _parse_canonical_int(
            fields["stale_ttl_microseconds"],
            "stale_ttl_microseconds",
        )
        grace_microseconds = _parse_canonical_int(
            fields["stale_grace_ttl_microseconds"],
            "stale_grace_ttl_microseconds",
        )
        if fresh_microseconds <= 0:
            raise PriceCacheCodecError("fresh_ttl_microseconds", "must be greater than 0")
        policy = _build_policy(
            fresh_microseconds,
            stale_microseconds,
            grace_microseconds,
        )
        expected_fresh_until = observed_at + policy.fresh_ttl
        expected_stale_until = expected_fresh_until + policy.stale_ttl
        expected_expires = expected_stale_until + policy.stale_grace_ttl
        fresh_until = _datetime_from_parts(
            fields["fresh_until_seconds"],
            fields["fresh_until_microseconds"],
            field="fresh_until",
        )
        stale_until = _datetime_from_parts(
            fields["stale_until_seconds"],
            fields["stale_until_microseconds"],
            field="stale_until",
        )
        expires_at = _datetime_from_parts(
            fields["expires_seconds"],
            fields["expires_microseconds"],
            field="expires_at",
        )
        if fresh_until != expected_fresh_until:
            raise PriceCacheCodecError(
                "fresh_until",
                "does not match observation and policy",
            )
        if stale_until != expected_stale_until:
            raise PriceCacheCodecError(
                "stale_until",
                "does not match observation and policy",
            )
        if expires_at != expected_expires:
            raise PriceCacheCodecError("expires_at", "does not match observation and policy")

        payload = _load_json_object(fields["payload_json"], field="payload_json")
        _require_exact_fields(payload, _PAYLOAD_FIELDS, field="payload_json")
        payload_schema = _require_exact_json_int(
            payload["schema_version"],
            field="payload_json.schema_version",
        )
        if payload_schema != schema_version:
            raise PriceCacheCodecError(
                "payload_json.schema_version",
                "does not match metadata schema version",
            )
        payload_key = _decode_key_object(payload["key"], field="payload_json.key")
        if payload_key != expected_key:
            raise PriceCacheCodecError("payload_json.key", "does not match expected cache key")
        candidates = _decode_candidates(payload["candidates"])
        canonical_payload = _canonical_json(
            {
                "candidates": [candidate.to_serializable() for candidate in candidates],
                "key": _load_json_object(expected_key.serialize(), field="key_json"),
                "schema_version": payload_schema,
            }
        )
        if fields["payload_json"] != canonical_payload:
            raise PriceCacheCodecError("payload_json", "is not canonical")

        try:
            return CachedPriceSnapshot(
                key=key,
                candidates=candidates,
                observed_at=observed_at,
                stored_at=stored_at,
                policy=policy,
                schema_version=schema_version,
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise PriceCacheCodecError("snapshot", type(exc).__name__) from exc


def _decode_hash_record(record: RedisHashRecord) -> dict[str, str]:
    if isinstance(record, Mapping):
        items = list(record.items())
    elif isinstance(record, Sequence) and not isinstance(record, (str, bytes, bytearray)):
        values = list(record)
        if len(values) % 2 != 0:
            raise PriceCacheCodecError("record", "expected field/value pairs")
        items = list(zip(values[::2], values[1::2], strict=True))
    else:
        raise PriceCacheCodecError("record", "expected hash mapping or field/value sequence")

    result: dict[str, str] = {}
    for raw_name, raw_value in items:
        name = _decode_redis_text(raw_name, field="record field name")
        value = _decode_redis_text(raw_value, field=name)
        if name in result:
            raise PriceCacheCodecError(name, "duplicate field")
        result[name] = value
    return result


def _decode_redis_text(value: object, *, field: str) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PriceCacheCodecError(field, "invalid UTF-8") from exc
    if isinstance(value, str):
        return value
    raise PriceCacheCodecError(field, "must be bytes or string")


def _load_json_object(value: str, *, field: str) -> dict[str, object]:
    try:
        decoded = json.loads(value, object_pairs_hook=_reject_duplicate_json_keys)
    except (json.JSONDecodeError, ValueError) as exc:
        raise PriceCacheCodecError(field, "malformed JSON") from exc
    if not isinstance(decoded, dict):
        raise PriceCacheCodecError(field, "must be a JSON object")
    return decoded


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _decode_key(value: str) -> PriceCacheKey:
    return _decode_key_object(_load_json_object(value, field="key_json"), field="key_json")


def _decode_key_object(value: object, *, field: str) -> PriceCacheKey:
    if not isinstance(value, dict):
        raise PriceCacheCodecError(field, "must be a JSON object")
    _require_exact_fields(value, _KEY_FIELDS, field=field)
    schema_version = _require_exact_json_int(
        value["schema_version"],
        field=f"{field}.schema_version",
    )
    try:
        return PriceCacheKey(
            market_hash_name=_require_json_string(
                value["market_hash_name"],
                field=f"{field}.market_hash_name",
            ),
            game=_require_json_string(value["game"], field=f"{field}.game"),
            currency=_require_json_string(value["currency"], field=f"{field}.currency"),
            source=_require_json_string(value["source"], field=f"{field}.source"),
            snapshot_type=_require_json_string(
                value["snapshot_type"],
                field=f"{field}.snapshot_type",
            ),
            schema_version=schema_version,
        )
    except (TypeError, ValueError) as exc:
        raise PriceCacheCodecError(field, type(exc).__name__) from exc


def _decode_candidates(value: object) -> tuple[NormalizedPriceCandidate, ...]:
    if not isinstance(value, list):
        raise PriceCacheCodecError("payload_json.candidates", "must be a JSON array")
    candidates: list[NormalizedPriceCandidate] = []
    for index, raw_candidate in enumerate(value):
        field = f"payload_json.candidates[{index}]"
        if not isinstance(raw_candidate, dict):
            raise PriceCacheCodecError(field, "must be a JSON object")
        _require_exact_fields(raw_candidate, _CANDIDATE_FIELDS, field=field)
        source_update_time = raw_candidate["source_update_time"]
        if isinstance(source_update_time, bool) or not isinstance(
            source_update_time,
            (int, str, type(None)),
        ):
            raise PriceCacheCodecError(f"{field}.source_update_time", "invalid type")
        try:
            candidates.append(
                NormalizedPriceCandidate(
                    platform=_require_json_string(
                        raw_candidate["platform"],
                        field=f"{field}.platform",
                    ),
                    platform_item_id=_optional_json_string(
                        raw_candidate["platform_item_id"],
                        field=f"{field}.platform_item_id",
                    ),
                    sell_price_cny=_optional_decimal_string(
                        raw_candidate["sell_price_cny"],
                        field=f"{field}.sell_price_cny",
                    ),
                    sell_count=_optional_exact_json_int(
                        raw_candidate["sell_count"],
                        field=f"{field}.sell_count",
                    ),
                    bidding_price_cny=_optional_decimal_string(
                        raw_candidate["bidding_price_cny"],
                        field=f"{field}.bidding_price_cny",
                    ),
                    bidding_count=_optional_exact_json_int(
                        raw_candidate["bidding_count"],
                        field=f"{field}.bidding_count",
                    ),
                    source_update_time=source_update_time,
                )
            )
        except (TypeError, ValueError, InvalidOperation) as exc:
            raise PriceCacheCodecError(field, type(exc).__name__) from exc
    return tuple(candidates)


def _optional_decimal_string(value: object, *, field: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PriceCacheCodecError(field, "must be a decimal string or null")
    try:
        decimal_value = Decimal(value)
    except InvalidOperation as exc:
        raise PriceCacheCodecError(field, "malformed Decimal") from exc
    if not decimal_value.is_finite():
        raise PriceCacheCodecError(field, "must be finite")
    if decimal_value < 0:
        raise PriceCacheCodecError(field, "must be nonnegative")
    if str(decimal_value) != value:
        raise PriceCacheCodecError(field, "is not canonical")
    return decimal_value


def _optional_exact_json_int(value: object, *, field: str) -> int | None:
    if value is None:
        return None
    result = _require_exact_json_int(value, field=field)
    if result < 0:
        raise PriceCacheCodecError(field, "must be nonnegative")
    return result


def _require_exact_json_int(value: object, *, field: str) -> int:
    if type(value) is not int:
        raise PriceCacheCodecError(field, "must be an integer")
    return value


def _require_json_string(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise PriceCacheCodecError(field, "must be a string")
    return value


def _optional_json_string(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _require_json_string(value, field=field)


def _require_exact_fields(
    value: Mapping[str, object],
    expected: frozenset[str],
    *,
    field: str,
) -> None:
    actual = frozenset(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        raise PriceCacheCodecError(field, f"missing fields: {', '.join(missing)}")
    raise PriceCacheCodecError(field, f"unexpected fields: {', '.join(unexpected)}")


def _parse_canonical_int(value: str, field: str) -> int:
    if not _CANONICAL_NONNEGATIVE_INTEGER.fullmatch(value):
        raise PriceCacheCodecError(field, "must be a canonical nonnegative integer")
    return int(value)


def _datetime_parts(value: datetime) -> tuple[int, int]:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    normalized = value.astimezone(UTC)
    delta = normalized - epoch
    seconds = delta.days * 86_400 + delta.seconds
    if seconds < 0:
        raise ValueError("price cache timestamps must be on or after Unix epoch")
    return seconds, delta.microseconds


def _datetime_from_parts(seconds_value: str, microseconds_value: str, *, field: str) -> datetime:
    seconds = _parse_canonical_int(seconds_value, f"{field}.seconds")
    microseconds = _parse_canonical_int(
        microseconds_value,
        f"{field}.microseconds",
    )
    if microseconds > 999_999:
        raise PriceCacheCodecError(f"{field}.microseconds", "must be in 0..999999")
    try:
        return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
            seconds=seconds,
            microseconds=microseconds,
        )
    except OverflowError as exc:
        raise PriceCacheCodecError(field, "timestamp out of range") from exc


def _build_policy(fresh: int, stale: int, grace: int) -> PriceCachePolicy:
    try:
        return PriceCachePolicy(
            fresh_ttl=timedelta(microseconds=fresh),
            stale_ttl=timedelta(microseconds=stale),
            stale_grace_ttl=timedelta(microseconds=grace),
        )
    except (OverflowError, ValueError) as exc:
        raise PriceCacheCodecError("policy", type(exc).__name__) from exc


def _timedelta_microseconds(value: timedelta) -> int:
    return value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
