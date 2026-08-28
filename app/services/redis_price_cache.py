from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.services.price_cache import (
    CachedPriceSnapshot,
    PriceCacheKey,
    PriceCacheLookup,
    PriceCacheReadPolicy,
    PriceCacheState,
    PriceCacheWriteResult,
    evaluate_price_cache_lookup,
)
from app.services.price_cache_codec import (
    PriceCacheCodecError,
    RedisPriceCacheRecordCodec,
)

DEFAULT_REDIS_PRICE_CACHE_NAMESPACE = "steamdt-price-cache-v1"
REDIS_PRICE_CACHE_PHYSICAL_CLEANUP_GRACE_MILLISECONDS = 5_000
REDIS_PRICE_CACHE_SCAN_COUNT = 100

PUT_CREATED = "created"
PUT_REPLACED = "replaced"
PUT_IGNORED_OLDER = "ignored_older"
PUT_UNCHANGED_EQUAL = "unchanged_equal"
PUT_FUTURE = "future"
PUT_CORRUPT = "corrupt"

REDIS_PRICE_CACHE_PUT_SCRIPT = r'''
local key = KEYS[1]
local function parse_uint(value)
    if value == false or
       (value ~= "0" and string.match(value, "^[1-9][0-9]*$") == nil) then
        return nil
    end
    return tonumber(value)
end
local observed_seconds = parse_uint(ARGV[1])
local observed_microseconds = parse_uint(ARGV[2])
local expires_seconds = parse_uint(ARGV[3])
local expires_microseconds = parse_uint(ARGV[4])
local cleanup_grace_ms = parse_uint(ARGV[5])
local field_count = parse_uint(ARGV[6])
if observed_seconds == nil or observed_microseconds == nil or
   expires_seconds == nil or expires_microseconds == nil or
   cleanup_grace_ms == nil or field_count == nil or field_count == 0 or
   #ARGV ~= 6 + (field_count * 2) or
   observed_microseconds > 999999 or expires_microseconds > 999999 then
    return {"invalid_args", 0, 0}
end

local redis_time = redis.call("TIME")
local now_seconds = tonumber(redis_time[1])
local now_microseconds = tonumber(redis_time[2])

local incoming = {}
for index = 0, field_count - 1 do
    local field = ARGV[7 + (index * 2)]
    if incoming[field] ~= nil then
        return {"invalid_args", now_seconds, now_microseconds}
    end
    incoming[field] = ARGV[8 + (index * 2)]
end

if observed_seconds > now_seconds or
   (observed_seconds == now_seconds and observed_microseconds > now_microseconds) then
    return {"future", now_seconds, now_microseconds}
end

local existing_type = redis.call("TYPE", key)["ok"]
local result = "created"
if existing_type ~= "none" then
    if existing_type ~= "hash" then
        return {"corrupt", now_seconds, now_microseconds, "wrong_type"}
    end
    local existing = redis.call("HGETALL", key)
    if #existing ~= field_count * 2 + 4 then
        return {"corrupt", now_seconds, now_microseconds, "unexpected_fields"}
    end
    local existing_fields = {}
    for index = 1, #existing, 2 do
        existing_fields[existing[index]] = true
    end
    for field, _value in pairs(incoming) do
        if existing_fields[field] ~= true then
            return {"corrupt", now_seconds, now_microseconds, "missing_field"}
        end
    end
    if existing_fields["stored_seconds"] ~= true or
       existing_fields["stored_microseconds"] ~= true then
        return {"corrupt", now_seconds, now_microseconds, "missing_storage_time"}
    end
    local existing_seconds_text = redis.call("HGET", key, "observed_seconds")
    local existing_microseconds_text = redis.call("HGET", key, "observed_microseconds")
    local existing_seconds = parse_uint(existing_seconds_text)
    local existing_microseconds = parse_uint(existing_microseconds_text)
    if existing_seconds == nil or existing_microseconds == nil or
       existing_microseconds > 999999 then
        return {"corrupt", now_seconds, now_microseconds, "missing_observation"}
    end
    if existing_seconds > observed_seconds or
       (existing_seconds == observed_seconds and
        existing_microseconds > observed_microseconds) then
        return {"ignored_older", now_seconds, now_microseconds, unpack(existing)}
    end
    if existing_seconds == observed_seconds and
       existing_microseconds == observed_microseconds then
        return {"unchanged_equal", now_seconds, now_microseconds, unpack(existing)}
    end
    result = "replaced"
end

local expiry_microseconds_ms = math.ceil(expires_microseconds / 1000)
local max_safe_integer = 9007199254740991
if expires_seconds > math.floor(
    (max_safe_integer - cleanup_grace_ms - expiry_microseconds_ms) / 1000
) then
    return {"invalid_args", now_seconds, now_microseconds}
end
local physical_expires_at_ms =
    (expires_seconds * 1000) + expiry_microseconds_ms + cleanup_grace_ms

redis.call("DEL", key)
local write_args = {}
for index = 0, field_count - 1 do
    table.insert(write_args, ARGV[7 + (index * 2)])
    table.insert(write_args, ARGV[8 + (index * 2)])
end
table.insert(write_args, "stored_seconds")
table.insert(write_args, tostring(now_seconds))
table.insert(write_args, "stored_microseconds")
table.insert(write_args, tostring(now_microseconds))
redis.call("HSET", key, unpack(write_args))
local stored = redis.call("HGETALL", key)
redis.call("PEXPIREAT", key, physical_expires_at_ms)
return {result, now_seconds, now_microseconds, unpack(stored)}
'''

REDIS_PRICE_CACHE_GET_SCRIPT = r'''
local key = KEYS[1]
local function parse_uint(value)
    if value == false or
       (value ~= "0" and string.match(value, "^[1-9][0-9]*$") == nil) then
        return nil
    end
    return tonumber(value)
end
local redis_time = redis.call("TIME")
local now_seconds = tonumber(redis_time[1])
local now_microseconds = tonumber(redis_time[2])

local existing_type = redis.call("TYPE", key)["ok"]
if existing_type == "none" then
    return {"missing", now_seconds, now_microseconds}
end
if existing_type ~= "hash" then
    return {"corrupt", now_seconds, now_microseconds, "wrong_type"}
end

local record = redis.call("HGETALL", key)
local observed_seconds = parse_uint(redis.call("HGET", key, "observed_seconds"))
local observed_microseconds = parse_uint(redis.call("HGET", key, "observed_microseconds"))
local fresh_until_seconds = parse_uint(redis.call("HGET", key, "fresh_until_seconds"))
local fresh_until_microseconds = parse_uint(redis.call("HGET", key, "fresh_until_microseconds"))
local stale_until_seconds = parse_uint(redis.call("HGET", key, "stale_until_seconds"))
local stale_until_microseconds = parse_uint(redis.call("HGET", key, "stale_until_microseconds"))
local expires_seconds = parse_uint(redis.call("HGET", key, "expires_seconds"))
local expires_microseconds = parse_uint(redis.call("HGET", key, "expires_microseconds"))
if observed_seconds == nil or observed_microseconds == nil or
   fresh_until_seconds == nil or fresh_until_microseconds == nil or
   stale_until_seconds == nil or stale_until_microseconds == nil or
   expires_seconds == nil or expires_microseconds == nil or
   observed_microseconds > 999999 or fresh_until_microseconds > 999999 or
   stale_until_microseconds > 999999 or expires_microseconds > 999999 then
    return {"corrupt", now_seconds, now_microseconds, "malformed_time_metadata"}
end

if now_seconds < observed_seconds or
   (now_seconds == observed_seconds and now_microseconds < observed_microseconds) then
    return {"corrupt", now_seconds, now_microseconds, "clock_before_observation"}
end

local state = "fresh"
local function at_or_after(left_seconds, left_microseconds, right_seconds, right_microseconds)
    return left_seconds > right_seconds or
        (left_seconds == right_seconds and left_microseconds >= right_microseconds)
end
if at_or_after(now_seconds, now_microseconds, expires_seconds, expires_microseconds) then
    state = "expired"
    redis.call("DEL", key)
elseif at_or_after(
    now_seconds,
    now_microseconds,
    stale_until_seconds,
    stale_until_microseconds
) then
    state = "stale_grace"
elseif at_or_after(
    now_seconds,
    now_microseconds,
    fresh_until_seconds,
    fresh_until_microseconds
) then
    state = "stale"
end
return {"record", now_seconds, now_microseconds, state, unpack(record)}
'''

REDIS_PRICE_CACHE_PURGE_SCRIPT = r'''
local key = KEYS[1]
local function parse_uint(value)
    if value == false or
       (value ~= "0" and string.match(value, "^[1-9][0-9]*$") == nil) then
        return nil
    end
    return tonumber(value)
end
local redis_time = redis.call("TIME")
local now_seconds = tonumber(redis_time[1])
local now_microseconds = tonumber(redis_time[2])

local existing_type = redis.call("TYPE", key)["ok"]
if existing_type == "none" then
    return {"missing", 0}
end
if existing_type ~= "hash" then
    return {"corrupt", 0, "wrong_type"}
end
local required_fields = {
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
    "payload_json"
}
if redis.call("HLEN", key) ~= #required_fields then
    return {"corrupt", 0, "unexpected_fields"}
end
for _, field in ipairs(required_fields) do
    if redis.call("HEXISTS", key, field) ~= 1 then
        return {"corrupt", 0, "missing_field"}
    end
end
if redis.call("HGET", key, "codec_version") ~= "1" or
   redis.call("HGET", key, "schema_version") ~= "1" then
    return {"corrupt", 0, "unsupported_version"}
end
local key_digest = redis.call("HGET", key, "key_digest")
if string.len(key_digest) ~= 64 or
   string.match(key_digest, "^[0-9a-f]+$") == nil then
    return {"corrupt", 0, "malformed_digest"}
end
local observed_seconds = parse_uint(redis.call("HGET", key, "observed_seconds"))
local observed_microseconds = parse_uint(redis.call("HGET", key, "observed_microseconds"))
local stored_seconds = parse_uint(redis.call("HGET", key, "stored_seconds"))
local stored_microseconds = parse_uint(redis.call("HGET", key, "stored_microseconds"))
local fresh_ttl = parse_uint(redis.call("HGET", key, "fresh_ttl_microseconds"))
local stale_ttl = parse_uint(redis.call("HGET", key, "stale_ttl_microseconds"))
local grace_ttl = parse_uint(redis.call("HGET", key, "stale_grace_ttl_microseconds"))
local fresh_until_seconds = parse_uint(redis.call("HGET", key, "fresh_until_seconds"))
local fresh_until_microseconds = parse_uint(redis.call("HGET", key, "fresh_until_microseconds"))
local stale_until_seconds = parse_uint(redis.call("HGET", key, "stale_until_seconds"))
local stale_until_microseconds = parse_uint(redis.call("HGET", key, "stale_until_microseconds"))
local expires_seconds = parse_uint(redis.call("HGET", key, "expires_seconds"))
local expires_microseconds = parse_uint(redis.call("HGET", key, "expires_microseconds"))
if observed_seconds == nil or observed_microseconds == nil or
   stored_seconds == nil or stored_microseconds == nil or
   fresh_ttl == nil or fresh_ttl == 0 or stale_ttl == nil or grace_ttl == nil or
   fresh_until_seconds == nil or fresh_until_microseconds == nil or
   stale_until_seconds == nil or stale_until_microseconds == nil or
   expires_seconds == nil or expires_microseconds == nil or
   observed_microseconds > 999999 or stored_microseconds > 999999 or
   fresh_until_microseconds > 999999 or stale_until_microseconds > 999999 or
   expires_microseconds > 999999 then
    return {"corrupt", 0, "malformed_metadata"}
end
if now_seconds > expires_seconds or
   (now_seconds == expires_seconds and now_microseconds >= expires_microseconds) then
    return {"deleted", redis.call("DEL", key)}
end
return {"live", 0}
'''


class AsyncRedisPriceCacheClient(Protocol):
    """Minimum externally owned redis-py async surface used by this cache core."""

    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> object:
        """Evaluate one atomic Lua operation."""

    async def scan(
        self,
        cursor: int = 0,
        *,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[bytes | str]]:
        """Return one standard redis-py paginated namespace scan page."""

    async def delete(self, *names: str | bytes) -> object:
        """Delete exact keys and return the number removed."""


class PriceCacheBackendError(RuntimeError):
    """Redis availability or response-contract failure; cache operations fail closed."""

    def __init__(self, operation: str, reason: str) -> None:
        self.backend = "redis"
        self.operation = operation
        self.reason = reason
        super().__init__(
            f"Redis price-cache backend failed: operation={operation}, reason={reason}"
        )


class RedisPriceCache:
    """Externally owned Redis cache using server-time atomic single-key scripts."""

    def __init__(
        self,
        redis_client: AsyncRedisPriceCacheClient,
        *,
        namespace: str = DEFAULT_REDIS_PRICE_CACHE_NAMESPACE,
        codec: RedisPriceCacheRecordCodec | None = None,
        scan_count: int = REDIS_PRICE_CACHE_SCAN_COUNT,
    ) -> None:
        self.redis_client = redis_client
        self.namespace = normalize_redis_price_cache_namespace(namespace)
        if type(scan_count) is not int or scan_count <= 0:
            raise ValueError("scan_count must be a positive integer")
        self.scan_count = scan_count
        self.codec = codec or RedisPriceCacheRecordCodec()

    def key_for(self, key: PriceCacheKey) -> str:
        digest = key.stable_digest()
        return f"{{{self.namespace}:{digest}}}:snapshot"

    def scan_pattern(self) -> str:
        return f"{{{self.namespace}:*}}:snapshot"

    async def put(self, snapshot: CachedPriceSnapshot) -> PriceCacheWriteResult:
        record = self.codec.encode_for_put(snapshot)
        args: list[object] = [
            record.observed_seconds,
            record.observed_microseconds,
            record.expires_seconds,
            record.expires_microseconds,
            REDIS_PRICE_CACHE_PHYSICAL_CLEANUP_GRACE_MILLISECONDS,
            len(record.fields),
        ]
        for field, value in record.fields:
            args.extend((field, value))
        response = await self._eval(
            "put",
            REDIS_PRICE_CACHE_PUT_SCRIPT,
            self.key_for(snapshot.key),
            *args,
        )
        values = _require_response_sequence(response, operation="put", minimum=3)
        tag = _response_text(values[0], operation="put")
        _parse_server_time(values[1:3], operation="put")
        if tag == PUT_FUTURE:
            if len(values) != 3:
                raise _backend_error("put", "malformed future response")
            raise ValueError("observed_at cannot be later than Redis server time")
        if tag == "invalid_args":
            if len(values) != 3:
                raise _backend_error("put", "malformed invalid-arguments response")
            raise _backend_error("put", "Lua rejected put arguments")
        if tag == PUT_CORRUPT:
            if len(values) != 4:
                raise _backend_error("put", "malformed corrupt response")
            raise PriceCacheCodecError("record", "stored Redis hash is corrupt")
        results = {
            PUT_CREATED: PriceCacheWriteResult.CREATED,
            PUT_REPLACED: PriceCacheWriteResult.REPLACED,
            PUT_IGNORED_OLDER: PriceCacheWriteResult.IGNORED_OLDER,
            PUT_UNCHANGED_EQUAL: PriceCacheWriteResult.UNCHANGED_EQUAL,
        }
        result = results.get(tag)
        if result is None:
            raise _backend_error("put", "unknown Lua response tag")
        if len(values) <= 3 or (len(values) - 3) % 2 != 0:
            raise _backend_error("put", "malformed stored hash response")
        stored = self.codec.decode(
            snapshot.key,
            _require_hash_values(values[3:], operation="put"),
        )
        if tag in {PUT_CREATED, PUT_REPLACED} and stored.observed_at != snapshot.observed_at:
            raise _backend_error("put", "stored observation does not match incoming observation")
        return result

    async def get(
        self,
        key: PriceCacheKey,
        *,
        read_policy: PriceCacheReadPolicy = PriceCacheReadPolicy.FRESH_ONLY,
    ) -> PriceCacheLookup:
        response = await self._eval(
            "get",
            REDIS_PRICE_CACHE_GET_SCRIPT,
            self.key_for(key),
        )
        values = _require_response_sequence(response, operation="get", minimum=3)
        tag = _response_text(values[0], operation="get")
        now = _parse_server_time(values[1:3], operation="get")
        if tag == "missing":
            if len(values) != 3:
                raise _backend_error("get", "malformed missing response")
            return PriceCacheLookup.missing(key)
        if tag == "corrupt":
            if len(values) != 4:
                raise _backend_error("get", "malformed corrupt response")
            raise PriceCacheCodecError("record", "stored Redis hash is corrupt")
        if tag != "record" or len(values) <= 4:
            raise _backend_error("get", "malformed record response")
        if (len(values) - 4) % 2 != 0:
            raise _backend_error("get", "malformed record field/value response")
        state = _parse_state(values[3])
        snapshot = self.codec.decode(
            key,
            _require_hash_values(values[4:], operation="get"),
        )
        lookup = evaluate_price_cache_lookup(
            snapshot,
            now=now,
            read_policy=read_policy,
        )
        if lookup.state != state:
            raise _backend_error("get", "Lua and Python state mismatch")
        return lookup

    async def delete(self, key: PriceCacheKey) -> bool:
        try:
            response = await self.redis_client.delete(self.key_for(key))
        except Exception as exc:
            raise _backend_error("delete", type(exc).__name__) from exc
        return _parse_delete_count(response, operation="delete") == 1

    async def clear(self) -> None:
        async for redis_key in self._scan_namespace_keys(operation="clear"):
            try:
                response = await self.redis_client.delete(redis_key)
            except Exception as exc:
                raise _backend_error("clear", type(exc).__name__) from exc
            _parse_delete_count(response, operation="clear")

    async def purge_expired(self) -> int:
        removed = 0
        async for redis_key in self._scan_namespace_keys(operation="purge_expired"):
            response = await self._eval(
                "purge_expired",
                REDIS_PRICE_CACHE_PURGE_SCRIPT,
                redis_key,
            )
            values = _require_response_sequence(
                response,
                operation="purge_expired",
                minimum=2,
            )
            tag = _response_text(values[0], operation="purge_expired")
            if tag == "corrupt":
                if len(values) != 3:
                    raise _backend_error("purge_expired", "malformed corrupt response")
                raise PriceCacheCodecError("record", "stored Redis hash is corrupt")
            if tag not in {"missing", "live", "deleted"}:
                raise _backend_error("purge_expired", "unknown Lua response tag")
            if len(values) != 2:
                raise _backend_error("purge_expired", "malformed Lua response length")
            count = _parse_delete_count(values[1], operation="purge_expired")
            if tag != "deleted" and count != 0:
                raise _backend_error("purge_expired", "non-delete response returned count")
            removed += count
        return removed

    async def _eval(
        self,
        operation: str,
        script: str,
        redis_key: str | bytes,
        *args: object,
    ) -> object:
        try:
            return await self.redis_client.eval(script, 1, redis_key, *args)
        except PriceCacheCodecError:
            raise
        except Exception as exc:
            raise _backend_error(operation, type(exc).__name__) from exc

    async def _scan_namespace_keys(
        self,
        *,
        operation: str,
    ) -> AsyncIterator[str | bytes]:
        cursor = 0
        while True:
            try:
                response = await self.redis_client.scan(
                    cursor,
                    match=self.scan_pattern(),
                    count=self.scan_count,
                )
            except Exception as exc:
                raise _backend_error(operation, type(exc).__name__) from exc
            cursor, keys = _parse_scan_response(response, operation=operation)
            for redis_key in keys:
                if self._is_exact_namespace_key(redis_key):
                    yield redis_key
            if _cursor_is_done(cursor):
                return

    def _is_exact_namespace_key(self, value: str | bytes) -> bool:
        try:
            text = value.decode("utf-8") if isinstance(value, bytes) else value
        except UnicodeDecodeError:
            return False
        prefix = f"{{{self.namespace}:"
        if not text.startswith(prefix) or not text.endswith("}:snapshot"):
            return False
        digest = text[len(prefix) : -len("}:snapshot")]
        return re.fullmatch(r"[0-9a-f]{64}", digest) is not None


def normalize_redis_price_cache_namespace(namespace: str) -> str:
    """Normalize one namespace using the cache core's exact key-safety rules."""

    if not isinstance(namespace, str):
        raise TypeError("namespace must be a string")
    normalized = namespace.strip()
    if not normalized:
        raise ValueError("namespace cannot be empty")
    if re.fullmatch(r"[A-Za-z0-9._:-]+", normalized) is None:
        raise ValueError("namespace contains unsupported characters")
    return normalized


def _require_response_sequence(
    response: object,
    *,
    operation: str,
    minimum: int,
) -> list[object]:
    if not isinstance(response, Sequence) or isinstance(
        response,
        (str, bytes, bytearray),
    ):
        raise _backend_error(operation, "expected sequence response")
    values = list(response)
    if len(values) < minimum:
        raise _backend_error(operation, "response is too short")
    return values


def _require_hash_values(
    values: Sequence[object],
    *,
    operation: str,
) -> list[str | bytes]:
    result: list[str | bytes] = []
    for value in values:
        if not isinstance(value, (str, bytes)):
            raise _backend_error(operation, "hash response values must be text")
        result.append(value)
    return result


def _response_text(value: object, *, operation: str) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _backend_error(operation, "invalid UTF-8 response tag") from exc
    if isinstance(value, str):
        return value
    raise _backend_error(operation, "response tag must be text")


def _parse_server_time(values: Sequence[object], *, operation: str) -> datetime:
    if len(values) != 2:
        raise _backend_error(operation, "invalid Redis TIME response")
    seconds = _exact_nonnegative_int(values[0], operation=operation)
    microseconds = _exact_nonnegative_int(values[1], operation=operation)
    if microseconds > 999_999:
        raise _backend_error(operation, "invalid Redis TIME microseconds")
    try:
        return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
            seconds=seconds,
            microseconds=microseconds,
        )
    except OverflowError as exc:
        raise _backend_error(operation, "Redis TIME is out of range") from exc


def _exact_nonnegative_int(value: object, *, operation: str) -> int:
    if type(value) is int:
        if value < 0:
            raise _backend_error(operation, "expected nonnegative integer response")
        return value
    if isinstance(value, bytes):
        try:
            text = value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise _backend_error(
                operation,
                "expected nonnegative integer response",
            ) from exc
    elif isinstance(value, str):
        text = value
    else:
        raise _backend_error(operation, "expected nonnegative integer response")
    if re.fullmatch(r"0|[1-9][0-9]*", text) is None:
        raise _backend_error(operation, "expected nonnegative integer response")
    return int(text)


def _parse_state(value: object) -> PriceCacheState:
    text = _response_text(value, operation="get")
    try:
        return PriceCacheState(text)
    except ValueError as exc:
        raise _backend_error("get", "unknown cache state") from exc


def _parse_delete_count(value: object, *, operation: str) -> int:
    if type(value) is not int or value not in {0, 1}:
        raise _backend_error(operation, "invalid delete count")
    return value


def _parse_scan_response(
    response: object,
    *,
    operation: str,
) -> tuple[int, list[str | bytes]]:
    if not isinstance(response, (list, tuple)):
        raise _backend_error(operation, "invalid SCAN response")
    if len(response) != 2:
        raise _backend_error(operation, "invalid SCAN response length")
    cursor = _normalize_scan_cursor(response[0], operation=operation)
    keys = response[1]
    if not isinstance(keys, (list, tuple)):
        raise _backend_error(operation, "invalid SCAN keys")
    parsed_keys: list[str | bytes] = []
    for key in keys:
        if not isinstance(key, (str, bytes)):
            raise _backend_error(operation, "invalid SCAN key")
        parsed_keys.append(key)
    return cursor, parsed_keys


def _normalize_scan_cursor(value: object, *, operation: str) -> int:
    if type(value) is int:
        if value < 0:
            raise _backend_error(operation, "invalid SCAN cursor")
        return value
    if isinstance(value, bytes):
        try:
            text = value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise _backend_error(operation, "invalid SCAN cursor") from exc
    elif isinstance(value, str):
        text = value
    else:
        raise _backend_error(operation, "invalid SCAN cursor")
    if re.fullmatch(r"0|[1-9][0-9]*", text) is None:
        raise _backend_error(operation, "invalid SCAN cursor")
    return int(text)


def _cursor_is_done(cursor: int) -> bool:
    return cursor == 0


def _backend_error(operation: str, reason: str) -> PriceCacheBackendError:
    return PriceCacheBackendError(operation, reason)
