import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

import httpx

from app.clients.steamdt_errors import (
    SteamDTApiError,
    SteamDTError,
    SteamDTHttpStatusError,
    SteamDTRateLimitError,
    SteamDTResponseParseError,
    SteamDTTransportError,
    redact_steamdt_error_text,
)
from app.clients.steamdt_price_selection import (
    SteamDTPriceSelectionConfig,
    select_steamdt_price_quote,
)
from app.services.steamdt_rate_limiter import (
    InMemorySteamDTRateLimiter,
    SteamDTEndpoint,
    SteamDTRateLimiter,
    SteamDTRateLimitPolicy,
    build_steamdt_rate_limit_policies,
)

UNCONFIRMED_MAPPING_ERROR = (
    "SteamDT API endpoint/field mapping is not fully confirmed. "
    "See docs/STEAMDT_API_NOTES.md."
)
KLINE_MAPPING_UNCONFIRMED_ERROR = (
    "SteamDT kline point mapping is not confirmed. See docs/STEAMDT_API_NOTES.md."
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
    rate_limit_policies: dict[SteamDTEndpoint, SteamDTRateLimitPolicy] = field(
        default_factory=build_steamdt_rate_limit_policies
    )

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
        for endpoint in SteamDTEndpoint:
            if endpoint not in self.rate_limit_policies:
                raise ValueError(
                    f"rate_limit_policies is missing endpoint policy: {endpoint.value}"
                )

    def __repr__(self) -> str:
        return (
            "SteamDTClientConfig("
            f"base_url={self.base_url!r}, "
            f"api_key={self._redacted_api_key()}, "
            f"timeout_seconds={self.timeout_seconds}, "
            f"max_retries={self.max_retries}, "
            f"dry_run={self.dry_run}, "
            f"rate_limit_per_minute={self.rate_limit_per_minute}, "
            "rate_limit_policies=<endpoint-specific>"
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


@dataclass(frozen=True)
class SteamDTPlatformPrice:
    """Normalized platform-level price record parsed from SteamDT price responses."""

    platform: str
    platform_item_id: str | None = None
    sell_price_cny: Decimal | None = None
    sell_count: int | None = None
    bidding_price_cny: Decimal | None = None
    bidding_count: int | None = None
    update_time: int | str | None = None
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.platform.strip():
            raise ValueError("platform cannot be empty")
        if self.sell_price_cny is not None and self.sell_price_cny < 0:
            raise ValueError("sell_price_cny must be greater than or equal to 0")
        if self.bidding_price_cny is not None and self.bidding_price_cny < 0:
            raise ValueError("bidding_price_cny must be greater than or equal to 0")
        if self.sell_count is not None and self.sell_count < 0:
            raise ValueError("sell_count must be greater than or equal to 0")
        if self.bidding_count is not None and self.bidding_count < 0:
            raise ValueError("bidding_count must be greater than or equal to 0")


@dataclass(frozen=True)
class SteamDTAvgPrice:
    """Normalized average-price view for one market hash name."""

    market_hash_name: str
    avg_price_cny: Decimal | None = None
    platform_avg_prices: dict[str, Decimal] | None = None
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.market_hash_name.strip():
            raise ValueError("market_hash_name cannot be empty")
        if self.avg_price_cny is not None and self.avg_price_cny < 0:
            raise ValueError("avg_price_cny must be greater than or equal to 0")
        if self.platform_avg_prices is not None:
            for value in self.platform_avg_prices.values():
                if value < 0:
                    raise ValueError(
                        "platform_avg_prices values must be greater than or equal to 0"
                    )


@dataclass(frozen=True)
class SteamDTWearParseResult:
    """Structured parse result for SteamDT wear endpoint responses."""

    inspect_link: str | None
    wear_info: SteamDTWearInfo
    sync: bool | None = None
    success: bool | None = None
    task_id: str | None = None
    raw: dict[str, Any] | None = None


class SteamDTClient(Protocol):
    """Protocol for SteamDT client abstractions used in future V1.1 phases."""

    async def get_price_single(self, market_hash_name: str) -> SteamDTPriceQuote:
        """Return one SteamDT price quote for a single market hash name."""

    async def get_price_batch(
        self,
        market_hash_names: list[str],
    ) -> SteamDTBatchPriceResult:
        """Return SteamDT price quotes for multiple market hash names."""

    async def get_avg_price(self, market_hash_name: str) -> SteamDTAvgPrice:
        """Return SteamDT average price information for one market hash name."""

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
        missing = [
            name for name in market_hash_names if name not in self.price_quotes_by_name
        ]
        return SteamDTBatchPriceResult(quotes=quotes, missing=missing, raw=None)

    async def get_avg_price(self, market_hash_name: str) -> SteamDTAvgPrice:
        """Return deterministic avg price info by reusing single price quotes when available."""

        quote = await self.get_price_single(market_hash_name)
        return SteamDTAvgPrice(
            market_hash_name=quote.market_hash_name,
            avg_price_cny=quote.price_cny,
            platform_avg_prices={},
            raw=quote.raw,
        )

    async def get_base_item_info(self, market_hash_name: str) -> SteamDTBaseItemInfo:
        """Return deterministic base item info or raise if missing."""

        try:
            return self.base_info_by_name[market_hash_name]
        except KeyError as exc:
            raise RuntimeError(
                "missing mock SteamDT base item info for market_hash_name: "
                f"{market_hash_name}"
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

    async def get_avg_price(self, market_hash_name: str) -> SteamDTAvgPrice:
        """Refuse to fetch avg price in dry-run mode."""

        raise RuntimeError(
            "real SteamDT HTTP requests are disabled in dry-run mode"
        )

    async def get_wear_info(self, inspect_link: str) -> SteamDTWearInfo:
        """Refuse to fabricate wear info in dry-run mode."""

        raise RuntimeError(
            "dry-run mode enabled and no real SteamDT request is made for get_wear_info"
        )



def _require_response_wrapper(payload: dict[str, Any], *, endpoint: str | None = None) -> Any:
    """Validate the common SteamDT wrapper and return the inner `data` payload."""

    if not isinstance(payload, dict):
        raise SteamDTResponseParseError(
            "SteamDT response payload must be a dict",
            endpoint=endpoint,
        )

    if payload.get("success") is False:
        error_code = payload.get("errorCode")
        error_msg = payload.get("errorMsg")
        error_code_str = payload.get("errorCodeStr")
        if error_code == 4005 or str(error_code) == "4005":
            raise SteamDTRateLimitError(
                "SteamDT API rate limit reached",
                endpoint=endpoint,
                error_code=error_code,
                error_msg=None if error_msg is None else str(error_msg),
                error_code_str=None if error_code_str is None else str(error_code_str),
            )
        raise SteamDTApiError(
            "SteamDT response indicated failure",
            endpoint=endpoint,
            error_code=error_code,
            error_msg=None if error_msg is None else str(error_msg),
            error_code_str=None if error_code_str is None else str(error_code_str),
        )

    if "data" not in payload:
        raise SteamDTResponseParseError(
            "SteamDT response is missing data field",
            endpoint=endpoint,
        )

    return payload["data"]



def _to_decimal_or_none(value: Any) -> Decimal | None:
    """Convert a raw value into Decimal or return None for empty values."""

    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except SteamDTResponseParseError:
        raise
    except Exception as exc:
        raise SteamDTResponseParseError(
            f"cannot convert value to Decimal: {redact_steamdt_error_text(type(value).__name__)}",
            endpoint="parse_decimal",
        ) from exc



def _to_int_or_none(value: Any) -> int | None:
    """Convert a raw value into int or return None for empty values."""

    if value is None or value == "":
        return None
    if isinstance(value, float) and not value.is_integer():
        raise SteamDTResponseParseError(
            "cannot convert non-integer float to int",
            endpoint="parse_int",
        )
    try:
        return int(value)
    except Exception as exc:
        raise SteamDTResponseParseError(
            f"cannot convert value to int: {redact_steamdt_error_text(type(value).__name__)}",
            endpoint="parse_int",
        ) from exc



def parse_price_single_response(
    market_hash_name: str,
    payload: dict[str, Any],
    *,
    endpoint: str | None = "parse_price_single_response",
) -> list[SteamDTPlatformPrice]:
    """Parse SteamDT single-price response data into platform-level price records."""

    if not market_hash_name.strip():
        raise ValueError("market_hash_name cannot be empty")

    data = _require_response_wrapper(payload, endpoint=endpoint)
    if not isinstance(data, list):
        raise SteamDTResponseParseError(
            "SteamDT single price response data must be a list",
            endpoint=endpoint,
        )

    results: list[SteamDTPlatformPrice] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("SteamDT single price item must be a dict")
        platform = item.get("platform")
        if platform is None or str(platform).strip() == "":
            raise ValueError("SteamDT platform field is required")
        results.append(
            SteamDTPlatformPrice(
                platform=str(platform),
                platform_item_id=(
                    None
                    if item.get("platformItemId") in (None, "")
                    else str(item.get("platformItemId"))
                ),
                sell_price_cny=_to_decimal_or_none(item.get("sellPrice")),
                sell_count=_to_int_or_none(item.get("sellCount")),
                bidding_price_cny=_to_decimal_or_none(item.get("biddingPrice")),
                bidding_count=_to_int_or_none(item.get("biddingCount")),
                update_time=item.get("updateTime"),
                raw=dict(item),
            )
        )
    return results



def parse_price_batch_response(
    requested_market_hash_names: list[str],
    payload: dict[str, Any],
    *,
    endpoint: str | None = "parse_price_batch_response",
) -> dict[str, list[SteamDTPlatformPrice]]:
    """Parse SteamDT batch-price response data into grouped platform-level price records."""

    data = _require_response_wrapper(payload, endpoint=endpoint)
    if not isinstance(data, list):
        raise SteamDTResponseParseError(
            "SteamDT batch price response data must be a list",
            endpoint=endpoint,
        )

    parsed: dict[str, list[SteamDTPlatformPrice]] = {}
    for batch_item in data:
        if not isinstance(batch_item, dict):
            raise ValueError("SteamDT batch price item must be a dict")
        market_hash_name = batch_item.get("marketHashName")
        if market_hash_name is None or str(market_hash_name).strip() == "":
            raise ValueError("SteamDT batch item marketHashName is required")
        data_list = batch_item.get("dataList")
        if data_list is None:
            parsed[str(market_hash_name)] = []
            continue
        if not isinstance(data_list, list):
            raise ValueError("SteamDT batch item dataList must be a list")
        parsed[str(market_hash_name)] = parse_price_single_response(
            str(market_hash_name),
            {"success": True, "data": data_list},
            endpoint=endpoint,
        )
    return parsed



def parse_avg_price_response(
    market_hash_name: str,
    payload: dict[str, Any],
    *,
    endpoint: str | None = "parse_avg_price_response",
) -> SteamDTAvgPrice:
    """Parse SteamDT 7-day average price response into a normalized avg-price model."""

    if not market_hash_name.strip():
        raise ValueError("market_hash_name cannot be empty")

    data = _require_response_wrapper(payload, endpoint=endpoint)
    if not isinstance(data, dict):
        raise ValueError("SteamDT avg price response data must be a dict")

    response_market_hash_name = data.get("marketHashName")
    if response_market_hash_name not in (None, market_hash_name):
        raise ValueError("response marketHashName does not match requested market_hash_name")

    data_list = data.get("dataList")
    if data_list is None:
        platform_avg_prices: dict[str, Decimal] = {}
    else:
        if not isinstance(data_list, list):
            raise ValueError("SteamDT avg price dataList must be a list")
        platform_avg_prices = {}
        for item in data_list:
            if not isinstance(item, dict):
                raise ValueError("SteamDT avg price platform item must be a dict")
            platform = item.get("platform")
            if platform is None or str(platform).strip() == "":
                raise ValueError("SteamDT avg price platform is required")
            avg_price = _to_decimal_or_none(item.get("avgPrice"))
            if avg_price is None:
                raise ValueError("SteamDT avg price platform avgPrice is required")
            platform_avg_prices[str(platform)] = avg_price

    return SteamDTAvgPrice(
        market_hash_name=market_hash_name,
        avg_price_cny=_to_decimal_or_none(data.get("avgPrice")),
        platform_avg_prices=platform_avg_prices,
        raw=dict(data),
    )



def parse_base_item_info_response(
    payload: dict[str, Any],
) -> list[SteamDTBaseItemInfo]:
    """Parse SteamDT base-item response data into normalized base item info models."""

    data = _require_response_wrapper(payload)
    if not isinstance(data, list):
        raise ValueError("SteamDT base item response data must be a list")

    parsed: list[SteamDTBaseItemInfo] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("SteamDT base item entry must be a dict")
        market_hash_name = item.get("marketHashName")
        if market_hash_name is None or str(market_hash_name).strip() == "":
            raise ValueError("SteamDT base item marketHashName is required")
        parsed.append(
            SteamDTBaseItemInfo(
                market_hash_name=str(market_hash_name),
                raw=dict(item),
            )
        )
    return parsed



def parse_wear_response(
    inspect_link: str,
    payload: dict[str, Any],
) -> SteamDTWearParseResult:
    """Parse SteamDT wear response into normalized wear information and metadata."""

    data = _require_response_wrapper(payload)
    if not isinstance(data, dict):
        raise ValueError("SteamDT wear response data must be a dict")

    item_preview_data = data.get("itemPreviewData")
    if item_preview_data is None:
        wear_info = SteamDTWearInfo(
            inspect_link=inspect_link or None,
            float_value=None,
            paint_seed=None,
            raw=dict(data),
        )
        return SteamDTWearParseResult(
            inspect_link=inspect_link or None,
            wear_info=wear_info,
            sync=data.get("sync"),
            success=data.get("success"),
            task_id=(
                None if data.get("taskId") in (None, "") else str(data.get("taskId"))
            ),
            raw=dict(data),
        )

    if not isinstance(item_preview_data, dict):
        raise ValueError("SteamDT itemPreviewData must be a dict when present")

    float_wear = item_preview_data.get("floatWear")
    parsed_float = None
    if float_wear not in (None, ""):
        parsed_float = float(str(float_wear))
    paint_seed = _to_int_or_none(item_preview_data.get("paintseed"))
    wear_info = SteamDTWearInfo(
        inspect_link=inspect_link or None,
        float_value=parsed_float,
        paint_seed=paint_seed,
        raw=dict(item_preview_data),
    )
    return SteamDTWearParseResult(
        inspect_link=inspect_link or None,
        wear_info=wear_info,
        sync=data.get("sync"),
        success=data.get("success"),
        task_id=(None if data.get("taskId") in (None, "") else str(data.get("taskId"))),
        raw=dict(data),
    )



def parse_kline_response(
    market_hash_name: str,
    payload: dict[str, Any],
) -> list[SteamDTHistoricalPricePoint]:
    """Validate wrapper shape and refuse to parse kline points until mapping is confirmed."""

    if not market_hash_name.strip():
        raise ValueError("market_hash_name cannot be empty")
    _require_response_wrapper(payload)
    raise NotImplementedError(KLINE_MAPPING_UNCONFIRMED_ERROR)




def _select_lowest_positive_sell_price_quote(
    market_hash_name: str,
    platform_prices: list[SteamDTPlatformPrice],
    *,
    original_payload: dict[str, Any] | None = None,
) -> SteamDTPriceQuote | None:
    """Select the lowest positive sell price from parsed platform prices."""

    positive_sell_prices = [
        price
        for price in platform_prices
        if price.sell_price_cny is not None and price.sell_price_cny > 0
    ]
    if not positive_sell_prices:
        return None

    selected = min(
        positive_sell_prices,
        key=lambda price: price.sell_price_cny or Decimal("Infinity"),
    )
    return SteamDTPriceQuote(
        market_hash_name=market_hash_name,
        price_cny=selected.sell_price_cny or Decimal("0"),
        source="steamdt",
        raw={
            "selected_strategy": "lowest_positive_sell_price",
            "platform_prices": [price.raw for price in platform_prices],
            "original_payload": original_payload,
        },
    )


def _parse_retry_after_seconds(value: str | None) -> float | None:
    """Parse Retry-After seconds when SteamDT/httpx provides it as a number."""

    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _steamdt_endpoint_for_path(path: str) -> SteamDTEndpoint:
    """Map a confirmed SteamDT path to its stable local endpoint identifier."""

    if path == "/open/cs2/v1/price/single":
        return SteamDTEndpoint.PRICE_SINGLE
    if path == "/open/cs2/v1/price/batch":
        return SteamDTEndpoint.PRICE_BATCH
    if path == "/open/cs2/v1/price/avg":
        return SteamDTEndpoint.PRICE_AVG
    if path == "/open/cs2/v1/base":
        return SteamDTEndpoint.BASE
    if path == "/open/cs2/item/v1/kline":
        return SteamDTEndpoint.KLINE
    if path == "/open/cs2/v1/wear":
        return SteamDTEndpoint.WEAR
    raise ValueError(f"unknown SteamDT endpoint path: {path}")


class SteamDTHttpClient:
    """HTTP client skeleton for future direct SteamDT REST access.

    Public domain-facing methods remain unimplemented until endpoint and field mapping
    details are fully confirmed in docs/STEAMDT_API_NOTES.md.
    """

    def __init__(
        self,
        config: SteamDTClientConfig,
        http_client: httpx.AsyncClient | None = None,
        *,
        rate_limiter: SteamDTRateLimiter | None = None,
    ) -> None:
        self.config = config
        self.http_client = http_client
        self.rate_limiter = rate_limiter or InMemorySteamDTRateLimiter(
            config.rate_limit_policies
        )

    async def get_price_single_with_selection(
        self,
        market_hash_name: str,
        *,
        selection_config: SteamDTPriceSelectionConfig | None = None,
        avg_price_cny: Decimal | None = None,
    ) -> SteamDTPriceQuote:
        """Fetch a single price quote and apply a caller-provided selection strategy."""

        if not market_hash_name.strip():
            raise ValueError("market_hash_name cannot be empty")
        if self.config.dry_run:
            raise RuntimeError("real SteamDT HTTP requests are disabled in dry-run mode")

        path = "/open/cs2/v1/price/single"
        endpoint = SteamDTEndpoint.PRICE_SINGLE
        payload = await self._request_json(
            "GET",
            path,
            endpoint=endpoint,
            params={"marketHashName": market_hash_name},
        )
        try:
            platform_prices = parse_price_single_response(
                market_hash_name,
                payload,
                endpoint=path,
            )
        except SteamDTRateLimitError as exc:
            await self.rate_limiter.record_server_limit(
                endpoint,
                retry_after_seconds=exc.retry_after_seconds,
            )
            raise
        except SteamDTError:
            raise
        except ValueError as exc:
            raise SteamDTResponseParseError(str(exc), endpoint=path) from exc
        selected_result = select_steamdt_price_quote(
            market_hash_name,
            platform_prices,
            config=selection_config or SteamDTPriceSelectionConfig(),
            avg_price_cny=avg_price_cny,
            original_payload=payload,
        )
        if selected_result.quote is None:
            raise RuntimeError(
                "SteamDT single price response did not contain any acceptable sellPrice "
                f"values; reason_codes={selected_result.reason_codes}"
            )
        return selected_result.quote

    async def get_price_single(self, market_hash_name: str) -> SteamDTPriceQuote:
        """Fetch one official read-only SteamDT price quote via the single-price endpoint."""

        return await self.get_price_single_with_selection(market_hash_name)

    async def get_price_batch_with_selection(
        self,
        market_hash_names: list[str],
        *,
        selection_config: SteamDTPriceSelectionConfig | None = None,
        avg_prices_by_name: dict[str, Decimal] | None = None,
    ) -> SteamDTBatchPriceResult:
        """Fetch batch price quotes and apply a caller-provided selection strategy per name."""

        if not market_hash_names:
            return SteamDTBatchPriceResult(quotes={}, missing=[], raw=None)

        cleaned_names = list(
            dict.fromkeys(name.strip() for name in market_hash_names if name.strip())
        )
        if not cleaned_names:
            return SteamDTBatchPriceResult(quotes={}, missing=[], raw=None)
        if self.config.dry_run:
            return SteamDTBatchPriceResult(quotes={}, missing=cleaned_names, raw=None)

        path = "/open/cs2/v1/price/batch"
        endpoint = SteamDTEndpoint.PRICE_BATCH
        payload = await self._request_json(
            "POST",
            path,
            endpoint=endpoint,
            json={"marketHashNames": cleaned_names},
        )
        try:
            parsed_batch = parse_price_batch_response(cleaned_names, payload, endpoint=path)
        except SteamDTRateLimitError as exc:
            await self.rate_limiter.record_server_limit(
                endpoint,
                retry_after_seconds=exc.retry_after_seconds,
            )
            raise
        except SteamDTError:
            raise
        except ValueError as exc:
            raise SteamDTResponseParseError(str(exc), endpoint=path) from exc

        quotes: dict[str, SteamDTPriceQuote] = {}
        missing: list[str] = []
        for name in cleaned_names:
            platform_prices = parsed_batch.get(name)
            if platform_prices is None:
                missing.append(name)
                continue
            selection_result = select_steamdt_price_quote(
                name,
                platform_prices,
                config=selection_config or SteamDTPriceSelectionConfig(),
                avg_price_cny=None if avg_prices_by_name is None else avg_prices_by_name.get(name),
                original_payload=payload,
            )
            if selection_result.quote is None:
                missing.append(name)
                continue
            quotes[name] = selection_result.quote

        return SteamDTBatchPriceResult(
            quotes=quotes,
            missing=missing,
            raw=payload,
        )

    async def get_price_batch(
        self,
        market_hash_names: list[str],
    ) -> SteamDTBatchPriceResult:
        """Fetch official read-only SteamDT batch price quotes via the batch-price endpoint."""

        return await self.get_price_batch_with_selection(market_hash_names)

    async def get_avg_price(self, market_hash_name: str) -> SteamDTAvgPrice:
        """Fetch one official read-only SteamDT 7-day average price result."""

        if not market_hash_name.strip():
            raise ValueError("market_hash_name cannot be empty")
        if self.config.dry_run:
            raise RuntimeError("real SteamDT HTTP requests are disabled in dry-run mode")

        path = "/open/cs2/v1/price/avg"
        endpoint = SteamDTEndpoint.PRICE_AVG
        payload = await self._request_json(
            "GET",
            path,
            endpoint=endpoint,
            params={"marketHashName": market_hash_name},
        )
        try:
            return parse_avg_price_response(market_hash_name, payload, endpoint=path)
        except SteamDTRateLimitError as exc:
            await self.rate_limiter.record_server_limit(
                endpoint,
                retry_after_seconds=exc.retry_after_seconds,
            )
            raise
        except SteamDTError:
            raise
        except ValueError as exc:
            raise SteamDTResponseParseError(str(exc), endpoint=path) from exc

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
        endpoint: SteamDTEndpoint | None = None,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an HTTP request with timeout, retry, and endpoint rate limiting."""

        if self.config.dry_run:
            raise RuntimeError("real SteamDT HTTP requests are disabled in dry-run mode")
        if not self.config.base_url.strip():
            raise ValueError("base_url cannot be empty")

        limiter_endpoint = endpoint or _steamdt_endpoint_for_path(path)
        last_error: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            await self.rate_limiter.acquire(limiter_endpoint)
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
            except httpx.TransportError as exc:
                last_error = SteamDTTransportError(str(exc), endpoint=path)
                if attempt >= self.config.max_retries:
                    raise last_error from exc
                await asyncio.sleep(2**attempt * 0.1)
                continue
            except httpx.HTTPError as exc:
                raise SteamDTTransportError(str(exc), endpoint=path) from exc

            status_code = response.status_code
            if status_code == 429:
                retry_after_seconds = _parse_retry_after_seconds(
                    response.headers.get("Retry-After")
                )
                await self.rate_limiter.record_server_limit(
                    limiter_endpoint,
                    retry_after_seconds=retry_after_seconds,
                )
                raise SteamDTRateLimitError(
                    "SteamDT HTTP rate limit reached",
                    endpoint=path,
                    retry_after_seconds=retry_after_seconds,
                    status_code=status_code,
                )
            if 400 <= status_code < 500:
                raise SteamDTHttpStatusError(
                    "SteamDT HTTP client error",
                    endpoint=path,
                    status_code=status_code,
                )
            if status_code >= 500:
                last_error = SteamDTHttpStatusError(
                    "SteamDT HTTP server error",
                    endpoint=path,
                    status_code=status_code,
                )
                if attempt >= self.config.max_retries:
                    raise last_error
                await asyncio.sleep(2**attempt * 0.1)
                continue

            try:
                payload = response.json()
            except ValueError as exc:
                raise SteamDTResponseParseError(
                    "SteamDT response JSON could not be parsed",
                    endpoint=path,
                ) from exc
            if not isinstance(payload, dict):
                raise SteamDTResponseParseError(
                    "SteamDT response payload must be a JSON object",
                    endpoint=path,
                )
            return payload

        if last_error is not None:
            raise last_error
        raise SteamDTTransportError("SteamDT HTTP request failed", endpoint=path)

    def _build_headers(self) -> dict[str, str]:
        """Build safe HTTP headers for confirmed transport-level behavior only."""

        headers = {"Content-Type": "application/json"}
        if not self.config.dry_run and self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers
