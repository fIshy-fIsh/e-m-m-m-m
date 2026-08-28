import asyncio
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import app.services.price_cache_factory as price_cache_factory_module
from app.config import Settings
from app.services.price_cache import InMemoryPriceCache, PriceCache
from app.services.price_cache_factory import (
    SteamDTPriceCacheCompositionError,
    SteamDTPriceCacheConstructionCleanupError,
    SteamDTPriceCacheContextExitError,
    SteamDTPriceCacheRuntime,
    SteamDTPriceCacheRuntimeCloseError,
    create_steamdt_price_cache_runtime,
)
from app.services.redis_price_cache import (
    DEFAULT_REDIS_PRICE_CACHE_NAMESPACE,
    RedisPriceCache,
)


class FakeRedisClient:
    def __init__(self, *, close_error: Exception | None = None) -> None:
        self.close_error = close_error
        self.eval_calls = 0
        self.scan_calls = 0
        self.delete_calls = 0
        self.ping_calls = 0
        self.time_calls = 0
        self.close_calls = 0

    async def eval(self, script: str, numkeys: int, *args: object) -> object:
        self.eval_calls += 1
        raise AssertionError("factory construction must not call EVAL")

    async def scan(
        self,
        cursor: int = 0,
        *,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[bytes | str]]:
        self.scan_calls += 1
        raise AssertionError("factory construction must not call SCAN")

    async def delete(self, *names: str | bytes) -> object:
        self.delete_calls += 1
        raise AssertionError("factory construction must not call DELETE")

    async def ping(self) -> bool:
        self.ping_calls += 1
        raise AssertionError("factory construction must not call PING")

    async def time(self) -> tuple[int, int]:
        self.time_calls += 1
        raise AssertionError("factory construction must not call TIME")

    async def aclose(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


class LegacyCloseRedisClient(FakeRedisClient):
    aclose = None

    def close(self) -> None:
        self.close_calls += 1


class BusinessError(RuntimeError):
    pass


class BlockingCloseRedisClient(FakeRedisClient):
    def __init__(self, *, close_error: Exception | None = None) -> None:
        super().__init__(close_error=close_error)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def aclose(self) -> None:
        self.close_calls += 1
        self.started.set()
        await self.release.wait()
        if self.close_error is not None:
            raise self.close_error


def _settings(
    *,
    backend: str = "inmemory",
    redis_url: str = "redis://redis:6379/0",
    namespace: str = DEFAULT_REDIS_PRICE_CACHE_NAMESPACE,
) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://cs2bot:password@postgres:5432/cs2tradeup",
        redis_url=redis_url,
        bymykel_base_url="https://example.test",
        steamdt_price_cache_backend=backend,
        steamdt_price_cache_redis_namespace=namespace,
    )


def _run_create(
    settings: Settings,
    **kwargs: Any,
) -> SteamDTPriceCacheRuntime:
    return asyncio.run(create_steamdt_price_cache_runtime(settings, **kwargs))


def _assert_no_commands(client: FakeRedisClient) -> None:
    assert client.eval_calls == 0
    assert client.scan_calls == 0
    assert client.delete_calls == 0
    assert client.ping_calls == 0
    assert client.time_calls == 0


def test_default_backend_creates_inmemory_cache_without_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def redis_factory(_url: str) -> FakeRedisClient:
        raise AssertionError("default backend must not create Redis")

    monkeypatch.setattr(
        price_cache_factory_module,
        "_create_redis_client_from_url",
        redis_factory,
    )
    runtime = _run_create(_settings())

    assert isinstance(runtime.cache, InMemoryPriceCache)
    assert runtime.redis_client is None
    assert runtime.owns_redis_client is False


@pytest.mark.parametrize("backend", ["inmemory", " INMEMORY "])
def test_explicit_inmemory_backend_is_normalized(backend: str) -> None:
    runtime = _run_create(_settings(backend=backend))

    assert isinstance(runtime.cache, InMemoryPriceCache)


@pytest.mark.parametrize("backend", ["redis", " REDIS "])
def test_explicit_redis_backend_is_normalized(backend: str) -> None:
    client = FakeRedisClient()

    runtime = _run_create(_settings(backend=backend), redis_client=client)

    assert isinstance(runtime.cache, RedisPriceCache)
    assert runtime.cache.redis_client is client
    assert runtime.redis_client is client
    assert runtime.owns_redis_client is False
    _assert_no_commands(client)


@pytest.mark.parametrize("backend", ["", "memory", "filesystem"])
def test_unsupported_backend_is_composition_error(backend: str) -> None:
    with pytest.raises(SteamDTPriceCacheCompositionError, match="unsupported"):
        _run_create(_settings(backend=backend))


@pytest.mark.parametrize(
    "redis_url",
    ["", "not-a-url", "http://localhost:6379", "redis:///0", "redis://host:0"],
)
def test_missing_or_malformed_redis_url_is_rejected(redis_url: str) -> None:
    with pytest.raises(SteamDTPriceCacheCompositionError, match="redis_url"):
        _run_create(_settings(backend="redis", redis_url=redis_url))


@pytest.mark.parametrize(
    "namespace",
    ["", " ", "has space", "glob*", "glob?", "glob[", "{tag}", "line\nbreak"],
)
def test_invalid_namespace_fails_before_client_creation(namespace: str) -> None:
    calls = 0

    def redis_factory(_url: str) -> FakeRedisClient:
        nonlocal calls
        calls += 1
        return FakeRedisClient()

    with pytest.raises(SteamDTPriceCacheCompositionError, match="namespace"):
        _run_create(
            _settings(backend="redis", namespace=namespace),
            redis_client_factory=redis_factory,
        )

    assert calls == 0


def test_valid_namespace_is_normalized_and_passed_to_cache() -> None:
    client = FakeRedisClient()

    runtime = _run_create(
        _settings(backend="redis", namespace=" custom.cache-v1 "),
        redis_client=client,
    )

    assert isinstance(runtime.cache, RedisPriceCache)
    assert runtime.cache.namespace == "custom.cache-v1"


def test_factory_created_client_uses_formal_url_and_is_owned() -> None:
    client = FakeRedisClient()
    urls: list[str] = []

    def redis_factory(url: str) -> FakeRedisClient:
        urls.append(url)
        return client

    runtime = _run_create(
        _settings(backend="redis", redis_url=" redis://cache.test:6379/4 "),
        redis_client_factory=redis_factory,
    )

    assert urls == ["redis://cache.test:6379/4"]
    assert runtime.redis_client is client
    assert runtime.owns_redis_client is True
    _assert_no_commands(client)


def test_external_client_makes_formal_url_irrelevant() -> None:
    client = FakeRedisClient()

    runtime = _run_create(
        _settings(backend="redis", redis_url="malformed-production-url"),
        redis_client=client,
    )

    assert runtime.redis_client is client
    assert runtime.owns_redis_client is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"redis_client": FakeRedisClient()}, "redis_client cannot"),
        ({"redis_client_factory": lambda _url: FakeRedisClient()}, "redis_client_factory"),
        (
            {"redis_price_cache_factory": lambda *_args, **_kwargs: None},
            "redis_price_cache_factory",
        ),
        ({"redis_client_owned": True}, "requires an injected"),
    ],
)
def test_inmemory_rejects_redis_arguments(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(SteamDTPriceCacheCompositionError, match=message):
        _run_create(_settings(), **kwargs)


def test_inmemory_rejects_owned_injected_client_and_closes_it() -> None:
    client = FakeRedisClient()

    with pytest.raises(SteamDTPriceCacheCompositionError, match="redis_client cannot"):
        _run_create(
            _settings(),
            redis_client=client,
            redis_client_owned=True,
        )

    assert client.close_calls == 1


def test_injected_client_and_client_factory_are_rejected() -> None:
    with pytest.raises(SteamDTPriceCacheCompositionError, match="cannot both"):
        _run_create(
            _settings(backend="redis"),
            redis_client=FakeRedisClient(),
            redis_client_factory=lambda _url: FakeRedisClient(),
        )


def test_redis_backend_rejects_inmemory_clock() -> None:
    client = FakeRedisClient()

    with pytest.raises(SteamDTPriceCacheCompositionError, match="clock cannot"):
        _run_create(
            _settings(backend="redis"),
            redis_client=client,
            clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        )

    assert client.close_calls == 0


def test_factory_creation_does_not_issue_redis_commands() -> None:
    client = FakeRedisClient()

    runtime = _run_create(
        _settings(backend="redis"),
        redis_client_factory=lambda _url: client,
    )

    assert isinstance(runtime.cache, RedisPriceCache)
    _assert_no_commands(client)
    assert client.close_calls == 0


def test_factory_created_client_is_closed_once() -> None:
    client = FakeRedisClient()
    runtime = _run_create(
        _settings(backend="redis"),
        redis_client_factory=lambda _url: client,
    )

    asyncio.run(runtime.aclose())
    asyncio.run(runtime.aclose())

    assert client.close_calls == 1


def test_external_client_is_not_closed_by_default() -> None:
    client = FakeRedisClient()
    runtime = _run_create(_settings(backend="redis"), redis_client=client)

    asyncio.run(runtime.aclose())

    assert client.close_calls == 0


def test_owned_external_client_is_closed_once() -> None:
    client = FakeRedisClient()
    runtime = _run_create(
        _settings(backend="redis"),
        redis_client=client,
        redis_client_owned=True,
    )

    asyncio.run(runtime.aclose())
    asyncio.run(runtime.aclose())

    assert client.close_calls == 1


def test_inmemory_runtime_close_is_idempotent() -> None:
    runtime = _run_create(_settings())

    asyncio.run(runtime.aclose())
    asyncio.run(runtime.aclose())

    assert runtime.redis_client is None


@pytest.mark.parametrize("fail_close", [False, True])
def test_concurrent_aclose_callers_wait_for_and_share_one_result(
    fail_close: bool,
) -> None:
    underlying_error = RuntimeError("redis close failed") if fail_close else None
    client = BlockingCloseRedisClient(close_error=underlying_error)
    runtime = _run_create(
        _settings(backend="redis"),
        redis_client=client,
        redis_client_owned=True,
    )

    async def close_concurrently() -> tuple[list[object], object]:
        callers = [asyncio.create_task(runtime.aclose()) for _ in range(3)]
        await client.started.wait()
        await asyncio.sleep(0)
        assert client.close_calls == 1
        assert all(not caller.done() for caller in callers)
        client.release.set()
        results = await asyncio.gather(*callers, return_exceptions=True)
        try:
            await runtime.aclose()
        except Exception as exc:
            completed_result: object = exc
        else:
            completed_result = None
        return results, completed_result

    results, completed_result = asyncio.run(close_concurrently())

    assert client.close_calls == 1
    if fail_close:
        assert all(
            isinstance(result, SteamDTPriceCacheRuntimeCloseError)
            for result in results
        )
        errors = [
            result
            for result in results
            if isinstance(result, SteamDTPriceCacheRuntimeCloseError)
        ]
        assert errors[0] is errors[1] is errors[2] is completed_result
        assert errors[0].close_error is underlying_error
    else:
        assert results == [None, None, None]
        assert completed_result is None


def test_async_context_manager_closes_owned_client() -> None:
    client = FakeRedisClient()
    runtime = _run_create(
        _settings(backend="redis"),
        redis_client_factory=lambda _url: client,
    )

    async def use_runtime() -> None:
        async with runtime as entered:
            assert entered is runtime
            assert client.close_calls == 0

    asyncio.run(use_runtime())

    assert client.close_calls == 1


def test_context_manager_preserves_body_and_close_failures() -> None:
    body_error = BusinessError("business-secret")
    underlying_close_error = RuntimeError("redis-close-secret")
    client = FakeRedisClient(close_error=underlying_close_error)
    runtime = _run_create(
        _settings(backend="redis"),
        redis_client=client,
        redis_client_owned=True,
    )

    async def use_runtime() -> None:
        async with runtime:
            raise body_error

    with pytest.raises(SteamDTPriceCacheContextExitError) as exc_info:
        asyncio.run(use_runtime())

    error = exc_info.value
    formatted = "".join(traceback.format_exception(error))
    assert error.body_error is body_error
    assert isinstance(error.close_error, SteamDTPriceCacheRuntimeCloseError)
    assert error.close_error.close_error is underlying_close_error
    assert "business-secret" not in str(error)
    assert "redis-close-secret" not in str(error)
    assert "business-secret" not in formatted
    assert "redis-close-secret" not in formatted
    assert client.close_calls == 1


def test_context_manager_propagates_body_error_when_close_succeeds() -> None:
    body_error = BusinessError("business failed")
    client = FakeRedisClient()
    runtime = _run_create(
        _settings(backend="redis"),
        redis_client=client,
        redis_client_owned=True,
    )

    async def use_runtime() -> None:
        async with runtime:
            raise body_error

    with pytest.raises(BusinessError) as exc_info:
        asyncio.run(use_runtime())

    assert exc_info.value is body_error
    assert client.close_calls == 1


def test_context_manager_propagates_close_error_without_body_error() -> None:
    underlying_close_error = RuntimeError("redis close failed")
    client = FakeRedisClient(close_error=underlying_close_error)
    runtime = _run_create(
        _settings(backend="redis"),
        redis_client=client,
        redis_client_owned=True,
    )

    async def use_runtime() -> None:
        async with runtime:
            pass

    with pytest.raises(SteamDTPriceCacheRuntimeCloseError) as exc_info:
        asyncio.run(use_runtime())

    assert exc_info.value.close_error is underlying_close_error
    assert client.close_calls == 1


def test_runtime_supports_legacy_synchronous_close() -> None:
    client = LegacyCloseRedisClient()
    runtime = _run_create(
        _settings(backend="redis"),
        redis_client=client,
        redis_client_owned=True,
    )

    asyncio.run(runtime.aclose())

    assert client.close_calls == 1


def test_runtime_close_failure_is_safe_inspectable_and_not_retried() -> None:
    password = "dummy-close-password"
    close_error = RuntimeError(f"redis://user:{password}@localhost/0")
    client = FakeRedisClient(close_error=close_error)
    runtime = _run_create(
        _settings(backend="redis"),
        redis_client=client,
        redis_client_owned=True,
    )

    with pytest.raises(SteamDTPriceCacheRuntimeCloseError) as exc_info:
        asyncio.run(runtime.aclose())

    assert exc_info.value.close_error is close_error
    assert password not in str(exc_info.value)
    assert password not in "".join(traceback.format_exception(exc_info.value))
    with pytest.raises(SteamDTPriceCacheRuntimeCloseError) as repeated_exc_info:
        asyncio.run(runtime.aclose())
    assert repeated_exc_info.value is exc_info.value
    assert client.close_calls == 1


def test_factory_created_client_is_closed_when_cache_construction_fails() -> None:
    client = FakeRedisClient()
    construction_error = RuntimeError("cache construction failed")

    def fail_cache(
        _client: FakeRedisClient,
        *,
        namespace: str,
    ) -> PriceCache:
        raise construction_error

    with pytest.raises(SteamDTPriceCacheCompositionError) as exc_info:
        _run_create(
            _settings(backend="redis"),
            redis_client_factory=lambda _url: client,
            redis_price_cache_factory=fail_cache,
        )

    assert exc_info.value.original_error is construction_error
    assert client.close_calls == 1


@pytest.mark.parametrize("owned", [False, True])
def test_external_client_construction_failure_obeys_ownership(owned: bool) -> None:
    client = FakeRedisClient()

    def fail_cache(
        _client: FakeRedisClient,
        *,
        namespace: str,
    ) -> PriceCache:
        raise RuntimeError("cache construction failed")

    with pytest.raises(SteamDTPriceCacheCompositionError):
        _run_create(
            _settings(backend="redis"),
            redis_client=client,
            redis_client_owned=owned,
            redis_price_cache_factory=fail_cache,
        )

    assert client.close_calls == int(owned)


def test_construction_and_cleanup_errors_are_both_inspectable_and_safe() -> None:
    construction_secret = "dummy-construction-secret"
    cleanup_secret = "dummy-cleanup-secret"
    construction_error = RuntimeError(
        f"Authorization: Bearer {construction_secret}"
    )
    cleanup_error = RuntimeError(
        f"redis://user:{cleanup_secret}@localhost/0"
    )
    client = FakeRedisClient(close_error=cleanup_error)

    def fail_cache(
        _client: FakeRedisClient,
        *,
        namespace: str,
    ) -> PriceCache:
        raise construction_error

    with pytest.raises(SteamDTPriceCacheConstructionCleanupError) as exc_info:
        _run_create(
            _settings(backend="redis"),
            redis_client_factory=lambda _url: client,
            redis_price_cache_factory=fail_cache,
        )

    error = exc_info.value
    formatted = "".join(traceback.format_exception(error))
    assert error.construction_error is construction_error
    assert error.cleanup_error is cleanup_error
    assert construction_secret not in str(error)
    assert cleanup_secret not in str(error)
    assert construction_secret not in formatted
    assert cleanup_secret not in formatted
    assert client.close_calls == 1


def test_client_factory_error_does_not_leak_url_or_credentials() -> None:
    password = "dummy-password"
    query_token = "dummy-query-token"
    bearer_token = "dummy-bearer-token"
    redis_url = (
        f"rediss://user:{password}@localhost:6379/0?token={query_token}"
    )
    factory_error = RuntimeError(
        f"cannot create {redis_url}; Authorization: Bearer {bearer_token}"
    )

    def fail_client(_url: str) -> FakeRedisClient:
        raise factory_error

    with pytest.raises(SteamDTPriceCacheCompositionError) as exc_info:
        _run_create(
            _settings(backend="redis", redis_url=redis_url),
            redis_client_factory=fail_client,
        )

    public_text = str(exc_info.value)
    formatted = "".join(traceback.format_exception(exc_info.value))
    assert exc_info.value.original_error is factory_error
    for secret in (password, query_token, bearer_token, redis_url):
        assert secret not in public_text
        assert secret not in formatted


def test_direct_cache_construction_remains_compatible() -> None:
    client = FakeRedisClient()

    assert isinstance(InMemoryPriceCache(), InMemoryPriceCache)
    cache = RedisPriceCache(client)
    assert cache.redis_client is client
    _assert_no_commands(client)


def test_pipeline_and_scheduler_do_not_import_cache_factory() -> None:
    for path in (
        Path("app/services/pipeline_service.py"),
        Path("app/services/pipeline_alert_service.py"),
        Path("app/jobs/scheduler.py"),
    ):
        assert "price_cache_factory" not in path.read_text(encoding="utf-8")
