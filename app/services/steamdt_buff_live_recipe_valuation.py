from __future__ import annotations

from decimal import Decimal

from app.services.live_recipe_construction import LiveRecipeConstructionResult
from app.services.live_recipe_valuation import (
    LiveRecipeValuationResult,
    value_live_recipes,
)
from app.services.recipe_solver import RecipeSolverConfig
from app.services.risk_filter import RiskFilterConfig
from app.services.steamdt_buff_price_provider import SteamDTBuffPriceProvider
from app.services.steamdt_market_data import SteamDTMarketDataClient
from app.services.valuation_service import ValuationService

__all__ = ("value_live_recipes_with_steamdt_buff_prices",)


async def value_live_recipes_with_steamdt_buff_prices(
    *,
    construction_result: LiveRecipeConstructionResult,
    client: SteamDTMarketDataClient,
    solver_config: RecipeSolverConfig,
    risk_config: RiskFilterConfig,
    liquidity_score: Decimal | None = None,
) -> LiveRecipeValuationResult:
    """Value live recipes through the closed aggregate-price composition."""

    price_provider = SteamDTBuffPriceProvider(client)
    valuation_service = ValuationService(price_provider)
    return await value_live_recipes(
        construction_result=construction_result,
        valuation_service=valuation_service,
        solver_config=solver_config,
        risk_config=risk_config,
        liquidity_score=liquidity_score,
    )
