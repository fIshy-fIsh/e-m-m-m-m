import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from redis.exceptions import ConnectionError, ResponseError, TimeoutError

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.clients.steamdt_errors import (
    SteamDTHttpStatusError,
    SteamDTRateLimitBackendError,
    SteamDTRateLimitError,
    SteamDTResponseParseError,
)
from app.services.redis_steamdt_rate_limiter import (
    REDIS_STEAMDT_ACQUIRE_SCRIPT,
    REDIS_STEAMDT_RECORD_SERVER_LIMIT_SCRIPT,
    RedisSteamDTRateLimiter,
)
from app.services.steamdt_rate_limiter import (
    SteamDTEndpoint,
    SteamDTRateLimitPolicy,
    build_steamdt_rate_limit_policies,
)


@dataclass
class FakeRedisBackend:
    now_ms: int = 0
    requests: dict[str, dict[str, int]] = field(default_factory=dict)
    blocked: dict[str, int] = field(default_factory=dict)
    ttl_ms: dict[str, int] = field(default_factory=dict)
    calls: list[tuple[str, int, tuple[object, ...]]] = field(default_factory=list)
    malformed_response: bool = False
    error: Exception | None = None

    def advance(self, seconds: float) -> None:
        self.now_ms += int(seconds * 1000)


class FakeRedisEvalClient:
    def __init__(self, backend: FakeRedisBackend | None = None) -> None:
        self.backend = backend or FakeRedisBackend()
        self._lock = asyncio.Lock()

    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> object:
        async with self._lock:
            self.backend.calls.append((script, numkeys, keys_and_args))
            if self.backend.error is not None:
                raise self.backend.error
            if self.backend.malformed_response:
                return ["malformed"]
            if script == REDIS_STEAMDT_ACQUIRE_SCRIPT:
                return self._eval_acquire(numkeys, keys_and_args)
            if script == REDIS_STEAMDT_RECORD_SERVER_LIMIT_SCRIPT:
                return self._eval_record(numkeys, keys_and_args)
            raise ResponseError("unknown script")

    def _eval_acquire(self, numkeys: int, args: tuple[object, ...]) -> list[int]:
        assert numkeys == 2
        requests_key = str(args[0])
        blocked_key = str(args[1])
        max_requests = int(args[2])
        window_ms = int(args[3])
        requests_ttl_ms = int(args[4])
        member = str(args[5])
        now_ms = self.backend.now_ms

        blocked_until_ms = self.backend.blocked.get(blocked_key, 0)
        if blocked_until_ms > now_ms:
            return [0, blocked_until_ms - now_ms, -1]

        request_members = self.backend.requests.setdefault(requests_key, {})
        cutoff = now_ms - window_ms
        for request_member, score in list(request_members.items()):
            if score <= cutoff:
                del request_members[request_member]

        if len(request_members) >= max_requests:
            oldest = min(request_members.values())
            return [0, max(0, oldest + window_ms - now_ms), 0]

        request_members[member] = now_ms
        self.backend.ttl_ms[requests_key] = requests_ttl_ms
        return [1, 0, max_requests - len(request_members)]

    def _eval_record(self, numkeys: int, args: tuple[object, ...]) -> list[int]:
        assert numkeys == 1
        blocked_key = str(args[0])
        block_ms = max(0, int(args[1]))
        cleanup_grace_ms = int(args[2])
        now_ms = self.backend.now_ms
        requested = now_ms + block_ms
        existing = self.backend.blocked.get(blocked_key, 0)
        final = max(existing, requested)
        self.backend.blocked[blocked_key] = final
        self.backend.ttl_ms[blocked_key] = max(1, final - now_ms + cleanup_grace_ms)
        return [final, max(0, final - now_ms)]


def _policies(
    *,
    single: int = 2,
    batch: int = 1,
    avg: int = 2,
    batch_buffer: float = 5.0,
) -> dict[SteamDTEndpoint, SteamDTRateLimitPolicy]:
    return build_steamdt_rate_limit_policies(
        price_single_per_minute=single,
        price_batch_per_minute=batch,
        price_avg_per_minute=avg,
        base_per_day=1,
        kline_per_minute=120,
        wear_per_hour=36000,
        price_batch_safety_buffer_seconds=batch_buffer,
    )


def _single_response(status_code: int, payload: Any) -> httpx.Response:
    response = httpx.Response(status_code, json=payload)
    response.request = httpx.Request(
        "GET",
        "https://open.steamdt.com/open/cs2/v1/price/single",
    )
    return response


def _successful_single_payload() -> dict[str, object]:
    return {
        "success": True,
        "data": [{"platform": "steam", "sellPrice": "12.34", "sellCount": 2}],
    }


def test_redis_limiter_rejects_empty_namespace() -> None:
    with pytest.raises(ValueError, match="namespace"):
        RedisSteamDTRateLimiter(FakeRedisEvalClient(), _policies(), namespace="")


@pytest.mark.parametrize("namespace", ["bad{namespace", "bad}namespace"])
def test_redis_limiter_rejects_namespace_with_hash_tag_braces(namespace: str) -> None:
    with pytest.raises(ValueError, match="namespace"):
        RedisSteamDTRateLimiter(FakeRedisEvalClient(), _policies(), namespace=namespace)


@pytest.mark.parametrize("namespace", ["bad\nnamespace", "bad\x00namespace"])
def test_redis_limiter_rejects_namespace_with_control_characters(namespace: str) -> None:
    with pytest.raises(ValueError, match="namespace"):
        RedisSteamDTRateLimiter(FakeRedisEvalClient(), _policies(), namespace=namespace)


def test_same_endpoint_keys_use_same_cluster_hash_tag() -> None:
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(), _policies())

    requests_key, blocked_key = limiter.keys_for_endpoint(SteamDTEndpoint.PRICE_BATCH)

    assert requests_key.startswith("{steamdt-rate-limit-v1:price_batch}")
    assert blocked_key.startswith("{steamdt-rate-limit-v1:price_batch}")
    assert requests_key.endswith(":requests")
    assert blocked_key.endswith(":blocked")


def test_different_endpoints_use_different_keys() -> None:
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(), _policies())

    single_keys = limiter.keys_for_endpoint(SteamDTEndpoint.PRICE_SINGLE)
    batch_keys = limiter.keys_for_endpoint(SteamDTEndpoint.PRICE_BATCH)

    assert single_keys != batch_keys


def test_keys_do_not_include_secret_market_name_or_url() -> None:
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(), _policies())

    joined_keys = " ".join(limiter.keys_for_endpoint(SteamDTEndpoint.PRICE_SINGLE))

    assert "super-secret" not in joined_keys
    assert "AK-47" not in joined_keys
    assert "https://open.steamdt.com" not in joined_keys
    assert "/open/cs2" not in joined_keys


def test_missing_policy_fails_clearly() -> None:
    limiter = RedisSteamDTRateLimiter(
        FakeRedisEvalClient(),
        {SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(1, 60)},
    )

    with pytest.raises(ValueError, match="missing SteamDT rate-limit policy"):
        limiter.keys_for_endpoint(SteamDTEndpoint.PRICE_BATCH)


def test_acquire_first_request_is_allowed() -> None:
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(), _policies(single=1))

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_acquire_allows_requests_within_policy() -> None:
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(), _policies(single=2))

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))
    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_acquire_exhaustion_fails_fast_with_retry_after() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies(single=1))

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))

    assert exc_info.value.endpoint == SteamDTEndpoint.PRICE_SINGLE.value
    assert exc_info.value.retry_after_seconds == 60
    assert exc_info.value.retry_after_seconds >= 0


def test_acquire_allows_after_window_expires() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies(single=1))

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))
    backend.advance(60.1)

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_batch_safety_buffer_affects_redis_window() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(
        FakeRedisEvalClient(backend),
        _policies(batch=1, batch_buffer=5),
    )

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_BATCH))
    backend.advance(60)

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_BATCH))
    assert exc_info.value.retry_after_seconds == 5

    backend.advance(5.1)
    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_BATCH))


def test_requests_key_receives_cleanup_ttl() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies(single=1))
    requests_key, _blocked_key = limiter.keys_for_endpoint(SteamDTEndpoint.PRICE_SINGLE)

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))

    assert backend.ttl_ms[requests_key] >= 120000


def test_same_millisecond_members_do_not_overwrite_each_other() -> None:
    backend = FakeRedisBackend()
    members = iter(["member-a", "member-b"])
    limiter = RedisSteamDTRateLimiter(
        FakeRedisEvalClient(backend),
        _policies(single=2),
        member_factory=lambda: next(members),
    )
    requests_key, _blocked_key = limiter.keys_for_endpoint(SteamDTEndpoint.PRICE_SINGLE)

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))
    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))

    assert set(backend.requests[requests_key]) == {"member-a", "member-b"}


def test_malformed_acquire_response_fails_closed() -> None:
    backend = FakeRedisBackend(malformed_response=True)
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())

    with pytest.raises(SteamDTRateLimitBackendError):
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_two_limiter_instances_share_batch_quota() -> None:
    backend = FakeRedisBackend()
    limiter_a = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies(batch=1))
    limiter_b = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies(batch=1))

    asyncio.run(limiter_a.acquire(SteamDTEndpoint.PRICE_BATCH))

    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(limiter_b.acquire(SteamDTEndpoint.PRICE_BATCH))


def test_two_limiter_instances_share_single_count() -> None:
    backend = FakeRedisBackend()
    limiter_a = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies(single=2))
    limiter_b = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies(single=2))

    asyncio.run(limiter_a.acquire(SteamDTEndpoint.PRICE_SINGLE))
    asyncio.run(limiter_b.acquire(SteamDTEndpoint.PRICE_SINGLE))

    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(limiter_a.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_shared_state_keeps_endpoints_independent() -> None:
    backend = FakeRedisBackend()
    limiter_a = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies(batch=1))
    limiter_b = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies(batch=1))

    asyncio.run(limiter_a.acquire(SteamDTEndpoint.PRICE_BATCH))
    asyncio.run(limiter_b.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_concurrent_cross_instance_acquire_does_not_exceed_policy() -> None:
    backend = FakeRedisBackend()
    limiters = [
        RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies(single=2))
        for _ in range(5)
    ]

    async def run() -> list[object]:
        return await asyncio.gather(
            *(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE) for limiter in limiters),
            return_exceptions=True,
        )

    results = asyncio.run(run())

    assert sum(result is None for result in results) == 2
    assert sum(isinstance(result, SteamDTRateLimitError) for result in results) == 3


def test_server_block_recorded_by_one_instance_blocks_another() -> None:
    backend = FakeRedisBackend()
    limiter_a = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())
    limiter_b = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())

    asyncio.run(
        limiter_a.record_server_limit(
            SteamDTEndpoint.PRICE_BATCH,
            retry_after_seconds=30,
        )
    )

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(limiter_b.acquire(SteamDTEndpoint.PRICE_BATCH))
    assert exc_info.value.retry_after_seconds == 30


def test_server_block_does_not_affect_other_endpoints() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())

    asyncio.run(
        limiter.record_server_limit(
            SteamDTEndpoint.PRICE_BATCH,
            retry_after_seconds=30,
        )
    )

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_longer_server_block_is_not_replaced_by_shorter_block() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())

    asyncio.run(
        limiter.record_server_limit(
            SteamDTEndpoint.PRICE_SINGLE,
            retry_after_seconds=60,
        )
    )
    backend.advance(10)
    asyncio.run(
        limiter.record_server_limit(
            SteamDTEndpoint.PRICE_SINGLE,
            retry_after_seconds=5,
        )
    )

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))
    assert exc_info.value.retry_after_seconds == 50


def test_server_block_expires_after_clock_advances() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())

    asyncio.run(
        limiter.record_server_limit(
            SteamDTEndpoint.PRICE_SINGLE,
            retry_after_seconds=10,
        )
    )
    backend.advance(10.1)

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_record_server_limit_none_uses_effective_policy_window() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies(batch_buffer=5))

    asyncio.run(limiter.record_server_limit(SteamDTEndpoint.PRICE_BATCH))

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_BATCH))
    assert exc_info.value.retry_after_seconds == 65


def test_negative_retry_after_is_normalized_safely() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())

    asyncio.run(
        limiter.record_server_limit(
            SteamDTEndpoint.PRICE_SINGLE,
            retry_after_seconds=-5,
        )
    )

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_blocked_key_receives_ttl() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())
    _requests_key, blocked_key = limiter.keys_for_endpoint(SteamDTEndpoint.PRICE_SINGLE)

    asyncio.run(
        limiter.record_server_limit(
            SteamDTEndpoint.PRICE_SINGLE,
            retry_after_seconds=30,
        )
    )

    assert backend.ttl_ms[blocked_key] >= 90000


@pytest.mark.parametrize(
    "error",
    [ConnectionError("redis://:password@redis/0"), TimeoutError("timeout")],
)
def test_redis_connection_or_timeout_error_becomes_backend_error(error: Exception) -> None:
    backend = FakeRedisBackend(error=error)
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())

    with pytest.raises(SteamDTRateLimitBackendError) as exc_info:
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))

    assert exc_info.value.backend == "redis"
    assert exc_info.value.operation == "acquire"
    assert not isinstance(exc_info.value, SteamDTRateLimitError)


def test_redis_response_error_becomes_backend_error() -> None:
    backend = FakeRedisBackend(error=ResponseError("Authorization: Bearer super-secret"))
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())

    with pytest.raises(SteamDTRateLimitBackendError) as exc_info:
        asyncio.run(limiter.record_server_limit(SteamDTEndpoint.PRICE_SINGLE))

    assert exc_info.value.operation == "record_server_limit"
    assert not isinstance(exc_info.value, SteamDTRateLimitError)


def test_backend_error_text_does_not_leak_password_api_key_or_authorization() -> None:
    backend = FakeRedisBackend(
        error=ConnectionError(
            "redis://:redis-password@redis/0 Authorization: Bearer super-secret-steamdt-key"
        )
    )
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())

    with pytest.raises(SteamDTRateLimitBackendError) as exc_info:
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))

    error_text = str(exc_info.value)
    assert "redis-password" not in error_text
    assert "super-secret-steamdt-key" not in error_text
    assert "Authorization:" not in error_text


def test_backend_error_does_not_fallback_to_in_memory() -> None:
    backend = FakeRedisBackend(error=ConnectionError("down"))
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())

    with pytest.raises(SteamDTRateLimitBackendError):
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))
    with pytest.raises(SteamDTRateLimitBackendError):
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_client_with_redis_limiter_allow_calls_http_transport() -> None:
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(), _policies(single=1))
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    mock_http_client.request.return_value = _single_response(200, _successful_single_payload())
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    result = asyncio.run(client.get_price_single("A"))

    assert result.price_cny == Decimal("12.34")
    mock_http_client.request.assert_awaited_once()


def test_client_with_redis_limiter_deny_skips_http_transport() -> None:
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(), _policies(single=1))
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))

    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(client.get_price_single("A"))
    mock_http_client.request.assert_not_called()


def test_client_with_redis_backend_failure_skips_http_transport() -> None:
    backend = FakeRedisBackend(error=ConnectionError("down"))
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    with pytest.raises(SteamDTRateLimitBackendError):
        asyncio.run(client.get_price_single("A"))
    mock_http_client.request.assert_not_called()


def test_client_http_429_calls_redis_record_server_limit() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    response = _single_response(429, {"success": False})
    response.headers["Retry-After"] = "2.5"
    mock_http_client.request.return_value = response
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)
    _requests_key, blocked_key = limiter.keys_for_endpoint(SteamDTEndpoint.PRICE_SINGLE)

    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(client.get_price_single("A"))

    assert backend.blocked[blocked_key] == 2500
    mock_http_client.request.assert_awaited_once()


def test_client_wrapper_4005_calls_redis_record_server_limit() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    mock_http_client.request.return_value = _single_response(
        200,
        {
            "success": False,
            "errorCode": 4005,
            "errorMsg": "limit",
            "errorCodeStr": "RATE_LIMIT",
            "data": None,
        },
    )
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)
    _requests_key, blocked_key = limiter.keys_for_endpoint(SteamDTEndpoint.PRICE_SINGLE)

    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(client.get_price_single("A"))

    assert backend.blocked[blocked_key] == 60000
    mock_http_client.request.assert_awaited_once()


def test_client_parser_error_does_not_call_server_block() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    mock_http_client.request.return_value = _single_response(200, {"success": True, "data": {}})
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    with pytest.raises(SteamDTResponseParseError):
        asyncio.run(client.get_price_single("A"))

    assert backend.blocked == {}


@pytest.mark.parametrize("status_code", [401, 403, 404])
def test_client_401_403_404_do_not_call_server_block(status_code: int) -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies())
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=0)
    mock_http_client = AsyncMock()
    mock_http_client.request.return_value = _single_response(status_code, {"success": False})
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)

    with pytest.raises(SteamDTHttpStatusError):
        asyncio.run(client.get_price_single("A"))

    assert backend.blocked == {}


def test_client_retry_attempt_goes_through_injected_redis_limiter() -> None:
    backend = FakeRedisBackend()
    limiter = RedisSteamDTRateLimiter(FakeRedisEvalClient(backend), _policies(single=2))
    config = SteamDTClientConfig(api_key="secret-key", dry_run=False, max_retries=1)
    mock_http_client = AsyncMock()
    mock_http_client.request.side_effect = [
        httpx.ReadTimeout("timeout"),
        _single_response(200, _successful_single_payload()),
    ]
    client = SteamDTHttpClient(config, http_client=mock_http_client, rate_limiter=limiter)
    requests_key, _blocked_key = limiter.keys_for_endpoint(SteamDTEndpoint.PRICE_SINGLE)

    asyncio.run(client.get_price_single("A"))

    assert len(backend.requests[requests_key]) == 2
    assert mock_http_client.request.await_count == 2


def test_acquire_script_uses_two_keys_and_no_dynamic_key_generation() -> None:
    assert "KEYS[1]" in REDIS_STEAMDT_ACQUIRE_SCRIPT
    assert "KEYS[2]" in REDIS_STEAMDT_ACQUIRE_SCRIPT
    assert "redis.call(\"TIME\")" in REDIS_STEAMDT_ACQUIRE_SCRIPT
    assert "ZREMRANGEBYSCORE" in REDIS_STEAMDT_ACQUIRE_SCRIPT
    assert "ZCARD" in REDIS_STEAMDT_ACQUIRE_SCRIPT
    assert "ZADD" in REDIS_STEAMDT_ACQUIRE_SCRIPT
    assert "steamdt-rate-limit" not in REDIS_STEAMDT_ACQUIRE_SCRIPT


def test_record_script_uses_max_block_semantics() -> None:
    assert "KEYS[1]" in REDIS_STEAMDT_RECORD_SERVER_LIMIT_SCRIPT
    assert "redis.call(\"TIME\")" in REDIS_STEAMDT_RECORD_SERVER_LIMIT_SCRIPT
    assert "existing_blocked_until_ms > final_blocked_until_ms" in (
        REDIS_STEAMDT_RECORD_SERVER_LIMIT_SCRIPT
    )
    assert "PSETEX" in REDIS_STEAMDT_RECORD_SERVER_LIMIT_SCRIPT


def test_lua_scripts_do_not_contain_secrets_or_raw_response_storage() -> None:
    scripts = f"{REDIS_STEAMDT_ACQUIRE_SCRIPT}\n{REDIS_STEAMDT_RECORD_SERVER_LIMIT_SCRIPT}"

    assert "Authorization" not in scripts
    assert "Bearer" not in scripts
    assert "api_key" not in scripts.lower()
    assert "raw" not in scripts.lower()


class FakeCleanupRedis:
    def __init__(self, pages: list[tuple[object, list[object]]]) -> None:
        self.pages = pages
        self.scan_calls: list[dict[str, object]] = []
        self.deleted: list[object] = []
        self.flushdb_called = False
        self.flushall_called = False

    async def scan(
        self,
        *,
        cursor: object = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[object, list[object]]:
        self.scan_calls.append({"cursor": cursor, "match": match, "count": count})
        if len(self.scan_calls) <= len(self.pages):
            return self.pages[len(self.scan_calls) - 1]
        return 0, []

    async def delete(self, *keys: object) -> int:
        self.deleted.extend(keys)
        return len(keys)

    async def flushdb(self) -> None:
        self.flushdb_called = True
        raise AssertionError("FLUSHDB must not be called")

    async def flushall(self) -> None:
        self.flushall_called = True
        raise AssertionError("FLUSHALL must not be called")


class FakeFailingRedis:
    def __init__(self) -> None:
        self.closed = False

    async def ping(self) -> bool:
        raise ConnectionError("redis://user:dummy-password@localhost:6379/15?token=dummy-token")

    async def scan(
        self,
        *,
        cursor: object = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[object]]:
        return 0, []

    async def delete(self, *keys: object) -> int:
        return 0

    async def aclose(self) -> None:
        self.closed = True


def test_redis_smoke_opt_in_defaults_false() -> None:
    from scripts import steamdt_redis_limiter_smoke as smoke

    assert smoke.parse_bool_env({}, smoke.RUN_REDIS_INTEGRATION_ENV) is False


def test_redis_smoke_async_guard_does_not_create_client() -> None:
    from scripts import steamdt_redis_limiter_smoke as smoke

    messages: list[str] = []

    def forbidden_factory(_url: str) -> object:
        raise AssertionError("Redis client must not be created when guard is false")

    exit_code = asyncio.run(
        smoke.async_main(
            {smoke.RUN_REDIS_INTEGRATION_ENV: "false"},
            printer=messages.append,
            redis_factory=forbidden_factory,
        )
    )

    assert exit_code == 0
    assert "STEAMDT_RUN_REDIS_INTEGRATION_TESTS is not true" in "\n".join(messages)


@pytest.mark.parametrize("entrypoint", ["direct", "module"])
def test_redis_smoke_script_entrypoints_guard_without_redis_connection(entrypoint: str) -> None:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["STEAMDT_RUN_REDIS_INTEGRATION_TESTS"] = "false"
    env.pop("STEAMDT_TEST_REDIS_URL", None)

    if entrypoint == "direct":
        command = [sys.executable, "scripts/steamdt_redis_limiter_smoke.py"]
    else:
        command = [sys.executable, "-m", "scripts.steamdt_redis_limiter_smoke"]

    result = subprocess.run(
        command,
        cwd=project_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    combined_output = f"{result.stdout}\n{result.stderr}"

    assert result.returncode == 0
    assert "STEAMDT_RUN_REDIS_INTEGRATION_TESTS is not true" in combined_output
    assert "ModuleNotFoundError" not in combined_output
    assert "redis://" not in combined_output
    assert "Authorization:" not in combined_output


def test_redis_smoke_invalid_namespace_is_rejected_before_connection() -> None:
    from scripts import steamdt_redis_limiter_smoke as smoke

    created = False
    messages: list[str] = []

    def forbidden_factory(_url: str) -> object:
        nonlocal created
        created = True
        raise AssertionError("Redis client must not be created before namespace validation")

    exit_code = asyncio.run(
        smoke.async_main(
            {
                smoke.RUN_REDIS_INTEGRATION_ENV: "true",
                smoke.TEST_REDIS_NAMESPACE_ENV: "bad{namespace",
            },
            printer=messages.append,
            redis_factory=forbidden_factory,
        )
    )

    assert exit_code == 1
    assert created is False
    assert "namespace" in "\n".join(messages)


def test_redact_redis_url_hides_password_and_query_values() -> None:
    from scripts.steamdt_redis_limiter_smoke import redact_redis_url

    redacted = redact_redis_url(
        "redis://user:dummy-password@localhost:6379/15?token=dummy-token"
    )

    assert "dummy-password" not in redacted
    assert "dummy-token" not in redacted
    assert "redis://user:[REDACTED]@localhost:6379/15" in redacted


def test_safe_redis_error_message_hides_password_and_authorization() -> None:
    from scripts.steamdt_redis_limiter_smoke import safe_redis_error_message

    redis_url = "redis://user:dummy-password@localhost:6379/15?token=dummy-token"
    message = safe_redis_error_message(
        ConnectionError(f"failed {redis_url} Authorization: Bearer dummy-token-123456"),
        redis_url=redis_url,
    )

    assert "dummy-password" not in message
    assert "dummy-token" not in message
    assert "Authorization:" not in message


def test_cleanup_pattern_is_exact_to_current_namespace() -> None:
    from scripts.steamdt_redis_limiter_smoke import build_namespace_scan_pattern

    assert build_namespace_scan_pattern("steamdt-rate-limit-integration-v1-test") == (
        "{steamdt-rate-limit-integration-v1-test:*}:*"
    )


def test_cleanup_helper_uses_scan_pagination_and_only_deletes_matching_keys() -> None:
    from scripts.steamdt_redis_limiter_smoke import cleanup_namespace_keys

    redis = FakeCleanupRedis(
        pages=[
            (
                1,
                [
                    b"{steamdt-rate-limit-integration-v1-test:price_single}:requests",
                    b"{other-namespace:price_single}:requests",
                ],
            ),
            (
                0,
                [
                    "{steamdt-rate-limit-integration-v1-test:price_batch}:blocked",
                    "not-a-matching-key",
                ],
            ),
        ]
    )

    deleted_count = asyncio.run(
        cleanup_namespace_keys(redis, "steamdt-rate-limit-integration-v1-test")
    )

    assert deleted_count == 2
    assert redis.deleted == [
        b"{steamdt-rate-limit-integration-v1-test:price_single}:requests",
        "{steamdt-rate-limit-integration-v1-test:price_batch}:blocked",
    ]
    assert len(redis.scan_calls) == 2
    assert redis.flushdb_called is False
    assert redis.flushall_called is False


def test_cleanup_helper_handles_no_matching_keys() -> None:
    from scripts.steamdt_redis_limiter_smoke import cleanup_namespace_keys

    redis = FakeCleanupRedis(pages=[(0, ["{other:price_single}:requests"])])

    deleted_count = asyncio.run(
        cleanup_namespace_keys(redis, "steamdt-rate-limit-integration-v1-test")
    )

    assert deleted_count == 0
    assert redis.deleted == []


def test_smoke_harness_does_not_import_or_call_steamdt_http_client() -> None:
    from scripts import steamdt_redis_limiter_smoke as smoke

    script_path = Path(smoke.__file__)
    script_text = script_path.read_text(encoding="utf-8")

    assert "SteamDTHttpClient" not in script_text
    assert "SteamDTClientConfig" not in script_text


def test_redis_smoke_failure_returns_non_zero_and_redacts_url() -> None:
    from scripts import steamdt_redis_limiter_smoke as smoke

    fake_client = FakeFailingRedis()
    redis_url = "redis://user:dummy-password@localhost:6379/15?token=dummy-token"
    messages: list[str] = []

    exit_code = asyncio.run(
        smoke.async_main(
            {
                smoke.RUN_REDIS_INTEGRATION_ENV: "true",
                smoke.TEST_REDIS_URL_ENV: redis_url,
                smoke.TEST_REDIS_NAMESPACE_ENV: smoke.DEFAULT_TEST_REDIS_NAMESPACE,
            },
            printer=messages.append,
            redis_factory=lambda _url: fake_client,
        )
    )
    combined_output = "\n".join(messages)

    assert exit_code == 1
    assert fake_client.closed is True
    assert "dummy-password" not in combined_output
    assert "dummy-token" not in combined_output
    assert "Authorization:" not in combined_output


def test_default_redis_integration_env_does_not_connect_real_redis() -> None:
    from scripts import steamdt_redis_limiter_smoke as smoke

    calls: list[str] = []

    exit_code = asyncio.run(
        smoke.async_main(
            {},
            printer=lambda message: calls.append(message),
            redis_factory=lambda _url: (_ for _ in ()).throw(AssertionError("no Redis")),
        )
    )

    assert exit_code == 0
    assert calls
