import asyncio
import os
import uuid
from collections.abc import Callable

import pytest

from app.clients.steamdt_errors import SteamDTRateLimitError
from app.services.steamdt_rate_limiter import SteamDTEndpoint
from scripts import steamdt_redis_limiter_smoke as smoke

RUN_INTEGRATION = (
    os.getenv("STEAMDT_RUN_REDIS_INTEGRATION_TESTS", "").strip().lower() == "true"
)
pytestmark = pytest.mark.skipif(
    not RUN_INTEGRATION,
    reason="Redis integration tests require explicit opt-in",
)


async def _with_redis_client(callback: Callable[[object], object]) -> object:
    from redis.asyncio import Redis

    redis_url = os.getenv("STEAMDT_TEST_REDIS_URL", smoke.DEFAULT_TEST_REDIS_URL)
    client = Redis.from_url(redis_url)
    try:
        return await callback(client)
    finally:
        await client.aclose()


async def _with_namespace(
    redis_client: object,
    callback: Callable[[str], object],
) -> object:
    namespace = smoke.build_test_namespace(
        os.getenv("STEAMDT_TEST_REDIS_NAMESPACE"),
        suffix=uuid.uuid4().hex,
    )
    await smoke.cleanup_namespace_keys(redis_client, namespace)
    try:
        return await callback(namespace)
    finally:
        await smoke.cleanup_namespace_keys(redis_client, namespace)
        assert await smoke._namespace_key_count(redis_client, namespace) == 0


def _limiter(redis_client: object, namespace: str) -> smoke.RedisSteamDTRateLimiter:
    return smoke.RedisSteamDTRateLimiter(
        redis_client,
        smoke.build_test_policies(),
        namespace=namespace,
    )


def test_two_instances_share_price_batch_quota() -> None:
    async def run(redis_client: object) -> None:
        async def scenario(namespace: str) -> None:
            limiter_a = _limiter(redis_client, namespace)
            limiter_b = _limiter(redis_client, namespace)

            await limiter_a.acquire(SteamDTEndpoint.PRICE_BATCH)

            with pytest.raises(SteamDTRateLimitError) as exc_info:
                await limiter_b.acquire(SteamDTEndpoint.PRICE_BATCH)
            assert exc_info.value.retry_after_seconds is not None
            assert exc_info.value.retry_after_seconds > 0

        await _with_namespace(redis_client, scenario)

    asyncio.run(_with_redis_client(run))


def test_endpoint_independence() -> None:
    async def run(redis_client: object) -> None:
        async def scenario(namespace: str) -> None:
            limiter = _limiter(redis_client, namespace)

            await limiter.acquire(SteamDTEndpoint.PRICE_BATCH)
            with pytest.raises(SteamDTRateLimitError):
                await limiter.acquire(SteamDTEndpoint.PRICE_BATCH)

            await limiter.acquire(SteamDTEndpoint.PRICE_SINGLE)
            await limiter.acquire(SteamDTEndpoint.PRICE_SINGLE)
            with pytest.raises(SteamDTRateLimitError):
                await limiter.acquire(SteamDTEndpoint.PRICE_SINGLE)

            await limiter.acquire(SteamDTEndpoint.PRICE_AVG)

        await _with_namespace(redis_client, scenario)

    asyncio.run(_with_redis_client(run))


def test_window_expiry() -> None:
    async def run(redis_client: object) -> None:
        async def scenario(namespace: str) -> None:
            limiter = _limiter(redis_client, namespace)

            await limiter.acquire(SteamDTEndpoint.PRICE_BATCH)
            with pytest.raises(SteamDTRateLimitError):
                await limiter.acquire(SteamDTEndpoint.PRICE_BATCH)

            await asyncio.sleep(2.3)
            await limiter.acquire(SteamDTEndpoint.PRICE_BATCH)

        await _with_namespace(redis_client, scenario)

    asyncio.run(_with_redis_client(run))


def test_shared_server_block() -> None:
    async def run(redis_client: object) -> None:
        async def scenario(namespace: str) -> None:
            limiter_a = _limiter(redis_client, namespace)
            limiter_b = _limiter(redis_client, namespace)

            await limiter_a.record_server_limit(
                SteamDTEndpoint.PRICE_BATCH,
                retry_after_seconds=0.5,
            )

            with pytest.raises(SteamDTRateLimitError):
                await limiter_b.acquire(SteamDTEndpoint.PRICE_BATCH)
            await limiter_b.acquire(SteamDTEndpoint.PRICE_SINGLE)
            await asyncio.sleep(0.6)
            await limiter_b.acquire(SteamDTEndpoint.PRICE_BATCH)

        await _with_namespace(redis_client, scenario)

    asyncio.run(_with_redis_client(run))


def test_longer_block_wins() -> None:
    async def run(redis_client: object) -> None:
        async def scenario(namespace: str) -> None:
            limiter_a = _limiter(redis_client, namespace)
            limiter_b = _limiter(redis_client, namespace)

            await limiter_a.record_server_limit(
                SteamDTEndpoint.PRICE_BATCH,
                retry_after_seconds=1.2,
            )
            await asyncio.sleep(0.1)
            await limiter_b.record_server_limit(
                SteamDTEndpoint.PRICE_BATCH,
                retry_after_seconds=0.2,
            )

            with pytest.raises(SteamDTRateLimitError) as exc_info:
                await limiter_b.acquire(SteamDTEndpoint.PRICE_BATCH)
            assert exc_info.value.retry_after_seconds is not None
            assert exc_info.value.retry_after_seconds >= 0.8

        await _with_namespace(redis_client, scenario)

    asyncio.run(_with_redis_client(run))


def test_ttls_are_positive() -> None:
    async def run(redis_client: object) -> None:
        async def scenario(namespace: str) -> None:
            limiter = _limiter(redis_client, namespace)

            await limiter.acquire(SteamDTEndpoint.PRICE_SINGLE)
            requests_key, _blocked_key = limiter.keys_for_endpoint(SteamDTEndpoint.PRICE_SINGLE)
            await limiter.record_server_limit(
                SteamDTEndpoint.PRICE_BATCH,
                retry_after_seconds=1.0,
            )
            _batch_requests_key, blocked_key = limiter.keys_for_endpoint(
                SteamDTEndpoint.PRICE_BATCH
            )

            assert await redis_client.pttl(requests_key) > 0
            assert await redis_client.pttl(blocked_key) > 0

        await _with_namespace(redis_client, scenario)

    asyncio.run(_with_redis_client(run))


def test_same_millisecond_request_members_do_not_collide() -> None:
    async def run(redis_client: object) -> None:
        async def scenario(namespace: str) -> None:
            limiter_a = _limiter(redis_client, namespace)
            limiter_b = _limiter(redis_client, namespace)

            await asyncio.gather(
                limiter_a.acquire(SteamDTEndpoint.PRICE_SINGLE),
                limiter_b.acquire(SteamDTEndpoint.PRICE_SINGLE),
            )

            requests_key, _blocked_key = limiter_a.keys_for_endpoint(SteamDTEndpoint.PRICE_SINGLE)
            assert await redis_client.zcard(requests_key) == 2
            with pytest.raises(SteamDTRateLimitError):
                await limiter_a.acquire(SteamDTEndpoint.PRICE_SINGLE)

        await _with_namespace(redis_client, scenario)

    asyncio.run(_with_redis_client(run))


def test_namespace_cleanup() -> None:
    async def run(redis_client: object) -> None:
        async def scenario(namespace: str) -> None:
            limiter = _limiter(redis_client, namespace)
            await limiter.acquire(SteamDTEndpoint.PRICE_SINGLE)

            assert await smoke._namespace_key_count(redis_client, namespace) > 0
            await smoke.cleanup_namespace_keys(redis_client, namespace)

            assert await smoke._namespace_key_count(redis_client, namespace) == 0

        await _with_namespace(redis_client, scenario)

    asyncio.run(_with_redis_client(run))


def test_smoke_harness_closes_owned_client(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOwnedClient:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    owned = FakeOwnedClient()

    async def fake_run(redis_client: object, *, namespace: str, printer=print) -> None:
        assert redis_client is owned
        assert namespace.startswith(smoke.DEFAULT_TEST_REDIS_NAMESPACE)

    monkeypatch.setattr(smoke, "run_redis_limiter_smoke", fake_run)

    exit_code = asyncio.run(
        smoke.async_main(
            {
                smoke.RUN_REDIS_INTEGRATION_ENV: "true",
                smoke.TEST_REDIS_URL_ENV: smoke.DEFAULT_TEST_REDIS_URL,
                smoke.TEST_REDIS_NAMESPACE_ENV: smoke.DEFAULT_TEST_REDIS_NAMESPACE,
            },
            printer=lambda _message: None,
            redis_factory=lambda _url: owned,
        )
    )

    assert exit_code == 0
    assert owned.closed is True
