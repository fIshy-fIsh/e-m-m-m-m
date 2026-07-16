import inspect
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, cast
from urllib.parse import parse_qsl, urlsplit

import httpx

from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.config import Settings
from app.services.redis_steamdt_rate_limiter import (
    AsyncRedisEvalClient,
    RedisSteamDTRateLimiter,
)
from app.services.steamdt_rate_limiter import (
    InMemorySteamDTRateLimiter,
    SteamDTRateLimiter,
    build_steamdt_rate_limit_policies,
)

DEFAULT_STEAMDT_RATE_LIMIT_REDIS_NAMESPACE = "steamdt-rate-limit-v1"


class SteamDTRateLimitBackend(StrEnum):
    """Supported SteamDT rate-limiter backends for explicit composition."""

    INMEMORY = "inmemory"
    REDIS = "redis"


class SteamDTClientCompositionError(RuntimeError):
    """Configuration or construction failure while composing a SteamDT client runtime."""


class SteamDTClientRuntimeCloseError(RuntimeError):
    """One or more owned SteamDT runtime resources failed to close."""

    def __init__(
        self,
        *,
        http_error: Exception | None = None,
        redis_error: Exception | None = None,
    ) -> None:
        self.http_error = http_error
        self.redis_error = redis_error
        failed_resources = []
        if http_error is not None:
            failed_resources.append("SteamDT HTTP client")
        if redis_error is not None:
            failed_resources.append("Redis client")
        super().__init__(
            "failed to close SteamDT runtime resources: "
            f"{', '.join(failed_resources)}"
        )


class RedisClientFactory(Protocol):
    def __call__(self, redis_url: str) -> AsyncRedisEvalClient:
        """Create an async Redis client without transferring URL ownership downstream."""


class SteamDTHttpClientFactory(Protocol):
    def __call__(
        self,
        config: SteamDTClientConfig,
        *,
        http_client: httpx.AsyncClient | None,
        rate_limiter: SteamDTRateLimiter,
    ) -> SteamDTHttpClient:
        """Create a SteamDT HTTP client with an explicit rate limiter."""


@dataclass
class SteamDTClientRuntime:
    """Composed SteamDT client runtime with explicit optional Redis ownership."""

    client: SteamDTHttpClient
    rate_limiter: SteamDTRateLimiter
    redis_client: AsyncRedisEvalClient | None = None
    owns_redis_client: bool = False
    _closed: bool = field(default=False, init=False, repr=False)

    async def aclose(self) -> None:
        """Close the SteamDT HTTP client, then every owned backend resource, once."""

        if self._closed:
            return
        self._closed = True
        http_error: Exception | None = None
        redis_error: Exception | None = None
        try:
            await self.client.aclose()
        except Exception as exc:
            http_error = exc
        if self.owns_redis_client and self.redis_client is not None:
            try:
                await _close_redis_client(self.redis_client)
            except Exception as exc:
                redis_error = exc
        if http_error is not None or redis_error is not None:
            raise SteamDTClientRuntimeCloseError(
                http_error=http_error,
                redis_error=redis_error,
            ) from http_error or redis_error

    async def __aenter__(self) -> "SteamDTClientRuntime":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


def build_steamdt_client_config(settings: Settings) -> SteamDTClientConfig:
    """Build SteamDT HTTP client config from already-parsed application settings."""

    policies = build_steamdt_rate_limit_policies(
        price_single_per_minute=settings.steamdt_rate_limit_price_single_per_minute,
        price_batch_per_minute=settings.steamdt_rate_limit_price_batch_per_minute,
        price_avg_per_minute=settings.steamdt_rate_limit_price_avg_per_minute,
        base_per_day=settings.steamdt_rate_limit_base_per_day,
        kline_per_minute=settings.steamdt_rate_limit_kline_per_minute,
        wear_per_hour=settings.steamdt_rate_limit_wear_per_hour,
        price_batch_safety_buffer_seconds=(
            settings.steamdt_rate_limit_price_batch_safety_buffer_seconds
        ),
    )
    return SteamDTClientConfig(
        base_url=settings.steamdt_base_url,
        api_key=settings.steamdt_api_key or None,
        dry_run=settings.steamdt_dry_run,
        rate_limit_per_minute=settings.steamdt_rate_limit_per_minute,
        rate_limit_policies=policies,
    )


async def create_steamdt_client_runtime(
    settings: Settings,
    *,
    http_client: httpx.AsyncClient | None = None,
    redis_client: AsyncRedisEvalClient | None = None,
    redis_client_owned: bool = False,
    redis_client_factory: RedisClientFactory | None = None,
    steamdt_client_factory: SteamDTHttpClientFactory | None = None,
) -> SteamDTClientRuntime:
    """Compose a SteamDT client with an explicitly selected rate-limiter backend."""

    owned_redis_client: AsyncRedisEvalClient | None = (
        redis_client if redis_client is not None and redis_client_owned else None
    )

    try:
        backend = _parse_backend(settings.steamdt_rate_limit_backend)
        client_config = build_steamdt_client_config(settings)
        if backend == SteamDTRateLimitBackend.INMEMORY:
            if redis_client is not None:
                raise SteamDTClientCompositionError(
                    "redis_client cannot be supplied when SteamDT rate-limit backend is inmemory"
                )
            rate_limiter: SteamDTRateLimiter = InMemorySteamDTRateLimiter(
                client_config.rate_limit_policies
            )
            runtime_redis_client = None
            owns_redis_client = False
        else:
            namespace = settings.steamdt_rate_limit_redis_namespace.strip()
            if not namespace:
                raise SteamDTClientCompositionError(
                    "steamdt_rate_limit_redis_namespace cannot be empty"
                )
            if redis_client is None:
                redis_url = settings.redis_url.strip()
                if not redis_url:
                    raise SteamDTClientCompositionError(
                        "redis_url is required when SteamDT rate-limit backend is redis"
                    )
                _validate_redis_url(redis_url)
                try:
                    if redis_client_factory is None:
                        redis_client = _create_redis_client_from_url(redis_url)
                    else:
                        redis_client = redis_client_factory(redis_url)
                except Exception as exc:
                    message = _safe_composition_error_message(exc, redis_url=redis_url)
                    raise SteamDTClientCompositionError(
                        "failed to create Redis client for SteamDT rate limiter: "
                        f"{message}"
                    ) from exc
                owned_redis_client = redis_client
                owns_redis_client = True
            else:
                owns_redis_client = redis_client_owned
            rate_limiter = RedisSteamDTRateLimiter(
                redis_client,
                client_config.rate_limit_policies,
                namespace=namespace,
            )
            runtime_redis_client = redis_client

        client_factory = steamdt_client_factory or _build_steamdt_http_client
        client = client_factory(
            client_config,
            http_client=http_client,
            rate_limiter=rate_limiter,
        )
        return SteamDTClientRuntime(
            client=client,
            rate_limiter=rate_limiter,
            redis_client=runtime_redis_client,
            owns_redis_client=owns_redis_client,
        )
    except Exception:
        if owned_redis_client is not None:
            await _close_redis_client(owned_redis_client)
        raise


def _parse_backend(raw_backend: str) -> SteamDTRateLimitBackend:
    backend = raw_backend.strip().lower()
    for candidate in SteamDTRateLimitBackend:
        if backend == candidate.value:
            return candidate
    raise SteamDTClientCompositionError(
        "unsupported SteamDT rate-limit backend: "
        f"{raw_backend!r}; expected 'inmemory' or 'redis'"
    )


def _validate_redis_url(redis_url: str) -> None:
    try:
        parsed = urlsplit(redis_url)
        port = parsed.port
    except ValueError as exc:
        raise SteamDTClientCompositionError(
            "redis_url is invalid for SteamDT rate-limit backend"
        ) from exc
    if parsed.scheme not in {"redis", "rediss", "unix"}:
        raise SteamDTClientCompositionError(
            "redis_url must use redis, rediss, or unix scheme for SteamDT rate limiter"
        )
    if parsed.scheme in {"redis", "rediss"} and not parsed.hostname:
        raise SteamDTClientCompositionError(
            "redis_url must include a host for SteamDT rate-limit backend"
        )
    if port is not None and not 0 < port <= 65535:
        raise SteamDTClientCompositionError(
            "redis_url contains an invalid port for SteamDT rate-limit backend"
        )


def _create_redis_client_from_url(redis_url: str) -> AsyncRedisEvalClient:
    from redis.asyncio import Redis

    return cast(AsyncRedisEvalClient, Redis.from_url(redis_url))


def _build_steamdt_http_client(
    config: SteamDTClientConfig,
    *,
    http_client: httpx.AsyncClient | None,
    rate_limiter: SteamDTRateLimiter,
) -> SteamDTHttpClient:
    return SteamDTHttpClient(config, http_client=http_client, rate_limiter=rate_limiter)


async def _close_redis_client(redis_client: AsyncRedisEvalClient) -> None:
    close = getattr(redis_client, "aclose", None)
    if close is None:
        close = getattr(redis_client, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def _safe_composition_error_message(
    exc: Exception,
    *,
    redis_url: str | None = None,
) -> str:
    message = str(exc) or type(exc).__name__
    if redis_url:
        message = message.replace(redis_url, _redact_redis_url(redis_url))
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
    return f"{type(exc).__name__}: {message}"


def _redact_redis_url(redis_url: str) -> str:
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
    return parsed._replace(netloc=netloc, query=query).geturl()
