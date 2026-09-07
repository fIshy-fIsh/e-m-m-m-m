"""Phase 17B opt-in recipe-first one-shot runtime coordinator.

The coordinator owns the discovery front half and delegates the mature
acquisition, concrete-search, valuation, EV, and risk path to
``RecipeFirstScannerOrchestrator`` exactly once. External market seams are
injected. This module never imports Phase 16G validation harness code.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from decimal import Decimal
from itertools import islice
from typing import Any, cast

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
    BuffGoodsIdIdentityResolver,
)
from app.services.market_universe_builder import StatTrakMode
from app.services.prescreen_price_book import PreScreenPriceBook
from app.services.recipe_family import RecipeFamily, RecipeFamilyGenerator
from app.services.recipe_family_geometry import (
    RecipeFamilyGeometry,
    compute_recipe_family_geometry,
)
from app.services.recipe_family_prescreen_economics import (
    RecipeFamilyPreScreenEconomics,
    RecipeFamilyPreScreenEconomicsConfig,
    RecipeFamilyPreScreenScenario,
    compute_recipe_family_prescreen_economics,
)
from app.services.recipe_family_ranking import (
    RecipeFamilyPreScreenCandidate,
    RecipeFamilyRankingResult,
    rank_recipe_family_candidates,
)
from app.services.recipe_first_acquisition import (
    ExistingRecipeFirstAcquisitionPipeline,
    RawBuffListingPageProvider,
)
from app.services.recipe_first_runtime_contract import (
    RecipeFirstDiscoveryBudget,
    RecipeFirstEvaluationSummary,
    RecipeFirstOperatorRunReport,
    RecipeFirstRankedFamilySummary,
    RecipeFirstRuntimeConfig,
    RecipeFirstRuntimeCounters,
    RecipeFirstRuntimeEvidence,
    RecipeFirstRuntimePhase,
    RecipeFirstRuntimeTerminalCode,
    RecipeFirstRuntimeTerminalGroup,
)
from app.services.recipe_first_scanner_orchestrator import (
    RecipeFirstScannerConfig,
    RecipeFirstScannerOrchestrator,
    RecipeFirstScannerRecipeEvaluation,
    RecipeFirstScannerRunCounters,
    RecipeFirstScannerRunResult,
)
from app.services.recipe_solver import RecipeSolverConfig
from app.services.risk_filter import RiskFilterConfig
from app.services.scanner_cached_buff_price_resolver import (
    ScannerCachedBuffPriceResolver,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.static_float_feasibility import (
    InputIdentityFloatEvidence,
    StaticFloatFeasibilityResult,
    StaticFloatFeasibilityStatus,
    build_input_identity_float_evidence,
    compute_static_float_feasibility,
)
from app.services.steamdt_batch_prescreen import (
    PRESCREEN_BATCH_CHUNK_SIZE,
    SteamDTBatchPreScreenRequest,
    SteamDTBatchPreScreenResolver,
    SteamDTBatchPreScreenResult,
    SteamDTBatchTransport,
)
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.targeted_buff_scan_plan import (
    TargetedBuffScanDecision,
    TargetedBuffScanPlan,
    build_targeted_buff_input_candidates,
    build_targeted_buff_scan_decision,
    build_targeted_buff_scan_plan,
)
from app.services.tradeup_engine import TradeupResult
from app.services.valuation_service import ValuationService

__all__ = (
    "RecipeFirstRuntimeCoordinator",
    "RecipeFirstRuntimeCoordinatorError",
)


class RecipeFirstRuntimeCoordinatorError(RuntimeError):
    """The Phase 17B composition contract failed closed."""


@dataclass(frozen=True, kw_only=True, repr=False)
class _FamilyCandidateEvidence:
    family: RecipeFamily
    geometry: RecipeFamilyGeometry
    feasibility: StaticFloatFeasibilityResult
    input_evidence: tuple[InputIdentityFloatEvidence, ...]
    prescreen_names: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class _DiscoverySummary:
    visited: int = 0
    infeasible: int = 0
    contract_failed: int = 0


@dataclass(frozen=True, kw_only=True)
class _PrescreenSummary:
    logical: int = 0
    unique: int = 0
    attempted: int = 0
    dispatched: int = 0
    selected: int = 0
    missing: int = 0
    selection_failures: int = 0
    transport_errors: int = 0
    atomically_blocked: int = 0


class _BudgetedBatchTransport:
    """Count dispatch starts and enforce the admitted batch count."""

    def __init__(self, *, delegate: SteamDTBatchTransport, budget: int) -> None:
        if not hasattr(delegate, "get_price_batch_with_selection"):
            raise RecipeFirstRuntimeCoordinatorError(
                "prescreen transport lacks required method"
            )
        self._delegate = delegate
        self._budget = budget
        self.dispatch_started = 0

    async def get_price_batch_with_selection(
        self,
        market_hash_names: list[str],
        *,
        selection_config: Any = None,
        avg_prices_by_name: dict[str, Decimal] | None = None,
    ) -> Any:
        if self.dispatch_started >= self._budget:
            raise RecipeFirstRuntimeCoordinatorError(
                "prescreen batch dispatch cap exceeded"
            )
        self.dispatch_started += 1
        return await self._delegate.get_price_batch_with_selection(
            market_hash_names,
            selection_config=selection_config,
            avg_prices_by_name=avg_prices_by_name,
        )


class _BudgetedRawListingProvider:
    """Lock the family at the actual BUFF dispatch seam and count starts."""

    def __init__(
        self,
        *,
        delegate: RawBuffListingPageProvider,
        max_dispatches: int,
        on_dispatch_started: Callable[[], None],
    ) -> None:
        if not hasattr(delegate, "get_listings"):
            raise RecipeFirstRuntimeCoordinatorError(
                "listing provider lacks get_listings"
            )
        self._delegate = delegate
        self._max_dispatches = max_dispatches
        self._on_dispatch_started = on_dispatch_started
        self.attempted = 0
        self.dispatch_started = 0
        self.succeeded = 0
        self.failed = 0

    async def get_listings(self, goods_id: str) -> list:
        if self.dispatch_started >= self._max_dispatches:
            raise RecipeFirstRuntimeCoordinatorError(
                "targeted BUFF dispatch cap exceeded"
            )
        self.attempted += 1
        self.dispatch_started += 1
        self._on_dispatch_started()
        try:
            listings = await self._delegate.get_listings(goods_id)
        except (MemoryError, asyncio.CancelledError):
            raise
        except RecipeFirstRuntimeCoordinatorError:
            self.failed += 1
            raise
        except Exception as exc:
            self.failed += 1
            raise _ExternalBuffProviderError() from exc
        self.succeeded += 1
        return listings


class _ExternalBuffProviderError(RuntimeError):
    """Raw BUFF provider failed after a dispatch start."""


class RecipeFirstRuntimeCoordinator:
    """Coordinate one bounded opt-in recipe-first run.

    Family discovery is lazy and globally bounded. All exact names are
    atomically admitted before the first batch dispatch. The active family
    may switch to ranked family #2 once, before any BUFF dispatch starts.
    """

    def __init__(
        self,
        *,
        config: RecipeFirstRuntimeConfig,
        discovery_budget: RecipeFirstDiscoveryBudget,
        identity_resolver: BuffCommunityIdentityResolver,
        metadata_resolver: PinnedSkinMetadataResolver,
        finish_index: StructuralOutputFinishIndex,
        prescreen_transport: SteamDTBatchTransport,
        listing_provider: RawBuffListingPageProvider,
        valuation_service: ValuationService,
        risk_config: RiskFilterConfig,
        cached_price_resolver: ScannerCachedBuffPriceResolver | None = None,
        intrinsic_resolver: Any = None,
        pre_buff_active_validator: Callable[[TargetedBuffScanPlan], bool]
        | None = None,
        final_price_source: str = "steamdt:buff",
        family_iterator_factory: Callable[
            [RecipeFamilyGenerator], Iterator[RecipeFamily]
        ]
        | None = None,
    ) -> None:
        if type(config) is not RecipeFirstRuntimeConfig or not config.enabled:
            raise RecipeFirstRuntimeCoordinatorError(
                "explicit enabled RecipeFirstRuntimeConfig required"
            )
        if type(discovery_budget) is not RecipeFirstDiscoveryBudget:
            raise RecipeFirstRuntimeCoordinatorError(
                "invalid RecipeFirstDiscoveryBudget"
            )
        if type(identity_resolver) is not BuffCommunityIdentityResolver:
            raise RecipeFirstRuntimeCoordinatorError(
                "identity_resolver must be BuffCommunityIdentityResolver"
            )
        if type(metadata_resolver) is not PinnedSkinMetadataResolver:
            raise RecipeFirstRuntimeCoordinatorError(
                "metadata_resolver must be PinnedSkinMetadataResolver"
            )
        if type(finish_index) is not StructuralOutputFinishIndex:
            raise RecipeFirstRuntimeCoordinatorError(
                "finish_index must be StructuralOutputFinishIndex"
            )
        if not hasattr(prescreen_transport, "get_price_batch_with_selection"):
            raise RecipeFirstRuntimeCoordinatorError("invalid prescreen transport")
        if not hasattr(listing_provider, "get_listings"):
            raise RecipeFirstRuntimeCoordinatorError("invalid listing provider")
        if type(valuation_service) is not ValuationService:
            raise RecipeFirstRuntimeCoordinatorError("invalid valuation service")
        if type(risk_config) is not RiskFilterConfig:
            raise RecipeFirstRuntimeCoordinatorError("invalid risk config")
        if (
            type(final_price_source) is not str
            or final_price_source != "steamdt:buff"
        ):
            raise RecipeFirstRuntimeCoordinatorError(
                "final price source must be exact steamdt:buff"
            )
        known_collections = {
            skin.collection_name
            for skin in metadata_resolver.skins
            if skin.collection_name is not None
        }
        if not set(config.collection_allowlist).issubset(known_collections):
            raise RecipeFirstRuntimeCoordinatorError(
                "collection allowlist contains unknown pinned collection"
            )

        self._config = config
        self._budget = discovery_budget
        self._identity = identity_resolver
        self._metadata = metadata_resolver
        self._finish_index = finish_index
        self._batch_transport = _BudgetedBatchTransport(
            delegate=prescreen_transport,
            budget=discovery_budget.max_prescreen_batch_dispatches,
        )
        self._prescreen = SteamDTBatchPreScreenResolver(
            client=cast(SteamDTBatchTransport, self._batch_transport)
        )
        self._raw_listing = _BudgetedRawListingProvider(
            delegate=listing_provider,
            max_dispatches=config.max_targeted_buff_goods_ids,
            on_dispatch_started=self._lock_active_family,
        )
        self._valuation_service = valuation_service
        self._risk_config = risk_config
        self._cached_price_resolver = cached_price_resolver
        self._intrinsic_resolver = intrinsic_resolver
        self._active_validator = pre_buff_active_validator
        self._final_price_source = final_price_source
        self._family_iterator_factory = family_iterator_factory
        self._buff_locked = False
        self._fallback_used = False
        self._last_prescreen_result: SteamDTBatchPreScreenResult | None = None

    @property
    def buff_dispatch_started(self) -> int:
        return self._raw_listing.dispatch_started

    @property
    def fallback_used(self) -> bool:
        return self._fallback_used

    async def run_once(self) -> RecipeFirstOperatorRunReport:
        phases: list[RecipeFirstRuntimePhase] = []
        safe_errors: list[str] = []

        candidates, discovery = self._discover(phases=phases)
        if not candidates:
            code = (
                RecipeFirstRuntimeTerminalCode.INTERNAL_CONTRACT_FAILURE
                if discovery.contract_failed > 0
                else RecipeFirstRuntimeTerminalCode.NO_CONCRETE_SELECTION
            )
            return self._report(
                code=code,
                phases=phases,
                discovery=discovery,
                prescreen=_PrescreenSummary(),
                ranking=None,
                decision=None,
                downstream=None,
                safe_errors=safe_errors,
            )

        names = self._dedupe_names(candidates)
        admitted, prescreen_summary = self._admit_prescreen(
            names=names,
            logical=sum(len(item.prescreen_names) for item in candidates),
        )
        if not admitted:
            phases.append(
                RecipeFirstRuntimePhase(
                    name="prescreen_admission",
                    status="blocked",
                    detail=(
                        f"unique={len(names)} names_cap={self._budget.max_prescreen_names} "
                        f"batch_cap={self._budget.max_prescreen_batch_dispatches}"
                    ),
                )
            )
            return self._report(
                code=RecipeFirstRuntimeTerminalCode.PRESCREEN_INCOMPLETE,
                phases=phases,
                discovery=discovery,
                prescreen=prescreen_summary,
                ranking=None,
                decision=None,
                downstream=None,
                safe_errors=safe_errors,
            )

        result = await self._run_prescreen(names=names, phases=phases)
        if result is None:
            safe_errors.append("PRESCREEN_PROVIDER_FAILURE")
            return self._report(
                code=RecipeFirstRuntimeTerminalCode.EXTERNAL_PROVIDER_FAILURE,
                phases=phases,
                discovery=discovery,
                prescreen=replace(
                    prescreen_summary,
                    dispatched=self._batch_transport.dispatch_started,
                    transport_errors=1,
                ),
                ranking=None,
                decision=None,
                downstream=None,
                safe_errors=safe_errors,
            )

        self._last_prescreen_result = result
        prescreen_summary = self._prescreen_summary(
            result=result,
            logical=prescreen_summary.logical,
        )
        if result.diagnostics.transport_errors:
            phases.append(
                RecipeFirstRuntimePhase(
                    name="prescreen",
                    status="failed",
                    detail=(
                        f"dispatches={self._batch_transport.dispatch_started} "
                        f"transport_errors={len(result.diagnostics.transport_errors)}"
                    ),
                )
            )
            return self._report(
                code=RecipeFirstRuntimeTerminalCode.EXTERNAL_PROVIDER_FAILURE,
                phases=phases,
                discovery=discovery,
                prescreen=prescreen_summary,
                ranking=None,
                decision=None,
                downstream=None,
                safe_errors=["PRESCREEN_PROVIDER_FAILURE"],
            )
        if (
            result.missing_market_hash_names
            or result.terminal_selection_failures
        ):
            phases.append(
                RecipeFirstRuntimePhase(
                    name="prescreen",
                    status="incomplete",
                    detail=(
                        f"selected={len(result.quotes)} "
                        f"missing={len(result.missing_market_hash_names)} "
                        f"failures={len(result.terminal_selection_failures)}"
                    ),
                )
            )
            return self._report(
                code=RecipeFirstRuntimeTerminalCode.PRESCREEN_INCOMPLETE,
                phases=phases,
                discovery=discovery,
                prescreen=prescreen_summary,
                ranking=None,
                decision=None,
                downstream=None,
                safe_errors=safe_errors,
            )

        price_book = PreScreenPriceBook(
            quotes_by_name={quote.market_hash_name: quote for quote in result.quotes}
        )
        ranking, plans_by_key, build_error = self._rank(
            candidates=candidates,
            price_book=price_book,
        )
        if build_error is not None:
            safe_errors.append(build_error)
            return self._report(
                code=RecipeFirstRuntimeTerminalCode.INTERNAL_CONTRACT_FAILURE,
                phases=phases,
                discovery=discovery,
                prescreen=prescreen_summary,
                ranking=None,
                decision=None,
                downstream=None,
                safe_errors=safe_errors,
            )
        assert ranking is not None
        if not ranking.ranked:
            phases.append(
                RecipeFirstRuntimePhase(
                    name="ranking",
                    status="complete",
                    detail="retained=0",
                )
            )
            return self._report(
                code=RecipeFirstRuntimeTerminalCode.NO_CONCRETE_SELECTION,
                phases=phases,
                discovery=discovery,
                prescreen=prescreen_summary,
                ranking=ranking,
                decision=None,
                downstream=None,
                safe_errors=safe_errors,
            )

        try:
            decision = build_targeted_buff_scan_decision(
                ranking.ranked_family_keys,
                plans_by_family_key=plans_by_key,
            )
            decision = self._resolve_pre_buff_fallback(
                decision=decision,
                plans_by_key=plans_by_key,
            )
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception as exc:
            safe_errors.append(type(exc).__name__)
            return self._report(
                code=RecipeFirstRuntimeTerminalCode.INTERNAL_CONTRACT_FAILURE,
                phases=phases,
                discovery=discovery,
                prescreen=prescreen_summary,
                ranking=ranking,
                decision=None,
                downstream=None,
                safe_errors=safe_errors,
            )
        if decision.active_plan is None or decision.active_family_key is None:
            return self._report(
                code=RecipeFirstRuntimeTerminalCode.BUFF_ACQUISITION_INSUFFICIENT,
                phases=phases,
                discovery=discovery,
                prescreen=prescreen_summary,
                ranking=ranking,
                decision=decision,
                downstream=None,
                safe_errors=safe_errors,
            )

        active = next(
            (
                item
                for item in candidates
                if item.family.family_key == decision.active_family_key
            ),
            None,
        )
        if active is None:
            safe_errors.append("ACTIVE_FAMILY_NOT_RETAINED")
            return self._report(
                code=RecipeFirstRuntimeTerminalCode.INTERNAL_CONTRACT_FAILURE,
                phases=phases,
                discovery=discovery,
                prescreen=prescreen_summary,
                ranking=ranking,
                decision=decision,
                downstream=None,
                safe_errors=safe_errors,
            )

        phases.append(
            RecipeFirstRuntimePhase(
                name="ranking",
                status="ok",
                detail=(
                    f"retained={len(ranking.ranked)} "
                    f"active={decision.active_family_key} "
                    f"fallback_used={self._fallback_used}"
                ),
            )
        )
        try:
            downstream = await self._downstream(
                decision=decision,
                active=active,
            )
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception as exc:
            safe_errors.append(type(exc).__name__)
            return self._report(
                code=RecipeFirstRuntimeTerminalCode.INTERNAL_CONTRACT_FAILURE,
                phases=phases,
                discovery=discovery,
                prescreen=prescreen_summary,
                ranking=ranking,
                decision=decision,
                downstream=None,
                safe_errors=safe_errors,
            )

        code = self._classify_downstream(downstream)
        phases.append(
            RecipeFirstRuntimePhase(
                name="downstream",
                status="ok" if code in {
                    RecipeFirstRuntimeTerminalCode.SUCCESS_OPPORTUNITIES_FOUND,
                    RecipeFirstRuntimeTerminalCode.RISK_FILTER_REJECTED,
                    RecipeFirstRuntimeTerminalCode.NO_CONCRETE_SELECTION,
                } else "incomplete",
                detail=(
                    f"evaluations={len(downstream.evaluations)} "
                    f"opportunities={len(downstream.opportunities)}"
                ),
            )
        )
        return self._report(
            code=code,
            phases=phases,
            discovery=discovery,
            prescreen=prescreen_summary,
            ranking=ranking,
            decision=decision,
            downstream=downstream,
            safe_errors=safe_errors,
        )

    def _discover(
        self,
        *,
        phases: list[RecipeFirstRuntimePhase],
    ) -> tuple[tuple[_FamilyCandidateEvidence, ...], _DiscoverySummary]:
        retained: list[_FamilyCandidateEvidence] = []
        visited = 0
        infeasible = 0
        contract_failed = 0
        allow = set(self._config.collection_allowlist)
        seen_family_hashes: set[str] = set()
        exhausted = False

        for rarity in self._config.input_rarities:
            if exhausted:
                break
            for mode in self._config.stattrak_modes:
                generator = RecipeFamilyGenerator.from_catalogs(
                    skins=self._metadata.skins,
                    identity_resolver=self._identity,
                    finish_index=self._finish_index,
                    input_rarity=rarity,
                    stattrak_mode=mode,
                )
                iterator = (
                    self._family_iterator_factory(generator)
                    if self._family_iterator_factory is not None
                    else generator.iter_families()
                )
                remaining = self._budget.max_family_states_considered - visited
                for family in islice(iterator, remaining):
                    visited += 1
                    if type(family) is not RecipeFamily:
                        contract_failed += 1
                        continue
                    if family.family_hash in seen_family_hashes:
                        continue
                    seen_family_hashes.add(family.family_hash)
                    if allow and not {
                        name for name, _count in family.collection_counts
                    }.issubset(allow):
                        continue
                    try:
                        geometry = compute_recipe_family_geometry(
                            family,
                            finish_index=self._finish_index,
                        )
                        feasibility = compute_static_float_feasibility(
                            family,
                            skins=self._metadata.skins,
                            identity_resolver=self._identity,
                            finish_index=self._finish_index,
                        )
                        input_evidence = build_input_identity_float_evidence(
                            skins=self._metadata.skins,
                            identity_resolver=self._identity,
                            input_rarity=family.input_rarity,
                            stattrak_mode=family.stattrak_mode,
                            represented_collections=tuple(
                                name for name, _count in family.collection_counts
                            ),
                        )
                    except (MemoryError, asyncio.CancelledError):
                        raise
                    except Exception:
                        contract_failed += 1
                        continue
                    if (
                        feasibility.status
                        is not StaticFloatFeasibilityStatus.FEASIBLE
                        or not input_evidence
                    ):
                        infeasible += 1
                        continue
                    names = _dedupe_exact_names(
                        tuple(item.market_hash_name for item in input_evidence)
                        + tuple(
                            item.exact_market_hash_name
                            for item in feasibility.reachable_outputs
                        )
                    )
                    if not names:
                        infeasible += 1
                        continue
                    retained.append(
                        _FamilyCandidateEvidence(
                            family=family,
                            geometry=geometry,
                            feasibility=feasibility,
                            input_evidence=input_evidence,
                            prescreen_names=names,
                        )
                    )
                if visited >= self._budget.max_family_states_considered:
                    exhausted = True
                    break

        summary = _DiscoverySummary(
            visited=visited,
            infeasible=infeasible,
            contract_failed=contract_failed,
        )
        phases.append(
            RecipeFirstRuntimePhase(
                name="discovery",
                status="ok" if retained else "complete",
                detail=(
                    f"visited={visited} feasible={len(retained)} "
                    f"infeasible={infeasible} contract_failed={contract_failed}"
                ),
            )
        )
        return tuple(retained), summary

    @staticmethod
    def _dedupe_names(
        candidates: tuple[_FamilyCandidateEvidence, ...],
    ) -> tuple[str, ...]:
        return _dedupe_exact_names(
            tuple(name for item in candidates for name in item.prescreen_names)
        )

    def _admit_prescreen(
        self,
        *,
        names: tuple[str, ...],
        logical: int,
    ) -> tuple[bool, _PrescreenSummary]:
        chunks = (
            len(names) + PRESCREEN_BATCH_CHUNK_SIZE - 1
        ) // PRESCREEN_BATCH_CHUNK_SIZE
        admitted = (
            len(names) <= self._budget.max_prescreen_names
            and chunks <= self._budget.max_prescreen_batch_dispatches
        )
        return admitted, _PrescreenSummary(
            logical=logical,
            unique=len(names),
            atomically_blocked=0 if admitted else len(names),
        )

    async def _run_prescreen(
        self,
        *,
        names: tuple[str, ...],
        phases: list[RecipeFirstRuntimePhase],
    ) -> SteamDTBatchPreScreenResult | None:
        try:
            return await self._prescreen.prescreen(
                SteamDTBatchPreScreenRequest(market_hash_names=list(names))
            )
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception as exc:
            phases.append(
                RecipeFirstRuntimePhase(
                    name="prescreen",
                    status="failed",
                    detail=type(exc).__name__,
                )
            )
            return None

    def _prescreen_summary(
        self,
        *,
        result: SteamDTBatchPreScreenResult,
        logical: int,
    ) -> _PrescreenSummary:
        d = result.diagnostics
        return _PrescreenSummary(
            logical=logical,
            unique=d.unique_names,
            attempted=d.transport_attempted_names,
            dispatched=self._batch_transport.dispatch_started,
            selected=d.selected_names,
            missing=d.missing_names,
            selection_failures=d.terminal_selection_failures,
            transport_errors=len(d.transport_errors),
        )

    def _rank(
        self,
        *,
        candidates: tuple[_FamilyCandidateEvidence, ...],
        price_book: PreScreenPriceBook,
    ) -> tuple[
        RecipeFamilyRankingResult | None,
        dict[str, TargetedBuffScanPlan | None],
        str | None,
    ]:
        ranking_candidates: list[RecipeFamilyPreScreenCandidate] = []
        plans_by_key: dict[str, TargetedBuffScanPlan | None] = {}
        try:
            for item in candidates:
                economics: tuple[RecipeFamilyPreScreenEconomics, ...] = (
                    compute_recipe_family_prescreen_economics(
                        item.family,
                        geometry=item.geometry,
                        static_feasibility=item.feasibility,
                        input_evidence=item.input_evidence,
                        price_book=price_book,
                        config=RecipeFamilyPreScreenEconomicsConfig(
                            sell_fee_rate=self._config.sell_fee_rate
                        ),
                    )
                )
                targeted_inputs = build_targeted_buff_input_candidates(
                    family=item.family,
                    input_evidence=item.input_evidence,
                    price_book=price_book,
                )
                plan: TargetedBuffScanPlan | None = None
                if targeted_inputs:
                    try:
                        candidate_plan = build_targeted_buff_scan_plan(
                            item.family,
                            candidates=targeted_inputs,
                            priority=1,
                        )
                    except Exception:
                        candidate_plan = None
                    if (
                        candidate_plan is not None
                        and candidate_plan.hard_request_count
                        <= self._config.max_targeted_buff_goods_ids
                    ):
                        plan = candidate_plan
                plans_by_key[item.family.family_key] = plan
                ranking_candidates.append(
                    RecipeFamilyPreScreenCandidate(
                        family=item.family,
                        static_feasibility=item.feasibility,
                        economics=economics,
                        targeted_plan=plan,
                        batch_prescreen_succeeded=True,
                    )
                )
            return (
                rank_recipe_family_candidates(iter(ranking_candidates)),
                plans_by_key,
                None,
            )
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception as exc:
            return None, plans_by_key, type(exc).__name__

    def _resolve_pre_buff_fallback(
        self,
        *,
        decision: TargetedBuffScanDecision,
        plans_by_key: dict[str, TargetedBuffScanPlan | None],
    ) -> TargetedBuffScanDecision:
        if decision.active_plan is None or self._active_validator is None:
            return decision
        try:
            active_usable = self._active_validator(decision.active_plan)
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception as exc:
            raise RecipeFirstRuntimeCoordinatorError(
                "pre-BUFF active-plan validator contract failed"
            ) from exc
        if active_usable:
            return decision
        if self._buff_locked or self._raw_listing.dispatch_started:
            raise RecipeFirstRuntimeCoordinatorError(
                "fallback forbidden after BUFF dispatch start"
            )
        fallback_key = decision.fallback_family_key
        if fallback_key is None or self._fallback_used:
            return TargetedBuffScanDecision(
                ranked_family_keys=decision.ranked_family_keys,
                active_family_key=None,
                active_plan=None,
                fallback_family_key=None,
                hard_request_cap=decision.hard_request_cap,
                diagnostics=decision.diagnostics
                + ("active_plan_unusable_before_buff",),
            )
        fallback_plan = plans_by_key.get(fallback_key)
        if fallback_plan is None:
            return TargetedBuffScanDecision(
                ranked_family_keys=decision.ranked_family_keys,
                active_family_key=None,
                active_plan=None,
                fallback_family_key=None,
                hard_request_cap=decision.hard_request_cap,
                diagnostics=decision.diagnostics
                + ("fallback_plan_unavailable_before_buff",),
            )
        self._fallback_used = True
        return TargetedBuffScanDecision(
            ranked_family_keys=decision.ranked_family_keys,
            active_family_key=fallback_key,
            active_plan=fallback_plan,
            fallback_family_key=None,
            hard_request_cap=decision.hard_request_cap,
            diagnostics=decision.diagnostics
            + ("fallback_consumed_before_buff",),
        )

    def _lock_active_family(self) -> None:
        self._buff_locked = True

    async def _downstream(
        self,
        *,
        decision: TargetedBuffScanDecision,
        active: _FamilyCandidateEvidence,
    ) -> RecipeFirstScannerRunResult:
        pipeline = ExistingRecipeFirstAcquisitionPipeline(
            listing_provider=cast(RawBuffListingPageProvider, self._raw_listing),
            identity_resolver=cast(BuffGoodsIdIdentityResolver, self._identity),
            metadata_resolver=self._metadata,
            intrinsic_resolver=self._intrinsic_resolver,
        )
        orchestrator = RecipeFirstScannerOrchestrator(
            listing_provider=pipeline,
            identity_resolver=cast(BuffGoodsIdIdentityResolver, self._identity),
            valuation_service=self._valuation_service,
            finish_index=self._finish_index,
            solver_config=RecipeSolverConfig(
                input_rarity=active.family.input_rarity,
                sell_fee_rate=self._config.sell_fee_rate,
                target_stattrak=(
                    active.family.stattrak_mode is StatTrakMode.STATTRAK
                ),
            ),
            risk_config=self._risk_config,
            enumeration_config=self._config.enumeration_config,
            config=RecipeFirstScannerConfig(
                enabled=True,
                max_valuation_requests_per_run=(
                    self._config.max_final_valuation_requests
                ),
            ),
            cached_price_resolver=self._cached_price_resolver,
        )
        return await orchestrator.run_once(
            decision=decision,
            family=active.family,
            geometry=active.geometry,
        )

    @staticmethod
    def _classify_downstream(
        result: RecipeFirstScannerRunResult,
    ) -> RecipeFirstRuntimeTerminalCode:
        if result.counters.valuation_requests_blocked > 0:
            return (
                RecipeFirstRuntimeTerminalCode.VALUATION_REQUEST_BUDGET_BLOCKED
            )
        if result.diagnostics.page_failures:
            if all(
                reason == _ExternalBuffProviderError.__name__
                for _goods_id, reason in result.diagnostics.page_failures
            ):
                return RecipeFirstRuntimeTerminalCode.EXTERNAL_PROVIDER_FAILURE
            return (
                RecipeFirstRuntimeTerminalCode.IDENTITY_INTRINSIC_METADATA_CONTRACT_FAILURE
            )
        if any(not item.valuation_completed for item in result.evaluations):
            return RecipeFirstRuntimeTerminalCode.FINAL_VALUATION_INCOMPLETE
        if any(
            item.valuation_completed and item.risk_decision is None
            for item in result.evaluations
        ):
            return RecipeFirstRuntimeTerminalCode.INTERNAL_CONTRACT_FAILURE
        if result.opportunities:
            return RecipeFirstRuntimeTerminalCode.SUCCESS_OPPORTUNITIES_FOUND
        if result.evaluations and all(
            item.risk_decision is not None
            and item.risk_decision.passed is False
            for item in result.evaluations
        ):
            return RecipeFirstRuntimeTerminalCode.RISK_FILTER_REJECTED
        if (
            not result.evaluations
            and result.counters.family_compatible_inputs < 10
        ):
            return RecipeFirstRuntimeTerminalCode.BUFF_ACQUISITION_INSUFFICIENT
        return RecipeFirstRuntimeTerminalCode.NO_CONCRETE_SELECTION

    def _report(
        self,
        *,
        code: RecipeFirstRuntimeTerminalCode,
        phases: list[RecipeFirstRuntimePhase],
        discovery: _DiscoverySummary,
        prescreen: _PrescreenSummary,
        ranking: RecipeFamilyRankingResult | None,
        decision: TargetedBuffScanDecision | None,
        downstream: RecipeFirstScannerRunResult | None,
        safe_errors: list[str],
    ) -> RecipeFirstOperatorRunReport:
        counters = self._report_counters(
            discovery=discovery,
            prescreen=prescreen,
            ranking=ranking,
            downstream=downstream,
        )
        evidence = self._report_evidence(
            ranking=ranking,
            decision=decision,
            downstream=downstream,
        )
        return RecipeFirstOperatorRunReport(
            mode="recipe-first-one-shot",
            run_id=1,
            terminal_group=_group_for_code(code),
            terminal_code=code,
            config_identity=self._config_identity(),
            discovery_budget=self._budget,
            counters=counters,
            phases=tuple(phases),
            evidence=evidence,
            incompleteness_flags=(
                ()
                if _group_for_code(code)
                in {
                    RecipeFirstRuntimeTerminalGroup.SUCCESS,
                    RecipeFirstRuntimeTerminalGroup.EXPECTED_NO_OPPORTUNITY,
                }
                else (code.value,)
            ),
            safe_error_codes=tuple(safe_errors),
        )

    def _report_counters(
        self,
        *,
        discovery: _DiscoverySummary,
        prescreen: _PrescreenSummary,
        ranking: RecipeFamilyRankingResult | None,
        downstream: RecipeFirstScannerRunResult | None,
    ) -> RecipeFirstRuntimeCounters:
        d = downstream.counters if downstream is not None else (
            RecipeFirstScannerRunCounters()
        )
        return RecipeFirstRuntimeCounters(
            families_visited=discovery.visited,
            families_infeasible=discovery.infeasible,
            families_contract_failed=discovery.contract_failed,
            families_ranked_retained=(
                len(ranking.ranked) if ranking is not None else 0
            ),
            families_ranked_excluded=(
                ranking.excluded_count if ranking is not None else 0
            ),
            prescreen_logical_requested=prescreen.logical,
            prescreen_unique_after_dedupe=prescreen.unique,
            prescreen_attempted=prescreen.attempted,
            prescreen_dispatch_started=prescreen.dispatched,
            prescreen_succeeded=prescreen.selected,
            prescreen_missing=prescreen.missing,
            prescreen_terminal_selection_failures=prescreen.selection_failures,
            prescreen_transport_error_count=prescreen.transport_errors,
            prescreen_atomically_blocked=prescreen.atomically_blocked,
            buff_attempted=self._raw_listing.attempted,
            buff_dispatch_started=self._raw_listing.dispatch_started,
            buff_succeeded=self._raw_listing.succeeded,
            buff_provider_failure=self._raw_listing.failed,
            buff_contract_failure=0,
            fallback_family_used=self._fallback_used,
            run_reuse_hits=d.run_reuse_hits,
            cache_hits_fresh_selected=d.cache_hits_fresh_selected,
            cache_misses=d.cache_misses,
            cache_policy_blocked=d.cache_policy_blocked,
            cache_expired=d.cache_expired,
            cache_selection_failures=d.cache_selection_failures,
            live_demand=d.live_demand,
            live_attempted=d.live_attempted,
            live_succeeded=d.live_succeeded,
            live_failed=d.live_failed,
            live_atomically_blocked=d.live_atomically_blocked,
            evaluations_total=d.recipes_evaluated,
            evaluations_valuation_completed=d.recipes_fully_valued,
            evaluations_risk_rejected=d.recipes_risk_rejected,
            evaluations_budget_blocked=d.valuation_requests_blocked,
            opportunities_found=d.opportunities_found,
        )

    def _report_evidence(
        self,
        *,
        ranking: RecipeFamilyRankingResult | None,
        decision: TargetedBuffScanDecision | None,
        downstream: RecipeFirstScannerRunResult | None,
    ) -> RecipeFirstRuntimeEvidence:
        evaluation_summaries = tuple(
            _evaluation_summary(index, item, self._final_price_source)
            for index, item in enumerate(
                downstream.evaluations if downstream is not None else ()
            )
        )
        evaluation = (
            downstream.evaluations[0]
            if downstream is not None and downstream.evaluations
            else None
        )
        rows: tuple[TradeupResult, ...] = ()
        input_count = 0
        metrics = None
        risk = None
        rejection = None
        if evaluation is not None:
            rows = (
                evaluation.valued_tradeup_results
                if evaluation.valued_tradeup_results
                else evaluation.selection.concrete_outcomes.tradeup_results
            )
            input_count = len(evaluation.selection.selection.recipe.input_items)
            metrics = evaluation.metrics
            risk = evaluation.risk_decision
            rejection = evaluation.rejection_reason
        complete = evaluation is not None and evaluation.valuation_completed
        plan = decision.active_plan if decision is not None else None
        return RecipeFirstRuntimeEvidence(
            prescreen_quote_names=(
                tuple(q.market_hash_name for q in self._last_prescreen_result.quotes)
                if self._last_prescreen_result is not None
                else ()
            ),
            prescreen_missing_names=(
                self._last_prescreen_result.missing_market_hash_names
                if self._last_prescreen_result is not None
                else ()
            ),
            prescreen_terminal_selection_failures=(
                self._last_prescreen_result.terminal_selection_failures
                if self._last_prescreen_result is not None
                else ()
            ),
            ranked_families=(
                _ranking_summaries(ranking) if ranking is not None else ()
            ),
            selected_active_family_key=(
                decision.active_family_key if decision is not None else None
            ),
            selected_active_family_hash=(
                plan.family_hash if plan is not None else None
            ),
            fallback_family_key=(
                decision.fallback_family_key if decision is not None else None
            ),
            fallback_reason=(
                "fallback_consumed_before_buff"
                if self._fallback_used
                else (
                    "fallback_available_before_buff"
                    if decision is not None
                    and decision.fallback_family_key is not None
                    else None
                )
            ),
            targeted_goods_ids=(plan.goods_ids if plan is not None else ()),
            targeted_goods_market_hash_names=(
                plan.market_hash_names if plan is not None else ()
            ),
            concrete_input_summary_count=input_count,
            concrete_output_names=tuple(
                row.output_market_hash_name for row in rows
            ),
            concrete_output_probabilities=tuple(row.probability for row in rows),
            concrete_output_floats=tuple(row.output_float for row in rows),
            concrete_output_wears=tuple(row.output_wear for row in rows),
            final_quote_market_hash_names=(
                tuple(row.output_market_hash_name for row in rows)
                if complete
                else ()
            ),
            final_quote_price_cny=(
                tuple(row.estimated_price_cny for row in rows)
                if complete
                else ()
            ),
            final_quote_source=(
                tuple(self._final_price_source for _row in rows)
                if complete
                else ()
            ),
            evaluations=evaluation_summaries,
            selected_family_evaluations_count=(
                len(downstream.evaluations) if downstream is not None else 0
            ),
            selected_family_evaluations_complete=(
                sum(item.valuation_completed for item in downstream.evaluations)
                if downstream is not None
                else 0
            ),
            selected_family_opportunities=(
                len(downstream.opportunities) if downstream is not None else 0
            ),
            input_total_cost_cny=(
                metrics.input_total_cost_cny if metrics is not None else None
            ),
            expected_gross_revenue_cny=(
                metrics.expected_revenue_cny if metrics is not None else None
            ),
            expected_profit_cny=(
                metrics.expected_profit_cny if metrics is not None else None
            ),
            roi=metrics.roi if metrics is not None else None,
            profit_probability=(
                metrics.profit_probability if metrics is not None else None
            ),
            worst_case_loss_cny=(
                max(Decimal("0"), -metrics.worst_case_profit_cny)
                if metrics is not None
                else None
            ),
            risk_passed=risk.passed if risk is not None else None,
            risk_reason_codes=(
                tuple(risk.reason_codes) if risk is not None else ()
            ),
            risk_rejection_reason=rejection,
        )

    def _config_identity(self) -> tuple[str, ...]:
        return (
            "enabled=true",
            f"preview={self._config.preview}",
            f"rarities={','.join(self._config.input_rarities)}",
            f"stattrak_modes={','.join(m.value for m in self._config.stattrak_modes)}",
            f"collection_allowlist_size={len(self._config.collection_allowlist)}",
            f"max_targeted_buff_goods_ids={self._config.max_targeted_buff_goods_ids}",
            f"max_final_valuation_requests={self._config.max_final_valuation_requests}",
            f"sell_fee_rate={self._config.sell_fee_rate}",
            f"enumeration_candidates={self._config.enumeration_config.max_recipe_candidates_returned}",
            f"enumeration_states={self._config.enumeration_config.max_candidate_states_explored}",
            f"cache_backend={self._config.cache_backend}",
            f"output_format={self._config.output_format.value}",
        )


def _dedupe_exact_names(names: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for name in names:
        if type(name) is not str or not name or name != name.strip():
            raise RecipeFirstRuntimeCoordinatorError(
                "prescreen names must be exact non-empty strings"
            )
        if name in seen:
            continue
        seen.add(name)
        unique.append(name)
    return tuple(unique)


def _evaluation_summary(
    index: int,
    evaluation: RecipeFirstScannerRecipeEvaluation,
    final_source: str,
) -> RecipeFirstEvaluationSummary:
    rows = (
        evaluation.valued_tradeup_results
        if evaluation.valued_tradeup_results
        else evaluation.selection.concrete_outcomes.tradeup_results
    )
    metrics = evaluation.metrics
    risk = evaluation.risk_decision
    complete = evaluation.valuation_completed
    return RecipeFirstEvaluationSummary(
        index=index,
        valuation_completed=complete,
        rejection_reason=evaluation.rejection_reason,
        concrete_input_count=len(evaluation.selection.selection.recipe.input_items),
        output_names=tuple(row.output_market_hash_name for row in rows),
        output_probabilities=tuple(row.probability for row in rows),
        output_floats=tuple(row.output_float for row in rows),
        output_wears=tuple(row.output_wear for row in rows),
        final_price_cny=(
            tuple(row.estimated_price_cny for row in rows) if complete else ()
        ),
        final_price_source=(
            tuple(final_source for _row in rows) if complete else ()
        ),
        input_total_cost_cny=(
            metrics.input_total_cost_cny if metrics is not None else None
        ),
        expected_gross_revenue_cny=(
            metrics.expected_revenue_cny if metrics is not None else None
        ),
        expected_profit_cny=(
            metrics.expected_profit_cny if metrics is not None else None
        ),
        roi=metrics.roi if metrics is not None else None,
        profit_probability=(
            metrics.profit_probability if metrics is not None else None
        ),
        worst_case_loss_cny=(
            max(Decimal("0"), -metrics.worst_case_profit_cny)
            if metrics is not None
            else None
        ),
        risk_passed=risk.passed if risk is not None else None,
        risk_reason_codes=tuple(risk.reason_codes) if risk is not None else (),
    )


def _ranking_summaries(
    ranking: RecipeFamilyRankingResult,
) -> tuple[RecipeFirstRankedFamilySummary, ...]:
    rows: list[RecipeFirstRankedFamilySummary] = []
    for rank, item in enumerate(ranking.ranked, start=1):
        base = item.economics_for(RecipeFamilyPreScreenScenario.BASE)
        conservative = item.economics_for(
            RecipeFamilyPreScreenScenario.CONSERVATIVE
        )
        rows.append(
            RecipeFirstRankedFamilySummary(
                rank=rank,
                family_key=item.family_key,
                family_hash=item.family_hash,
                base_estimated_roi=base.estimated_roi,
                base_estimated_profit_cny=base.estimated_profit_cny,
                conservative_estimated_roi=conservative.estimated_roi,
                conservative_estimated_profit_cny=(
                    conservative.estimated_profit_cny
                ),
                base_known_sell_count_sum=base.known_sell_count_sum,
                targeted_goods_count=(
                    item.targeted_plan.hard_request_count
                    if item.targeted_plan is not None
                    else None
                ),
                exclusion_reasons=(),
            )
        )
    return tuple(rows)


def _group_for_code(
    code: RecipeFirstRuntimeTerminalCode,
) -> RecipeFirstRuntimeTerminalGroup:
    if code is RecipeFirstRuntimeTerminalCode.SUCCESS_OPPORTUNITIES_FOUND:
        return RecipeFirstRuntimeTerminalGroup.SUCCESS
    if code in {
        RecipeFirstRuntimeTerminalCode.SUCCESS_NO_QUALIFYING_OPPORTUNITY,
        RecipeFirstRuntimeTerminalCode.NO_CONCRETE_SELECTION,
        RecipeFirstRuntimeTerminalCode.RISK_FILTER_REJECTED,
    }:
        return RecipeFirstRuntimeTerminalGroup.EXPECTED_NO_OPPORTUNITY
    if code in {
        RecipeFirstRuntimeTerminalCode.PRESCREEN_INCOMPLETE,
        RecipeFirstRuntimeTerminalCode.BUFF_ACQUISITION_INSUFFICIENT,
        RecipeFirstRuntimeTerminalCode.FINAL_VALUATION_INCOMPLETE,
        RecipeFirstRuntimeTerminalCode.VALUATION_REQUEST_BUDGET_BLOCKED,
        RecipeFirstRuntimeTerminalCode.EXTERNAL_PROVIDER_FAILURE,
    }:
        return RecipeFirstRuntimeTerminalGroup.INCOMPLETE_OR_PROVIDER
    return RecipeFirstRuntimeTerminalGroup.CONTRACT_OR_CONFIGURATION
