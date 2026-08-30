import asyncio
import inspect
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, cast
from urllib.parse import urlsplit

from app.services.price_cache import InMemoryPriceCache, PriceCache, UtcClock
from app.services.redis_price_cache import (
    AsyncRedisPriceCacheClient,
    RedisPriceCache,
    normalize_redis_price_cache_namespace,
)


class SteamDTPriceCacheBackend(StrEnum):
    """Supported price-cache backends for explicit SteamDT composition."""

    INMEMORY = "inmemory"
    REDIS = "redis"


class SteamDTPriceCacheCompositionError(RuntimeError):
    """Configuration or construction failure while composing a price cache."""

    def __init__(
        self,
        message: str,
        *,
        original_error: Exception | None = None,
    ) -> None:
        self.original_error = original_error
        super().__init__(message)


class SteamDTPriceCacheConstructionCleanupError(
    SteamDTPriceCacheCompositionError
):
    """Cache construction and owned Redis cleanup both failed."""

    def __init__(
        self,
        *,
        construction_error: Exception,
        cleanup_error: Exception,
    ) -> None:
        self.construction_error = construction_error
        self.cleanup_error = cleanup_error
        super().__init__(
            "SteamDT price-cache construction failed and owned Redis cleanup also failed",
            original_error=construction_error,
        )


class SteamDTPriceCacheRuntimeCloseError(RuntimeError):
    """An owned Redis client failed to close."""

    def __init__(self, *, close_error: Exception) -> None:
        self.close_error = close_error
        super().__init__(
            "failed to close owned Redis client for SteamDT price-cache runtime"
        )


class SteamDTPriceCacheContextExitError(RuntimeError):
    """The context body and owned runtime cleanup both failed."""

    def __init__(
        self,
        *,
        body_error: BaseException,
        close_error: SteamDTPriceCacheRuntimeCloseError,
    ) -> None:
        self.body_error = body_error
        self.close_error = close_error
        super().__init__(
            "SteamDT price-cache context body failed and runtime cleanup also failed"
        )


class SteamDTPriceCacheSettings(Protocol):
    """Narrow settings surface consumed by price-cache composition."""

    steamdt_price_cache_backend: str
    steamdt_price_cache_redis_namespace: str
    redis_url: str


class RedisPriceCacheClientFactory(Protocol):
    def __call__(self, redis_url: str) -> AsyncRedisPriceCacheClient:
        """Create a lazy async Redis client from the formal application URL."""


class RedisPriceCacheFactory(Protocol):
    def __call__(
        self,
        redis_client: AsyncRedisPriceCacheClient,
        *,
        namespace: str,
    ) -> PriceCache:
        """Construct a price cache without issuing a Redis command."""


@dataclass
class SteamDTPriceCacheRuntime:
    """Composed price cache with explicit optional Redis client ownership."""

    cache: PriceCache
    redis_client: AsyncRedisPriceCacheClient | None = field(default=None, repr=False)
    owns_redis_client: bool = False
    _close_task: asyncio.Task[None] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _close_complete: bool = field(default=False, init=False, repr=False)
    _close_error: SteamDTPriceCacheRuntimeCloseError | None = field(
        default=None,
        init=False,
        repr=False,
    )

    async def aclose(self) -> None:
        """Close the owned Redis client once and share its result with all callers."""

        if self._close_complete:
            if self._close_error is not None:
                raise self._close_error
            return
        close_task = self._close_task
        if close_task is None:
            close_task = asyncio.create_task(self._close_once())
            self._close_task = close_task
        await asyncio.shield(close_task)

    async def _close_once(self) -> None:
        try:
            if self.owns_redis_client and self.redis_client is not None:
                await _close_redis_client(self.redis_client)
        except Exception as exc:
            self._close_error = SteamDTPriceCacheRuntimeCloseError(close_error=exc)
            raise self._close_error from None
        finally:
            self._close_complete = True

    async def __aenter__(self) -> "SteamDTPriceCacheRuntime":
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        try:
            await self.aclose()
        except SteamDTPriceCacheRuntimeCloseError as close_error:
            if exc is None:
                raise
            raise SteamDTPriceCacheContextExitError(
                body_error=exc,
                close_error=close_error,
            ) from None


async def create_steamdt_price_cache_runtime(
    settings: SteamDTPriceCacheSettings,
    *,
    clock: UtcClock | None = None,
    redis_client: AsyncRedisPriceCacheClient | None = None,
    redis_client_owned: bool = False,
    redis_client_factory: RedisPriceCacheClientFactory | None = None,
    redis_price_cache_factory: RedisPriceCacheFactory | None = None,
) -> SteamDTPriceCacheRuntime:
    """Compose an explicitly selected price-cache backend without backend I/O."""

    owned_redis_client = (
        redis_client if redis_client is not None and redis_client_owned is True else None
    )
    try:
        backend = _parse_backend(settings.steamdt_price_cache_backend)
        _validate_common_arguments(
            redis_client=redis_client,
            redis_client_owned=redis_client_owned,
            redis_client_factory=redis_client_factory,
        )

        if backend == SteamDTPriceCacheBackend.INMEMORY:
            _validate_inmemory_arguments(
                redis_client=redis_client,
                redis_client_factory=redis_client_factory,
                redis_price_cache_factory=redis_price_cache_factory,
            )
            return SteamDTPriceCacheRuntime(cache=InMemoryPriceCache(clock=clock))

        if clock is not None:
            raise SteamDTPriceCacheCompositionError(
                "clock cannot be supplied when SteamDT price-cache backend is redis"
            )
        namespace = _normalize_namespace(settings.steamdt_price_cache_redis_namespace)

        runtime_redis_client = redis_client
        owns_redis_client = redis_client_owned
        if runtime_redis_client is None:
            redis_url = settings.redis_url.strip()
            if not redis_url:
                raise SteamDTPriceCacheCompositionError(
                    "redis_url is required when SteamDT price-cache backend is redis"
                )
            _validate_redis_url(redis_url)
            try:
                client_factory = redis_client_factory or _create_redis_client_from_url
                runtime_redis_client = client_factory(redis_url)
            except Exception as exc:
                raise SteamDTPriceCacheCompositionError(
                    "failed to create Redis client for SteamDT price cache: "
                    f"{type(exc).__name__}",
                    original_error=exc,
                ) from None
            if runtime_redis_client is None:
                raise SteamDTPriceCacheCompositionError(
                    "Redis client factory returned no client for SteamDT price cache"
                )
            owns_redis_client = True
            owned_redis_client = runtime_redis_client

        cache_factory = redis_price_cache_factory or _build_redis_price_cache
        cache = cache_factory(runtime_redis_client, namespace=namespace)
        return SteamDTPriceCacheRuntime(
            cache=cache,
            redis_client=runtime_redis_client,
            owns_redis_client=owns_redis_client,
        )
    except Exception as construction_error:
        if owned_redis_client is not None:
            try:
                await _close_redis_client(owned_redis_client)
            except Exception as cleanup_error:
                raise SteamDTPriceCacheConstructionCleanupError(
                    construction_error=construction_error,
                    cleanup_error=cleanup_error,
                ) from None
        if isinstance(construction_error, SteamDTPriceCacheCompositionError):
            raise construction_error from None
        raise SteamDTPriceCacheCompositionError(
            "failed to construct Redis price cache",
            original_error=construction_error,
        ) from None


def _parse_backend(raw_backend: str) -> SteamDTPriceCacheBackend:
    if not isinstance(raw_backend, str):
        raise SteamDTPriceCacheCompositionError(
            "steamdt_price_cache_backend must be a string"
        )
    backend = raw_backend.strip().lower()
    for candidate in SteamDTPriceCacheBackend:
        if backend == candidate.value:
            return candidate
    raise SteamDTPriceCacheCompositionError(
        "unsupported SteamDT price-cache backend: "
        f"{raw_backend!r}; expected 'inmemory' or 'redis'"
    )


def _validate_common_arguments(
    *,
    redis_client: AsyncRedisPriceCacheClient | None,
    redis_client_owned: bool,
    redis_client_factory: RedisPriceCacheClientFactory | None,
) -> None:
    if type(redis_client_owned) is not bool:
        raise SteamDTPriceCacheCompositionError("redis_client_owned must be a bool")
    if redis_client_owned and redis_client is None:
        raise SteamDTPriceCacheCompositionError(
            "redis_client_owned=true requires an injected redis_client"
        )
    if redis_client is not None and redis_client_factory is not None:
        raise SteamDTPriceCacheCompositionError(
            "redis_client and redis_client_factory cannot both be supplied"
        )


def _validate_inmemory_arguments(
    *,
    redis_client: AsyncRedisPriceCacheClient | None,
    redis_client_factory: RedisPriceCacheClientFactory | None,
    redis_price_cache_factory: RedisPriceCacheFactory | None,
) -> None:
    if redis_client is not None:
        raise SteamDTPriceCacheCompositionError(
            "redis_client cannot be supplied when SteamDT price-cache backend is inmemory"
        )
    if redis_client_factory is not None:
        raise SteamDTPriceCacheCompositionError(
            "redis_client_factory cannot be supplied when SteamDT price-cache backend "
            "is inmemory"
        )
    if redis_price_cache_factory is not None:
        raise SteamDTPriceCacheCompositionError(
            "redis_price_cache_factory cannot be supplied when SteamDT price-cache "
            "backend is inmemory"
        )


def _normalize_namespace(namespace: str) -> str:
    try:
        return normalize_redis_price_cache_namespace(namespace)
    except (TypeError, ValueError) as exc:
        raise SteamDTPriceCacheCompositionError(
            "steamdt_price_cache_redis_namespace is invalid",
            original_error=exc,
        ) from None


def _validate_redis_url(redis_url: str) -> None:
    try:
        parsed = urlsplit(redis_url)
        port = parsed.port
    except ValueError as exc:
        raise SteamDTPriceCacheCompositionError(
            "redis_url is invalid for SteamDT price-cache backend",
            original_error=exc,
        ) from None
    if parsed.scheme not in {"redis", "rediss", "unix"}:
        raise SteamDTPriceCacheCompositionError(
            "redis_url must use redis, rediss, or unix scheme for SteamDT price cache"
        )
    if parsed.scheme in {"redis", "rediss"} and not parsed.hostname:
        raise SteamDTPriceCacheCompositionError(
            "redis_url must include a host for SteamDT price-cache backend"
        )
    if port is not None and not 0 < port <= 65535:
        raise SteamDTPriceCacheCompositionError(
            "redis_url contains an invalid port for SteamDT price-cache backend"
        )


def _create_redis_client_from_url(redis_url: str) -> AsyncRedisPriceCacheClient:
    from redis.asyncio import Redis

    return cast(AsyncRedisPriceCacheClient, Redis.from_url(redis_url))


def _build_redis_price_cache(
    redis_client: AsyncRedisPriceCacheClient,
    *,
    namespace: str,
) -> PriceCache:
    return RedisPriceCache(redis_client, namespace=namespace)


async def _close_redis_client(redis_client: AsyncRedisPriceCacheClient) -> None:
    close = getattr(redis_client, "aclose", None)
    if close is None:
        close = getattr(redis_client, "close", None)
    if close is None:
        raise RuntimeError("owned Redis client does not expose a close method")
    result = close()
    if inspect.isawaitable(result):
        await result
