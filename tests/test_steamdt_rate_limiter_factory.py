import asyncio
from typing import Any

import pytest

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.clients.steamdt_errors import SteamDTRateLimitBackendError, SteamDTRateLimitError
from app.config import Settings
from app.services.redis_steamdt_rate_limiter import RedisSteamDTRateLimiter
from app.services.steamdt_rate_limiter import InMemorySteamDTRateLimiter, SteamDTEndpoint
from app.services.steamdt_rate_limiter_factory import (
    DEFAULT_STEAMDT_RATE_LIMIT_REDIS_NAMESPACE,
    SteamDTClientCompositionError,
    SteamDTClientRuntime,
    SteamDTClientRuntimeCloseError,
    create_steamdt_client_runtime,
)


class FakeRedisClient:
    def __init__(self, *, fail_eval: bool = False, fail_close: bool = False) -> None:
        self.fail_eval = fail_eval
        self.fail_close = fail_close
        self.eval_calls: list[tuple[str, int, tuple[object, ...]]] = []
        self.closed_count = 0

    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object:
        self.eval_calls.append((script, numkeys, keys_and_args))
        if self.fail_eval:
            raise RuntimeError("redis backend failed")
        return [1, 0, 0]

    async def aclose(self) -> None:
        self.closed_count += 1
        if self.fail_close:
            raise RuntimeError("redis close failed")


class FakeHttpClient:
    def __init__(self, *, fail_close: bool = False) -> None:
        self.fail_close = fail_close
        self.closed_count = 0

    async def aclose(self) -> None:
        self.closed_count += 1
        if self.fail_close:
            raise RuntimeError("http close failed")


class FakeSteamDTHttpClient(SteamDTHttpClient):
    def __init__(
        self,
        config: SteamDTClientConfig,
        *,
        rate_limiter: object,
    ) -> None:
        self.config = config
        self.http_client = None
        self.rate_limiter = rate_limiter


def _settings(
    *,
    backend: str = "inmemory",
    redis_url: str = "redis://redis:6379/0",
    namespace: str = DEFAULT_STEAMDT_RATE_LIMIT_REDIS_NAMESPACE,
) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://cs2bot:password@postgres:5432/cs2tradeup",
        redis_url=redis_url,
        bymykel_base_url="https://example.test",
        steamdt_rate_limit_backend=backend,
        steamdt_rate_limit_redis_namespace=namespace,
    )


def _run_create(
    settings: Settings,
    **kwargs: Any,
) -> SteamDTClientRuntime:
    return asyncio.run(create_steamdt_client_runtime(settings, **kwargs))


def test_default_backend_creates_inmemory_limiter_without_redis() -> None:
    settings = _settings()

    def redis_factory(_url: str) -> FakeRedisClient:
        raise AssertionError("Redis factory must not be called for default backend")

    runtime = _run_create(settings, redis_client_factory=redis_factory)

    assert isinstance(runtime.rate_limiter, InMemorySteamDTRateLimiter)
    assert runtime.redis_client is None
    assert runtime.owns_redis_client is False
    assert isinstance(runtime.client.rate_limiter, InMemorySteamDTRateLimiter)


def test_explicit_inmemory_backend_creates_inmemory_limiter() -> None:
    runtime = _run_create(_settings(backend="inmemory"))

    assert isinstance(runtime.rate_limiter, InMemorySteamDTRateLimiter)
    assert runtime.client.rate_limiter is runtime.rate_limiter


def test_explicit_redis_backend_creates_redis_limiter() -> None:
    fake_redis = FakeRedisClient()

    runtime = _run_create(
        _settings(backend="redis"),
        redis_client_factory=lambda _url: fake_redis,
    )

    assert isinstance(runtime.rate_limiter, RedisSteamDTRateLimiter)
    assert runtime.redis_client is fake_redis
    assert runtime.owns_redis_client is True
    assert runtime.client.rate_limiter is runtime.rate_limiter
    assert runtime.rate_limiter.namespace == DEFAULT_STEAMDT_RATE_LIMIT_REDIS_NAMESPACE


@pytest.mark.parametrize("backend", ["memory", "", "REDIS "])
def test_unsupported_backend_is_rejected(backend: str) -> None:
    if backend.strip().lower() == "redis":
        return
    with pytest.raises(SteamDTClientCompositionError, match="unsupported"):
        _run_create(_settings(backend=backend))


def test_redis_backend_missing_redis_url_is_rejected() -> None:
    with pytest.raises(SteamDTClientCompositionError, match="redis_url is required"):
        _run_create(_settings(backend="redis", redis_url=""))


@pytest.mark.parametrize("redis_url", ["not-a-url", "http://localhost:6379", "redis:///0"])
def test_redis_backend_invalid_redis_url_is_rejected(redis_url: str) -> None:
    with pytest.raises(SteamDTClientCompositionError, match="redis_url"):
        _run_create(_settings(backend="redis", redis_url=redis_url))


def test_empty_redis_namespace_is_rejected() -> None:
    with pytest.raises(SteamDTClientCompositionError, match="namespace"):
        _run_create(_settings(backend="redis", namespace=" "), redis_client=FakeRedisClient())


def test_config_error_does_not_leak_redis_password_or_query_secret() -> None:
    redis_url = "redis://user:dummy-password@localhost:6379/0?token=dummy-token"

    def redis_factory(url: str) -> FakeRedisClient:
        raise RuntimeError(f"cannot connect to {url}")

    with pytest.raises(SteamDTClientCompositionError) as exc_info:
        _run_create(
            _settings(backend="redis", redis_url=redis_url),
            redis_client_factory=redis_factory,
        )

    error_text = str(exc_info.value)
    assert "dummy-password" not in error_text
    assert "dummy-token" not in error_text
    assert "redis://user:dummy-password" not in error_text
    assert "[REDACTED]" in error_text


def test_factory_created_redis_client_is_closed() -> None:
    fake_redis = FakeRedisClient()
    runtime = _run_create(
        _settings(backend="redis"),
        redis_client_factory=lambda _url: fake_redis,
    )

    asyncio.run(runtime.aclose())

    assert fake_redis.closed_count == 1


def test_external_redis_client_is_not_closed_by_default() -> None:
    fake_redis = FakeRedisClient()
    runtime = _run_create(_settings(backend="redis"), redis_client=fake_redis)

    asyncio.run(runtime.aclose())

    assert fake_redis.closed_count == 0


def test_external_redis_client_is_closed_when_owned() -> None:
    fake_redis = FakeRedisClient()
    runtime = _run_create(
        _settings(backend="redis"),
        redis_client=fake_redis,
        redis_client_owned=True,
    )

    asyncio.run(runtime.aclose())

    assert fake_redis.closed_count == 1


def test_runtime_aclose_is_idempotent() -> None:
    fake_http = FakeHttpClient()
    fake_redis = FakeRedisClient()
    runtime = _run_create(
        _settings(backend="redis"),
        http_client=fake_http,
        redis_client_factory=lambda _url: fake_redis,
    )

    asyncio.run(runtime.aclose())
    asyncio.run(runtime.aclose())

    assert fake_http.closed_count == 1
    assert fake_redis.closed_count == 1


def test_runtime_closes_http_client_before_owned_redis() -> None:
    events: list[str] = []

    class RecordingHttpClient(FakeHttpClient):
        async def aclose(self) -> None:
            events.append("http")
            await super().aclose()

    class RecordingRedisClient(FakeRedisClient):
        async def aclose(self) -> None:
            events.append("redis")
            await super().aclose()

    runtime = _run_create(
        _settings(backend="redis"),
        http_client=RecordingHttpClient(),
        redis_client_factory=lambda _url: RecordingRedisClient(),
    )

    asyncio.run(runtime.aclose())

    assert events == ["http", "redis"]


def test_http_close_failure_still_closes_owned_redis() -> None:
    fake_http = FakeHttpClient(fail_close=True)
    fake_redis = FakeRedisClient()
    runtime = _run_create(
        _settings(backend="redis"),
        http_client=fake_http,
        redis_client_factory=lambda _url: fake_redis,
    )

    with pytest.raises(SteamDTClientRuntimeCloseError) as exc_info:
        asyncio.run(runtime.aclose())

    assert isinstance(exc_info.value.http_error, RuntimeError)
    assert exc_info.value.redis_error is None
    assert fake_http.closed_count == 1
    assert fake_redis.closed_count == 1


def test_redis_close_failure_happens_after_http_client_is_closed() -> None:
    fake_http = FakeHttpClient()
    fake_redis = FakeRedisClient(fail_close=True)
    runtime = _run_create(
        _settings(backend="redis"),
        http_client=fake_http,
        redis_client_factory=lambda _url: fake_redis,
    )

    with pytest.raises(SteamDTClientRuntimeCloseError) as exc_info:
        asyncio.run(runtime.aclose())

    assert exc_info.value.http_error is None
    assert isinstance(exc_info.value.redis_error, RuntimeError)
    assert fake_http.closed_count == 1
    assert fake_redis.closed_count == 1


def test_both_close_failures_are_preserved() -> None:
    fake_http = FakeHttpClient(fail_close=True)
    fake_redis = FakeRedisClient(fail_close=True)
    runtime = _run_create(
        _settings(backend="redis"),
        http_client=fake_http,
        redis_client_factory=lambda _url: fake_redis,
    )

    with pytest.raises(
        SteamDTClientRuntimeCloseError,
        match="SteamDT HTTP client, Redis client",
    ) as exc_info:
        asyncio.run(runtime.aclose())

    assert isinstance(exc_info.value.http_error, RuntimeError)
    assert isinstance(exc_info.value.redis_error, RuntimeError)
    assert str(exc_info.value.http_error) == "http close failed"
    assert str(exc_info.value.redis_error) == "redis close failed"


def test_inmemory_runtime_close_closes_http_without_touching_redis() -> None:
    fake_http = FakeHttpClient()
    runtime = _run_create(_settings(backend="inmemory"), http_client=fake_http)

    asyncio.run(runtime.aclose())
    asyncio.run(runtime.aclose())

    assert fake_http.closed_count == 1
    assert runtime.redis_client is None


def test_async_context_manager_closes_complete_runtime() -> None:
    fake_http = FakeHttpClient()
    fake_redis = FakeRedisClient()
    runtime = _run_create(
        _settings(backend="redis"),
        http_client=fake_http,
        redis_client_factory=lambda _url: fake_redis,
    )

    async def use_runtime() -> None:
        async with runtime as entered:
            assert entered is runtime
            assert fake_http.closed_count == 0
            assert fake_redis.closed_count == 0

    asyncio.run(use_runtime())

    assert fake_http.closed_count == 1
    assert fake_redis.closed_count == 1


def test_inmemory_runtime_close_does_not_touch_redis() -> None:
    runtime = _run_create(_settings(backend="inmemory"))

    asyncio.run(runtime.aclose())
    asyncio.run(runtime.aclose())

    assert runtime.redis_client is None


def test_owned_redis_client_is_closed_when_client_construction_fails() -> None:
    fake_redis = FakeRedisClient()

    def failing_client_factory(
        _config: SteamDTClientConfig,
        *,
        http_client: object | None,
        rate_limiter: object,
    ) -> SteamDTHttpClient:
        raise RuntimeError("client construction failed")

    with pytest.raises(RuntimeError, match="client construction failed"):
        _run_create(
            _settings(backend="redis"),
            redis_client_factory=lambda _url: fake_redis,
            steamdt_client_factory=failing_client_factory,
        )

    assert fake_redis.closed_count == 1


def test_owned_external_client_is_closed_when_redis_composition_fails() -> None:
    fake_redis = FakeRedisClient()

    with pytest.raises(SteamDTClientCompositionError, match="namespace"):
        _run_create(
            _settings(backend="redis", namespace=" "),
            redis_client=fake_redis,
            redis_client_owned=True,
        )

    assert fake_redis.closed_count == 1


def test_inmemory_limiter_is_injected_into_client() -> None:
    runtime = _run_create(_settings(backend="inmemory"))

    assert runtime.client.rate_limiter is runtime.rate_limiter
    assert isinstance(runtime.client.rate_limiter, InMemorySteamDTRateLimiter)


def test_redis_limiter_is_injected_into_client() -> None:
    runtime = _run_create(
        _settings(backend="redis"),
        redis_client_factory=lambda _url: FakeRedisClient(),
    )

    assert runtime.client.rate_limiter is runtime.rate_limiter
    assert isinstance(runtime.client.rate_limiter, RedisSteamDTRateLimiter)


def test_direct_steamdt_http_client_construction_still_defaults_to_inmemory() -> None:
    client = SteamDTHttpClient(SteamDTClientConfig())

    assert isinstance(client.rate_limiter, InMemorySteamDTRateLimiter)


def test_redis_backend_error_does_not_fallback_to_inmemory() -> None:
    fake_redis = FakeRedisClient(fail_eval=True)
    runtime = _run_create(_settings(backend="redis"), redis_client=fake_redis)

    with pytest.raises(SteamDTRateLimitBackendError):
        asyncio.run(runtime.client.rate_limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))

    assert isinstance(runtime.client.rate_limiter, RedisSteamDTRateLimiter)
    assert not isinstance(runtime.client.rate_limiter, InMemorySteamDTRateLimiter)


def test_endpoint_specific_policies_are_preserved() -> None:
    settings = _settings(backend="inmemory")
    runtime = _run_create(settings)

    policies = runtime.client.config.rate_limit_policies
    assert policies[SteamDTEndpoint.PRICE_SINGLE].max_requests == 60
    assert policies[SteamDTEndpoint.PRICE_BATCH].max_requests == 1
    assert policies[SteamDTEndpoint.PRICE_BATCH].safety_buffer_seconds == 5.0
    assert policies[SteamDTEndpoint.PRICE_AVG].max_requests == 10


def test_factory_creation_does_not_request_steamdt() -> None:
    calls: list[str] = []

    def client_factory(
        config: SteamDTClientConfig,
        *,
        http_client: object | None,
        rate_limiter: object,
    ) -> SteamDTHttpClient:
        calls.append("construct")
        return FakeSteamDTHttpClient(config, rate_limiter=rate_limiter)

    runtime = _run_create(
        _settings(backend="inmemory"),
        steamdt_client_factory=client_factory,
    )

    assert calls == ["construct"]
    assert runtime.client.rate_limiter is runtime.rate_limiter


def test_default_factory_does_not_connect_to_redis() -> None:
    def redis_factory(_url: str) -> FakeRedisClient:
        raise AssertionError("default in-memory backend must not create Redis")

    runtime = _run_create(_settings(), redis_client_factory=redis_factory)

    assert runtime.redis_client is None


def test_configuration_errors_are_not_quota_errors() -> None:
    with pytest.raises(SteamDTClientCompositionError) as exc_info:
        _run_create(_settings(backend="redis", redis_url=""))

    assert not isinstance(exc_info.value, SteamDTRateLimitError)
