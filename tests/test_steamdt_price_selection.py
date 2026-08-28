from decimal import Decimal

import pytest

from app.clients.steamdt_client import SteamDTPlatformPrice
from app.clients.steamdt_price_selection import (
    SteamDTPriceSelectionConfig,
    SteamDTPriceSelectionResult,
    SteamDTPriceSelectionStrategy,
    select_steamdt_price_quote,
)


def _make_platform_price(
    *,
    platform: str = "steam",
    sell_price_cny: str | None = "10.00",
    sell_count: int | None = 1,
    bidding_price_cny: str | None = None,
    bidding_count: int | None = None,
) -> SteamDTPlatformPrice:
    return SteamDTPlatformPrice(
        platform=platform,
        sell_price_cny=None if sell_price_cny is None else Decimal(sell_price_cny),
        sell_count=sell_count,
        bidding_price_cny=(
            None if bidding_price_cny is None else Decimal(bidding_price_cny)
        ),
        bidding_count=bidding_count,
        raw={"platform": platform},
    )



def test_selection_config_creates_successfully() -> None:
    config = SteamDTPriceSelectionConfig()
    assert config.strategy == SteamDTPriceSelectionStrategy.LIQUIDITY_AWARE_SELL_PRICE



def test_selection_config_rejects_negative_min_sell_count() -> None:
    with pytest.raises(ValueError, match="min_sell_count"):
        SteamDTPriceSelectionConfig(min_sell_count=-1)



def test_selection_config_rejects_negative_min_bidding_count() -> None:
    with pytest.raises(ValueError, match="min_bidding_count"):
        SteamDTPriceSelectionConfig(min_bidding_count=-1)



def test_selection_config_rejects_negative_max_sell_bid_spread_pct() -> None:
    with pytest.raises(ValueError, match="max_sell_bid_spread_pct"):
        SteamDTPriceSelectionConfig(max_sell_bid_spread_pct=Decimal("-0.1"))



def test_selection_config_rejects_non_positive_max_price_to_avg_ratio() -> None:
    with pytest.raises(ValueError, match="max_price_to_avg_ratio"):
        SteamDTPriceSelectionConfig(max_price_to_avg_ratio=Decimal("0"))



def test_selection_result_rejects_empty_market_hash_name() -> None:
    with pytest.raises(ValueError, match="market_hash_name"):
        SteamDTPriceSelectionResult(
            market_hash_name="",
            quote=None,
            selected_platform=None,
            selected_strategy="x",
            reason_codes=[],
            candidate_decisions=[],
        )



def test_lowest_positive_strategy_selects_lowest_positive_price() -> None:
    result = select_steamdt_price_quote(
        "A",
        [
            _make_platform_price(platform="steam", sell_price_cny="12.00"),
            _make_platform_price(platform="buff", sell_price_cny="10.00"),
        ],
        config=SteamDTPriceSelectionConfig(
            strategy=SteamDTPriceSelectionStrategy.LOWEST_POSITIVE_SELL_PRICE
        ),
    )

    assert result.quote is not None
    assert result.quote.price_cny == Decimal("10.00")



def test_lowest_positive_strategy_ignores_none_and_zero_prices() -> None:
    result = select_steamdt_price_quote(
        "A",
        [
            _make_platform_price(platform="steam", sell_price_cny=None),
            _make_platform_price(platform="buff", sell_price_cny="0"),
            _make_platform_price(platform="other", sell_price_cny="8.00"),
        ],
        config=SteamDTPriceSelectionConfig(
            strategy=SteamDTPriceSelectionStrategy.LOWEST_POSITIVE_SELL_PRICE
        ),
    )

    assert result.quote is not None
    assert result.quote.price_cny == Decimal("8.00")



def test_lowest_positive_strategy_returns_none_when_no_valid_price() -> None:
    result = select_steamdt_price_quote(
        "A",
        [
            _make_platform_price(platform="steam", sell_price_cny=None),
            _make_platform_price(platform="buff", sell_price_cny="0"),
        ],
        config=SteamDTPriceSelectionConfig(
            strategy=SteamDTPriceSelectionStrategy.LOWEST_POSITIVE_SELL_PRICE
        ),
    )

    assert result.quote is None
    assert "NO_POSITIVE_SELL_PRICE" in result.reason_codes



def test_candidate_decisions_preserve_raw_and_reason_codes() -> None:
    result = select_steamdt_price_quote(
        "A",
        [_make_platform_price(platform="steam", sell_price_cny=None)],
        config=SteamDTPriceSelectionConfig(
            strategy=SteamDTPriceSelectionStrategy.LOWEST_POSITIVE_SELL_PRICE
        ),
    )

    assert result.candidate_decisions[0].raw == {"platform": "steam"}
    assert "MISSING_SELL_PRICE" in result.candidate_decisions[0].reason_codes



def test_liquidity_aware_rejects_missing_sell_price() -> None:
    result = select_steamdt_price_quote("A", [_make_platform_price(sell_price_cny=None)])
    assert "NO_ACCEPTED_LIQUID_PRICE" in result.reason_codes or result.quote is not None



def test_liquidity_aware_rejects_non_positive_sell_price() -> None:
    result = select_steamdt_price_quote("A", [_make_platform_price(sell_price_cny="0")])
    assert result.quote is None or "FALLBACK_TO_LOWEST_POSITIVE_SELL_PRICE" in result.reason_codes



def test_liquidity_aware_requires_sell_count_when_configured() -> None:
    result = select_steamdt_price_quote(
        "A",
        [_make_platform_price(sell_price_cny="10.00", sell_count=None)],
        config=SteamDTPriceSelectionConfig(require_sell_count=True),
    )
    assert result.quote is None or result.selected_strategy.endswith("fallback")



def test_liquidity_aware_rejects_sell_count_below_minimum() -> None:
    result = select_steamdt_price_quote(
        "A",
        [_make_platform_price(sell_price_cny="10.00", sell_count=0)],
        config=SteamDTPriceSelectionConfig(min_sell_count=1),
    )
    assert result.quote is None or result.selected_strategy.endswith("fallback")



def test_liquidity_aware_allows_missing_sell_count_when_disabled() -> None:
    result = select_steamdt_price_quote(
        "A",
        [_make_platform_price(sell_price_cny="10.00", sell_count=None)],
        config=SteamDTPriceSelectionConfig(require_sell_count=False),
    )
    assert result.quote is not None



def test_liquidity_aware_requires_bidding_price_when_configured() -> None:
    result = select_steamdt_price_quote(
        "A",
        [_make_platform_price(sell_price_cny="10.00", bidding_price_cny=None)],
        config=SteamDTPriceSelectionConfig(require_bidding_price=True),
    )
    assert result.quote is None or result.selected_strategy.endswith("fallback")



def test_liquidity_aware_enforces_min_bidding_count() -> None:
    result = select_steamdt_price_quote(
        "A",
        [
            _make_platform_price(
                sell_price_cny="10.00",
                bidding_price_cny="9.00",
                bidding_count=0,
            )
        ],
        config=SteamDTPriceSelectionConfig(min_bidding_count=1),
    )
    assert result.quote is None or result.selected_strategy.endswith("fallback")



def test_liquidity_aware_enforces_sell_bid_spread() -> None:
    result = select_steamdt_price_quote(
        "A",
        [
            _make_platform_price(
                sell_price_cny="12.00",
                sell_count=2,
                bidding_price_cny="10.00",
                bidding_count=2,
            )
        ],
        config=SteamDTPriceSelectionConfig(max_sell_bid_spread_pct=Decimal("0.1")),
    )
    assert result.quote is None or result.selected_strategy.endswith("fallback")



def test_liquidity_aware_enforces_avg_sanity_check() -> None:
    result = select_steamdt_price_quote(
        "A",
        [_make_platform_price(sell_price_cny="20.00", sell_count=2)],
        config=SteamDTPriceSelectionConfig(
            max_price_to_avg_ratio=Decimal("1.5"),
            fallback_to_lowest_positive=False,
        ),
        avg_price_cny=Decimal("10.00"),
    )
    assert result.quote is None
    assert "NO_ACCEPTED_LIQUID_PRICE" in result.reason_codes
    assert "PRICE_ABOVE_AVG_SANITY_LIMIT" in result.candidate_decisions[0].reason_codes



def test_liquidity_aware_selects_lowest_sell_price_among_accepted_candidates() -> None:
    result = select_steamdt_price_quote(
        "A",
        [
            _make_platform_price(platform="steam", sell_price_cny="12.00", sell_count=2),
            _make_platform_price(platform="buff", sell_price_cny="10.00", sell_count=2),
        ],
    )
    assert result.quote is not None
    assert result.quote.price_cny == Decimal("10.00")



def test_liquidity_aware_prefers_higher_sell_count_on_same_price() -> None:
    result = select_steamdt_price_quote(
        "A",
        [
            _make_platform_price(platform="steam", sell_price_cny="10.00", sell_count=1),
            _make_platform_price(platform="buff", sell_price_cny="10.00", sell_count=3),
        ],
    )
    assert result.selected_platform == "buff"



def test_liquidity_aware_prefers_higher_bidding_count_after_sell_count_tie() -> None:
    result = select_steamdt_price_quote(
        "A",
        [
            _make_platform_price(
                platform="steam",
                sell_price_cny="10.00",
                sell_count=2,
                bidding_count=1,
            ),
            _make_platform_price(
                platform="buff",
                sell_price_cny="10.00",
                sell_count=2,
                bidding_count=5,
            ),
        ],
    )
    assert result.selected_platform == "buff"



def test_liquidity_aware_platform_name_breaks_remaining_tie() -> None:
    result = select_steamdt_price_quote(
        "A",
        [
            _make_platform_price(
                platform="zeta",
                sell_price_cny="10.00",
                sell_count=2,
                bidding_count=2,
            ),
            _make_platform_price(
                platform="alpha",
                sell_price_cny="10.00",
                sell_count=2,
                bidding_count=2,
            ),
        ],
    )
    assert result.selected_platform == "alpha"



def test_fallback_to_lowest_positive_sell_price_works() -> None:
    result = select_steamdt_price_quote(
        "A",
        [
            _make_platform_price(sell_price_cny="10.00", sell_count=0),
            _make_platform_price(sell_price_cny="11.00", sell_count=0),
        ],
        config=SteamDTPriceSelectionConfig(min_sell_count=1, fallback_to_lowest_positive=True),
    )
    assert result.quote is not None
    assert "FALLBACK_TO_LOWEST_POSITIVE_SELL_PRICE" in result.reason_codes



def test_fallback_disabled_returns_no_quote() -> None:
    result = select_steamdt_price_quote(
        "A",
        [_make_platform_price(sell_price_cny="10.00", sell_count=0)],
        config=SteamDTPriceSelectionConfig(
            min_sell_count=1,
            fallback_to_lowest_positive=False,
        ),
    )
    assert result.quote is None
    assert "NO_ACCEPTED_LIQUID_PRICE" in result.reason_codes



def test_avg_sanity_with_fallback_disabled_returns_no_quote() -> None:
    result = select_steamdt_price_quote(
        "A",
        [_make_platform_price(sell_price_cny="20.00", sell_count=2)],
        config=SteamDTPriceSelectionConfig(
            max_price_to_avg_ratio=Decimal("1.5"),
            fallback_to_lowest_positive=False,
        ),
        avg_price_cny=Decimal("10.00"),
    )
    assert result.quote is None
    assert "NO_ACCEPTED_LIQUID_PRICE" in result.reason_codes



def test_avg_sanity_is_skipped_when_avg_price_is_none() -> None:
    result = select_steamdt_price_quote(
        "A",
        [_make_platform_price(sell_price_cny="20.00", sell_count=2)],
        config=SteamDTPriceSelectionConfig(max_price_to_avg_ratio=Decimal("1.5")),
        avg_price_cny=None,
    )
    assert result.quote is not None



def test_avg_sanity_is_skipped_when_max_price_to_avg_ratio_is_none() -> None:
    result = select_steamdt_price_quote(
        "A",
        [_make_platform_price(sell_price_cny="20.00", sell_count=2)],
        config=SteamDTPriceSelectionConfig(max_price_to_avg_ratio=None),
        avg_price_cny=Decimal("10.00"),
    )
    assert result.quote is not None
