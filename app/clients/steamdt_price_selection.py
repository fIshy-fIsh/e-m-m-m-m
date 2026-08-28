from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.clients.steamdt_client import SteamDTPlatformPrice, SteamDTPriceQuote


class SteamDTPriceSelectionStrategy(StrEnum):
    """Supported SteamDT price selection strategies for smoke-stage valuation."""

    LOWEST_POSITIVE_SELL_PRICE = "lowest_positive_sell_price"
    LIQUIDITY_AWARE_SELL_PRICE = "liquidity_aware_sell_price"


@dataclass(frozen=True)
class SteamDTPriceSelectionConfig:
    """Configuration for conservative SteamDT platform-price selection."""

    strategy: SteamDTPriceSelectionStrategy = (
        SteamDTPriceSelectionStrategy.LIQUIDITY_AWARE_SELL_PRICE
    )
    min_sell_count: int = 1
    require_sell_count: bool = True
    min_bidding_count: int = 0
    require_bidding_price: bool = False
    max_sell_bid_spread_pct: Decimal | None = None
    max_price_to_avg_ratio: Decimal | None = None
    fallback_to_lowest_positive: bool = True

    def __post_init__(self) -> None:
        if self.min_sell_count < 0:
            raise ValueError("min_sell_count must be greater than or equal to 0")
        if self.min_bidding_count < 0:
            raise ValueError("min_bidding_count must be greater than or equal to 0")
        if self.max_sell_bid_spread_pct is not None and self.max_sell_bid_spread_pct < 0:
            raise ValueError(
                "max_sell_bid_spread_pct must be greater than or equal to 0"
            )
        if self.max_price_to_avg_ratio is not None and self.max_price_to_avg_ratio <= 0:
            raise ValueError("max_price_to_avg_ratio must be greater than 0")


@dataclass(frozen=True)
class SteamDTPriceCandidateDecision:
    """Evaluation result for one platform price candidate."""

    platform: str
    sell_price_cny: Decimal | None
    sell_count: int | None
    bidding_price_cny: Decimal | None
    bidding_count: int | None
    accepted: bool
    reason_codes: list[str]
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class SteamDTPriceSelectionResult:
    """Final selected quote plus decision trace for one market hash name."""

    market_hash_name: str
    quote: "SteamDTPriceQuote | None"
    selected_platform: str | None
    selected_strategy: str
    reason_codes: list[str]
    candidate_decisions: list[SteamDTPriceCandidateDecision]
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.market_hash_name.strip():
            raise ValueError("market_hash_name cannot be empty")
        if not self.selected_strategy.strip():
            raise ValueError("selected_strategy cannot be empty")
        if self.quote is not None and self.selected_platform is None:
            raise ValueError("selected_platform is required when quote is present")



def select_steamdt_price_quote(
    market_hash_name: str,
    platform_prices: list["SteamDTPlatformPrice"],
    *,
    config: SteamDTPriceSelectionConfig | None = None,
    avg_price_cny: Decimal | None = None,
    original_payload: dict[str, Any] | None = None,
) -> SteamDTPriceSelectionResult:
    """Select a conservative SteamDT price quote from platform-level price candidates."""

    if not market_hash_name.strip():
        raise ValueError("market_hash_name cannot be empty")

    config = config or SteamDTPriceSelectionConfig()
    if config.strategy == SteamDTPriceSelectionStrategy.LOWEST_POSITIVE_SELL_PRICE:
        return _select_lowest_positive_sell_price(
            market_hash_name,
            platform_prices,
            original_payload=original_payload,
        )
    return _select_liquidity_aware_sell_price(
        market_hash_name,
        platform_prices,
        config=config,
        avg_price_cny=avg_price_cny,
        original_payload=original_payload,
    )



def _select_lowest_positive_sell_price(
    market_hash_name: str,
    platform_prices: list["SteamDTPlatformPrice"],
    *,
    original_payload: dict[str, Any] | None = None,
) -> SteamDTPriceSelectionResult:
    """Select the lowest positive sell price without applying liquidity gating."""

    from app.clients.steamdt_client import SteamDTPriceQuote

    candidate_decisions: list[SteamDTPriceCandidateDecision] = []
    accepted_candidates: list[SteamDTPlatformPrice] = []

    for price in platform_prices:
        reasons: list[str] = []
        accepted = True
        if price.sell_price_cny is None:
            reasons.append("MISSING_SELL_PRICE")
            accepted = False
        elif price.sell_price_cny <= 0:
            reasons.append("NON_POSITIVE_SELL_PRICE")
            accepted = False

        if accepted:
            reasons.append("ACCEPTED_LOWEST_POSITIVE")
            accepted_candidates.append(price)

        candidate_decisions.append(
            SteamDTPriceCandidateDecision(
                platform=price.platform,
                sell_price_cny=price.sell_price_cny,
                sell_count=price.sell_count,
                bidding_price_cny=price.bidding_price_cny,
                bidding_count=price.bidding_count,
                accepted=accepted,
                reason_codes=reasons,
                raw=price.raw,
            )
        )

    if not accepted_candidates:
        return SteamDTPriceSelectionResult(
            market_hash_name=market_hash_name,
            quote=None,
            selected_platform=None,
            selected_strategy=SteamDTPriceSelectionStrategy.LOWEST_POSITIVE_SELL_PRICE.value,
            reason_codes=["NO_POSITIVE_SELL_PRICE"],
            candidate_decisions=candidate_decisions,
            raw={"original_payload": original_payload},
        )

    selected = min(
        accepted_candidates,
        key=lambda price: (price.sell_price_cny or Decimal("Infinity"), price.platform),
    )
    quote = SteamDTPriceQuote(
        market_hash_name=market_hash_name,
        price_cny=selected.sell_price_cny or Decimal("0"),
        source="steamdt",
        raw={
            "selected_strategy": SteamDTPriceSelectionStrategy.LOWEST_POSITIVE_SELL_PRICE.value,
            "reason_codes": ["ACCEPTED_LOWEST_POSITIVE"],
            "selected_platform": selected.platform,
            "platform_prices": [price.raw for price in platform_prices],
            "original_payload": original_payload,
        },
    )
    return SteamDTPriceSelectionResult(
        market_hash_name=market_hash_name,
        quote=quote,
        selected_platform=selected.platform,
        selected_strategy=SteamDTPriceSelectionStrategy.LOWEST_POSITIVE_SELL_PRICE.value,
        reason_codes=["ACCEPTED_LOWEST_POSITIVE"],
        candidate_decisions=candidate_decisions,
        raw={"original_payload": original_payload},
    )



def _select_liquidity_aware_sell_price(
    market_hash_name: str,
    platform_prices: list["SteamDTPlatformPrice"],
    *,
    config: SteamDTPriceSelectionConfig,
    avg_price_cny: Decimal | None,
    original_payload: dict[str, Any] | None = None,
) -> SteamDTPriceSelectionResult:
    """Select a conservative price with basic liquidity-aware gating and fallback."""

    from app.clients.steamdt_client import SteamDTPriceQuote

    candidate_decisions: list[SteamDTPriceCandidateDecision] = []
    accepted_candidates: list[SteamDTPlatformPrice] = []

    for price in platform_prices:
        reasons: list[str] = []
        accepted = True

        if price.sell_price_cny is None:
            reasons.append("MISSING_SELL_PRICE")
            accepted = False
        elif price.sell_price_cny <= 0:
            reasons.append("NON_POSITIVE_SELL_PRICE")
            accepted = False

        if config.require_sell_count:
            if price.sell_count is None:
                reasons.append("MISSING_SELL_COUNT")
                accepted = False
            elif price.sell_count < config.min_sell_count:
                reasons.append("SELL_COUNT_BELOW_MINIMUM")
                accepted = False
        elif price.sell_count is None:
            reasons.append("SELL_COUNT_MISSING_ALLOWED")

        if config.require_bidding_price:
            if price.bidding_price_cny is None:
                reasons.append("MISSING_BIDDING_PRICE")
                accepted = False
            elif price.bidding_price_cny <= 0:
                reasons.append("NON_POSITIVE_BIDDING_PRICE")
                accepted = False
        elif price.bidding_price_cny is None:
            reasons.append("BIDDING_PRICE_MISSING_ALLOWED")

        if config.min_bidding_count > 0:
            if price.bidding_count is None:
                reasons.append("MISSING_BIDDING_COUNT")
                accepted = False
            elif price.bidding_count < config.min_bidding_count:
                reasons.append("BIDDING_COUNT_BELOW_MINIMUM")
                accepted = False

        if config.max_sell_bid_spread_pct is not None:
            if (
                price.bidding_price_cny is not None
                and price.bidding_price_cny > 0
                and price.sell_price_cny is not None
            ):
                spread = (
                    (price.sell_price_cny - price.bidding_price_cny)
                    / price.bidding_price_cny
                )
                if spread > config.max_sell_bid_spread_pct:
                    reasons.append("SELL_BID_SPREAD_TOO_WIDE")
                    accepted = False
            elif not config.require_bidding_price:
                reasons.append("SPREAD_CHECK_SKIPPED_NO_BID")

        if (
            avg_price_cny is not None
            and config.max_price_to_avg_ratio is not None
            and price.sell_price_cny is not None
            and price.sell_price_cny > avg_price_cny * config.max_price_to_avg_ratio
        ):
            reasons.append("PRICE_ABOVE_AVG_SANITY_LIMIT")
            accepted = False
            if config.fallback_to_lowest_positive:
                reasons.append("AVG_SANITY_WOULD_BLOCK_FALLBACK")

        if accepted:
            accepted_candidates.append(price)

        candidate_decisions.append(
            SteamDTPriceCandidateDecision(
                platform=price.platform,
                sell_price_cny=price.sell_price_cny,
                sell_count=price.sell_count,
                bidding_price_cny=price.bidding_price_cny,
                bidding_count=price.bidding_count,
                accepted=accepted,
                reason_codes=reasons,
                raw=price.raw,
            )
        )

    if accepted_candidates:
        selected = min(
            accepted_candidates,
            key=lambda price: (
                price.sell_price_cny or Decimal("Infinity"),
                -(price.sell_count or 0),
                -(price.bidding_count or 0),
                price.platform,
            ),
        )
        quote = SteamDTPriceQuote(
            market_hash_name=market_hash_name,
            price_cny=selected.sell_price_cny or Decimal("0"),
            source="steamdt",
            raw={
                "selected_strategy": SteamDTPriceSelectionStrategy.LIQUIDITY_AWARE_SELL_PRICE.value,
                "reason_codes": ["LIQUIDITY_ACCEPTED"],
                "selected_platform": selected.platform,
                "platform_prices": [price.raw for price in platform_prices],
                "original_payload": original_payload,
            },
        )
        return SteamDTPriceSelectionResult(
            market_hash_name=market_hash_name,
            quote=quote,
            selected_platform=selected.platform,
            selected_strategy=SteamDTPriceSelectionStrategy.LIQUIDITY_AWARE_SELL_PRICE.value,
            reason_codes=["LIQUIDITY_ACCEPTED"],
            candidate_decisions=candidate_decisions,
            raw={"original_payload": original_payload},
        )

    if config.fallback_to_lowest_positive:
        fallback_result = _select_lowest_positive_sell_price(
            market_hash_name,
            platform_prices,
            original_payload=original_payload,
        )
        if (
            fallback_result.quote is not None
            and avg_price_cny is not None
            and config.max_price_to_avg_ratio is not None
            and fallback_result.quote.price_cny
            > avg_price_cny * config.max_price_to_avg_ratio
        ):
            return SteamDTPriceSelectionResult(
                market_hash_name=market_hash_name,
                quote=None,
                selected_platform=None,
                selected_strategy=(
                    "liquidity_aware_sell_price_with_lowest_positive_fallback"
                ),
                reason_codes=["NO_ACCEPTED_LIQUID_PRICE"],
                candidate_decisions=candidate_decisions,
                raw={"original_payload": original_payload},
            )
        if fallback_result.quote is not None:
            return SteamDTPriceSelectionResult(
                market_hash_name=market_hash_name,
                quote=fallback_result.quote,
                selected_platform=fallback_result.selected_platform,
                selected_strategy=(
                    "liquidity_aware_sell_price_with_lowest_positive_fallback"
                ),
                reason_codes=["FALLBACK_TO_LOWEST_POSITIVE_SELL_PRICE"],
                candidate_decisions=candidate_decisions,
                raw={"original_payload": original_payload},
            )

    return SteamDTPriceSelectionResult(
        market_hash_name=market_hash_name,
        quote=None,
        selected_platform=None,
        selected_strategy=SteamDTPriceSelectionStrategy.LIQUIDITY_AWARE_SELL_PRICE.value,
        reason_codes=["NO_ACCEPTED_LIQUID_PRICE"],
        candidate_decisions=candidate_decisions,
        raw={"original_payload": original_payload},
    )
