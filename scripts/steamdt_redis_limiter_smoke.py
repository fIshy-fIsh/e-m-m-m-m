# ruff: noqa: I001
import asyncio
import fnmatch
import inspect
import os
import re
import sys
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlunsplit

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.steamdt_errors import SteamDTRateLimitError
from app.services.redis_steamdt_rate_limiter import RedisSteamDTRateLimiter
from app.services.steamdt_rate_limiter import SteamDTEndpoint, SteamDTRateLimitPolicy

if __package__:
    from .steamdt_smoke_utils import parse_bool_env
else:
    from steamdt_smoke_utils import parse_bool_env

RUN_REDIS_INTEGRATION_ENV = "STEAMDT_RUN_REDIS_INTEGRATION_TESTS"
TEST_REDIS_URL_ENV = "STEAMDT_TEST_REDIS_URL"
TEST_REDIS_NAMESPACE_ENV = "STEAMDT_TEST_REDIS_NAMESPACE"
DEFAULT_TEST_REDIS_URL = "redis://localhost:6379/15"
DEFAULT_TEST_REDIS_NAMESPACE = "steamdt-rate-limit-integration-v1"
PRODUCTION_REDIS_NAMESPACE = "steamdt-rate-limit-v1"
REDIS_SCAN_COUNT = 100


class _NamespaceValidationRedisClient:
    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object:
        raise RuntimeError("namespace validation client must not evaluate Redis scripts")


def redact_redis_url(redis_url: str) -> str:
    """Return a Redis URL with credentials and query values removed from display."""

    try:
        parsed = urlsplit(redis_url)
    except ValueError:
        return re.sub(r"redis://([^\s/@]+:)?[^\s/@]+@", r"redis://\1[REDACTED]@", redis_url)

    netloc = parsed.netloc
    if "@" in netloc:
        auth, host = netloc.rsplit("@", 1)
        if ":" in auth:
            username, _password = auth.split(":", 1)
            auth = f"{username}:[REDACTED]"
        netloc = f"{auth}@{host}"

    query = "[REDACTED_QUERY]" if parsed.query else ""
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, ""))


def safe_redis_error_message(exc: Exception, *, redis_url: str | None = None) -> str:
    """Format an exception without leaking Redis credentials or auth headers."""

    message = str(exc) or type(exc).__name__
    if redis_url:
        redacted_url = redact_redis_url(redis_url)
        message = message.replace(redis_url, redacted_url)
        try:
            parsed = urlsplit(redis_url)
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.password:
                message = message.replace(parsed.password, "[REDACTED]")
            for _key, value in parse_qsl(parsed.query, keep_blank_values=True):
                if value:
                    message = message.replace(value, "[REDACTED]")
    message = re.sub(
        r"Authorization\s*[:=]\s*Bearer\s+[^\s,;]+",
        "[REDACTED_AUTHORIZATION]",
        message,
        flags=re.IGNORECASE,
    )
    message = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}", "Bearer [REDACTED]", message)
    message = re.sub(r"redis://([^\s/@]+:)?[^\s/@]+@", r"redis://\1[REDACTED]@", message)
    if len(message) > 300:
        message = f"{message[:300]}..."
    return f"{type(exc).__name__}: {message}"


def build_test_policies() -> dict[SteamDTEndpoint, SteamDTRateLimitPolicy]:
    """Build short-window Redis limiter policies used only by the integration harness."""

    return {
        SteamDTEndpoint.PRICE_BATCH: SteamDTRateLimitPolicy(
            max_requests=1,
            window_seconds=2.0,
            safety_buffer_seconds=0.2,
        ),
        SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(
            max_requests=2,
            window_seconds=2.0,
        ),
        SteamDTEndpoint.PRICE_AVG: SteamDTRateLimitPolicy(
            max_requests=2,
            window_seconds=2.0,
        ),
    }


def _validate_test_namespace(namespace: str) -> None:
    if namespace == PRODUCTION_REDIS_NAMESPACE:
        raise ValueError("test namespace cannot use the production Redis limiter namespace")
    RedisSteamDTRateLimiter(
        _NamespaceValidationRedisClient(),
        build_test_policies(),
        namespace=namespace,
    )


def build_test_namespace(
    base_namespace: str | None = None,
    *,
    suffix: str | None = None,
) -> str:
    """Build and validate an isolated test namespace before connecting to Redis."""

    base = (base_namespace or DEFAULT_TEST_REDIS_NAMESPACE).strip()
    _validate_test_namespace(base)
    namespace_suffix = suffix if suffix is not None else uuid.uuid4().hex
    namespace = f"{base}-{namespace_suffix}" if namespace_suffix else base
    _validate_test_namespace(namespace)
    return namespace


def build_namespace_scan_pattern(namespace: str) -> str:
    """Return the narrow cleanup pattern for one exact test namespace."""

    _validate_test_namespace(namespace)
    return f"{{{namespace}:*}}:*"


def _decode_redis_value(value: object) -> object:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _redis_cursor_is_done(cursor: object) -> bool:
    cursor = _decode_redis_value(cursor)
    return str(cursor) == "0"


def _key_matches_pattern(key: object, pattern: str) -> bool:
    decoded = _decode_redis_value(key)
    return isinstance(decoded, str) and fnmatch.fnmatchcase(decoded, pattern)


async def cleanup_namespace_keys(redis_client: object, namespace: str) -> int:
    """Delete only keys belonging to the exact test namespace, using paged SCAN."""

    pattern = build_namespace_scan_pattern(namespace)
    cursor: object = 0
    deleted_count = 0
    while True:
        cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=REDIS_SCAN_COUNT)
        matched_keys = [key for key in keys if _key_matches_pattern(key, pattern)]
        if matched_keys:
            deleted_count += int(await redis_client.delete(*matched_keys))
        if _redis_cursor_is_done(cursor):
            return deleted_count


async def _namespace_key_count(redis_client: object, namespace: str) -> int:
    pattern = build_namespace_scan_pattern(namespace)
    cursor: object = 0
    count = 0
    while True:
        cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=REDIS_SCAN_COUNT)
        count += sum(1 for key in keys if _key_matches_pattern(key, pattern))
        if _redis_cursor_is_done(cursor):
            return count


async def _expect_rate_limited(coro: object, *, scenario: str) -> SteamDTRateLimitError:
    try:
        await coro
    except SteamDTRateLimitError as exc:
        if exc.retry_after_seconds is None or exc.retry_after_seconds <= 0:
            raise RuntimeError(f"{scenario} returned non-positive retry_after_seconds") from exc
        return exc
    raise RuntimeError(f"{scenario} did not raise SteamDTRateLimitError")


async def _assert_positive_pttl(redis_client: object, key: str, *, label: str) -> None:
    ttl = int(await redis_client.pttl(key))
    if ttl <= 0:
        raise RuntimeError(f"{label} TTL was not positive")


async def _close_redis_client(redis_client: object) -> None:
    close = getattr(redis_client, "aclose", None)
    if close is None:
        close = getattr(redis_client, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


async def run_redis_limiter_smoke(
    redis_client: object,
    *,
    namespace: str,
    printer: Callable[[str], None] = print,
) -> None:
    """Run the real Redis/Lua limiter contract smoke against an injected Redis client."""

    policies = build_test_policies()
    primary_error: Exception | None = None
    cleanup_error: Exception | None = None

    try:
        await cleanup_namespace_keys(redis_client, namespace)
        printer("smoke script: steamdt_redis_limiter_smoke")
        printer("smoke mode: redis_limiter_integration")

        ping_result = await redis_client.ping()
        if ping_result not in (True, b"PONG", "PONG"):
            raise RuntimeError("Redis PING did not return success")
        printer("redis connection: pass")

        limiter_a = RedisSteamDTRateLimiter(redis_client, policies, namespace=namespace)
        limiter_b = RedisSteamDTRateLimiter(redis_client, policies, namespace=namespace)

        await limiter_a.acquire(SteamDTEndpoint.PRICE_BATCH)
        await _expect_rate_limited(
            limiter_b.acquire(SteamDTEndpoint.PRICE_BATCH),
            scenario="shared batch quota",
        )
        printer("shared batch quota: pass")

        await limiter_a.acquire(SteamDTEndpoint.PRICE_SINGLE)
        await limiter_b.acquire(SteamDTEndpoint.PRICE_SINGLE)
        await _expect_rate_limited(
            limiter_a.acquire(SteamDTEndpoint.PRICE_SINGLE),
            scenario="endpoint independence single quota",
        )
        await limiter_a.acquire(SteamDTEndpoint.PRICE_AVG)
        printer("endpoint independence: pass")

        await asyncio.sleep(2.3)
        await limiter_b.acquire(SteamDTEndpoint.PRICE_BATCH)
        printer("window recovery: pass")

        await cleanup_namespace_keys(redis_client, namespace)
        await limiter_a.record_server_limit(
            SteamDTEndpoint.PRICE_BATCH,
            retry_after_seconds=0.5,
        )
        await _expect_rate_limited(
            limiter_b.acquire(SteamDTEndpoint.PRICE_BATCH),
            scenario="shared server block",
        )
        await limiter_b.acquire(SteamDTEndpoint.PRICE_SINGLE)
        await asyncio.sleep(0.6)
        await limiter_b.acquire(SteamDTEndpoint.PRICE_BATCH)
        printer("shared server block: pass")

        await cleanup_namespace_keys(redis_client, namespace)
        await limiter_a.record_server_limit(
            SteamDTEndpoint.PRICE_BATCH,
            retry_after_seconds=1.2,
        )
        await asyncio.sleep(0.1)
        await limiter_b.record_server_limit(
            SteamDTEndpoint.PRICE_BATCH,
            retry_after_seconds=0.2,
        )
        longer_block_error = await _expect_rate_limited(
            limiter_b.acquire(SteamDTEndpoint.PRICE_BATCH),
            scenario="longer block wins",
        )
        if (
            longer_block_error.retry_after_seconds is None
            or longer_block_error.retry_after_seconds < 0.8
        ):
            raise RuntimeError("shorter server block replaced the longer block")
        printer("longer block wins: pass")

        await cleanup_namespace_keys(redis_client, namespace)
        await limiter_a.acquire(SteamDTEndpoint.PRICE_SINGLE)
        single_requests_key, _single_blocked_key = limiter_a.keys_for_endpoint(
            SteamDTEndpoint.PRICE_SINGLE
        )
        await limiter_a.record_server_limit(
            SteamDTEndpoint.PRICE_BATCH,
            retry_after_seconds=1.0,
        )
        _batch_requests_key, batch_blocked_key = limiter_a.keys_for_endpoint(
            SteamDTEndpoint.PRICE_BATCH
        )
        await _assert_positive_pttl(redis_client, single_requests_key, label="requests")
        await _assert_positive_pttl(redis_client, batch_blocked_key, label="blocked")
        printer("requests ttl: pass")
        printer("blocked ttl: pass")

        await cleanup_namespace_keys(redis_client, namespace)
        await asyncio.gather(
            limiter_a.acquire(SteamDTEndpoint.PRICE_SINGLE),
            limiter_b.acquire(SteamDTEndpoint.PRICE_SINGLE),
        )
        await _expect_rate_limited(
            limiter_a.acquire(SteamDTEndpoint.PRICE_SINGLE),
            scenario="unique request members",
        )
        unique_requests_key, _unique_blocked_key = limiter_a.keys_for_endpoint(
            SteamDTEndpoint.PRICE_SINGLE
        )
        if int(await redis_client.zcard(unique_requests_key)) != 2:
            raise RuntimeError("same-millisecond request members collided")
        printer("unique request members: pass")
        printer("SteamDT requests sent: 0")
    except Exception as exc:
        primary_error = exc
    finally:
        try:
            await cleanup_namespace_keys(redis_client, namespace)
            if await _namespace_key_count(redis_client, namespace) != 0:
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
    """Run the opt-in smoke script and return a process exit code."""

    environ = os.environ if environ is None else environ
    if not parse_bool_env(environ, RUN_REDIS_INTEGRATION_ENV):
        printer(
            "SteamDT Redis limiter integration smoke skipped:\n"
            f"{RUN_REDIS_INTEGRATION_ENV} is not true."
        )
        return 0

    try:
        namespace = build_test_namespace(environ.get(TEST_REDIS_NAMESPACE_ENV))
    except ValueError as exc:
        printer(f"SteamDT Redis limiter integration smoke failed: {safe_redis_error_message(exc)}")
        return 1

    redis_url = environ.get(TEST_REDIS_URL_ENV, DEFAULT_TEST_REDIS_URL)
    redis_client: object | None = None
    try:
        if redis_factory is None:
            from redis.asyncio import Redis

            redis_client = Redis.from_url(redis_url)
        else:
            redis_client = redis_factory(redis_url)
        await run_redis_limiter_smoke(redis_client, namespace=namespace, printer=printer)
        return 0
    except Exception as exc:
        printer(
            "SteamDT Redis limiter integration smoke failed: "
            f"{safe_redis_error_message(exc, redis_url=redis_url)}"
        )
        return 1
    finally:
        if redis_client is not None:
            try:
                await _close_redis_client(redis_client)
            except Exception as exc:
                printer(
                    "SteamDT Redis limiter Redis client close warning: "
                    f"{safe_redis_error_message(exc, redis_url=redis_url)}"
                )


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
