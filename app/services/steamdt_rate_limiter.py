import asyncio
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.clients.steamdt_errors import SteamDTRateLimitError


class SteamDTEndpoint(StrEnum):
    """Stable SteamDT endpoint identifiers used by the local limiter."""

    PRICE_SINGLE = "price_single"
    PRICE_BATCH = "price_batch"
    PRICE_AVG = "price_avg"
    BASE = "base"
    KLINE = "kline"
    WEAR = "wear"


STEAMDT_ENDPOINT_PATHS: dict[SteamDTEndpoint, str] = {
    SteamDTEndpoint.PRICE_SINGLE: "/open/cs2/v1/price/single",
    SteamDTEndpoint.PRICE_BATCH: "/open/cs2/v1/price/batch",
    SteamDTEndpoint.PRICE_AVG: "/open/cs2/v1/price/avg",
    SteamDTEndpoint.BASE: "/open/cs2/v1/base",
    SteamDTEndpoint.KLINE: "/open/cs2/item/v1/kline",
    SteamDTEndpoint.WEAR: "/open/cs2/v1/wear",
}


@dataclass(frozen=True)
class SteamDTRateLimitPolicy:
    """Per-endpoint SteamDT request budget for an in-process sliding window."""

    max_requests: int
    window_seconds: float
    safety_buffer_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.max_requests <= 0:
            raise ValueError("max_requests must be greater than 0")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be greater than 0")
        if self.safety_buffer_seconds < 0:
            raise ValueError("safety_buffer_seconds must be greater than or equal to 0")

    @property
    def effective_window_seconds(self) -> float:
        """Return the enforced window, including project safety buffer."""

        return self.window_seconds + self.safety_buffer_seconds


DEFAULT_STEAMDT_RATE_LIMIT_POLICIES: dict[SteamDTEndpoint, SteamDTRateLimitPolicy] = {
    SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(
        max_requests=60,
        window_seconds=60.0,
    ),
    SteamDTEndpoint.PRICE_BATCH: SteamDTRateLimitPolicy(
        max_requests=1,
        window_seconds=60.0,
        safety_buffer_seconds=5.0,
    ),
    SteamDTEndpoint.PRICE_AVG: SteamDTRateLimitPolicy(
        max_requests=10,
        window_seconds=60.0,
    ),
    SteamDTEndpoint.BASE: SteamDTRateLimitPolicy(
        max_requests=1,
        window_seconds=86400.0,
    ),
    SteamDTEndpoint.KLINE: SteamDTRateLimitPolicy(
        max_requests=120,
        window_seconds=60.0,
    ),
    SteamDTEndpoint.WEAR: SteamDTRateLimitPolicy(
        max_requests=36000,
        window_seconds=3600.0,
    ),
}


def build_steamdt_rate_limit_policies(
    *,
    price_single_per_minute: int = 60,
    price_batch_per_minute: int = 1,
    price_avg_per_minute: int = 10,
    base_per_day: int = 1,
    kline_per_minute: int = 120,
    wear_per_hour: int = 36000,
    price_batch_safety_buffer_seconds: float = 5.0,
) -> dict[SteamDTEndpoint, SteamDTRateLimitPolicy]:
    """Build endpoint-specific policies from config values."""

    return {
        SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(
            max_requests=price_single_per_minute,
            window_seconds=60.0,
        ),
        SteamDTEndpoint.PRICE_BATCH: SteamDTRateLimitPolicy(
            max_requests=price_batch_per_minute,
            window_seconds=60.0,
            safety_buffer_seconds=price_batch_safety_buffer_seconds,
        ),
        SteamDTEndpoint.PRICE_AVG: SteamDTRateLimitPolicy(
            max_requests=price_avg_per_minute,
            window_seconds=60.0,
        ),
        SteamDTEndpoint.BASE: SteamDTRateLimitPolicy(
            max_requests=base_per_day,
            window_seconds=86400.0,
        ),
        SteamDTEndpoint.KLINE: SteamDTRateLimitPolicy(
            max_requests=kline_per_minute,
            window_seconds=60.0,
        ),
        SteamDTEndpoint.WEAR: SteamDTRateLimitPolicy(
            max_requests=wear_per_hour,
            window_seconds=3600.0,
        ),
    }


class SteamDTRateLimiter(Protocol):
    """Protocol for endpoint-specific SteamDT request budget enforcement."""

    async def acquire(self, endpoint: SteamDTEndpoint) -> None:
        """Record one attempt or fail fast when the endpoint budget is exhausted."""

    async def record_server_limit(
        self,
        endpoint: SteamDTEndpoint,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        """Record a server-observed rate-limit cooldown for one endpoint."""


class InMemorySteamDTRateLimiter:
    """Process-local, endpoint-specific SteamDT sliding-window limiter."""

    def __init__(
        self,
        policies: Mapping[SteamDTEndpoint, SteamDTRateLimitPolicy] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._policies = dict(policies or DEFAULT_STEAMDT_RATE_LIMIT_POLICIES)
        self._clock = clock
        self._request_timestamps: dict[SteamDTEndpoint, deque[float]] = {
            endpoint: deque() for endpoint in self._policies
        }
        self._blocked_until: dict[SteamDTEndpoint, float] = {
            endpoint: 0.0 for endpoint in self._policies
        }
        self._locks: dict[SteamDTEndpoint, asyncio.Lock] = {
            endpoint: asyncio.Lock() for endpoint in self._policies
        }

    async def acquire(self, endpoint: SteamDTEndpoint) -> None:
        """Record one endpoint attempt or raise without sleeping when no budget remains."""

        policy = self._policy_for(endpoint)
        async with self._lock_for(endpoint):
            now = self._clock()
            blocked_until = self._blocked_until.get(endpoint, 0.0)
            if blocked_until > now:
                raise SteamDTRateLimitError(
                    "SteamDT local endpoint rate limit active",
                    endpoint=endpoint.value,
                    retry_after_seconds=max(0.0, blocked_until - now),
                )

            timestamps = self._timestamps_for(endpoint)
            self._prune_expired(timestamps, policy=policy, now=now)
            if len(timestamps) >= policy.max_requests:
                retry_after_seconds = max(
                    0.0,
                    timestamps[0] + policy.effective_window_seconds - now,
                )
                raise SteamDTRateLimitError(
                    "SteamDT local endpoint request budget exhausted",
                    endpoint=endpoint.value,
                    retry_after_seconds=retry_after_seconds,
                )

            timestamps.append(now)

    async def record_server_limit(
        self,
        endpoint: SteamDTEndpoint,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        """Record a server cooldown for one endpoint without affecting other buckets."""

        policy = self._policy_for(endpoint)
        async with self._lock_for(endpoint):
            now = self._clock()
            if retry_after_seconds is not None and retry_after_seconds > 0:
                block_seconds = retry_after_seconds
            else:
                block_seconds = policy.effective_window_seconds
            new_blocked_until = now + max(0.0, block_seconds)
            self._blocked_until[endpoint] = max(
                self._blocked_until.get(endpoint, 0.0),
                new_blocked_until,
            )

    def _policy_for(self, endpoint: SteamDTEndpoint) -> SteamDTRateLimitPolicy:
        try:
            return self._policies[endpoint]
        except KeyError as exc:
            message = f"missing SteamDT rate-limit policy for endpoint: {endpoint.value}"
            raise ValueError(message) from exc

    def _timestamps_for(self, endpoint: SteamDTEndpoint) -> deque[float]:
        if endpoint not in self._request_timestamps:
            self._request_timestamps[endpoint] = deque()
        return self._request_timestamps[endpoint]

    def _lock_for(self, endpoint: SteamDTEndpoint) -> asyncio.Lock:
        if endpoint not in self._locks:
            self._locks[endpoint] = asyncio.Lock()
        return self._locks[endpoint]

    @staticmethod
    def _prune_expired(
        timestamps: deque[float],
        *,
        policy: SteamDTRateLimitPolicy,
        now: float,
    ) -> None:
        cutoff = now - policy.effective_window_seconds
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()
