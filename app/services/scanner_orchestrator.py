"""Phase 13P — Read-only live one-shot opportunity scanner orchestrator.

This module composes the existing repository components into one
dependency-injected orchestrator that performs ONE bounded,
read-only, one-shot live scan:

  configured goods_id universe
    ↓
  BuffListingProvider.get_listings
    ↓
  IdentityResolvingBuffListingProvider       (identity-only)
    ↓
  IntrinsicFlagResolvingBuffListingProvider  (intrinsic-only)
    ↓
  convert_buff_listing_to_candidate
    ↓
  TradeUpInputCandidate
    ↓
  TradeUpInputEnrichment                     (metadata + Decimal→float)
    ↓
  run-wide bounded TradeUpEnrichedInput pool
    ↓
  scanner_recipe_composition.enumerate_scanner_recipe_selections
    ↓  bounded globally ordered exact InputItem selections
  ValuationService.value_tradeup_results     (existing price provider)
    ↓
  calculate_opportunity_metrics              (existing EV / ROI)
    ↓
  evaluate_opportunity                       (existing risk policy)
    ↓
  ScannerRunResult

The orchestrator performs no marketplace writes, no login, no cookies,
no scheduling, no purchase execution, and no hidden global client
construction. `MemoryError` propagates verbatim per `D-MEMORY-001`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol, cast

from app.services.buff_community_identity_resolver import (
    BuffGoodsIdIdentityResolver,
)
from app.services.buff_identity_listing_provider import bind_identity_to_provider
from app.services.buff_intrinsic_flag_listing_provider import (
    bind_intrinsic_flags_to_provider,
)
from app.services.buff_intrinsic_flag_resolver import (
    BuffListingIntrinsicFlagResolver,
    CanonicalNameIntrinsicFlagResolver,
)
from app.services.buff_listing_candidate_adapter import (
    convert_buff_listing_to_candidate,
)
from app.services.buff_listing_intrinsic_flags import BuffListingIntrinsicFlags
from app.services.buff_listing_provider import BuffListing
from app.services.ev_service import OpportunityMetrics, calculate_opportunity_metrics
from app.services.metadata_models import SkinMetadata
from app.services.recipe_solver import (
    ConstructedRecipeSelection,
    RecipeEnumerationConfig,
    RecipeSolverConfig,
)
from app.services.risk_filter import RiskDecision, RiskFilterConfig, evaluate_opportunity
from app.services.scanner_cached_buff_price_resolver import (
    ScannerCachedBuffPriceResolver,
)
from app.services.scanner_recipe_composition import (
    ScannerRecipeCompositionDiagnostics,
    enumerate_scanner_recipe_selections,
)
from app.services.scanner_valuation_session import (
    RunScopedValuationSession,
    SessionValuationResult,
)
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputEnricher,
    TradeUpEnrichedInput,
    TradeUpInputMetadataResolver,
    enrich_candidates,
)
from app.services.tradeup_engine import TradeupResult
from app.services.valuation_service import ValuationService

__all__ = (
    "LiveOpportunity",
    "LiveRecipeEvaluation",
    "LiveScannerOrchestrator",
    "ScannerRunDiagnostics",
    "ScannerRunResult",
    "ScannerRunStageCounters",
)


# ---------------------------------------------------------------------------
# Protocols and output DTOs
# ---------------------------------------------------------------------------


class BuffListingPageProvider(Protocol):
    """Structural surface for a provider that returns one listing page."""

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        """Return one listing page for one goods_id."""


class ScannerMetadataResolver(TradeUpInputMetadataResolver, Protocol):
    """Metadata resolver surface required by the one-shot scanner."""

    @property
    def skins(self) -> tuple[SkinMetadata, ...]:
        """Return the immutable full skin catalog for recipe construction."""


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveRecipeEvaluation:
    """One recipe's valuation/metrics/risk outcome, accepted or rejected.

    The DTO contains only values produced by existing domain services.
    It does not recompute prices, EV, ROI, or risk decisions.
    """

    recipe: ConstructedRecipeSelection
    output_market_hash_names_requested: tuple[str, ...]
    valued_tradeup_results: tuple[TradeupResult, ...]
    valuation_prices_resolved: int
    valuation_completed: bool
    missing_market_hash_names: tuple[str, ...]
    price_errors: tuple[str, ...]
    metrics: OpportunityMetrics | None
    risk_decision: RiskDecision | None
    rejection_reason: str | None
    listings: tuple[BuffListingIntrinsicFlags, ...]


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveOpportunity:
    """One completely valued recipe accepted by the existing risk policy."""

    evaluation: LiveRecipeEvaluation

    def __post_init__(self) -> None:
        if not self.evaluation.valuation_completed:
            raise ValueError("LiveOpportunity requires complete valuation")
        if self.evaluation.metrics is None:
            raise ValueError("LiveOpportunity requires metrics")
        if self.evaluation.risk_decision is None or not self.evaluation.risk_decision.passed:
            raise ValueError("LiveOpportunity requires a passed RiskDecision")

    @property
    def recipe(self) -> ConstructedRecipeSelection:
        return self.evaluation.recipe

    @property
    def valued_tradeup_results(self) -> tuple[TradeupResult, ...]:
        return self.evaluation.valued_tradeup_results

    @property
    def metrics(self) -> OpportunityMetrics:
        assert self.evaluation.metrics is not None
        return self.evaluation.metrics

    @property
    def risk_decision(self) -> RiskDecision:
        assert self.evaluation.risk_decision is not None
        return self.evaluation.risk_decision

    @property
    def listings(self) -> tuple[BuffListingIntrinsicFlags, ...]:
        return self.evaluation.listings


@dataclass(frozen=True, kw_only=True, repr=False)
class ScannerRunStageCounters:
    """Per-stage counters for one scanner run."""

    goods_ids_requested: int = 0
    goods_ids_succeeded: int = 0
    goods_ids_failed: int = 0
    listings_received: int = 0
    identity_resolved: int = 0
    identity_unresolved: int = 0
    intrinsic_resolved: int = 0
    intrinsic_unresolved: int = 0
    candidate_accepted: int = 0
    candidate_rejected: int = 0
    metadata_resolved: int = 0
    metadata_unresolved: int = 0
    input_items_created: int = 0
    recipes_evaluated: int = 0
    recipes_fully_valued: int = 0
    recipes_valuation_failed: int = 0
    recipes_rejected: int = 0
    opportunities_found: int = 0
    # Legacy valuation-request counters (Phase 13T semantics; preserved).
    # In Phase 14B, `attempted` and `blocked` keep their ADMITTED/BLOCKED
    # interpretation; only `attempted` is now the count of requested_names
    # for ADMITTED recipes, not the count of provider calls.
    valuation_requests_attempted: int = 0
    valuation_requests_succeeded: int = 0
    valuation_requests_failed: int = 0
    valuation_requests_blocked: int = 0
    # Phase 14B additive discriminators. cache_* are zero in 14B (no
    # persistent cache integration yet); reserved for 14C.
    run_reuse_hits: int = 0
    run_reuse_successes: int = 0
    run_reuse_failures: int = 0
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


@dataclass(frozen=True, kw_only=True, repr=False)
class ScannerRunDiagnostics:
    """Structured diagnostics for one scanner run."""

    goods_ids_failed_details: tuple[tuple[str, str], ...] = ()
    candidate_rejection_histogram: tuple[tuple[str, int], ...] = ()
    metadata_rejection_histogram: tuple[tuple[str, int], ...] = ()
    recipe_rejection_histogram: tuple[tuple[str, int], ...] = ()
    recipe_composition: ScannerRecipeCompositionDiagnostics | None = None


@dataclass(frozen=True, kw_only=True, repr=False)
class ScannerRunResult:
    """Immutable result of ONE bounded scanner run."""

    started_at: datetime
    completed_at: datetime
    goods_ids: tuple[str, ...]
    counters: ScannerRunStageCounters
    diagnostics: ScannerRunDiagnostics
    recipe_evaluations: tuple[LiveRecipeEvaluation, ...]
    opportunities: tuple[LiveOpportunity, ...]

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class LiveScannerOrchestrator:
    """ONE bounded, read-only, live scanner run."""

    HARD_MAX_GOODS_IDS = 10
    HARD_MAX_VALUATION_REQUESTS_PER_RUN = 60

    def __init__(
        self,
        *,
        listing_provider: BuffListingPageProvider,
        identity_resolver: BuffGoodsIdIdentityResolver,
        metadata_resolver: ScannerMetadataResolver,
        intrinsic_resolver: BuffListingIntrinsicFlagResolver | None = None,
        valuation_service: ValuationService | None = None,
        cached_price_resolver: ScannerCachedBuffPriceResolver | None = None,
        max_valuation_requests_per_run: int,
        solver_config: RecipeSolverConfig,
        risk_config: RiskFilterConfig,
        enumeration_config: RecipeEnumerationConfig | None = None,
    ) -> None:
        if listing_provider is None:
            raise TypeError("listing_provider is required")
        if identity_resolver is None:
            raise TypeError("identity_resolver is required")
        if metadata_resolver is None:
            raise TypeError("metadata_resolver is required")
        if solver_config is None:
            raise TypeError("solver_config is required")
        if risk_config is None:
            raise TypeError("risk_config is required")
        if cached_price_resolver is not None and type(
            cached_price_resolver
        ) is not ScannerCachedBuffPriceResolver:
            raise TypeError(
                "cached_price_resolver must be a ScannerCachedBuffPriceResolver"
            )
        if enumeration_config is not None and type(
            enumeration_config
        ) is not RecipeEnumerationConfig:
            raise TypeError("enumeration_config must be a RecipeEnumerationConfig")
        bounded_enumeration_config = (
            RecipeEnumerationConfig()
            if enumeration_config is None
            else RecipeEnumerationConfig(
                max_recipe_candidates_returned=(
                    enumeration_config.max_recipe_candidates_returned
                ),
                max_candidate_states_explored=(
                    enumeration_config.max_candidate_states_explored
                ),
            )
        )
        if (
            type(max_valuation_requests_per_run) is not int
            or max_valuation_requests_per_run <= 0
            or max_valuation_requests_per_run
            > self.HARD_MAX_VALUATION_REQUESTS_PER_RUN
        ):
            raise ValueError(
                "max_valuation_requests_per_run must be an integer in [1, 60]"
            )
        self._listing_provider = listing_provider
        identity_provider = bind_identity_to_provider(
            listing_provider, identity_resolver
        )
        self._intrinsic_provider = bind_intrinsic_flags_to_provider(
            identity_provider,
            intrinsic_resolver or CanonicalNameIntrinsicFlagResolver(),
        )
        self._metadata_resolver = metadata_resolver
        self._enricher = InMemoryTradeUpInputEnricher(metadata_resolver)
        self._solver_config = solver_config
        self._enumeration_config = bounded_enumeration_config
        self._risk_config = risk_config
        self._valuation_service = valuation_service
        self._cached_price_resolver = cached_price_resolver
        self._max_valuation_requests_per_run = max_valuation_requests_per_run
        # Monotonic per-orchestrator session id counter. The session
        # itself lives for exactly one ``run_once`` call and is rebuilt
        # on each invocation. Cross-run reuse is impossible by construction.
        self._next_session_id = 0

    async def run_once(
        self,
        goods_ids: Iterable[str],
    ) -> ScannerRunResult:
        """Run ONE bounded live scan and return a structured result.

        The configured universe is deduplicated in first-seen order and
        limited to ``HARD_MAX_GOODS_IDS``. Configuration violations fail
        closed. Per-goods acquisition failures are isolated and recorded.
        ``MemoryError`` propagates verbatim.
        """
        started_at = datetime.now(UTC)
        universe = _normalize_goods_ids(goods_ids, hard_max=self.HARD_MAX_GOODS_IDS)
        counters = ScannerRunStageCounters(goods_ids_requested=len(universe))
        failed_details: list[tuple[str, str]] = []
        candidate_rejections: Counter[str] = Counter()
        metadata_rejections: Counter[str] = Counter()
        recipe_rejections: Counter[str] = Counter()
        recipe_evaluations: list[LiveRecipeEvaluation] = []
        opportunities: list[LiveOpportunity] = []
        valuation_live_used = 0
        run_enriched_inputs: list[TradeUpEnrichedInput] = []
        listing_index: dict[str, BuffListingIntrinsicFlags] = {}

        # Construct a fresh scanner-owned run-scoped session for THIS
        # ``run_once`` call. The session owns the underlying live
        # price provider extracted from the injected ValuationService.
        # It is NOT a global singleton; it does NOT survive this call.
        session: RunScopedValuationSession | None = None
        if self._valuation_service is not None:
            session = RunScopedValuationSession(
                price_provider=self._valuation_service.price_provider,
                valuation_config=self._valuation_service.config,
                session_id=self._next_session_id,
                cached_price_resolver=self._cached_price_resolver,
            )
            self._next_session_id += 1

        for goods_id in universe:
            try:
                listings = cast(
                    list[BuffListingIntrinsicFlags],
                    await self._intrinsic_provider.get_listings(goods_id),
                )
            except MemoryError:
                raise
            except Exception as exc:
                counters = replace(
                    counters,
                    goods_ids_failed=counters.goods_ids_failed + 1,
                )
                failed_details.append((goods_id, _safe_reason(exc)))
                continue

            counters = replace(
                counters,
                goods_ids_succeeded=counters.goods_ids_succeeded + 1,
                listings_received=counters.listings_received + len(listings),
            )

            identity_resolved = sum(
                1 for listing in listings
                if listing.market_hash_name is not None
            )
            identity_unresolved = len(listings) - identity_resolved
            intrinsic_resolved = sum(
                1 for listing in listings
                if listing.stattrak is not None and listing.souvenir is not None
            )
            intrinsic_unresolved = len(listings) - intrinsic_resolved
            counters = replace(
                counters,
                identity_resolved=counters.identity_resolved + identity_resolved,
                identity_unresolved=counters.identity_unresolved + identity_unresolved,
                intrinsic_resolved=counters.intrinsic_resolved + intrinsic_resolved,
                intrinsic_unresolved=counters.intrinsic_unresolved
                + intrinsic_unresolved,
            )

            candidates: list[TradeUpInputCandidate] = []
            for listing in listings:
                outcome = convert_buff_listing_to_candidate(listing)  # type: ignore[arg-type]
                if isinstance(outcome, TradeUpInputCandidate):
                    candidates.append(outcome)
                else:
                    candidate_rejections[outcome.reason.value] += 1

            counters = replace(
                counters,
                candidate_accepted=counters.candidate_accepted + len(candidates),
                candidate_rejected=counters.candidate_rejected
                + (len(listings) - len(candidates)),
            )

            enrichment = enrich_candidates(candidates, self._enricher)
            enriched_inputs = list(enrichment.enriched)
            input_items = [item.input_item for item in enriched_inputs]
            for rejection in enrichment.rejected:
                metadata_rejections[rejection.reason.value] += 1

            counters = replace(
                counters,
                metadata_resolved=counters.metadata_resolved + len(input_items),
                metadata_unresolved=counters.metadata_unresolved
                + len(enrichment.rejected),
                input_items_created=counters.input_items_created + len(input_items),
            )

            for listing in listings:
                if listing.listing_id in listing_index:
                    raise ValueError("listing provenance contains duplicate listing_id")
                listing_index[listing.listing_id] = listing
            run_enriched_inputs.extend(enriched_inputs)

        composition = enumerate_scanner_recipe_selections(
            enriched_inputs=run_enriched_inputs,
            canonical_skins=self._metadata_resolver.skins,
            solver_config=self._solver_config,
            enumeration_config=self._enumeration_config,
        )

        for selection in composition.selections:
            counters = replace(
                counters,
                recipes_evaluated=counters.recipes_evaluated + 1,
            )
            requested_names = _unique_output_names(selection)
            requested_count = len(requested_names)

            # Phase 14B: when the session is alive, use the two-stage
            # prepare/execute contract; otherwise fall through to the
            # legacy "no valuation service" path (no provider exists,
            # so no live request can occur).
            if session is not None:
                plan = await session.prepare_output_prices(requested_names)
                live_demand_this_recipe = len(plan.new_live_names)
                if (
                    valuation_live_used + live_demand_this_recipe
                    > self._max_valuation_requests_per_run
                ):
                    session.record_atomically_blocked(plan)
                    counters = replace(
                        counters,
                        recipes_valuation_failed=(
                            counters.recipes_valuation_failed + 1
                        ),
                        recipes_rejected=counters.recipes_rejected + 1,
                        valuation_requests_blocked=(
                            counters.valuation_requests_blocked + requested_count
                        ),
                        live_demand=counters.live_demand + live_demand_this_recipe,
                        live_atomically_blocked=(
                            counters.live_atomically_blocked
                            + live_demand_this_recipe
                        ),
                        run_reuse_hits=(
                            counters.run_reuse_hits
                            + len(plan.memo_successes)
                            + len(plan.memo_terminal_failures)
                        ),
                        run_reuse_successes=(
                            counters.run_reuse_successes
                            + len(plan.memo_successes)
                        ),
                        run_reuse_failures=(
                            counters.run_reuse_failures
                            + len(plan.memo_terminal_failures)
                        ),
                        cache_hits_fresh_selected=(
                            counters.cache_hits_fresh_selected
                            + len(plan.cache_hits_fresh_selected)
                        ),
                        cache_misses=(
                            counters.cache_misses + len(plan.cache_misses)
                        ),
                        cache_policy_blocked=(
                            counters.cache_policy_blocked
                            + len(plan.cache_policy_blocked)
                        ),
                        cache_expired=(
                            counters.cache_expired + len(plan.cache_expired)
                        ),
                        cache_selection_failures=(
                            counters.cache_selection_failures
                            + len(plan.cache_terminal_selection_failures)
                        ),
                    )
                    recipe_rejections["VALUATION_REQUEST_CAP_EXCEEDED"] += 1
                    recipe_evaluations.append(
                        _build_blocked_evaluation(
                            selection,
                            requested_names,
                            listing_index,
                        )
                    )
                    continue

                valuation_live_used += live_demand_this_recipe
                counters = replace(
                    counters,
                    valuation_requests_attempted=(
                        counters.valuation_requests_attempted + requested_count
                    ),
                    live_demand=counters.live_demand + live_demand_this_recipe,
                    run_reuse_hits=(
                        counters.run_reuse_hits
                        + len(plan.memo_successes)
                        + len(plan.memo_terminal_failures)
                    ),
                    run_reuse_successes=(
                        counters.run_reuse_successes + len(plan.memo_successes)
                    ),
                    run_reuse_failures=(
                        counters.run_reuse_failures
                        + len(plan.memo_terminal_failures)
                    ),
                    cache_hits_fresh_selected=(
                        counters.cache_hits_fresh_selected
                        + len(plan.cache_hits_fresh_selected)
                    ),
                    cache_misses=(
                        counters.cache_misses + len(plan.cache_misses)
                    ),
                    cache_policy_blocked=(
                        counters.cache_policy_blocked
                        + len(plan.cache_policy_blocked)
                    ),
                    cache_expired=(
                        counters.cache_expired + len(plan.cache_expired)
                    ),
                    cache_selection_failures=(
                        counters.cache_selection_failures
                        + len(plan.cache_terminal_selection_failures)
                    ),
                )
                session_result = await session.resolve_prepared(
                    plan,
                    list(selection.recipe.tradeup_results),
                )
                evaluation = await self._evaluate_selection(
                    selection,
                    listing_index,
                    requested_names,
                    session_result,
                )
            else:
                # Legacy no-valuation-service branch: no provider exists, so
                # no live budget or Phase 14 live/cache counter is touched.
                # Preserve legacy logical accounting as closely as possible:
                # the recipe is admitted to the evaluation boundary and its
                # full requested_count is attempted/failed logically.
                session_result = None
                counters = replace(
                    counters,
                    valuation_requests_attempted=(
                        counters.valuation_requests_attempted + requested_count
                    ),
                )
                evaluation = await self._evaluate_selection(
                    selection,
                    listing_index,
                    requested_names,
                    None,
                )

            recipe_evaluations.append(evaluation)
            resolved_count = evaluation.valuation_prices_resolved
            failed_count = max(0, requested_count - resolved_count)
            base_updates = dict(
                valuation_requests_succeeded=(
                    counters.valuation_requests_succeeded + resolved_count
                ),
                valuation_requests_failed=(
                    counters.valuation_requests_failed + failed_count
                ),
            )
            if session_result is not None:
                base_updates.update(
                    live_attempted=(
                        counters.live_attempted
                        + session_result.live_attempted_delta
                    ),
                    live_succeeded=(
                        counters.live_succeeded
                        + session_result.live_succeeded_delta
                    ),
                    live_failed=(
                        counters.live_failed
                        + session_result.live_failed_delta
                    ),
                )
            counters = replace(counters, **base_updates)
            if not evaluation.valuation_completed:
                counters = replace(
                    counters,
                    recipes_valuation_failed=counters.recipes_valuation_failed + 1,
                    recipes_rejected=counters.recipes_rejected + 1,
                )
                recipe_rejections[
                    evaluation.rejection_reason or "VALUATION_INCOMPLETE"
                ] += 1
                continue

            counters = replace(
                counters,
                recipes_fully_valued=counters.recipes_fully_valued + 1,
            )
            if (
                evaluation.risk_decision is None
                or not evaluation.risk_decision.passed
            ):
                counters = replace(
                    counters,
                    recipes_rejected=counters.recipes_rejected + 1,
                )
                recipe_rejections["RISK_DECISION_REJECTED"] += 1
                continue
            opportunities.append(LiveOpportunity(evaluation=evaluation))

        opportunities.sort(
            key=lambda opp: (
                opp.metrics.expected_profit_cny,
                opp.metrics.roi,
            ),
            reverse=True,
        )
        counters = replace(
            counters,
            opportunities_found=len(opportunities),
        )
        completed_at = datetime.now(UTC)
        return ScannerRunResult(
            started_at=started_at,
            completed_at=completed_at,
            goods_ids=tuple(universe),
            counters=counters,
            diagnostics=ScannerRunDiagnostics(
                goods_ids_failed_details=tuple(failed_details),
                candidate_rejection_histogram=tuple(sorted(candidate_rejections.items())),
                metadata_rejection_histogram=tuple(sorted(metadata_rejections.items())),
                recipe_rejection_histogram=tuple(sorted(recipe_rejections.items())),
                recipe_composition=composition.diagnostics,
            ),
            recipe_evaluations=tuple(recipe_evaluations),
            opportunities=tuple(opportunities),
        )

    async def _evaluate_selection(
        self,
        selection: ConstructedRecipeSelection,
        listing_index: dict[str, BuffListingIntrinsicFlags],
        requested_names: tuple[str, ...],
        session_result: SessionValuationResult | None,
    ) -> LiveRecipeEvaluation:
        """Build the LiveRecipeEvaluation for one solver selection.

        When ``session_result`` is provided, the valuation field
        application has already happened inside the session via the
        existing ``ValuationService`` (``_FixedProvider``); this
        method only does metrics + risk + completion check.

        When ``session_result`` is ``None``, the legacy
        ``VALUATION_SERVICE_NOT_CONFIGURED`` branch is taken and no
        provider work is performed.
        """
        recipe = selection.recipe
        selected_listings = _selected_listings(selection, listing_index)

        if session_result is None or self._valuation_service is None:
            return LiveRecipeEvaluation(
                recipe=selection,
                output_market_hash_names_requested=requested_names,
                valued_tradeup_results=(),
                valuation_prices_resolved=0,
                valuation_completed=False,
                missing_market_hash_names=requested_names,
                price_errors=("VALUATION_SERVICE_NOT_CONFIGURED",),
                metrics=None,
                risk_decision=None,
                rejection_reason="VALUATION_SERVICE_NOT_CONFIGURED",
                listings=selected_listings,
            )

        valuation = session_result.valuation_result
        valued_results = tuple(valuation.tradeup_results)
        missing = tuple(valuation.missing_market_hash_names)
        errors = tuple(valuation.price_lookup_result.errors)
        complete = (
            not missing
            and not errors
            and len(valuation.price_lookup_result.quotes) == len(requested_names)
        )
        if not complete:
            return LiveRecipeEvaluation(
                recipe=selection,
                output_market_hash_names_requested=requested_names,
                valued_tradeup_results=valued_results,
                valuation_prices_resolved=len(valuation.price_lookup_result.quotes),
                valuation_completed=False,
                missing_market_hash_names=missing,
                price_errors=errors,
                metrics=None,
                risk_decision=None,
                rejection_reason="VALUATION_INCOMPLETE",
                listings=selected_listings,
            )

        metrics = calculate_opportunity_metrics(
            list(recipe.input_items),
            list(valued_results),
            self._solver_config.sell_fee_rate,
        )
        decision = evaluate_opportunity(
            metrics,
            list(recipe.input_items),
            self._risk_config,
            paint_seeds=list(recipe.paint_seeds),
        )
        return LiveRecipeEvaluation(
            recipe=selection,
            output_market_hash_names_requested=requested_names,
            valued_tradeup_results=valued_results,
            valuation_prices_resolved=len(valuation.price_lookup_result.quotes),
            valuation_completed=True,
            missing_market_hash_names=(),
            price_errors=(),
            metrics=metrics,
            risk_decision=decision,
            rejection_reason=None if decision.passed else "RISK_DECISION_REJECTED",
            listings=selected_listings,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_output_names(
    selection: ConstructedRecipeSelection,
) -> tuple[str, ...]:
    """Return exact output names in first-seen order."""
    return tuple(
        dict.fromkeys(
            result.output_market_hash_name
            for result in selection.recipe.tradeup_results
        )
    )


def _selected_listings(
    selection: ConstructedRecipeSelection,
    listing_index: dict[str, BuffListingIntrinsicFlags],
) -> tuple[BuffListingIntrinsicFlags, ...]:
    selected = tuple(
        listing_index[listing_id]
        for listing_id in selection.selected_listing_ids
        if listing_id in listing_index
    )
    if len(selected) != len(selection.selected_listing_ids):
        raise ValueError("selected listing provenance is incomplete")
    return selected


def _build_blocked_evaluation(
    selection: ConstructedRecipeSelection,
    requested_names: tuple[str, ...],
    listing_index: dict[str, BuffListingIntrinsicFlags],
) -> LiveRecipeEvaluation:
    return LiveRecipeEvaluation(
        recipe=selection,
        output_market_hash_names_requested=requested_names,
        valued_tradeup_results=(),
        valuation_prices_resolved=0,
        valuation_completed=False,
        missing_market_hash_names=requested_names,
        price_errors=("VALUATION_REQUEST_CAP_EXCEEDED",),
        metrics=None,
        risk_decision=None,
        rejection_reason="VALUATION_REQUEST_CAP_EXCEEDED",
        listings=_selected_listings(selection, listing_index),
    )


def _normalize_goods_ids(
    goods_ids: Iterable[str],
    *,
    hard_max: int,
) -> list[str]:
    """Validate, deduplicate, and bound a deterministic goods-id universe."""
    result: list[str] = []
    seen: set[str] = set()
    for raw in goods_ids:
        if type(raw) is not str:
            raise ValueError("goods_id must be a string")
        canonical = raw.strip()
        if not canonical:
            raise ValueError("goods_id must be non-empty")
        if canonical in seen:
            continue
        seen.add(canonical)
        result.append(canonical)
    if len(result) > hard_max:
        raise ValueError(
            f"goods_id universe exceeds hard maximum of {hard_max}"
        )
    return result


def _safe_reason(exc: BaseException) -> str:
    """Return a bounded context-free failure label without leaking payloads."""
    name = type(exc).__name__
    message = str(exc)
    if len(message) > 200:
        message = message[:200] + "..."
    return f"{name}: {message}" if message else name