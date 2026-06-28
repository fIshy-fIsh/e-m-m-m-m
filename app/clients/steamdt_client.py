import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

import httpx

UNCONFIRMED_MAPPING_ERROR = (
    "SteamDT API endpoint/field mapping is not fully confirmed. "
    "See docs/STEAMDT_API_NOTES.md."
)


@dataclass(frozen=True, repr=False)
class SteamDTClientConfig:
    """Configuration for SteamDT REST client abstractions."""

    base_url: str = "https://open.steamdt.com"
    api_key: str | None = None
    timeout_seconds: float = 10.0
    max_retries: int = 3
    dry_run: bool = True
    rate_limit_per_minute: int = 60

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("base_url cannot be empty")
        if not self.dry_run and not self.api_key:
            raise ValueError("api_key is required when dry_run is False")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        if self.max_retries < 0:
            raise ValueError("max_retries must be greater than or equal to 0")
        if self.rate_limit_per_minute <= 0:
            raise ValueError("rate_limit_per_minute must be greater than 0")

    def __repr__(self) -> str:
        return (
            "SteamDTClientConfig("
            f"base_url={self.base_url!r}, "
            f"api_key={self._redacted_api_key()}, "
            f"timeout_seconds={self.timeout_seconds}, "
            f"max_retries={self.max_retries}, "
            f"dry_run={self.dry_run}, "
            f"rate_limit_per_minute={self.rate_limit_per_minute}"
            ")"
        )

    def _redacted_api_key(self) -> str | None:
        if self.api_key is None or self.api_key == "":
            return None
        return "[REDACTED]"


@dataclass(frozen=True)
class SteamDTPriceQuote:
    """Internal price quote model for one market hash name."""

    market_hash_name: str
    price_cny: Decimal
    source: str = "steamdt"
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.market_hash_name.strip():
            raise ValueError("market_hash_name cannot be empty")
        if self.price_cny < 0:
            raise ValueError("price_cny must be greater than or equal to 0")


@dataclass(frozen=True)
class SteamDTBatchPriceResult:
    """Batch price query result with found quotes and missing names."""

    quotes: dict[str, SteamDTPriceQuote]
    missing: list[str]
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class SteamDTBaseItemInfo:
    """Internal base-item info model for SteamDT item metadata."""

    market_hash_name: str
    raw: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.market_hash_name.strip():
            raise ValueError("market_hash_name cannot be empty")


@dataclass(frozen=True)
class SteamDTHistoricalPricePoint:
    """Internal historical price point model."""

    market_hash_name: str
    timestamp: datetime
    price_cny: Decimal
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.market_hash_name.strip():
            raise ValueError("market_hash_name cannot be empty")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.price_cny < 0:
            raise ValueError("price_cny must be greater than or equal to 0")


@dataclass(frozen=True)
class SteamDTWearInfo:
    """Internal wear info model derived from inspect-based lookups."""

    inspect_link: str | None
    float_value: float | None
    paint_seed: int | None
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.float_value is not None and not 0.0 <= self.float_value <= 1.0:
            raise ValueError("float_value must be between 0 and 1")
        if self.paint_seed is not None and self.paint_seed < 0:
            raise ValueError("paint_seed must be greater than or equal to 0")


class SteamDTClient(Protocol):
    """Protocol for SteamDT client abstractions used in future V1.1 phases."""

    async def get_price_single(self, market_hash_name: str) -> SteamDTPriceQuote:
        """Return one SteamDT price quote for a single market hash name."""

    async def get_price_batch(
        self,
        market_hash_names: list[str],
    ) -> SteamDTBatchPriceResult:
        """Return SteamDT price quotes for multiple market hash names."""

    async def get_base_item_info(self, market_hash_name: str) -> SteamDTBaseItemInfo:
        """Return SteamDT base item information for one market hash name."""

    async def get_kline(
        self,
        market_hash_name: str,
    ) -> list[SteamDTHistoricalPricePoint]:
        """Return historical price points for one market hash name."""

    async def get_wear_info(self, inspect_link: str) -> SteamDTWearInfo:
        """Return wear information for one inspect link."""


class MockSteamDTClient:
    """Deterministic in-memory SteamDT client for unit tests and future mocks."""

    def __init__(
        self,
        price_quotes_by_name: dict[str, SteamDTPriceQuote] | None = None,
        base_info_by_name: dict[str, SteamDTBaseItemInfo] | None = None,
        kline_by_name: dict[str, list[SteamDTHistoricalPricePoint]] | None = None,
        wear_info_by_inspect_link: dict[str, SteamDTWearInfo] | None = None,
    ) -> None:
        self.price_quotes_by_name = price_quotes_by_name or {}
        self.base_info_by_name = base_info_by_name or {}
        self.kline_by_name = kline_by_name or {}
        self.wear_info_by_inspect_link = wear_info_by_inspect_link or {}

    async def get_price_single(self, market_hash_name: str) -> SteamDTPriceQuote:
        """Return a deterministic single-price quote or raise if missing."""

        try:
            return self.price_quotes_by_name[market_hash_name]
        except KeyError as exc:
            raise RuntimeError(
                f"missing mock SteamDT single price for market_hash_name: {market_hash_name}"
            ) from exc

    async def get_price_batch(
        self,
        market_hash_names: list[str],
    ) -> SteamDTBatchPriceResult:
        """Return deterministic batch price results with missing names preserved."""

        quotes = {
            name: self.price_quotes_by_name[name]
            for name in market_hash_names
            if name in self.price_quotes_by_name
        }
        missing = [name for name in market_hash_names if name not in self.price_quotes_by_name]
        return SteamDTBatchPriceResult(quotes=quotes, missing=missing, raw=None)

    async def get_base_item_info(self, market_hash_name: str) -> SteamDTBaseItemInfo:
        """Return deterministic base item info or raise if missing."""

        try:
            return self.base_info_by_name[market_hash_name]
        except KeyError as exc:
            raise RuntimeError(
                f"missing mock SteamDT base item info for market_hash_name: {market_hash_name}"
            ) from exc

    async def get_kline(
        self,
        market_hash_name: str,
    ) -> list[SteamDTHistoricalPricePoint]:
        """Return deterministic historical price points or an empty list."""

        return self.kline_by_name.get(market_hash_name, [])

    async def get_wear_info(self, inspect_link: str) -> SteamDTWearInfo:
        """Return deterministic wear info or raise if missing."""

        try:
            return self.wear_info_by_inspect_link[inspect_link]
        except KeyError as exc:
            raise RuntimeError(
                f"missing mock SteamDT wear info for inspect_link: {inspect_link}"
            ) from exc


class DryRunSteamDTClient:
    """Dry-run SteamDT client that never performs real external requests."""

    async def get_price_single(self, market_hash_name: str) -> SteamDTPriceQuote:
        """Refuse to fabricate a single SteamDT price in dry-run mode."""

        raise RuntimeError(
            "dry-run mode enabled and no real SteamDT request is made for get_price_single"
        )

    async def get_price_batch(
        self,
        market_hash_names: list[str],
    ) -> SteamDTBatchPriceResult:
        """Return an empty batch result and mark all requested names as missing."""

        return SteamDTBatchPriceResult(
            quotes={},
            missing=list(market_hash_names),
            raw=None,
        )

    async def get_base_item_info(self, market_hash_name: str) -> SteamDTBaseItemInfo:
        """Refuse to fabricate base item info in dry-run mode."""

        raise RuntimeError(
            "dry-run mode enabled and no real SteamDT request is made for get_base_item_info"
        )

    async def get_kline(
        self,
        market_hash_name: str,
    ) -> list[SteamDTHistoricalPricePoint]:
        """Return no historical price points in dry-run mode."""

        return []

    async def get_wear_info(self, inspect_link: str) -> SteamDTWearInfo:
        """Refuse to fabricate wear info in dry-run mode."""

        raise RuntimeError(
            "dry-run mode enabled and no real SteamDT request is made for get_wear_info"
        )


class SteamDTHttpClient:
    """HTTP client skeleton for future direct SteamDT REST access.

    Public domain-facing methods remain unimplemented until endpoint and field mapping
    details are fully confirmed in docs/STEAMDT_API_NOTES.md.
    """

    def __init__(
        self,
        config: SteamDTClientConfig,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.http_client = http_client
        self._minimum_interval_seconds = 60.0 / config.rate_limit_per_minute
        self._last_request_monotonic = 0.0

    async def get_price_single(self, market_hash_name: str) -> SteamDTPriceQuote:
        """Raise until SteamDT single-price endpoint mapping is fully confirmed."""

        raise NotImplementedError(UNCONFIRMED_MAPPING_ERROR)

    async def get_price_batch(
        self,
        market_hash_names: list[str],
    ) -> SteamDTBatchPriceResult:
        """Raise until SteamDT batch-price endpoint mapping is fully confirmed."""

        raise NotImplementedError(UNCONFIRMED_MAPPING_ERROR)

    async def get_base_item_info(self, market_hash_name: str) -> SteamDTBaseItemInfo:
        """Raise until SteamDT base-item endpoint mapping is fully confirmed."""

        raise NotImplementedError(UNCONFIRMED_MAPPING_ERROR)

    async def get_kline(
        self,
        market_hash_name: str,
    ) -> list[SteamDTHistoricalPricePoint]:
        """Raise until SteamDT kline/history endpoint mapping is fully confirmed."""

        raise NotImplementedError(UNCONFIRMED_MAPPING_ERROR)

    async def get_wear_info(self, inspect_link: str) -> SteamDTWearInfo:
        """Raise until SteamDT wear endpoint response mapping is fully confirmed."""

        raise NotImplementedError(UNCONFIRMED_MAPPING_ERROR)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an HTTP request with timeout, retry, and simple rate limiting."""

        if self.config.dry_run:
            raise RuntimeError("real SteamDT HTTP requests are disabled in dry-run mode")
        if not self.config.base_url.strip():
            raise ValueError("base_url cannot be empty")

        await self._respect_rate_limit()
        last_error: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                if self.http_client is not None:
                    response = await self.http_client.request(
                        method=method,
                        url=path,
                        json=json,
                        params=params,
                        headers=self._build_headers(),
                    )
                else:
                    async with httpx.AsyncClient(
                        base_url=self.config.base_url,
                        timeout=self.config.timeout_seconds,
                        headers=self._build_headers(),
                    ) as client:
                        response = await client.request(
                            method=method,
                            url=path,
                            json=json,
                            params=params,
                        )

                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise RuntimeError("SteamDT response payload must be a JSON object")
                return payload
            except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    raise RuntimeError("SteamDT HTTP request failed") from exc
                await asyncio.sleep(2**attempt * 0.1)

        raise RuntimeError("SteamDT HTTP request failed") from last_error

    async def _respect_rate_limit(self) -> None:
        """Apply a simple minimum-interval gate between outgoing requests."""

        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_request_monotonic
        remaining = self._minimum_interval_seconds - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)
        self._last_request_monotonic = asyncio.get_running_loop().time()

    def _build_headers(self) -> dict[str, str]:
        """Build safe HTTP headers for confirmed transport-level behavior only."""

        headers = {"Content-Type": "application/json"}
        if not self.config.dry_run and self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers
