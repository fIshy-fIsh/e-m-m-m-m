# ruff: noqa: I001
import asyncio
import inspect
import os
import re
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.price_cache import (
    CachedPriceSnapshot,
    NormalizedPriceCandidate,
    PriceCacheKey,
    PriceCachePolicy,
    PriceCacheReadPolicy,
    PriceCacheState,
    PriceCacheWriteResult,
)
from app.services.price_cache_codec import PriceCacheCodecError
from app.services.redis_price_cache import (
    DEFAULT_REDIS_PRICE_CACHE_NAMESPACE,
    REDIS_PRICE_CACHE_PHYSICAL_CLEANUP_GRACE_MILLISECONDS,
    RedisPriceCache,
)
from scripts.steamdt_redis_limiter_smoke import safe_redis_error_message

if __package__:
    from .steamdt_smoke_utils import parse_bool_env
else:
    from steamdt_smoke_utils import parse_bool_env

RUN_REDIS_PRICE_CACHE_INTEGRATION_ENV = (
    "STEAMDT_RUN_REDIS_PRICE_CACHE_INTEGRATION_TESTS"
)
TEST_REDIS_URL_ENV = "STEAMDT_TEST_REDIS_URL"
TEST_REDIS_PRICE_CACHE_NAMESPACE_ENV = (
    "STEAMDT_TEST_REDIS_PRICE_CACHE_NAMESPACE"
)
DEFAULT_TEST_REDIS_URL = "redis://localhost:6379/15"
DEFAULT_TEST_REDIS_PRICE_CACHE_NAMESPACE = "steamdt-price-cache-integration-v1"
LIMITER_TEST_NAMESPACE = "steamdt-rate-limit-integration-v1"
REDIS_SCAN_COUNT = 100
_NAMESPACE_SUFFIX = re.compile(r"[0-9a-f]{32}")
_CACHE_KEY = re.compile(r"\{(?P<namespace>[A-Za-z0-9._:-]+):[0-9a-f]{64}\}:snapshot")


class _NamespaceValidationRedisClient:
    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object:
        raise RuntimeError("namespace validation client must not evaluate Redis scripts")

    async def scan(
        self,
        cursor: int = 0,
        *,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[bytes | str]]:
        raise RuntimeError("namespace validation client must not scan Redis")

    async def delete(self, *names: str | bytes) -> object:
        raise RuntimeError("namespace validation client must not delete Redis keys")


def _validate_test_namespace_base(namespace: str) -> str:
    if not isinstance(namespace, str):
        raise TypeError("test namespace must be a string")
    normalized = namespace.strip()
    if not normalized:
        raise ValueError("test namespace cannot be empty")
    if normalized != namespace:
        raise ValueError("test namespace cannot contain surrounding whitespace")
    if not normalized.startswith(DEFAULT_TEST_REDIS_PRICE_CACHE_NAMESPACE):
        raise ValueError("test namespace must use the price-cache integration prefix")
    if normalized in {
        DEFAULT_REDIS_PRICE_CACHE_NAMESPACE,
        LIMITER_TEST_NAMESPACE,
    }:
        raise ValueError("test namespace cannot use a production or limiter namespace")
    RedisPriceCache(_NamespaceValidationRedisClient(), namespace=normalized)
    return normalized


def build_test_namespace(
    base_namespace: str | None = None,
    *,
    suffix: str | None = None,
) -> str:
    """Build one UUID-scoped integration namespace without touching Redis."""

    base = _validate_test_namespace_base(
        DEFAULT_TEST_REDIS_PRICE_CACHE_NAMESPACE
        if base_namespace is None
        else base_namespace
    )
    namespace_suffix = uuid.uuid4().hex if suffix is None else suffix
    if _NAMESPACE_SUFFIX.fullmatch(namespace_suffix) is None:
        raise ValueError("test namespace suffix must be a 32-character lowercase UUID hex")
    namespace = f"{base}-{namespace_suffix}"
    RedisPriceCache(_NamespaceValidationRedisClient(), namespace=namespace)
    return namespace


def build_namespace_scan_pattern(namespace: str) -> str:
    _validate_run_namespace(namespace)
    return f"{{{namespace}:*}}:snapshot"


def _validate_run_namespace(namespace: str) -> None:
    separator = namespace.rfind("-")
    if separator < 0:
        raise ValueError("test namespace must include a UUID suffix")
    _validate_test_namespace_base(namespace[:separator])
    if _NAMESPACE_SUFFIX.fullmatch(namespace[separator + 1 :]) is None:
        raise ValueError("test namespace must end with a lowercase UUID hex suffix")
    RedisPriceCache(_NamespaceValidationRedisClient(), namespace=namespace)


def _decode_key(value: object) -> str | None:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return value if isinstance(value, str) else None


def _is_exact_namespace_key(value: object, namespace: str) -> bool:
    text = _decode_key(value)
    if text is None:
        return False
    match = _CACHE_KEY.fullmatch(text)
    return match is not None and match.group("namespace") == namespace


def _exact_nonnegative_int(value: object, *, field: str) -> int:
    if type(value) is int:
        result = value
    elif isinstance(value, bytes):
        try:
            text = value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise RuntimeError(f"{field} was not an ASCII integer") from exc
        if re.fullmatch(r"0|[1-9][0-9]*", text) is None:
            raise RuntimeError(f"{field} was not a canonical nonnegative integer")
        result = int(text)
    elif isinstance(value, str):
        if re.fullmatch(r"0|[1-9][0-9]*", value) is None:
            raise RuntimeError(f"{field} was not a canonical nonnegative integer")
        result = int(value)
    else:
        raise RuntimeError(f"{field} was not an exact integer")
    if result < 0:
        raise RuntimeError(f"{field} was negative")
    return result


def _normalize_cursor(value: object) -> int:
    return _exact_nonnegative_int(value, field="SCAN cursor")


async def cleanup_namespace_keys(redis_client: object, namespace: str) -> int:
    """Delete only exact price-cache keys in one UUID namespace using paged SCAN."""

    pattern = build_namespace_scan_pattern(namespace)
    deleted = 0
    while True:
        cursor = 0
        deleted_this_pass = 0
        while True:
            response = await redis_client.scan(
                cursor=cursor,
                match=pattern,
                count=REDIS_SCAN_COUNT,
            )
            if not isinstance(response, (list, tuple)) or len(response) != 2:
                raise RuntimeError("cleanup SCAN returned an invalid response")
            cursor = _normalize_cursor(response[0])
            keys = response[1]
            if not isinstance(keys, (list, tuple)):
                raise RuntimeError("cleanup SCAN keys were invalid")
            matched = [key for key in keys if _is_exact_namespace_key(key, namespace)]
            if matched:
                count = await redis_client.delete(*matched)
                if type(count) is not int or count < 0 or count > len(matched):
                    raise RuntimeError("cleanup DEL returned an invalid count")
                deleted += count
                deleted_this_pass += count
            if cursor == 0:
                break
        if deleted_this_pass == 0:
            return deleted


async def namespace_key_count(redis_client: object, namespace: str) -> int:
    pattern = build_namespace_scan_pattern(namespace)
    cursor = 0
    count = 0
    while True:
        response = await redis_client.scan(cursor=cursor, match=pattern, count=REDIS_SCAN_COUNT)
        if not isinstance(response, (list, tuple)) or len(response) != 2:
            raise RuntimeError("namespace SCAN returned an invalid response")
        cursor = _normalize_cursor(response[0])
        keys = response[1]
        if not isinstance(keys, (list, tuple)):
            raise RuntimeError("namespace SCAN keys were invalid")
        count += sum(1 for key in keys if _is_exact_namespace_key(key, namespace))
        if cursor == 0:
            return count


async def redis_server_time(redis_client: object) -> datetime:
    """Read a strict timezone-aware UTC timestamp from real Redis TIME."""

    response = await redis_client.time()
    if not isinstance(response, Sequence) or isinstance(
        response,
        (str, bytes, bytearray),
    ):
        raise RuntimeError("Redis TIME did not return a sequence")
    values = list(response)
    if len(values) != 2:
        raise RuntimeError("Redis TIME did not return two values")
    seconds = _exact_nonnegative_int(values[0], field="Redis TIME seconds")
    microseconds = _exact_nonnegative_int(values[1], field="Redis TIME microseconds")
    if microseconds > 999_999:
        raise RuntimeError("Redis TIME microseconds were out of range")
    try:
        return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
            seconds=seconds,
            microseconds=microseconds,
        )
    except OverflowError as exc:
        raise RuntimeError("Redis TIME was out of datetime range") from exc


def _candidate(platform: str, price: str, item_id: str) -> NormalizedPriceCandidate:
    return NormalizedPriceCandidate(
        platform=platform,
        platform_item_id=item_id,
        sell_price_cny=Decimal(price),
        sell_count=17,
        bidding_price_cny=Decimal("100.000000000000000001"),
        bidding_count=5,
        source_update_time="2026-07-17T12:00:00.123456Z",
    )


def build_snapshot(
    observed_at: datetime,
    *,
    name: str,
    price: str = "123.450000000000000001",
    fresh: timedelta = timedelta(seconds=30),
    stale: timedelta = timedelta(seconds=30),
    grace: timedelta = timedelta(seconds=30),
    stored_at: datetime | None = None,
) -> CachedPriceSnapshot:
    candidate = _candidate("buff", price, "duplicate-id")
    return CachedPriceSnapshot(
        key=PriceCacheKey(market_hash_name=name),
        candidates=(
            candidate,
            _candidate("steam", "124.000000000000000009", "steam-id"),
            candidate,
        ),
        observed_at=observed_at,
        stored_at=stored_at or observed_at,
        policy=PriceCachePolicy(
            fresh_ttl=fresh,
            stale_ttl=stale,
            stale_grace_ttl=grace,
        ),
    )


def expected_physical_expiry_ms(snapshot: CachedPriceSnapshot) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = snapshot.expires_at - epoch
    seconds = delta.days * 86_400 + delta.seconds
    rounded_microseconds = (delta.microseconds + 999) // 1000
    return (
        seconds * 1000
        + rounded_microseconds
        + REDIS_PRICE_CACHE_PHYSICAL_CLEANUP_GRACE_MILLISECONDS
    )


async def _pexpiretime(redis_client: object, key: str) -> int:
    value = await redis_client.execute_command("PEXPIRETIME", key)
    if type(value) is not int or value < 0:
        raise RuntimeError("PEXPIRETIME did not return an absolute integer timestamp")
    return value


async def _close_redis_client(redis_client: object) -> None:
    close = getattr(redis_client, "aclose", None)
    if close is None:
        close = getattr(redis_client, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


async def run_redis_price_cache_smoke(
    redis_client_a: object,
    redis_client_b: object,
    *,
    namespace: str,
    printer: Callable[[str], None] = print,
) -> None:
    """Exercise the real Redis/Lua price-cache contract without SteamDT traffic."""

    _validate_run_namespace(namespace)
    primary_error: Exception | None = None
    cleanup_error: Exception | None = None
    cache_a = RedisPriceCache(redis_client_a, namespace=namespace, scan_count=2)
    cache_b = RedisPriceCache(redis_client_b, namespace=namespace, scan_count=2)

    try:
        await cleanup_namespace_keys(redis_client_a, namespace)
        printer("smoke script: steamdt_redis_price_cache_smoke")
        printer("smoke mode: redis_price_cache_integration")
        ping_a, ping_b = await asyncio.gather(
            redis_client_a.ping(),
            redis_client_b.ping(),
        )
        if ping_a not in (True, b"PONG", "PONG") or ping_b not in (
            True,
            b"PONG",
            "PONG",
        ):
            raise RuntimeError("Redis PING did not return success")
        printer("redis connection: pass")

        before = await redis_server_time(redis_client_a)
        basic = build_snapshot(
            before - timedelta(seconds=1),
            name="smoke-basic",
            stored_at=before + timedelta(days=1),
        )
        if await cache_a.put(basic) != PriceCacheWriteResult.CREATED:
            raise RuntimeError("basic create did not return CREATED")
        after = await redis_server_time(redis_client_a)
        lookup = await cache_a.get(basic.key)
        if not lookup.hit or lookup.snapshot is None:
            raise RuntimeError("basic get was not a hit")
        if not before <= lookup.snapshot.stored_at <= after:
            raise RuntimeError("stored_at was not stamped by Redis TIME")
        if lookup.snapshot.candidates != basic.candidates:
            raise RuntimeError("candidate round-trip changed ordering or precision")
        printer("basic create/get: pass")

        shared = await cache_b.get(basic.key)
        if not shared.hit or cache_a.key_for(basic.key) != cache_b.key_for(basic.key):
            raise RuntimeError("second Redis client did not observe the shared entry")
        printer("shared client visibility: pass")

        newer = build_snapshot(
            basic.observed_at + timedelta(microseconds=2),
            name="smoke-basic",
            price="200.000000000000000001",
        )
        if await cache_b.put(newer) != PriceCacheWriteResult.REPLACED:
            raise RuntimeError("newer observation did not replace")
        printer("newer ordering: pass")

        preserved = (await cache_a.get(newer.key)).snapshot
        if preserved is None:
            raise RuntimeError("newer snapshot was missing")
        expiry_before = await _pexpiretime(redis_client_a, cache_a.key_for(newer.key))
        older = build_snapshot(
            newer.observed_at - timedelta(microseconds=1),
            name="smoke-basic",
            price="1.0",
            fresh=timedelta(hours=1),
        )
        if await cache_a.put(older) != PriceCacheWriteResult.IGNORED_OLDER:
            raise RuntimeError("older observation was not ignored")
        if await _pexpiretime(redis_client_a, cache_a.key_for(newer.key)) != expiry_before:
            raise RuntimeError("older write changed physical expiry")
        printer("older preservation: pass")

        equal = build_snapshot(
            newer.observed_at,
            name="smoke-basic",
            price="2.0",
            fresh=timedelta(hours=2),
        )
        if await cache_b.put(equal) != PriceCacheWriteResult.UNCHANGED_EQUAL:
            raise RuntimeError("equal observation was not unchanged")
        equal_lookup = await cache_a.get(equal.key)
        if equal_lookup.snapshot != preserved:
            raise RuntimeError("equal write changed the preserved snapshot")
        if await _pexpiretime(redis_client_a, cache_a.key_for(equal.key)) != expiry_before:
            raise RuntimeError("equal write changed physical expiry")
        printer("equal preservation: pass")

        same_second = (await redis_server_time(redis_client_a)) - timedelta(seconds=5)
        first_time = same_second.replace(microsecond=100_000)
        second_time = same_second.replace(microsecond=100_001)
        micro_first = build_snapshot(first_time, name="smoke-micro", price="10.0")
        micro_second = build_snapshot(second_time, name="smoke-micro", price="11.0")
        if await cache_a.put(micro_first) != PriceCacheWriteResult.CREATED:
            raise RuntimeError("microsecond first write failed")
        if await cache_b.put(micro_second) != PriceCacheWriteResult.REPLACED:
            raise RuntimeError("microsecond newer write failed")
        if await cache_a.put(micro_first) != PriceCacheWriteResult.IGNORED_OLDER:
            raise RuntimeError("microsecond older write was not ignored")
        micro_lookup = await cache_b.get(micro_second.key)
        if micro_lookup.snapshot is None or micro_lookup.snapshot.observed_at != second_time:
            raise RuntimeError("microsecond timestamp was not preserved")
        printer("microsecond ordering: pass")

        future_time = (await redis_server_time(redis_client_a)) + timedelta(seconds=60)
        future = build_snapshot(
            future_time,
            name="smoke-future",
            stored_at=future_time + timedelta(days=1),
        )
        try:
            await cache_a.put(future)
        except ValueError:
            pass
        else:
            raise RuntimeError("future observation was accepted")
        if await redis_client_a.exists(cache_a.key_for(future.key)) != 0:
            raise RuntimeError("future observation created a key")
        printer("future observation rejection: pass")

        state_now = await redis_server_time(redis_client_a)
        fresh_snapshot = build_snapshot(state_now - timedelta(seconds=2), name="smoke-fresh")
        await cache_a.put(fresh_snapshot)
        fresh_lookup = await cache_b.get(fresh_snapshot.key)
        if fresh_lookup.state != PriceCacheState.FRESH or fresh_lookup.needs_refresh:
            raise RuntimeError("fresh state was incorrect")
        printer("fresh state: pass")

        stale_snapshot = build_snapshot(
            state_now - timedelta(seconds=20),
            name="smoke-stale",
            fresh=timedelta(seconds=10),
            stale=timedelta(seconds=30),
            grace=timedelta(seconds=30),
        )
        await cache_a.put(stale_snapshot)
        stale_blocked = await cache_b.get(stale_snapshot.key)
        stale_allowed = await cache_b.get(
            stale_snapshot.key,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE,
        )
        if stale_blocked.snapshot is not None or not stale_allowed.hit:
            raise RuntimeError("stale read policy was incorrect")
        printer("stale state: pass")

        grace_snapshot = build_snapshot(
            state_now - timedelta(seconds=25),
            name="smoke-grace",
            fresh=timedelta(seconds=5),
            stale=timedelta(seconds=5),
            grace=timedelta(seconds=40),
        )
        await cache_a.put(grace_snapshot)
        grace_blocked = await cache_b.get(
            grace_snapshot.key,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE,
        )
        grace_allowed = await cache_b.get(
            grace_snapshot.key,
            read_policy=PriceCacheReadPolicy.ALLOW_STALE_GRACE,
        )
        if grace_blocked.snapshot is not None or not grace_allowed.hit:
            raise RuntimeError("stale-grace read policy was incorrect")
        printer("stale-grace state: pass")

        expiring_now = await redis_server_time(redis_client_a)
        expiring = build_snapshot(
            expiring_now,
            name="smoke-expired",
            fresh=timedelta(milliseconds=300),
            stale=timedelta(0),
            grace=timedelta(0),
        )
        await cache_a.put(expiring)
        await asyncio.sleep(0.6)
        expired_lookup = await cache_b.get(expiring.key)
        missing_lookup = await cache_a.get(expiring.key)
        if (
            expired_lookup.state != PriceCacheState.EXPIRED
            or expired_lookup.snapshot is not None
            or not expired_lookup.expired
            or missing_lookup.state is not None
            or await redis_client_a.exists(cache_a.key_for(expiring.key)) != 0
        ):
            raise RuntimeError("expired get did not atomically delete the hash")
        printer("expired atomic delete: pass")

        absolute_now = await redis_server_time(redis_client_a)
        absolute = build_snapshot(
            absolute_now - timedelta(seconds=1),
            name="smoke-absolute",
            fresh=timedelta(seconds=10, microseconds=1),
            stale=timedelta(seconds=1, microseconds=1),
            grace=timedelta(seconds=1, microseconds=1),
        )
        await cache_a.put(absolute)
        actual_expiry = await _pexpiretime(redis_client_a, cache_a.key_for(absolute.key))
        if actual_expiry != expected_physical_expiry_ms(absolute):
            raise RuntimeError("PEXPIREAT was not observation-based and absolute")
        printer("absolute expiry: pass")

        wrong = build_snapshot(absolute_now - timedelta(seconds=1), name="smoke-wrong")
        wrong_key = cache_a.key_for(wrong.key)
        await redis_client_a.set(wrong_key, "redacted-test-value")
        try:
            await cache_a.get(wrong.key)
        except PriceCacheCodecError:
            pass
        else:
            raise RuntimeError("wrong-type get did not fail closed")
        try:
            await cache_b.put(wrong)
        except PriceCacheCodecError:
            pass
        else:
            raise RuntimeError("wrong-type put overwrote the key")
        if await redis_client_a.type(wrong_key) not in (b"string", "string"):
            raise RuntimeError("wrong-type key was changed")
        printer("wrong-type protection: pass")

        corrupt = build_snapshot(absolute_now - timedelta(seconds=1), name="smoke-corrupt")
        await cache_a.put(corrupt)
        corrupt_key = cache_a.key_for(corrupt.key)
        await redis_client_a.hdel(corrupt_key, "codec_version")
        try:
            await cache_b.get(corrupt.key)
        except PriceCacheCodecError:
            pass
        else:
            raise RuntimeError("corrupt hash get did not fail closed")
        corrupt_newer = build_snapshot(
            corrupt.observed_at + timedelta(microseconds=1),
            name="smoke-corrupt",
            price="999.0",
        )
        try:
            await cache_a.put(corrupt_newer)
        except PriceCacheCodecError:
            pass
        else:
            raise RuntimeError("newer put overwrote a corrupt hash")
        printer("corruption protection: pass")

        other_namespace = build_test_namespace(suffix=uuid.uuid4().hex)
        other_cache = RedisPriceCache(redis_client_a, namespace=other_namespace)
        other_snapshot = build_snapshot(absolute_now - timedelta(seconds=1), name="other")
        await other_cache.put(other_snapshot)
        unrelated_key = f"unrelated:{uuid.uuid4().hex}"
        limiter_like_key = f"{{{LIMITER_TEST_NAMESPACE}:price_single}}:requests"
        await redis_client_a.set(unrelated_key, "keep")
        await redis_client_a.set(limiter_like_key, "keep")
        try:
            await cache_a.clear()
            if await namespace_key_count(redis_client_a, namespace) != 0:
                raise RuntimeError("clear left current namespace keys")
            if await redis_client_a.exists(other_cache.key_for(other_snapshot.key)) != 1:
                raise RuntimeError("clear removed another price-cache namespace")
            if await redis_client_a.exists(unrelated_key) != 1:
                raise RuntimeError("clear removed an unrelated key")
            if await redis_client_a.exists(limiter_like_key) != 1:
                raise RuntimeError("clear removed a limiter-like key")
            printer("namespace isolation: pass")
            printer("clear pagination: pass")
        finally:
            await cleanup_namespace_keys(redis_client_a, other_namespace)
            await redis_client_a.delete(unrelated_key, limiter_like_key)

        purge_now = await redis_server_time(redis_client_a)
        live = build_snapshot(purge_now, name="smoke-purge-live")
        expired = build_snapshot(
            purge_now - timedelta(seconds=1),
            name="smoke-purge-expired",
            fresh=timedelta(milliseconds=300),
            stale=timedelta(0),
            grace=timedelta(0),
        )
        await cache_a.put(live)
        await cache_a.put(expired)
        if await cache_b.purge_expired() != 1:
            raise RuntimeError("purge_expired returned the wrong count")
        if await redis_client_a.exists(cache_a.key_for(live.key)) != 1:
            raise RuntimeError("purge_expired deleted a live entry")
        printer("purge expired: pass")

        race_now = (await redis_server_time(redis_client_a)) - timedelta(seconds=2)
        race_older = build_snapshot(race_now, name="smoke-race", price="1.0")
        race_newer = build_snapshot(
            race_now + timedelta(microseconds=1),
            name="smoke-race",
            price="2.0",
        )
        results = await asyncio.gather(
            cache_a.put(race_older),
            cache_b.put(race_newer),
        )
        race_lookup = await cache_a.get(race_newer.key)
        if (
            PriceCacheWriteResult.CREATED not in results
            or race_lookup.snapshot is None
            or race_lookup.snapshot.observed_at != race_newer.observed_at
        ):
            raise RuntimeError("concurrent newer/older race violated ordering")
        printer("concurrent ordering: pass")

        if await redis_client_a.ping() not in (True, b"PONG", "PONG"):
            raise RuntimeError("RedisPriceCache closed the injected client")
        if await redis_client_b.ping() not in (True, b"PONG", "PONG"):
            raise RuntimeError("RedisPriceCache closed the second injected client")
        printer("client ownership: pass")
        printer("SteamDT requests sent: 0")
    except Exception as exc:
        primary_error = exc
    finally:
        try:
            await cleanup_namespace_keys(redis_client_a, namespace)
            if await namespace_key_count(redis_client_a, namespace) != 0:
                raise RuntimeError("namespace cleanup left matching keys behind")
            printer("namespace cleanup: pass")
        except Exception as exc:
            cleanup_error = exc
            printer(f"cleanup warning: {safe_redis_error_message(exc)}")

    if primary_error is not None:
        raise primary_error
    if cleanup_error is not None:
        raise cleanup_error


async def async_main(
    environ: Mapping[str, str] | None = None,
    *,
    printer: Callable[[str], None] = print,
    redis_factory: Callable[[str], object] | None = None,
) -> int:
    environ = os.environ if environ is None else environ
    if not parse_bool_env(environ, RUN_REDIS_PRICE_CACHE_INTEGRATION_ENV):
        printer(
            "SteamDT Redis price-cache integration smoke skipped:\n"
            f"{RUN_REDIS_PRICE_CACHE_INTEGRATION_ENV} is not true."
        )
        return 0

    try:
        namespace = build_test_namespace(
            environ.get(TEST_REDIS_PRICE_CACHE_NAMESPACE_ENV)
        )
    except (TypeError, ValueError) as exc:
        printer(
            "SteamDT Redis price-cache integration smoke failed: "
            f"{safe_redis_error_message(exc)}"
        )
        return 1

    redis_url = environ.get(TEST_REDIS_URL_ENV, DEFAULT_TEST_REDIS_URL)
    clients: list[object] = []
    exit_code = 0
    try:
        if redis_factory is None:
            from redis.asyncio import Redis

            clients = [Redis.from_url(redis_url), Redis.from_url(redis_url)]
        else:
            clients = [redis_factory(redis_url), redis_factory(redis_url)]
        await run_redis_price_cache_smoke(
            clients[0],
            clients[1],
            namespace=namespace,
            printer=printer,
        )
    except Exception as exc:
        exit_code = 1
        printer(
            "SteamDT Redis price-cache integration smoke failed: "
            f"{safe_redis_error_message(exc, redis_url=redis_url)}"
        )
    finally:
        for client in reversed(clients):
            try:
                await _close_redis_client(client)
            except Exception as exc:
                printer(
                    "SteamDT Redis price-cache client close warning: "
                    f"{safe_redis_error_message(exc, redis_url=redis_url)}"
                )
    return exit_code


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
