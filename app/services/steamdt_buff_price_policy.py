from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import NoReturn

from app.clients.steamdt_client import SteamDTPlatformPrice
from app.services.steamdt_market_data import SteamDTMarketDataResult

_FIXED_ERROR_MESSAGE = "SteamDT BUFF output price selection failed"
_BUFF_PLATFORM = "BUFF"

__all__ = (
    "SteamDTBuffPriceSelectionReason",
    "SteamDTBuffPriceSelectionError",
    "SteamDTBuffOutputPrice",
    "select_buff_output_price",
)


class SteamDTBuffPriceSelectionReason(StrEnum):
    """Stable reasons why a BUFF aggregate sell price was unavailable."""

    INVALID_MARKET_DATA = "invalid_market_data"
    BUFF_RECORD_MISSING = "buff_record_missing"
    DUPLICATE_BUFF_RECORDS = "duplicate_buff_records"
    BUFF_SELL_PRICE_MISSING = "buff_sell_price_missing"
    BUFF_SELL_PRICE_NON_FINITE = "buff_sell_price_non_finite"
    BUFF_SELL_PRICE_NON_POSITIVE = "buff_sell_price_non_positive"


class SteamDTBuffPriceSelectionError(RuntimeError):
    """A fixed, non-sensitive BUFF price-policy failure."""

    def __init__(self, *, reason: SteamDTBuffPriceSelectionReason) -> None:
        if type(reason) is not SteamDTBuffPriceSelectionReason:
            raise TypeError("reason must be a SteamDTBuffPriceSelectionReason")
        self.reason = reason
        super().__init__(_FIXED_ERROR_MESSAGE)


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamDTBuffOutputPrice:
    """Detached gross BUFF aggregate sell price under the project CNY policy."""

    market_hash_name: str
    platform: str
    sell_price_cny: Decimal
    sell_count: int | None
    platform_item_id: str | None
    update_time: int | str | None

    def __post_init__(self) -> None:
        try:
            _validate_market_hash_name(self.market_hash_name)
            if type(self.platform) is not str or self.platform != _BUFF_PLATFORM:
                _raise_selection_error(
                    SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA
                )
            _validate_selected_price(self.sell_price_cny)
            _validate_sell_count(self.sell_count)
            _validate_platform_item_id(self.platform_item_id)
            _validate_update_time(self.update_time)
        except MemoryError:
            raise
        except SteamDTBuffPriceSelectionError:
            raise
        except Exception:
            _raise_selection_error(SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA)


def select_buff_output_price(
    *,
    market_data: SteamDTMarketDataResult,
) -> SteamDTBuffOutputPrice:
    """Select one exact BUFF gross sell price without bid or platform fallback."""

    try:
        if type(market_data) is not SteamDTMarketDataResult:
            _raise_selection_error(SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA)
        _validate_market_hash_name(market_data.market_hash_name)
        if type(market_data.quotes) is not tuple:
            _raise_selection_error(SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA)

        buff_quotes: list[SteamDTPlatformPrice] = []
        for quote in market_data.quotes:
            if type(quote) is not SteamDTPlatformPrice:
                _raise_selection_error(
                    SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA
                )
            if type(quote.platform) is not str or not quote.platform.strip():
                _raise_selection_error(
                    SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA
                )
            if quote.platform == _BUFF_PLATFORM:
                buff_quotes.append(quote)

        if not buff_quotes:
            _raise_selection_error(SteamDTBuffPriceSelectionReason.BUFF_RECORD_MISSING)
        if len(buff_quotes) != 1:
            _raise_selection_error(
                SteamDTBuffPriceSelectionReason.DUPLICATE_BUFF_RECORDS
            )

        quote = buff_quotes[0]
        if quote.sell_price_cny is None:
            _raise_selection_error(
                SteamDTBuffPriceSelectionReason.BUFF_SELL_PRICE_MISSING
            )
        _validate_selected_price(quote.sell_price_cny)
        _validate_sell_count(quote.sell_count)
        _validate_platform_item_id(quote.platform_item_id)
        _validate_update_time(quote.update_time)
        return SteamDTBuffOutputPrice(
            market_hash_name=market_data.market_hash_name,
            platform=quote.platform,
            sell_price_cny=quote.sell_price_cny,
            sell_count=quote.sell_count,
            platform_item_id=quote.platform_item_id,
            update_time=quote.update_time,
        )
    except MemoryError:
        raise
    except SteamDTBuffPriceSelectionError:
        raise
    except Exception:
        _raise_selection_error(SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA)


def _validate_market_hash_name(value: object) -> None:
    if type(value) is not str or not value or value != value.strip():
        _raise_selection_error(SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA)


def _validate_selected_price(value: object) -> None:
    if type(value) is not Decimal:
        _raise_selection_error(SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA)
    if not value.is_finite():
        _raise_selection_error(
            SteamDTBuffPriceSelectionReason.BUFF_SELL_PRICE_NON_FINITE
        )
    if value <= 0:
        _raise_selection_error(
            SteamDTBuffPriceSelectionReason.BUFF_SELL_PRICE_NON_POSITIVE
        )


def _validate_sell_count(value: object) -> None:
    if value is not None and (type(value) is not int or value < 0):
        _raise_selection_error(SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA)


def _validate_platform_item_id(value: object) -> None:
    if value is not None and type(value) is not str:
        _raise_selection_error(SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA)


def _validate_update_time(value: object) -> None:
    if value is not None and type(value) not in (int, str):
        _raise_selection_error(SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA)


def _raise_selection_error(reason: SteamDTBuffPriceSelectionReason) -> NoReturn:
    raise SteamDTBuffPriceSelectionError(reason=reason)
