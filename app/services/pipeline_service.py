import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal

from app.clients.buff_client import BuffClient
from app.services.ev_service import calculate_opportunity_metrics
from app.services.market_scan_service import ScanFilterConfig, ScanRunResult, scan_watchlist
from app.services.metadata_provider import MetadataProvider
from app.services.recipe_solver import RecipeCandidate, RecipeSolverConfig, solve_recipes
from app.services.risk_filter import RiskFilterConfig, evaluate_opportunity
from app.services.valuation_service import ValuationService


@dataclass(frozen=True)
class EndToEndPipelineConfig:
    """Configuration for the mock end-to-end pipeline orchestration."""

    goods_ids: list[str]
    scan_filter_config: ScanFilterConfig
    solver_config: RecipeSolverConfig
    risk_config: RiskFilterConfig
    liquidity_score: Decimal | None = None


@dataclass(frozen=True)
class EndToEndPipelineResult:
    """Aggregated result of one full mock pipeline run."""

    scan_result: ScanRunResult
    recipes: list[RecipeCandidate]
    errors: list[str]
    started_at: datetime
    finished_at: datetime

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware")
        if self.finished_at.tzinfo is None:
            raise ValueError("finished_at must be timezone-aware")



def _empty_scan_result(started_at: datetime, finished_at: datetime) -> ScanRunResult:
    """Create an empty scan result for pipeline-level fallback paths."""

    return ScanRunResult(
        candidates=[],
        errors=[],
        scanned_goods_ids=[],
        started_at=started_at,
        finished_at=finished_at,
    )


async def run_mock_pipeline(
    buff_client: BuffClient,
    metadata_provider: MetadataProvider,
    config: EndToEndPipelineConfig,
    *,
    valuation_service: ValuationService | None = None,
) -> EndToEndPipelineResult:
    """Run the mock scan -> metadata -> recipe pipeline without external side effects."""

    started_at = datetime.now(UTC)
    scan_result = await asyncio.to_thread(
        scan_watchlist,
        buff_client,
        config.goods_ids,
        config.scan_filter_config,
    )
    errors = list(scan_result.errors)

    try:
        skins = await metadata_provider.fetch_skins()
    except Exception as exc:
        finished_at = datetime.now(UTC)
        errors.append(f"Metadata provider failed: {exc}")
        return EndToEndPipelineResult(
            scan_result=scan_result,
            recipes=[],
            errors=errors,
            started_at=started_at,
            finished_at=finished_at,
        )

    try:
        recipes = solve_recipes(
            candidates=scan_result.candidates,
            skins=skins,
            solver_config=config.solver_config,
            risk_config=config.risk_config,
            liquidity_score=config.liquidity_score,
        )
    except Exception as exc:
        finished_at = datetime.now(UTC)
        errors.append(f"Recipe solver failed: {exc}")
        return EndToEndPipelineResult(
            scan_result=scan_result,
            recipes=[],
            errors=errors,
            started_at=started_at,
            finished_at=finished_at,
        )

    if valuation_service is not None and recipes:
        valued_recipes: list[RecipeCandidate] = []
        for recipe in recipes:
            try:
                valuation_result = await valuation_service.value_tradeup_results(
                    recipe.tradeup_results
                )
            except Exception as exc:
                errors.append(f"valuation error: {exc}")
                valued_recipes.append(recipe)
                continue

            for warning in valuation_result.warnings:
                errors.append(
                    f"valuation warning: {warning.code}: {warning.message}"
                )

            new_metrics = calculate_opportunity_metrics(
                input_items=recipe.input_items,
                tradeup_results=valuation_result.tradeup_results,
                sell_fee_rate=config.solver_config.sell_fee_rate,
            )
            new_risk_decision = evaluate_opportunity(
                metrics=new_metrics,
                input_items=recipe.input_items,
                config=config.risk_config,
                liquidity_score=config.liquidity_score,
                paint_seeds=None,
            )
            valued_recipes.append(
                replace(
                    recipe,
                    tradeup_results=valuation_result.tradeup_results,
                    metrics=new_metrics,
                    risk_decision=new_risk_decision,
                )
            )

        recipes = valued_recipes

    finished_at = datetime.now(UTC)
    return EndToEndPipelineResult(
        scan_result=scan_result,
        recipes=recipes,
        errors=errors,
        started_at=started_at,
        finished_at=finished_at,
    )
