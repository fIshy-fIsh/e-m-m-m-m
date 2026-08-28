import math
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from redis.exceptions import RedisError

from app.clients.steamdt_errors import (
    SteamDTRateLimitBackendError,
    SteamDTRateLimitError,
)
from app.services.steamdt_rate_limiter import (
    SteamDTEndpoint,
    SteamDTRateLimitPolicy,
)

REDIS_STEAMDT_RATE_LIMIT_CLEANUP_GRACE_SECONDS = 60.0

REDIS_STEAMDT_ACQUIRE_SCRIPT = """
local requests_key = KEYS[1]
local blocked_key = KEYS[2]
local max_requests = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local requests_ttl_ms = tonumber(ARGV[3])
local member = ARGV[4]

local redis_time = redis.call("TIME")
local now_ms = (tonumber(redis_time[1]) * 1000) + math.floor(tonumber(redis_time[2]) / 1000)

local blocked_until_ms = tonumber(redis.call("GET", blocked_key) or "0")
if blocked_until_ms > now_ms then
    return {0, blocked_until_ms - now_ms, -1}
end

redis.call("ZREMRANGEBYSCORE", requests_key, "-inf", now_ms - window_ms)
local current_count = redis.call("ZCARD", requests_key)
if current_count >= max_requests then
    local oldest = redis.call("ZRANGE", requests_key, 0, 0, "WITHSCORES")
    local retry_after_ms = 0
    if oldest[2] ~= nil then
        retry_after_ms = tonumber(oldest[2]) + window_ms - now_ms
        if retry_after_ms < 0 then
            retry_after_ms = 0
        end
    end
    return {0, retry_after_ms, 0}
end

redis.call("ZADD", requests_key, now_ms, member)
redis.call("PEXPIRE", requests_key, requests_ttl_ms)
return {1, 0, max_requests - current_count - 1}
"""

REDIS_STEAMDT_RECORD_SERVER_LIMIT_SCRIPT = """
local blocked_key = KEYS[1]
local block_ms = tonumber(ARGV[1])
local cleanup_grace_ms = tonumber(ARGV[2])

local redis_time = redis.call("TIME")
local now_ms = (tonumber(redis_time[1]) * 1000) + math.floor(tonumber(redis_time[2]) / 1000)

if block_ms < 0 then
    block_ms = 0
end

local requested_blocked_until_ms = now_ms + block_ms
local existing_blocked_until_ms = tonumber(redis.call("GET", blocked_key) or "0")
local final_blocked_until_ms = requested_blocked_until_ms
if existing_blocked_until_ms > final_blocked_until_ms then
    final_blocked_until_ms = existing_blocked_until_ms
end

local ttl_ms = final_blocked_until_ms - now_ms + cleanup_grace_ms
if ttl_ms <= 0 then
    ttl_ms = 1
end
redis.call("PSETEX", blocked_key, ttl_ms, tostring(final_blocked_until_ms))
return {final_blocked_until_ms, math.max(0, final_blocked_until_ms - now_ms)}
"""


class AsyncRedisEvalClient(Protocol):
    """Minimal async Redis client surface needed by the shared SteamDT limiter."""

    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> object:
        """Evaluate a Redis Lua script atomically."""


class RedisSteamDTRateLimiter:
    """Redis-backed, cross-process SteamDT endpoint rate limiter core."""

    def __init__(
        self,
        redis_client: AsyncRedisEvalClient,
        policies: Mapping[SteamDTEndpoint, SteamDTRateLimitPolicy],
        *,
        namespace: str = "steamdt-rate-limit-v1",
        member_factory: Callable[[], str] | None = None,
    ) -> None:
        self.redis_client = redis_client
        self._policies = dict(policies)
        self.namespace = _validate_namespace(namespace)
        self._member_factory = member_factory or _default_member_factory

    async def acquire(self, endpoint: SteamDTEndpoint) -> None:
        """Acquire one shared Redis request slot or fail closed before HTTP transport."""

        policy = self._policy_for(endpoint)
        requests_key, blocked_key = self.keys_for_endpoint(endpoint)
        member = self._member_factory()
        if not member:
            raise ValueError("member_factory must return a non-empty member")

        try:
            response = await self.redis_client.eval(
                REDIS_STEAMDT_ACQUIRE_SCRIPT,
                2,
                requests_key,
                blocked_key,
                policy.max_requests,
                _seconds_to_ms(policy.effective_window_seconds),
                _seconds_to_ms(
                    policy.effective_window_seconds
                    + REDIS_STEAMDT_RATE_LIMIT_CLEANUP_GRACE_SECONDS
                ),
                member,
            )
        except Exception as exc:
            raise _backend_error("acquire", endpoint, exc) from exc

        allowed, retry_after_ms = _parse_acquire_response(response, endpoint=endpoint)
        if allowed:
            return
        raise SteamDTRateLimitError(
            "SteamDT Redis endpoint request budget exhausted",
            endpoint=endpoint.value,
            retry_after_seconds=max(0.0, retry_after_ms / 1000.0),
        )

    async def record_server_limit(
        self,
        endpoint: SteamDTEndpoint,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        """Record a shared server cooldown for one endpoint without sleeping."""

        policy = self._policy_for(endpoint)
        _requests_key, blocked_key = self.keys_for_endpoint(endpoint)
        if retry_after_seconds is None:
            block_seconds = policy.effective_window_seconds
        else:
            block_seconds = max(0.0, retry_after_seconds)

        try:
            response = await self.redis_client.eval(
                REDIS_STEAMDT_RECORD_SERVER_LIMIT_SCRIPT,
                1,
                blocked_key,
                _seconds_to_ms_allow_zero(block_seconds),
                _seconds_to_ms(REDIS_STEAMDT_RATE_LIMIT_CLEANUP_GRACE_SECONDS),
            )
        except Exception as exc:
            raise _backend_error("record_server_limit", endpoint, exc) from exc

        _parse_record_response(response, endpoint=endpoint)

    def keys_for_endpoint(self, endpoint: SteamDTEndpoint) -> tuple[str, str]:
        """Return Redis keys for the endpoint request set and server block marker."""

        self._policy_for(endpoint)
        hash_tag = f"{{{self.namespace}:{endpoint.value}}}"
        return f"{hash_tag}:requests", f"{hash_tag}:blocked"

    def _policy_for(self, endpoint: SteamDTEndpoint) -> SteamDTRateLimitPolicy:
        try:
            return self._policies[endpoint]
        except KeyError as exc:
            message = f"missing SteamDT rate-limit policy for endpoint: {endpoint.value}"
            raise ValueError(message) from exc



def _default_member_factory() -> str:
    return uuid.uuid4().hex



def _validate_namespace(namespace: str) -> str:
    if not namespace:
        raise ValueError("namespace cannot be empty")
    if "{" in namespace or "}" in namespace:
        raise ValueError("namespace cannot contain Redis hash-tag braces")
    if any(ord(character) < 32 or ord(character) == 127 for character in namespace):
        raise ValueError("namespace cannot contain newline or control characters")
    return namespace



def _seconds_to_ms(seconds: float) -> int:
    return max(1, math.ceil(seconds * 1000.0))


def _seconds_to_ms_allow_zero(seconds: float) -> int:
    return max(0, math.ceil(seconds * 1000.0))



def _parse_acquire_response(
    response: object,
    *,
    endpoint: SteamDTEndpoint,
) -> tuple[bool, int]:
    try:
        if not isinstance(response, Sequence):
            raise ValueError("expected sequence response")
        values = list(response)
        if len(values) < 2:
            raise ValueError("expected at least two values")
        allowed = int(values[0])
        retry_after_ms = max(0, int(float(values[1])))
    except Exception as exc:
        raise _backend_error(
            "acquire",
            endpoint,
            exc,
            message="invalid Redis limiter response",
        ) from exc
    if allowed not in (0, 1):
        raise _backend_error("acquire", endpoint, ValueError("invalid allowed flag"))
    return allowed == 1, retry_after_ms



def _parse_record_response(response: object, *, endpoint: SteamDTEndpoint) -> None:
    try:
        if not isinstance(response, Sequence):
            raise ValueError("expected sequence response")
        values = list(response)
        if len(values) < 2:
            raise ValueError("expected at least two values")
        int(float(values[0]))
        retry_after_ms = int(float(values[1]))
    except Exception as exc:
        raise _backend_error(
            "record_server_limit",
            endpoint,
            exc,
            message="invalid Redis limiter response",
        ) from exc
    if retry_after_ms < 0:
        raise _backend_error(
            "record_server_limit",
            endpoint,
            ValueError("negative retry_after_ms"),
        )



def _backend_error(
    operation: str,
    endpoint: SteamDTEndpoint,
    cause: Exception,
    *,
    message: str | None = None,
) -> SteamDTRateLimitBackendError:
    reason = message or f"Redis limiter backend failed: {type(cause).__name__}"
    if isinstance(cause, RedisError):
        reason = message or f"Redis limiter backend failed: {type(cause).__name__}"
    return SteamDTRateLimitBackendError(
        reason,
        endpoint=endpoint.value,
        backend="redis",
        operation=operation,
    )
