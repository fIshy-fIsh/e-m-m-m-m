"""Phase 16E — Opt-in recipe-first scanner orchestration.

This isolated orchestrator consumes exactly one active targeted plan, acquires
only that plan's goods pages sequentially, executes the dedicated family-
constrained search, then reuses ``RunScopedValuationSession`` and the existing
EV/risk authorities. It never activates a fallback family and is not imported
by the current production scanner or CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.services.buff_community_identity_resolver import (
    BuffGoodsIdIdentityResolver,
)
from app.services.buff_item_identity import BuffItemIdentity
from app.services.ev_service import OpportunityMetrics, calculate_opportunity_metrics
from app.services.family_constrained_concrete_search import (
    FamilyConstrainedRecipeSearchDiagnostics,
    FamilyConstrainedRecipeSelection,
    search_family_constrained_recipes,
)
from app.services.recipe_family import RecipeFamily
from app.services.recipe_family_geometry import RecipeFamilyGeometry
from app.services.recipe_first_acquisition import (
    RecipeFirstAcquisitionPageProvider,
    RecipeFirstListingProvenance,
)
from app.services.recipe_solver import RecipeEnumerationConfig, RecipeSolverConfig
from app.services.risk_filter import RiskDecision, RiskFilterConfig, evaluate_opportunity
from app.services.scanner_cached_buff_price_resolver import (
    ScannerCachedBuffPriceResolver,
)
from app.services.scanner_valuation_session import (
    PreparedOutputPricePlan,
    RunScopedValuationSession,
    SessionValuationResult,
)
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.targeted_buff_scan_plan import (
    MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN,
    TargetedBuffScanDecision,
)
from app.services.trade_up_input_enrichment import TradeUpEnrichedInput
from app.services.tradeup_engine import TradeupResult
from app.services.valuation_service import ValuationService

__all__ = (
    "RecipeFirstScannerConfig",
    "RecipeFirstScannerError",
    "RecipeFirstScannerOpportunity",
    "RecipeFirstScannerOrchestrator",
    "RecipeFirstScannerRecipeEvaluation",
    "RecipeFirstScannerRunCounters",
    "RecipeFirstScannerRunDiagnostics",
    "RecipeFirstScannerRunResult",
)


class RecipeFirstScannerError(RuntimeError):
    """The opt-in recipe-first orchestration contract failed closed."""


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstScannerConfig:
    enabled: bool = False
    max_valuation_requests_per_run: int = 60

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise RecipeFirstScannerError("enabled must be bool")
        if (
            type(self.max_valuation_requests_per_run) is not int
            or not 1 <= self.max_valuation_requests_per_run <= 60
        ):
            raise RecipeFirstScannerError(
                "max valuation requests must be an integer in [1, 60]"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstScannerRunCounters:
    plan_goods_requested: int = 0
    plan_goods_succeeded: int = 0
    plan_goods_failed: int = 0
    listings_received: int = 0
    identity_resolved: int = 0
    identity_unresolved: int = 0
    intrinsic_resolved: int = 0
    intrinsic_unresolved: int = 0
    candidate_accepted: int = 0
    candidate_rejected: int = 0
    metadata_resolved: int = 0
    metadata_unresolved: int = 0
    family_compatible_inputs: int = 0
    family_search_states: int = 0
    family_selections: int = 0
    recipes_evaluated: int = 0
    recipes_fully_valued: int = 0
    recipes_valuation_failed: int = 0
    recipes_risk_rejected: int = 0
    opportunities_found: int = 0
    valuation_requests_attempted: int = 0
    valuation_requests_succeeded: int = 0
    valuation_requests_failed: int = 0
    valuation_requests_blocked: int = 0
    run_reuse_hits: int = 0
    cache_hits_fresh_selected: int = 0
    cache_misses: int = 0
    cache_policy_blocked: int = 0
    cache_expired: int = 0
    cache_selection_failures: int = 0
    live_demand: int = 0
    live_attempted: int = 0
    live_succeeded: int = 0
    live_failed: int = 0
    live_atomically_blocked: int = 0
    fallback_family_calls: int = 0


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstScannerRunDiagnostics:
    family_hash: str
    family_key: str
    active_plan_goods_ids: tuple[str, ...]
    page_failures: tuple[tuple[str, str], ...]
    family_search: FamilyConstrainedRecipeSearchDiagnostics | None


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstScannerRecipeEvaluation:
    selection: FamilyConstrainedRecipeSelection
    output_market_hash_names_requested: tuple[str, ...]
    valued_tradeup_results: tuple[TradeupResult, ...]
    valuation_prices_resolved: int
    valuation_completed: bool
    missing_market_hash_names: tuple[str, ...]
    price_errors: tuple[str, ...]
    metrics: OpportunityMetrics | None
    risk_decision: RiskDecision | None
    rejection_reason: str | None
    listings: tuple[RecipeFirstListingProvenance, ...]


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstScannerOpportunity:
    evaluation: RecipeFirstScannerRecipeEvaluation

    def __post_init__(self) -> None:
        if not self.evaluation.valuation_completed:
            raise RecipeFirstScannerError(
                "opportunity requires complete final valuation"
            )
        if self.evaluation.metrics is None:
            raise RecipeFirstScannerError("opportunity requires metrics")
        if (
            self.evaluation.risk_decision is None
            or not self.evaluation.risk_decision.passed
        ):
            raise RecipeFirstScannerError(
                "opportunity requires a passed risk decision"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstScannerRunResult:
    started_at: datetime
    completed_at: datetime
    counters: RecipeFirstScannerRunCounters
    diagnostics: RecipeFirstScannerRunDiagnostics
    evaluations: tuple[RecipeFirstScannerRecipeEvaluation, ...]
    opportunities: tuple[RecipeFirstScannerOpportunity, ...]


@dataclass(kw_only=True, repr=False)
class RecipeFirstScannerOrchestrator:
    listing_provider: RecipeFirstAcquisitionPageProvider
    identity_resolver: BuffGoodsIdIdentityResolver
    valuation_service: ValuationService
    finish_index: StructuralOutputFinishIndex
    solver_config: RecipeSolverConfig
    risk_config: RiskFilterConfig
    enumeration_config: RecipeEnumerationConfig = RecipeEnumerationConfig()
    config: RecipeFirstScannerConfig = RecipeFirstScannerConfig()
    cached_price_resolver: ScannerCachedBuffPriceResolver | None = None
    _next_session_id: int = 0

    async def run_once(
        self,
        *,
        decision: TargetedBuffScanDecision,
        family: RecipeFamily,
        geometry: RecipeFamilyGeometry,
    ) -> RecipeFirstScannerRunResult:
        """Run one opt-in recipe-first scan over exactly one active plan."""

        if not self.config.enabled:
            raise RecipeFirstScannerError("recipe-first scanner is disabled")
        await _validate_active_decision(
            decision=decision,
            family=family,
            identity_resolver=self.identity_resolver,
        )
        active_plan = decision.active_plan
        if active_plan is None:
            raise RecipeFirstScannerError("active plan is required")
        if family.family_hash != geometry.family_hash:
            raise RecipeFirstScannerError(
                "family and geometry family hashes must match"
            )

        started_at = datetime.now(UTC)
        counters = RecipeFirstScannerRunCounters(
            plan_goods_requested=active_plan.hard_request_count
        )
        page_failures: list[tuple[str, str]] = []
        enriched_inputs: list[TradeUpEnrichedInput] = []
        provenance_by_listing_id: dict[str, RecipeFirstListingProvenance] = {}
        seen_listing_keys: set[tuple[str, str, str]] = set()
        seen_listing_ids: set[str] = set()

        for item in active_plan.items:
            try:
                page = await self.listing_provider.acquire_page(
                    goods_id=item.goods_id,
                    market_hash_name=item.market_hash_name,
                )
            except MemoryError:
                raise
            except Exception as exc:
                counters = replace(
                    counters,
                    plan_goods_failed=counters.plan_goods_failed + 1,
                )
                page_failures.append((item.goods_id, type(exc).__name__))
                continue
            if (
                page.goods_id != item.goods_id
                or page.market_hash_name != item.market_hash_name
            ):
                raise RecipeFirstScannerError(
                    "acquisition page identity does not match active plan"
                )
            counts = page.counts
            counters = replace(
                counters,
                plan_goods_succeeded=counters.plan_goods_succeeded + 1,
                listings_received=(
                    counters.listings_received + counts.listings_received
                ),
                identity_resolved=(
                    counters.identity_resolved + counts.identity_resolved
                ),
                identity_unresolved=(
                    counters.identity_unresolved + counts.identity_unresolved
                ),
                intrinsic_resolved=(
                    counters.intrinsic_resolved + counts.intrinsic_resolved
                ),
                intrinsic_unresolved=(
                    counters.intrinsic_unresolved + counts.intrinsic_unresolved
                ),
                candidate_accepted=(
                    counters.candidate_accepted + counts.candidate_accepted
                ),
                candidate_rejected=(
                    counters.candidate_rejected + counts.candidate_rejected
                ),
                metadata_resolved=(
                    counters.metadata_resolved + counts.metadata_resolved
                ),
                metadata_unresolved=(
                    counters.metadata_unresolved + counts.metadata_unresolved
                ),
            )
            if len(page.enriched_inputs) != len(page.provenance):
                raise RecipeFirstScannerError(
                    "acquisition page provenance is not aligned"
                )
            for enriched, provenance in zip(
                page.enriched_inputs,
                page.provenance,
                strict=True,
            ):
                candidate = enriched.candidate
                expected_stattrak = family.stattrak_mode.value == "stattrak"
                if (
                    candidate.goods_id != item.goods_id
                    or candidate.market_hash_name != item.market_hash_name
                    or enriched.input_item.collection_name != item.collection_name
                    or enriched.input_item.rarity != family.input_rarity
                    or candidate.stattrak is not expected_stattrak
                    or enriched.input_item.stattrak is not expected_stattrak
                    or provenance.listing_id != candidate.listing_id
                    or provenance.goods_id != candidate.goods_id
                    or provenance.market_hash_name != candidate.market_hash_name
                    or provenance.asset_id != candidate.asset_id
                    or provenance.price_cny != candidate.price_cny
                    or provenance.paintwear != candidate.paintwear
                    or provenance.stattrak is not candidate.stattrak
                    or provenance.souvenir is not candidate.souvenir
                    or provenance.source != candidate.source
                ):
                    raise RecipeFirstScannerError(
                        "acquired candidate does not match active plan identity"
                    )
                listing_key = (
                    candidate.source,
                    candidate.goods_id,
                    candidate.listing_id,
                )
                if (
                    listing_key in seen_listing_keys
                    or candidate.listing_id in seen_listing_ids
                ):
                    raise RecipeFirstScannerError(
                        "duplicate listing provenance across active pages"
                    )
                seen_listing_keys.add(listing_key)
                seen_listing_ids.add(candidate.listing_id)
                provenance_by_listing_id[candidate.listing_id] = provenance
                enriched_inputs.append(enriched)

        search = search_family_constrained_recipes(
            family,
            geometry=geometry,
            finish_index=self.finish_index,
            enriched_inputs=tuple(enriched_inputs),
            solver_config=self.solver_config,
            enumeration_config=self.enumeration_config,
        )
        counters = replace(
            counters,
            family_compatible_inputs=search.diagnostics.retained_input_count,
            family_search_states=search.diagnostics.states_explored,
            family_selections=len(search.selections),
        )
        session = RunScopedValuationSession(
            price_provider=self.valuation_service.price_provider,
            valuation_config=self.valuation_service.config,
            session_id=self._next_session_id,
            cached_price_resolver=self.cached_price_resolver,
        )
        self._next_session_id += 1
        live_used = 0
        evaluations: list[RecipeFirstScannerRecipeEvaluation] = []
        opportunities: list[RecipeFirstScannerOpportunity] = []

        for selection in search.selections:
            counters = replace(
                counters,
                recipes_evaluated=counters.recipes_evaluated + 1,
            )
            names = selection.concrete_outcomes.output_market_hash_names
            prepared = await session.prepare_output_prices(names)
            counters = _add_prepare_counters(counters, prepared)
            new_live = len(prepared.new_live_names)
            if live_used + new_live > self.config.max_valuation_requests_per_run:
                session.record_atomically_blocked(prepared)
                counters = replace(
                    counters,
                    live_atomically_blocked=(
                        counters.live_atomically_blocked + new_live
                    ),
                    valuation_requests_blocked=(
                        counters.valuation_requests_blocked + len(names)
                    ),
                    recipes_valuation_failed=(
                        counters.recipes_valuation_failed + 1
                    ),
                )
                evaluations.append(
                    _blocked_evaluation(
                        selection,
                        names,
                        provenance_by_listing_id,
                    )
                )
                continue

            live_used += new_live
            session_result = await session.resolve_prepared(
                prepared,
                list(selection.concrete_outcomes.tradeup_results),
            )
            counters = replace(
                counters,
                live_attempted=(
                    counters.live_attempted
                    + session_result.live_attempted_delta
                ),
                live_succeeded=(
                    counters.live_succeeded
                    + session_result.live_succeeded_delta
                ),
                live_failed=(
                    counters.live_failed + session_result.live_failed_delta
                ),
                valuation_requests_attempted=(
                    counters.valuation_requests_attempted + len(names)
                ),
            )
            evaluation = _evaluate_session_result(
                selection=selection,
                requested_names=names,
                session_result=session_result,
                solver_config=self.solver_config,
                risk_config=self.risk_config,
                provenance_by_listing_id=provenance_by_listing_id,
            )
            evaluations.append(evaluation)
            resolved_count = evaluation.valuation_prices_resolved
            counters = replace(
                counters,
                valuation_requests_succeeded=(
                    counters.valuation_requests_succeeded + resolved_count
                ),
                valuation_requests_failed=(
                    counters.valuation_requests_failed
                    + max(0, len(names) - resolved_count)
                ),
            )
            if not evaluation.valuation_completed:
                counters = replace(
                    counters,
                    recipes_valuation_failed=(
                        counters.recipes_valuation_failed + 1
                    ),
                )
                continue
            counters = replace(
                counters,
                recipes_fully_valued=counters.recipes_fully_valued + 1,
            )
            if (
                evaluation.risk_decision is not None
                and evaluation.risk_decision.passed
            ):
                opportunities.append(
                    RecipeFirstScannerOpportunity(evaluation=evaluation)
                )
            else:
                counters = replace(
                    counters,
                    recipes_risk_rejected=(
                        counters.recipes_risk_rejected + 1
                    ),
                )

        counters = replace(
            counters,
            opportunities_found=len(opportunities),
        )
        return RecipeFirstScannerRunResult(
            started_at=started_at,
            completed_at=datetime.now(UTC),
            counters=counters,
            diagnostics=RecipeFirstScannerRunDiagnostics(
                family_hash=family.family_hash,
                family_key=family.family_key,
                active_plan_goods_ids=active_plan.goods_ids,
                page_failures=tuple(page_failures),
                family_search=search.diagnostics,
            ),
            evaluations=tuple(evaluations),
            opportunities=tuple(opportunities),
        )


async def _validate_active_decision(
    *,
    decision: object,
    family: RecipeFamily,
    identity_resolver: BuffGoodsIdIdentityResolver,
) -> None:
    if type(decision) is not TargetedBuffScanDecision:
        raise RecipeFirstScannerError(
            "decision must be TargetedBuffScanDecision"
        )
    plan = decision.active_plan
    if (
        plan is None
        or decision.active_family_key != family.family_key
        or plan.family_hash != family.family_hash
        or plan.stattrak_mode is not family.stattrak_mode
        or plan.hard_request_count != len(plan.items)
        or plan.hard_request_count > MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN
    ):
        raise RecipeFirstScannerError("active decision does not match family")
    family_collections = {name for name, _count in family.collection_counts}
    if {item.collection_name for item in plan.items} != family_collections:
        raise RecipeFirstScannerError(
            "active plan does not cover exactly the family collections"
        )
    if len(set(plan.goods_ids)) != len(plan.goods_ids) or len(
        set(plan.market_hash_names)
    ) != len(plan.market_hash_names):
        raise RecipeFirstScannerError("active plan identity collision")
    for item in plan.items:
        resolved = await identity_resolver.resolve_goods_id(item.goods_id)
        if (
            type(resolved) is not BuffItemIdentity
            or resolved.goods_id != item.goods_id
            or resolved.market_hash_name != item.market_hash_name
        ):
            raise RecipeFirstScannerError(
                "active plan reverse identity proof failed"
            )


def _add_prepare_counters(
    counters: RecipeFirstScannerRunCounters,
    prepared: PreparedOutputPricePlan,
) -> RecipeFirstScannerRunCounters:
    return replace(
        counters,
        run_reuse_hits=(
            counters.run_reuse_hits
            + len(prepared.memo_successes)
            + len(prepared.memo_terminal_failures)
        ),
        cache_hits_fresh_selected=(
            counters.cache_hits_fresh_selected
            + len(prepared.cache_hits_fresh_selected)
        ),
        cache_misses=counters.cache_misses + len(prepared.cache_misses),
        cache_policy_blocked=(
            counters.cache_policy_blocked
            + len(prepared.cache_policy_blocked)
        ),
        cache_expired=counters.cache_expired + len(prepared.cache_expired),
        cache_selection_failures=(
            counters.cache_selection_failures
            + len(prepared.cache_terminal_selection_failures)
        ),
        live_demand=counters.live_demand + len(prepared.new_live_names),
    )


def _evaluate_session_result(
    *,
    selection: FamilyConstrainedRecipeSelection,
    requested_names: tuple[str, ...],
    session_result: SessionValuationResult,
    solver_config: RecipeSolverConfig,
    risk_config: RiskFilterConfig,
    provenance_by_listing_id: dict[str, RecipeFirstListingProvenance],
) -> RecipeFirstScannerRecipeEvaluation:
    valuation = session_result.valuation_result
    valued = tuple(valuation.tradeup_results)
    missing = tuple(valuation.missing_market_hash_names)
    errors = tuple(valuation.price_lookup_result.errors)
    complete = (
        not missing
        and not errors
        and len(valuation.price_lookup_result.quotes) == len(requested_names)
        and len(valued) == len(selection.concrete_outcomes.outcomes)
    )
    listings = _gather_listings(
        selection,
        provenance_by_listing_id,
    )
    if not complete:
        return RecipeFirstScannerRecipeEvaluation(
            selection=selection,
            output_market_hash_names_requested=requested_names,
            valued_tradeup_results=valued,
            valuation_prices_resolved=len(valuation.price_lookup_result.quotes),
            valuation_completed=False,
            missing_market_hash_names=missing,
            price_errors=errors,
            metrics=None,
            risk_decision=None,
            rejection_reason="VALUATION_INCOMPLETE",
            listings=listings,
        )
    metrics = calculate_opportunity_metrics(
        list(selection.selection.recipe.input_items),
        list(valued),
        solver_config.sell_fee_rate,
    )
    risk = evaluate_opportunity(
        metrics,
        list(selection.selection.recipe.input_items),
        risk_config,
        paint_seeds=list(selection.selection.recipe.paint_seeds),
    )
    return RecipeFirstScannerRecipeEvaluation(
        selection=selection,
        output_market_hash_names_requested=requested_names,
        valued_tradeup_results=valued,
        valuation_prices_resolved=len(valuation.price_lookup_result.quotes),
        valuation_completed=True,
        missing_market_hash_names=(),
        price_errors=(),
        metrics=metrics,
        risk_decision=risk,
        rejection_reason=None if risk.passed else "RISK_DECISION_REJECTED",
        listings=listings,
    )


def _blocked_evaluation(
    selection: FamilyConstrainedRecipeSelection,
    names: tuple[str, ...],
    provenance_by_listing_id: dict[str, RecipeFirstListingProvenance],
) -> RecipeFirstScannerRecipeEvaluation:
    listings = _gather_listings(selection, provenance_by_listing_id)
    return RecipeFirstScannerRecipeEvaluation(
        selection=selection,
        output_market_hash_names_requested=names,
        valued_tradeup_results=(),
        valuation_prices_resolved=0,
        valuation_completed=False,
        missing_market_hash_names=names,
        price_errors=("VALUATION_REQUEST_CAP_EXCEEDED",),
        metrics=None,
        risk_decision=None,
        rejection_reason="VALUATION_REQUEST_CAP_EXCEEDED",
        listings=listings,
    )


def _gather_listings(
    selection: FamilyConstrainedRecipeSelection,
    provenance_by_listing_id: dict[str, RecipeFirstListingProvenance],
) -> tuple[RecipeFirstListingProvenance, ...]:
    listings: list[RecipeFirstListingProvenance] = []
    for listing_id in selection.selection.selected_listing_ids:
        provenance = provenance_by_listing_id.get(listing_id)
        if provenance is None:
            raise RecipeFirstScannerError(
                "selected listing provenance is missing"
            )
        listings.append(provenance)
    return tuple(listings)
