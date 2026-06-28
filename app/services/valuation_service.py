from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.services.price_provider import PriceLookupResult, PriceProvider
from app.services.tradeup_engine import TradeupResult


class ValuationMissingPriceStrategy(StrEnum):
    """Supported fallback strategies when price lookup data is missing."""

    KEEP_ORIGINAL = "KEEP_ORIGINAL"
    ZERO_PRICE = "ZERO_PRICE"
    DROP_RESULT = "DROP_RESULT"


@dataclass(frozen=True)
class ValuationConfig:
    """Configuration controlling valuation fallback behavior."""

    missing_price_strategy: ValuationMissingPriceStrategy = (
        ValuationMissingPriceStrategy.KEEP_ORIGINAL
    )
    require_all_prices: bool = False


@dataclass(frozen=True)
class ValuationWarning:
    """One warning emitted during the valuation process."""

    code: str
    message: str
    market_hash_name: str | None = None


@dataclass(frozen=True)
class ValuationResult:
    """Result of applying external price data onto trade-up results."""

    tradeup_results: list[TradeupResult]
    missing_market_hash_names: list[str]
    warnings: list[ValuationWarning]
    price_lookup_result: PriceLookupResult


class ValuationService:
    """Applies PriceProvider outputs onto TradeupResult valuation fields only."""

    def __init__(
        self,
        price_provider: PriceProvider,
        config: ValuationConfig | None = None,
    ) -> None:
        self.price_provider = price_provider
        self.config = config or ValuationConfig()

    async def value_tradeup_results(
        self,
        tradeup_results: list[TradeupResult],
    ) -> ValuationResult:
        """Update estimated output prices while preserving probability, float, and wear."""

        if not tradeup_results:
            return ValuationResult(
                tradeup_results=[],
                missing_market_hash_names=[],
                warnings=[],
                price_lookup_result=PriceLookupResult(quotes={}, missing=[], errors=[]),
            )

        output_names = list(
            dict.fromkeys(
                result.output_market_hash_name for result in tradeup_results
            )
        )

        try:
            price_lookup_result = await self.price_provider.get_prices(output_names)
        except Exception as exc:
            return ValuationResult(
                tradeup_results=list(tradeup_results),
                missing_market_hash_names=output_names,
                warnings=[
                    ValuationWarning(
                        code="PRICE_PROVIDER_ERROR",
                        message=str(exc),
                    )
                ],
                price_lookup_result=PriceLookupResult(
                    quotes={},
                    missing=output_names,
                    errors=[str(exc)],
                ),
            )

        warnings: list[ValuationWarning] = []
        missing_market_hash_names = list(price_lookup_result.missing)
        updated_results: list[TradeupResult] = []

        if self.config.require_all_prices and missing_market_hash_names:
            warnings.append(
                ValuationWarning(
                    code="REQUIRE_ALL_PRICES_NOT_SATISFIED",
                    message="Not all output prices were available from the price provider.",
                )
            )

        for result in tradeup_results:
            quote = price_lookup_result.quotes.get(result.output_market_hash_name)
            if quote is not None:
                updated_results.append(_replace_valuation_fields(result, quote.price_cny))
                continue

            if self.config.missing_price_strategy == ValuationMissingPriceStrategy.KEEP_ORIGINAL:
                warnings.append(
                    ValuationWarning(
                        code="MISSING_PRICE_KEEP_ORIGINAL",
                        message="Missing price; keeping original estimated price.",
                        market_hash_name=result.output_market_hash_name,
                    )
                )
                updated_results.append(
                    _replace_valuation_fields(result, result.estimated_price_cny)
                )
            elif self.config.missing_price_strategy == ValuationMissingPriceStrategy.ZERO_PRICE:
                warnings.append(
                    ValuationWarning(
                        code="MISSING_PRICE_ZEROED",
                        message="Missing price; setting estimated price to zero.",
                        market_hash_name=result.output_market_hash_name,
                    )
                )
                updated_results.append(_replace_valuation_fields(result, Decimal("0")))
            elif self.config.missing_price_strategy == ValuationMissingPriceStrategy.DROP_RESULT:
                warnings.append(
                    ValuationWarning(
                        code="MISSING_PRICE_DROPPED",
                        message="Missing price; dropping output result.",
                        market_hash_name=result.output_market_hash_name,
                    )
                )
            else:
                raise ValueError("unsupported missing price strategy")

        return ValuationResult(
            tradeup_results=updated_results,
            missing_market_hash_names=missing_market_hash_names,
            warnings=warnings,
            price_lookup_result=price_lookup_result,
        )



def _replace_valuation_fields(
    result: TradeupResult,
    new_price_cny: Decimal,
) -> TradeupResult:
    """Create a new TradeupResult with updated valuation fields only."""

    probability_decimal = Decimal(str(result.probability))
    return TradeupResult(
        output_market_hash_name=result.output_market_hash_name,
        probability=result.probability,
        output_float=result.output_float,
        output_wear=result.output_wear,
        estimated_price_cny=new_price_cny,
        expected_value_contribution=new_price_cny * probability_decimal,
    )
