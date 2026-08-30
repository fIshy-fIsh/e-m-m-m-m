from decimal import Decimal

import pytest

from app.clients.steamdt_client import SteamDTPlatformPrice
from app.clients.steamdt_price_selection import SteamDTPriceSelectionConfig
from app.services.scanner_cached_buff_price_selector import (
    SCANNER_STRICT_BUFF_SELECTION_STRATEGY,
    SCANNER_STRICT_BUFF_SOURCE,
    select_scanner_cached_buff_price,
)

NAME = "M4A1-S | Knight (Factory New)"


def _price(
    platform: str,
    sell: Decimal | None,
    *,
    bidding: Decimal | None = Decimal("999"),
) -> SteamDTPlatformPrice:
    return SteamDTPlatformPrice(
        platform=platform,
        platform_item_id=f"{platform}-id",
        sell_price_cny=sell,
        sell_count=3,
        bidding_price_cny=bidding,
        bidding_count=50,
        update_time="opaque",
        raw={"ignored": True},
    )


def test_buff_selected_even_when_non_buff_is_cheaper() -> None:
    result = select_scanner_cached_buff_price(
        NAME,
        [_price("Steam", Decimal("1")), _price("BUFF", Decimal("100"))],
    )

    assert result.market_hash_name == NAME
    assert result.selected_platform == "BUFF"
    assert result.selected_strategy == SCANNER_STRICT_BUFF_SELECTION_STRATEGY
    assert result.quote is not None
    assert result.quote.market_hash_name == NAME
    assert result.quote.price_cny == Decimal("100")
    assert result.quote.source == SCANNER_STRICT_BUFF_SOURCE
    assert result.quote.raw is None


@pytest.mark.parametrize(
    ("prices", "reason"),
    [
        ([_price("Steam", Decimal("1"))], "buff_record_missing"),
        (
            [_price("BUFF", Decimal("2")), _price("BUFF", Decimal("3"))],
            "duplicate_buff_records",
        ),
        ([_price("BUFF", None)], "buff_sell_price_missing"),
        ([_price("BUFF", Decimal("0"))], "buff_sell_price_non_positive"),
    ],
)
def test_strict_buff_failures_return_deterministic_selection_failure(
    prices: list[SteamDTPlatformPrice],
    reason: str,
) -> None:
    result = select_scanner_cached_buff_price(NAME, prices)

    assert result.market_hash_name == NAME
    assert result.quote is None
    assert result.selected_platform is None
    assert result.selected_strategy == SCANNER_STRICT_BUFF_SELECTION_STRATEGY
    assert result.reason_codes == [reason]


def test_generic_inputs_cannot_weaken_strict_buff_selection() -> None:
    config = SteamDTPriceSelectionConfig(
        require_bidding_price=True,
        min_bidding_count=10_000,
        fallback_to_lowest_positive=True,
    )
    result = select_scanner_cached_buff_price(
        NAME,
        [_price("Steam", Decimal("1")), _price("BUFF", Decimal("100"), bidding=None)],
        config=config,
        avg_price_cny=Decimal("0.01"),
        original_payload={"secret": "not retained"},
    )

    assert result.quote is not None
    assert result.quote.market_hash_name == NAME
    assert result.quote.price_cny == Decimal("100")
    assert result.selected_platform == "BUFF"
    assert result.raw is None


def test_exact_name_is_not_stripped_or_substituted() -> None:
    with pytest.raises(ValueError, match="surrounding whitespace"):
        select_scanner_cached_buff_price(
            f" {NAME}",
            [_price("BUFF", Decimal("100"))],
        )


def test_memory_error_from_input_iteration_propagates_verbatim() -> None:
    sentinel = MemoryError("selector sentinel")

    class MemoryList(list[SteamDTPlatformPrice]):
        def __iter__(self):  # type: ignore[no-untyped-def]
            raise sentinel

    with pytest.raises(MemoryError) as exc_info:
        select_scanner_cached_buff_price(NAME, MemoryList())

    assert exc_info.value is sentinel


def test_contract_error_is_not_converted_to_selection_failure() -> None:
    with pytest.raises(TypeError, match="SteamDTPlatformPrice"):
        select_scanner_cached_buff_price(
            NAME,
            [object()],  # type: ignore[list-item]
        )
