import asyncio

import pytest

from app.clients.steamdt_errors import SteamDTRateLimitError
from app.services.steamdt_rate_limiter import (
    InMemorySteamDTRateLimiter,
    SteamDTEndpoint,
    SteamDTRateLimitPolicy,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _limiter(
    policies: dict[SteamDTEndpoint, SteamDTRateLimitPolicy],
    clock: FakeClock,
) -> InMemorySteamDTRateLimiter:
    return InMemorySteamDTRateLimiter(policies, clock=clock)


def test_rate_limit_policy_rejects_non_positive_max_requests() -> None:
    with pytest.raises(ValueError, match="max_requests"):
        SteamDTRateLimitPolicy(max_requests=0, window_seconds=60)


def test_rate_limit_policy_rejects_non_positive_window_seconds() -> None:
    with pytest.raises(ValueError, match="window_seconds"):
        SteamDTRateLimitPolicy(max_requests=1, window_seconds=0)


def test_rate_limit_policy_rejects_negative_safety_buffer_seconds() -> None:
    with pytest.raises(ValueError, match="safety_buffer_seconds"):
        SteamDTRateLimitPolicy(
            max_requests=1,
            window_seconds=60,
            safety_buffer_seconds=-1,
        )


def test_price_batch_limit_does_not_block_price_single() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {
            SteamDTEndpoint.PRICE_BATCH: SteamDTRateLimitPolicy(1, 60),
            SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(1, 60),
        },
        clock,
    )

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_BATCH))

    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_BATCH))
    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_price_single_limit_does_not_block_price_avg() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {
            SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(1, 60),
            SteamDTEndpoint.PRICE_AVG: SteamDTRateLimitPolicy(1, 60),
        },
        clock,
    )

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))

    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))
    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_AVG))


def test_each_endpoint_uses_independent_sliding_window() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {
            SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(1, 10),
            SteamDTEndpoint.PRICE_AVG: SteamDTRateLimitPolicy(1, 20),
        },
        clock,
    )

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))
    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_AVG))
    clock.advance(11)

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))
    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_AVG))


def test_acquire_allows_requests_within_policy_budget() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(2, 60)},
        clock,
    )

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))
    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_acquire_fails_fast_when_budget_is_exhausted() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(1, 60)},
        clock,
    )

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))

    assert exc_info.value.endpoint == SteamDTEndpoint.PRICE_SINGLE.value
    assert exc_info.value.retry_after_seconds == 60


def test_acquire_allows_again_after_sliding_window_expires() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(1, 60)},
        clock,
    )

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))
    clock.advance(60.1)

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_retry_after_seconds_is_non_negative() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(1, 60)},
        clock,
    )

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))
    clock.advance(59.5)

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))

    assert exc_info.value.retry_after_seconds == pytest.approx(0.5)
    assert exc_info.value.retry_after_seconds >= 0


def test_batch_safety_buffer_extends_local_window() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {
            SteamDTEndpoint.PRICE_BATCH: SteamDTRateLimitPolicy(
                max_requests=1,
                window_seconds=60,
                safety_buffer_seconds=5,
            )
        },
        clock,
    )

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_BATCH))
    clock.advance(60)

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_BATCH))

    assert exc_info.value.retry_after_seconds == 5
    clock.advance(5.1)
    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_BATCH))


def test_record_server_limit_only_blocks_specific_endpoint() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {
            SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(10, 60),
            SteamDTEndpoint.PRICE_BATCH: SteamDTRateLimitPolicy(10, 60),
        },
        clock,
    )

    asyncio.run(
        limiter.record_server_limit(
            SteamDTEndpoint.PRICE_BATCH,
            retry_after_seconds=30,
        )
    )

    with pytest.raises(SteamDTRateLimitError):
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_BATCH))
    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_record_server_limit_uses_retry_after_when_present() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(10, 60)},
        clock,
    )

    asyncio.run(
        limiter.record_server_limit(
            SteamDTEndpoint.PRICE_SINGLE,
            retry_after_seconds=12.5,
        )
    )

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))
    assert exc_info.value.retry_after_seconds == 12.5


def test_record_server_limit_without_retry_after_uses_policy_window() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {
            SteamDTEndpoint.PRICE_BATCH: SteamDTRateLimitPolicy(
                max_requests=1,
                window_seconds=60,
                safety_buffer_seconds=5,
            )
        },
        clock,
    )

    asyncio.run(limiter.record_server_limit(SteamDTEndpoint.PRICE_BATCH))

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_BATCH))
    assert exc_info.value.retry_after_seconds == 65


def test_record_server_limit_keeps_longer_existing_block() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(10, 60)},
        clock,
    )

    asyncio.run(
        limiter.record_server_limit(
            SteamDTEndpoint.PRICE_SINGLE,
            retry_after_seconds=60,
        )
    )
    clock.advance(10)
    asyncio.run(
        limiter.record_server_limit(
            SteamDTEndpoint.PRICE_SINGLE,
            retry_after_seconds=5,
        )
    )

    with pytest.raises(SteamDTRateLimitError) as exc_info:
        asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))
    assert exc_info.value.retry_after_seconds == 50


def test_record_server_limit_expires_after_fake_clock_advances() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(10, 60)},
        clock,
    )

    asyncio.run(
        limiter.record_server_limit(
            SteamDTEndpoint.PRICE_SINGLE,
            retry_after_seconds=10,
        )
    )
    clock.advance(10.1)

    asyncio.run(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE))


def test_concurrent_acquire_same_endpoint_does_not_exceed_policy() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(1, 60)},
        clock,
    )

    async def run() -> list[object]:
        return await asyncio.gather(
            *(limiter.acquire(SteamDTEndpoint.PRICE_SINGLE) for _ in range(5)),
            return_exceptions=True,
        )

    results = asyncio.run(run())

    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, SteamDTRateLimitError) for result in results) == 4


def test_concurrent_acquire_different_endpoints_do_not_block_each_other() -> None:
    clock = FakeClock()
    limiter = _limiter(
        {
            SteamDTEndpoint.PRICE_SINGLE: SteamDTRateLimitPolicy(1, 60),
            SteamDTEndpoint.PRICE_BATCH: SteamDTRateLimitPolicy(1, 60),
            SteamDTEndpoint.PRICE_AVG: SteamDTRateLimitPolicy(1, 60),
        },
        clock,
    )

    async def run() -> list[object]:
        return await asyncio.gather(
            limiter.acquire(SteamDTEndpoint.PRICE_SINGLE),
            limiter.acquire(SteamDTEndpoint.PRICE_BATCH),
            limiter.acquire(SteamDTEndpoint.PRICE_AVG),
            return_exceptions=True,
        )

    assert asyncio.run(run()) == [None, None, None]
