import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from app.clients.steamdt_client import (
    SteamDTClient,
    SteamDTPriceQuote,
)
from app.clients.steamdt_errors import SteamDTError
from app.clients.steamdt_price_selection import SteamDTPriceSelectionConfig


@dataclass(frozen=True)
class PriceQuote:
    """Normalized generic price quote used by valuation components."""

    market_hash_name: str
    price_cny: Decimal
    source: str
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.market_hash_name.strip():
            raise ValueError("market_hash_name cannot be empty")
        if self.price_cny < 0:
            raise ValueError("price_cny must be greater than or equal to 0")
        if not self.source.strip():
            raise ValueError("source cannot be empty")


@dataclass(frozen=True)
class PriceLookupResult:
    """Batch lookup result for generic price providers."""

    quotes: dict[str, PriceQuote]
    missing: list[str]
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SteamDTPriceProviderConfig:
    """Configuration for SteamDT-backed price provider selection behavior."""

    selection_config: SteamDTPriceSelectionConfig | None = None
    enable_avg_sanity_check: bool = False
    fail_closed_on_avg_error: bool = True
    max_avg_requests_per_batch: int = 10

    def __post_init__(self) -> None:
        if self.max_avg_requests_per_batch < 0:
            raise ValueError("max_avg_requests_per_batch must be greater than or equal to 0")


class PriceProvider(Protocol):
    """Protocol for generic market price providers."""

    async def get_price(self, market_hash_name: str) -> PriceQuote:
        """Return a single normalized price quote for one market hash name."""

    async def get_prices(self, market_hash_names: list[str]) -> PriceLookupResult:
        """Return normalized quotes for many market hash names."""


class MockPriceProvider:
    """Deterministic in-memory price provider for unit tests."""

    def __init__(
        self,
        quotes_by_name: dict[str, PriceQuote] | None = None,
        fail_on_single_missing: bool = True,
    ) -> None:
        self.quotes_by_name = quotes_by_name or {}
        self.fail_on_single_missing = fail_on_single_missing

    async def get_price(self, market_hash_name: str) -> PriceQuote:
        """Return a deterministic single quote or raise if configured to fail."""

        if market_hash_name in self.quotes_by_name:
            return self.quotes_by_name[market_hash_name]
        if self.fail_on_single_missing:
            raise RuntimeError(
                f"missing mock price for market_hash_name: {market_hash_name}"
            )
        raise RuntimeError(f"price is missing for market_hash_name: {market_hash_name}")

    async def get_prices(self, market_hash_names: list[str]) -> PriceLookupResult:
        """Return deterministic batch quotes with missing names preserved."""

        quotes = {
            name: self.quotes_by_name[name]
            for name in market_hash_names
            if name in self.quotes_by_name
        }
        missing = [name for name in market_hash_names if name not in self.quotes_by_name]
        return PriceLookupResult(quotes=quotes, missing=missing)


class SteamDTPriceProvider:
    """SteamDT-backed adapter from SteamDT client models into generic price quotes."""

    def __init__(
        self,
        steamdt_client: SteamDTClient,
        config: SteamDTPriceProviderConfig | None = None,
    ) -> None:
        self.steamdt_client = steamdt_client
        self.config = config or SteamDTPriceProviderConfig()

    async def get_price(self, market_hash_name: str) -> PriceQuote:
        """Fetch and convert a single SteamDT price quote into a generic price quote."""

        if not market_hash_name.strip():
            raise ValueError("market_hash_name cannot be empty")

        avg_price_cny: Decimal | None = None
        if self.config.enable_avg_sanity_check:
            avg_price_cny = await self._get_single_avg_price(market_hash_name)

        try:
            selection_method = getattr(
                self.steamdt_client,
                "get_price_single_with_selection",
                None,
            )
            if self.config.enable_avg_sanity_check and callable(selection_method):
                quote = await selection_method(
                    market_hash_name,
                    selection_config=self.config.selection_config,
                    avg_price_cny=avg_price_cny,
                )
            else:
                quote = await self.steamdt_client.get_price_single(market_hash_name)
        except SteamDTError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"STEAMDT_PRICE_REQUEST_FAILED: {_safe_error_message(exc)}"
            ) from exc

        return _convert_steamdt_price_quote(quote)

    async def get_prices(self, market_hash_names: list[str]) -> PriceLookupResult:
        """Fetch and convert multiple SteamDT price quotes into generic price quotes."""

        cleaned_names = _clean_market_hash_names(market_hash_names)
        if not cleaned_names:
            return PriceLookupResult(quotes={}, missing=[], errors=[])

        avg_prices_by_name: dict[str, Decimal] | None = None
        errors: list[str] = []
        if self.config.enable_avg_sanity_check:
            avg_result = await self._get_batch_avg_prices(cleaned_names)
            if isinstance(avg_result, PriceLookupResult):
                return avg_result
            avg_prices_by_name, errors = avg_result

        try:
            selection_method = getattr(
                self.steamdt_client,
                "get_price_batch_with_selection",
                None,
            )
            if self.config.enable_avg_sanity_check and callable(selection_method):
                batch_result = await selection_method(
                    cleaned_names,
                    selection_config=self.config.selection_config,
                    avg_prices_by_name=avg_prices_by_name,
                )
            else:
                batch_result = await self.steamdt_client.get_price_batch(cleaned_names)
        except Exception as exc:
            return PriceLookupResult(
                quotes={},
                missing=cleaned_names,
                errors=[f"STEAMDT_PRICE_BATCH_FAILED: {_safe_error_message(exc)}"],
            )

        quotes = {
            name: _convert_steamdt_price_quote(quote)
            for name, quote in batch_result.quotes.items()
        }
        return PriceLookupResult(
            quotes=quotes,
            missing=list(batch_result.missing),
            errors=errors,
        )

    async def _get_single_avg_price(self, market_hash_name: str) -> Decimal | None:
        """Fetch optional avg sanity input for one name according to provider config."""

        if not _supports_method(self.steamdt_client, "get_avg_price"):
            if self.config.fail_closed_on_avg_error:
                raise RuntimeError(
                    "AVG_SANITY_UNSUPPORTED: SteamDT client does not support get_avg_price"
                )
            return None

        try:
            avg_result = await self.steamdt_client.get_avg_price(market_hash_name)
        except Exception as exc:
            if self.config.fail_closed_on_avg_error:
                raise RuntimeError(
                    f"AVG_SANITY_AVG_REQUEST_FAILED: {_safe_error_message(exc)}"
                ) from exc
            return None
        return avg_result.avg_price_cny

    async def _get_batch_avg_prices(
        self,
        market_hash_names: list[str],
    ) -> tuple[dict[str, Decimal], list[str]] | PriceLookupResult:
        """Fetch optional avg sanity inputs for a batch without expanding request volume."""

        if len(market_hash_names) > self.config.max_avg_requests_per_batch:
            return PriceLookupResult(
                quotes={},
                missing=market_hash_names,
                errors=[
                    "AVG_SANITY_BATCH_LIMIT_EXCEEDED: "
                    f"requested={len(market_hash_names)}, "
                    f"limit={self.config.max_avg_requests_per_batch}"
                ],
            )

        if not _supports_method(self.steamdt_client, "get_avg_price"):
            message = "AVG_SANITY_UNSUPPORTED: SteamDT client does not support get_avg_price"
            if self.config.fail_closed_on_avg_error:
                return PriceLookupResult(
                    quotes={},
                    missing=market_hash_names,
                    errors=[message],
                )
            return {}, [message]

        avg_prices_by_name: dict[str, Decimal] = {}
        errors: list[str] = []
        for name in market_hash_names:
            try:
                avg_result = await self.steamdt_client.get_avg_price(name)
            except Exception as exc:
                message = (
                    "AVG_SANITY_AVG_REQUEST_FAILED: "
                    f"market_hash_name={name}, error={_safe_error_message(exc)}"
                )
                if self.config.fail_closed_on_avg_error:
                    return PriceLookupResult(
                        quotes={},
                        missing=market_hash_names,
                        errors=[message],
                    )
                errors.append(message)
                continue

            if avg_result.avg_price_cny is not None:
                avg_prices_by_name[name] = avg_result.avg_price_cny

        return avg_prices_by_name, errors



def _convert_steamdt_price_quote(quote: SteamDTPriceQuote) -> PriceQuote:
    """Convert a SteamDT-specific price quote into the generic price quote model."""

    return PriceQuote(
        market_hash_name=quote.market_hash_name,
        price_cny=quote.price_cny,
        source=quote.source or "steamdt",
        raw=quote.raw,
    )



def _clean_market_hash_names(market_hash_names: list[str]) -> list[str]:
    """Strip, drop empty names, and deduplicate while preserving order."""

    return list(dict.fromkeys(name.strip() for name in market_hash_names if name.strip()))



def _supports_method(client: object, method_name: str) -> bool:
    """Return whether an injected client exposes a callable optional method."""

    return callable(getattr(client, method_name, None))



def _safe_error_message(error: Exception, api_key: str | None = None) -> str:
    """Format an exception without leaking API keys or Authorization bearer values."""

    message = str(error)
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    message = re.sub(
        r"Authorization\s*[:=]\s*Bearer\s+[^\s,;]+",
        "Authorization: Bearer [REDACTED]",
        message,
        flags=re.IGNORECASE,
    )
    message = re.sub(
        r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}",
        "Bearer [REDACTED]",
        message,
    )
    if len(message) > 300:
        message = f"{message[:300]}..."
    if not message:
        return type(error).__name__
    return f"{type(error).__name__}: {message}"
