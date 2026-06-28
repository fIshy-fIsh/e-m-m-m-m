import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

import httpx

UNCONFIRMED_MAPPING_ERROR = (
    "BUFF API endpoint mapping is not confirmed. See docs/BUFF_API_NOTES.md."
)


@dataclass(frozen=True)
class BuffClientConfig:
    """Configuration for BUFF market clients."""

    base_url: str
    api_key: str | None = None
    api_secret: str | None = None
    timeout_seconds: float = 10.0
    max_retries: int = 3
    rate_limit_per_minute: int = 60
    dry_run: bool = True


@dataclass(frozen=True)
class BuffSellOrder:
    """Internal representation of a BUFF sell order listing."""

    listing_id: str
    goods_id: str
    market_hash_name: str | None
    price_cny: Decimal
    float_value: float | None
    paint_seed: int | None
    inspect_link: str | None
    seller_id: str | None
    raw: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.listing_id.strip():
            raise ValueError("listing_id cannot be empty")
        if not self.goods_id.strip():
            raise ValueError("goods_id cannot be empty")
        if self.price_cny < 0:
            raise ValueError("price_cny must be greater than or equal to 0")
        if self.float_value is not None and not 0.0 <= self.float_value <= 1.0:
            raise ValueError("float_value must be between 0 and 1")


@dataclass(frozen=True)
class BuffGoodsInfo:
    """Internal representation of BUFF goods-level metadata."""

    goods_id: str
    market_hash_name: str
    localized_name: str | None
    sell_num: int | None
    buy_num: int | None
    raw: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.goods_id.strip():
            raise ValueError("goods_id cannot be empty")
        if not self.market_hash_name.strip():
            raise ValueError("market_hash_name cannot be empty")


@dataclass(frozen=True)
class BuffBuyOrder:
    """Internal representation of a BUFF buy order aggregate point."""

    goods_id: str
    price_cny: Decimal
    quantity: int | None
    raw: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.goods_id.strip():
            raise ValueError("goods_id cannot be empty")
        if self.price_cny < 0:
            raise ValueError("price_cny must be greater than or equal to 0")


@dataclass(frozen=True)
class BuffPricePoint:
    """Internal representation of one BUFF price history point."""

    goods_id: str
    price_cny: Decimal
    timestamp: datetime
    raw: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.goods_id.strip():
            raise ValueError("goods_id cannot be empty")
        if self.price_cny < 0:
            raise ValueError("price_cny must be greater than or equal to 0")


class BuffClient(Protocol):
    """Protocol for clients that expose BUFF market data retrieval methods."""

    async def get_sell_orders(
        self,
        goods_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[BuffSellOrder]:
        """Return sell orders for one goods_id."""

    async def get_goods_info(self, goods_id: str) -> BuffGoodsInfo:
        """Return goods-level information for one goods_id."""

    async def get_buy_orders(self, goods_id: str) -> list[BuffBuyOrder]:
        """Return buy orders for one goods_id."""

    async def get_price_history(self, goods_id: str) -> list[BuffPricePoint]:
        """Return historical price points for one goods_id."""


class MockBuffClient:
    """Mock BUFF client backed by injected in-memory fixtures."""

    def __init__(
        self,
        *,
        sell_orders_by_goods_id: dict[str, list[BuffSellOrder]] | None = None,
        goods_info_by_goods_id: dict[str, BuffGoodsInfo] | None = None,
        buy_orders_by_goods_id: dict[str, list[BuffBuyOrder]] | None = None,
        price_history_by_goods_id: dict[str, list[BuffPricePoint]] | None = None,
    ) -> None:
        self.sell_orders_by_goods_id = sell_orders_by_goods_id or {}
        self.goods_info_by_goods_id = goods_info_by_goods_id or {}
        self.buy_orders_by_goods_id = buy_orders_by_goods_id or {}
        self.price_history_by_goods_id = price_history_by_goods_id or {}

    async def get_sell_orders(
        self,
        goods_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[BuffSellOrder]:
        """Return pre-seeded sell orders for one goods_id."""

        return self.sell_orders_by_goods_id.get(goods_id, [])

    async def get_goods_info(self, goods_id: str) -> BuffGoodsInfo:
        """Return pre-seeded goods info for one goods_id."""

        try:
            return self.goods_info_by_goods_id[goods_id]
        except KeyError as exc:
            raise ValueError(f"missing mock goods info for goods_id: {goods_id}") from exc

    async def get_buy_orders(self, goods_id: str) -> list[BuffBuyOrder]:
        """Return pre-seeded buy orders for one goods_id."""

        return self.buy_orders_by_goods_id.get(goods_id, [])

    async def get_price_history(self, goods_id: str) -> list[BuffPricePoint]:
        """Return pre-seeded price history for one goods_id."""

        return self.price_history_by_goods_id.get(goods_id, [])


class DryRunBuffClient:
    """Dry-run BUFF client that never performs real external requests."""

    async def get_sell_orders(
        self,
        goods_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[BuffSellOrder]:
        """Return no sell orders in dry-run mode."""

        return []

    async def get_goods_info(self, goods_id: str) -> BuffGoodsInfo:
        """Return a placeholder goods info object in dry-run mode."""

        return BuffGoodsInfo(
            goods_id=goods_id,
            market_hash_name=f"DRY-RUN:{goods_id}",
            localized_name=None,
            sell_num=None,
            buy_num=None,
            raw={"dry_run": True},
        )

    async def get_buy_orders(self, goods_id: str) -> list[BuffBuyOrder]:
        """Return no buy orders in dry-run mode."""

        return []

    async def get_price_history(self, goods_id: str) -> list[BuffPricePoint]:
        """Return no price history in dry-run mode."""

        return []


class BuffHttpClient:
    """HTTP client skeleton for future BUFF API access.

    This client intentionally does not implement any real endpoint mapping, signature,
    or response-field parsing until official BUFF API details are confirmed.
    """

    def __init__(self, config: BuffClientConfig) -> None:
        self.config = config
        self._minimum_interval_seconds = (
            60.0 / config.rate_limit_per_minute if config.rate_limit_per_minute > 0 else 0.0
        )
        self._last_request_monotonic = 0.0

    async def get_sell_orders(
        self,
        goods_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[BuffSellOrder]:
        """Raise until official BUFF sell-order endpoint mapping is confirmed."""

        raise NotImplementedError(UNCONFIRMED_MAPPING_ERROR)

    async def get_goods_info(self, goods_id: str) -> BuffGoodsInfo:
        """Raise until official BUFF goods-info endpoint mapping is confirmed."""

        raise NotImplementedError(UNCONFIRMED_MAPPING_ERROR)

    async def get_buy_orders(self, goods_id: str) -> list[BuffBuyOrder]:
        """Raise until official BUFF buy-order endpoint mapping is confirmed."""

        raise NotImplementedError(UNCONFIRMED_MAPPING_ERROR)

    async def get_price_history(self, goods_id: str) -> list[BuffPricePoint]:
        """Raise until official BUFF price-history endpoint mapping is confirmed."""

        raise NotImplementedError(UNCONFIRMED_MAPPING_ERROR)

    async def _request_json(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an HTTP request with timeout, retry, and simple rate limiting."""

        if self.config.dry_run:
            raise RuntimeError("dry_run mode is enabled; real BUFF HTTP requests are disabled")
        if not self.config.base_url.strip():
            raise ValueError("base_url must not be empty for BuffHttpClient HTTP requests")

        await self._respect_rate_limit()

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    base_url=self.config.base_url,
                    timeout=self.config.timeout_seconds,
                ) as client:
                    response = await client.request(method=method, url=path, params=params)
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise ValueError("BUFF HTTP response payload must be a JSON object")
                    return payload
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    raise RuntimeError("failed to fetch BUFF JSON payload") from exc
                await asyncio.sleep(2**attempt * 0.1)

        raise RuntimeError("failed to fetch BUFF JSON payload") from last_error

    async def _respect_rate_limit(self) -> None:
        """Apply a simple minimum-interval gate between outgoing requests."""

        if self._minimum_interval_seconds <= 0:
            return

        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_request_monotonic
        remaining = self._minimum_interval_seconds - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)
        self._last_request_monotonic = asyncio.get_running_loop().time()
