"""Phase 16G-R6 — Repaired bounded Recipe-First + SteamDT live validation.

The runner composes the existing Phase 16E family-constrained concrete search
and run-scoped valuation authorities. External providers may be injected for
zero-network tests; the production composition retains the frozen live HTTP
caps and uses no cache, retry, pagination, polling, or fallback.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, cast

import httpx

from app.clients.steamdt_client import (
    SteamDTClient,
    SteamDTClientConfig,
    SteamDTHttpClient,
)
from app.services.buff_community_identity_resolver import (
    BuffGoodsIdIdentityResolver,
)
from app.services.buff_intrinsic_flag_resolver import (
    BuffListingIntrinsicFlagResolver,
    CanonicalNameIntrinsicFlagResolver,
)
from app.services.family_constrained_concrete_search import (
    FamilyConstrainedRecipeSearchResult,
    FamilyConstrainedRecipeSelection,
    search_family_constrained_recipes,
)
from app.services.price_provider import PriceLookupResult, PriceQuote
from app.services.recipe_family import RecipeFamily, StatTrakMode
from app.services.recipe_family_geometry import (
    RecipeFamilyGeometry,
    compute_recipe_family_geometry,
)
from app.services.recipe_first_acquisition import (
    ExistingRecipeFirstAcquisitionPipeline,
    RecipeFirstAcquisitionPage,
)
from app.services.recipe_first_live_case import LiveValidationCase
from app.services.recipe_first_live_runner import (
    _BudgetedRawListingProvider,
    _BudgetTracker,
)
from app.services.recipe_first_steamdt_live_case import (
    RecipeFirstSteamDTCase,
    RecipeFirstSteamDTCaseError,
)
from app.services.recipe_solver import RecipeEnumerationConfig, RecipeSolverConfig
from app.services.scanner_valuation_session import RunScopedValuationSession
from app.services.steamdt_batch_prescreen import (
    SteamDTBatchPreScreenQuote,
    SteamDTBatchPreScreenRequest,
    SteamDTBatchPreScreenResolver,
    SteamDTBatchPreScreenResult,
)
from app.services.steamdt_market_data import get_steamdt_market_data
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.trade_up_input_enrichment import (
    TradeUpEnrichedInput,
    TradeUpInputMetadataResolver,
)
from app.services.tradeup_engine import TradeupResult
from app.services.valuation_service import ValuationConfig

__all__ = (
    "CLASSIFICATION_BLOCKED",
    "CLASSIFICATION_CONTRACT_FAILURE",
    "CLASSIFICATION_IDENTITY_FAILURE",
    "CLASSIFICATION_INCONCLUSIVE",
    "CLASSIFICATION_VALIDATED",
    "LIVE_STEAMDT_RESULT_SCHEMA_VERSION",
    "LiveSteamDTConcreteSearchDiagnostics",
    "LiveSteamDTPageResult",
    "LiveSteamDTPhase",
    "LiveSteamDTRequestState",
    "LiveSteamDTRunResult",
    "RecipeFirstSteamDTLiveRunner",
    "RecipeFirstSteamDTLiveRunnerConfig",
    "RUN_STATUS_DISPATCHED",
    "RUN_STATUS_FAILED",
)

LIVE_STEAMDT_RESULT_SCHEMA_VERSION: int = 2

RUN_STATUS_DISPATCHED: str = "dispatched"
RUN_STATUS_FAILED: str = "failed"
_RUN_STATUSES: frozenset[str] = frozenset(
    {RUN_STATUS_DISPATCHED, RUN_STATUS_FAILED}
)

CLASSIFICATION_VALIDATED: str = "validated"
CLASSIFICATION_INCONCLUSIVE: str = "inconclusive"
CLASSIFICATION_CONTRACT_FAILURE: str = "contract_failure"
CLASSIFICATION_BLOCKED: str = "blocked"
CLASSIFICATION_IDENTITY_FAILURE: str = "identity_failure"

_STRICT_BUFF_SOURCE: str = "steamdt:buff"
_PROBABILITY_TOLERANCE: float = 1e-12

_BatchResultProvider = Callable[
    [tuple[str, ...]], Awaitable[SteamDTBatchPreScreenResult]
]
_SinglePriceFetcher = Callable[[str], Awaitable[PriceQuote]]


class _RawBuffListingProvider(Protocol):
    async def get_listings(self, goods_id: str) -> list: ...


class _RawPayloadClient(Protocol):
    async def fetch_sell_order_payload(self, goods_id: str) -> bytes: ...


class _BudgetExceeded(RuntimeError):
    """One frozen Phase16G HTTP budget was exhausted."""


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveSteamDTPageResult:
    goods_id: str
    market_hash_name: str
    request_status: str
    listing_count: int
    candidate_accepted: int
    metadata_resolved: int
    family_compatible: int
    family_incompatible: int

    def __post_init__(self) -> None:
        if self.request_status not in _RUN_STATUSES:
            raise RecipeFirstSteamDTCaseError(
                f"invalid request_status: {self.request_status!r}"
            )
        counters = (
            self.listing_count,
            self.candidate_accepted,
            self.metadata_resolved,
            self.family_compatible,
            self.family_incompatible,
        )
        if any(type(value) is not int or value < 0 for value in counters):
            raise RecipeFirstSteamDTCaseError(
                "page counters must be non-negative integers"
            )


@dataclass(frozen=True, kw_only=True)
class LiveSteamDTPhase:
    name: str
    status: str
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class LiveSteamDTRequestState:
    steamdt_batch_attempted: int
    steamdt_batch_dispatched: int
    steamdt_single_attempted: int
    steamdt_single_dispatched: int
    buff_attempted: int
    buff_dispatched: int


@dataclass(frozen=True, kw_only=True)
class LiveSteamDTConcreteSearchDiagnostics:
    family_hash: str
    eligible_input_count: int
    retained_input_count: int
    states_explored: int
    raw_candidates_found: int
    unique_candidates_returned: int
    duplicates_suppressed: int
    candidate_limit_reached: bool
    exploration_limit_reached: bool


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveSteamDTRunResult:
    case_sha256: str
    repository_commit_oid: str
    family_hash: str
    family_key: str
    input_rarity: str
    stattrak_mode: str
    hard_request_count: int
    static_feasibility_status: str
    prescreen_names: tuple[str, ...]
    phases: tuple[LiveSteamDTPhase, ...]
    page_results: tuple[LiveSteamDTPageResult, ...]
    prescreen_quotes: tuple[SteamDTBatchPreScreenQuote, ...]
    prescreen_missing_names: tuple[str, ...]
    prescreen_failure_names: tuple[tuple[str, str], ...]
    family_compatible_enriched_inputs: int
    family_incompatible_enriched_inputs: int
    concrete_selection_count: int
    concrete_output_market_hash_names: tuple[str, ...]
    concrete_search_diagnostics: LiveSteamDTConcreteSearchDiagnostics | None
    concrete_tradeup_results: tuple[TradeupResult, ...]
    valued_tradeup_results: tuple[TradeupResult, ...]
    structural_fields_preserved: bool | None
    structural_mismatch_reason: str | None
    final_quotes: tuple[PriceQuote, ...]
    final_missing_names: tuple[str, ...]
    final_errors: tuple[str, ...]
    final_new_live_names: tuple[str, ...]
    request_state: LiveSteamDTRequestState
    classification: str
    schema_version: int
    buff_http_cap: int
    steamdt_batch_http_cap: int
    steamdt_final_single_http_cap: int
    steamdt_total_http_cap: int

    def __post_init__(self) -> None:
        if self.schema_version != LIVE_STEAMDT_RESULT_SCHEMA_VERSION:
            raise RecipeFirstSteamDTCaseError(
                f"schema_version must equal {LIVE_STEAMDT_RESULT_SCHEMA_VERSION}"
            )
        for cap in (
            self.buff_http_cap,
            self.steamdt_batch_http_cap,
            self.steamdt_final_single_http_cap,
            self.steamdt_total_http_cap,
        ):
            if type(cap) is not int or cap <= 0:
                raise RecipeFirstSteamDTCaseError(
                    "result HTTP caps must be positive integers"
                )
        if type(self.concrete_tradeup_results) is not tuple or any(
            type(row) is not TradeupResult
            for row in self.concrete_tradeup_results
        ):
            raise RecipeFirstSteamDTCaseError(
                "concrete_tradeup_results must contain exact TradeupResult values"
            )
        if type(self.valued_tradeup_results) is not tuple or any(
            type(row) is not TradeupResult for row in self.valued_tradeup_results
        ):
            raise RecipeFirstSteamDTCaseError(
                "valued_tradeup_results must contain exact TradeupResult values"
            )
        if self.structural_fields_preserved is not None and type(
            self.structural_fields_preserved
        ) is not bool:
            raise RecipeFirstSteamDTCaseError(
                "structural_fields_preserved must be bool or None"
            )


@dataclass(frozen=True, kw_only=True)
class RecipeFirstSteamDTLiveRunnerConfig:
    pacing_seconds: float = 2.0
    timeout_seconds: float = 10.0
    api_key: str | None = None
    steamdt_base_url: str = "https://open.steamdt.com"
    steamdt_timeout_seconds: float = 10.0


def _build_steamdt_http_client(
    *, config: RecipeFirstSteamDTLiveRunnerConfig
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=config.steamdt_base_url,
        timeout=config.steamdt_timeout_seconds,
        follow_redirects=False,
        trust_env=False,
        headers={
            "Accept": "application/json",
            "User-Agent": "cs2-tradeup-readonly-schema-smoke/1.0",
        },
    )


class RecipeFirstSteamDTLiveRunner:
    """Perform one bounded Phase16G live validation attempt.

    ``batch_result_provider``, ``buff_listing_provider``, and
    ``single_price_fetcher`` are external-seam injections for offline tests.
    Production execution leaves all three unset.
    """

    def __init__(
        self,
        *,
        case: RecipeFirstSteamDTCase,
        buff_identity_resolver: BuffGoodsIdIdentityResolver,
        metadata_resolver: TradeUpInputMetadataResolver,
        family: RecipeFamily,
        geometry: RecipeFamilyGeometry,
        finish_index: StructuralOutputFinishIndex,
        solver_config: RecipeSolverConfig,
        enumeration_config: RecipeEnumerationConfig,
        intrinsic_resolver: BuffListingIntrinsicFlagResolver | None = None,
        config: RecipeFirstSteamDTLiveRunnerConfig | None = None,
        buff_http_client: httpx.AsyncClient | None = None,
        batch_result_provider: _BatchResultProvider | None = None,
        buff_listing_provider: _RawBuffListingProvider | None = None,
        single_price_fetcher: _SinglePriceFetcher | None = None,
    ) -> None:
        _validate_runner_authorities(
            case=case,
            family=family,
            geometry=geometry,
            finish_index=finish_index,
            solver_config=solver_config,
            enumeration_config=enumeration_config,
        )
        if not hasattr(buff_identity_resolver, "resolve_goods_id"):
            raise RecipeFirstSteamDTCaseError(
                "buff_identity_resolver must expose resolve_goods_id"
            )
        if not hasattr(metadata_resolver, "resolve"):
            raise RecipeFirstSteamDTCaseError(
                "metadata_resolver must expose resolve"
            )
        if intrinsic_resolver is not None and not hasattr(
            intrinsic_resolver, "resolve"
        ):
            raise RecipeFirstSteamDTCaseError(
                "intrinsic_resolver must expose resolve"
            )
        if buff_listing_provider is not None and not hasattr(
            buff_listing_provider, "get_listings"
        ):
            raise RecipeFirstSteamDTCaseError(
                "buff_listing_provider must expose get_listings"
            )
        cfg = config or RecipeFirstSteamDTLiveRunnerConfig()
        if type(cfg.pacing_seconds) is not float or cfg.pacing_seconds < 0.0:
            raise RecipeFirstSteamDTCaseError(
                "pacing_seconds must be non-negative float"
            )
        if (
            type(cfg.timeout_seconds) is not float
            or cfg.timeout_seconds <= 0.0
            or type(cfg.steamdt_timeout_seconds) is not float
            or cfg.steamdt_timeout_seconds <= 0.0
        ):
            raise RecipeFirstSteamDTCaseError(
                "timeout values must be positive floats"
            )

        self.case = case
        self.family = family
        self.geometry = geometry
        self.finish_index = finish_index
        self.solver_config = solver_config
        self.enumeration_config = enumeration_config
        self.buff_identity_resolver = buff_identity_resolver
        self.metadata_resolver = metadata_resolver
        self.intrinsic_resolver = (
            intrinsic_resolver or CanonicalNameIntrinsicFlagResolver()
        )
        self.config = cfg
        self._owns_buff_http = buff_http_client is None
        self._buff_http_client = buff_http_client
        self._tracker = _BudgetTracker(budget=case.buff_case.hard_request_count)
        self._owns_steamdt_http = True
        self._steamdt_http_client: httpx.AsyncClient | None = None
        self._batch_result_provider = batch_result_provider
        self._buff_listing_provider = buff_listing_provider
        self._single_price_fetcher = single_price_fetcher
        self._steamdt_batch_attempted = 0
        self._steamdt_batch_dispatched = 0
        self._steamdt_single_attempted = 0
        self._steamdt_single_dispatched = 0
        self._steamdt_batch_dispatch_started = 0
        self._steamdt_single_dispatch_started = 0

    @property
    def request_state(self) -> LiveSteamDTRequestState:
        return LiveSteamDTRequestState(
            steamdt_batch_attempted=self._steamdt_batch_attempted,
            steamdt_batch_dispatched=self._steamdt_batch_dispatched,
            steamdt_single_attempted=self._steamdt_single_attempted,
            steamdt_single_dispatched=self._steamdt_single_dispatched,
            buff_attempted=self._tracker.attempted,
            buff_dispatched=self._tracker.dispatched,
        )

    async def aclose(self) -> None:
        if self._owns_buff_http and self._buff_http_client is not None:
            try:
                await self._buff_http_client.aclose()
            except (MemoryError, asyncio.CancelledError):
                raise
            except Exception:
                pass
        if self._owns_steamdt_http and self._steamdt_http_client is not None:
            try:
                await self._steamdt_http_client.aclose()
            except (MemoryError, asyncio.CancelledError):
                raise
            except Exception:
                pass

    async def run(
        self,
        *,
        live_validation_authorized: bool,
    ) -> LiveSteamDTRunResult:
        from app.services.recipe_first_live_case import (
            LIVE_CASE_SCHEMA_VERSION as BUFF_SCHEMA,
        )

        phases: list[LiveSteamDTPhase] = []
        page_results: tuple[LiveSteamDTPageResult, ...] = ()
        prescreen_quotes: tuple[SteamDTBatchPreScreenQuote, ...] = ()
        prescreen_missing: tuple[str, ...] = ()
        prescreen_failures: tuple[tuple[str, str], ...] = ()
        compatible = 0
        incompatible = 0
        concrete_selection_count = 0
        concrete_names: tuple[str, ...] = ()
        concrete_diagnostics: LiveSteamDTConcreteSearchDiagnostics | None = None
        concrete_results: tuple[TradeupResult, ...] = ()
        valued_results: tuple[TradeupResult, ...] = ()
        structural_preserved: bool | None = None
        structural_mismatch: str | None = None
        final_quotes: tuple[PriceQuote, ...] = ()
        final_missing: tuple[str, ...] = ()
        final_errors: tuple[str, ...] = ()
        final_new_live: tuple[str, ...] = ()

        def finish(classification: str) -> LiveSteamDTRunResult:
            return self._build_result(
                phases=tuple(phases),
                page_results=page_results,
                prescreen_quotes=prescreen_quotes,
                prescreen_missing=prescreen_missing,
                prescreen_failures=prescreen_failures,
                compatible=compatible,
                incompatible=incompatible,
                concrete_selection_count=concrete_selection_count,
                concrete_output_market_hash_names=concrete_names,
                concrete_search_diagnostics=concrete_diagnostics,
                concrete_tradeup_results=concrete_results,
                valued_tradeup_results=valued_results,
                structural_fields_preserved=structural_preserved,
                structural_mismatch_reason=structural_mismatch,
                final_quotes=final_quotes,
                final_missing=final_missing,
                final_errors=final_errors,
                final_new_live=final_new_live,
                classification=classification,
            )

        if self.case.buff_case.case_schema_version != BUFF_SCHEMA:
            phases.append(
                LiveSteamDTPhase(
                    name="preflight",
                    status="failed",
                    detail="buff_case schema mismatch",
                )
            )
            return finish(CLASSIFICATION_BLOCKED)
        if self.config.api_key is None:
            phases.append(
                LiveSteamDTPhase(
                    name="preflight",
                    status="failed",
                    detail="api_key missing",
                )
            )
            return finish(CLASSIFICATION_BLOCKED)
        if not live_validation_authorized:
            phases.append(
                LiveSteamDTPhase(
                    name="preflight",
                    status="failed",
                    detail="live not authorized",
                )
            )
            return finish(CLASSIFICATION_BLOCKED)

        # Stage A: strict SteamDT batch pre-screen.
        try:
            prescreen_result = await self._run_prescreen()
            _validate_prescreen_result(
                prescreen_result,
                expected_names=self.case.prescreen_market_hash_names,
            )
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception as exc:
            phases.append(
                LiveSteamDTPhase(
                    name="prescreen",
                    status="failed",
                    detail=type(exc).__name__,
                )
            )
            return finish(CLASSIFICATION_CONTRACT_FAILURE)
        prescreen_quotes = prescreen_result.quotes
        prescreen_missing = prescreen_result.missing_market_hash_names
        prescreen_failures = prescreen_result.terminal_selection_failures
        phases.append(
            LiveSteamDTPhase(
                name="prescreen",
                status=(
                    "ok"
                    if not prescreen_missing and not prescreen_failures
                    else "failed"
                ),
                detail=(
                    f"selected={len(prescreen_quotes)} "
                    f"missing={len(prescreen_missing)} "
                    f"failures={len(prescreen_failures)}"
                ),
            )
        )
        if prescreen_missing or prescreen_failures:
            return finish(CLASSIFICATION_INCONCLUSIVE)

        # Stage B: one normalized BUFF acquisition page.
        try:
            page_result, compatible_inputs, incompatible = (
                await self._acquire_buff_page()
            )
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception as exc:
            phases.append(
                LiveSteamDTPhase(
                    name="buff_page",
                    status="failed",
                    detail=type(exc).__name__,
                )
            )
            return finish(CLASSIFICATION_CONTRACT_FAILURE)
        page_results = (page_result,)
        compatible = len(compatible_inputs)
        phases.append(
            LiveSteamDTPhase(
                name="buff_page",
                status=page_result.request_status,
                detail=(
                    f"listings={page_result.listing_count} "
                    f"compatible={compatible} "
                    f"incompatible={incompatible}"
                ),
            )
        )
        if incompatible > 0 or page_result.request_status != RUN_STATUS_DISPATCHED:
            return finish(CLASSIFICATION_CONTRACT_FAILURE)
        if compatible < 10:
            return finish(CLASSIFICATION_INCONCLUSIVE)

        # Stage C: real bounded Phase16E family-constrained concrete search.
        try:
            search_result = search_family_constrained_recipes(
                self.family,
                geometry=self.geometry,
                finish_index=self.finish_index,
                enriched_inputs=compatible_inputs,
                solver_config=self.solver_config,
                enumeration_config=self.enumeration_config,
            )
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception as exc:
            phases.append(
                LiveSteamDTPhase(
                    name="concrete_search",
                    status="failed",
                    detail=type(exc).__name__,
                )
            )
            return finish(CLASSIFICATION_CONTRACT_FAILURE)
        concrete_diagnostics = _redact_search_diagnostics(search_result)
        concrete_selection_count = len(search_result.selections)
        phases.append(
            LiveSteamDTPhase(
                name="concrete_search",
                status="ok" if concrete_selection_count == 1 else "failed",
                detail=(
                    f"selections={concrete_selection_count} "
                    f"states_explored={concrete_diagnostics.states_explored} "
                    "unique_candidates_returned="
                    f"{concrete_diagnostics.unique_candidates_returned}"
                ),
            )
        )
        if concrete_selection_count == 0:
            return finish(CLASSIFICATION_INCONCLUSIVE)
        if concrete_selection_count > 1:
            return finish(CLASSIFICATION_CONTRACT_FAILURE)

        selection = search_result.selections[0]
        concrete_names = selection.concrete_outcomes.output_market_hash_names
        concrete_results = selection.concrete_outcomes.tradeup_results
        if not _valid_concrete_selection(
            selection=selection,
            expected_family_hash=self.family.family_hash,
            concrete_names=concrete_names,
            concrete_results=concrete_results,
        ):
            return finish(CLASSIFICATION_CONTRACT_FAILURE)
        successful_prescreen_names = frozenset(
            quote.market_hash_name for quote in prescreen_quotes
        )
        if not set(concrete_names).issubset(successful_prescreen_names):
            return finish(CLASSIFICATION_CONTRACT_FAILURE)

        # Stage D: exact final valuation of the real concrete outputs.
        try:
            lookup, valued_results, final_new_live = (
                await self._run_final_valuation(
                    selection=selection,
                    concrete_names=concrete_names,
                )
            )
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception as exc:
            phases.append(
                LiveSteamDTPhase(
                    name="final_valuation",
                    status="failed",
                    detail=type(exc).__name__,
                )
            )
            final_errors = (type(exc).__name__,)
            return finish(CLASSIFICATION_CONTRACT_FAILURE)

        final_quotes = tuple(
            lookup.quotes[name]
            for name in concrete_names
            if name in lookup.quotes
        )
        final_missing = tuple(lookup.missing)
        final_errors = tuple(lookup.errors)
        structural_preserved, structural_mismatch = _compare_structural_fields(
            concrete_results,
            valued_results,
        )
        phases.append(
            LiveSteamDTPhase(
                name="final_valuation",
                status=(
                    "ok" if not final_missing and not final_errors else "failed"
                ),
                detail=(
                    f"new_live={len(final_new_live)} "
                    f"missing={len(final_missing)} "
                    f"errors={len(final_errors)}"
                ),
            )
        )

        if not structural_preserved:
            return finish(CLASSIFICATION_CONTRACT_FAILURE)
        if not _caps_respected(self.request_state, self.case):
            return finish(CLASSIFICATION_CONTRACT_FAILURE)
        if final_missing or final_errors:
            return finish(CLASSIFICATION_INCONCLUSIVE)
        if not self._validated_contract_holds(
            prescreen_quotes=prescreen_quotes,
            page_result=page_result,
            concrete_names=concrete_names,
            final_new_live=final_new_live,
            final_quotes=final_quotes,
        ):
            return finish(CLASSIFICATION_CONTRACT_FAILURE)
        return finish(CLASSIFICATION_VALIDATED)

    async def _run_prescreen(self) -> SteamDTBatchPreScreenResult:
        if self._steamdt_batch_attempted >= self.case.steamdt_batch_http_cap:
            raise _BudgetExceeded("steamdt batch cap reached")
        self._steamdt_batch_attempted += 1
        if self._batch_result_provider is not None:
            self._steamdt_batch_dispatch_started += 1
            result = await self._batch_result_provider(
                self.case.prescreen_market_hash_names
            )
            self._steamdt_batch_dispatched += 1
            return result

        if self._steamdt_http_client is None:
            self._steamdt_http_client = _build_steamdt_http_client(
                config=self.config
            )
        client = SteamDTHttpClient(
            config=SteamDTClientConfig(
                base_url=self.config.steamdt_base_url,
                api_key=self.config.api_key,
                max_retries=0,
                dry_run=False,
            ),
            http_client=self._steamdt_http_client,
        )
        resolver = SteamDTBatchPreScreenResolver(
            client=_BudgetedSteamDTBatchTransport(
                client=cast(SteamDTClient, client),
                tracker=self,
            )
        )
        result = await resolver.prescreen(
            SteamDTBatchPreScreenRequest(
                market_hash_names=list(self.case.prescreen_market_hash_names)
            )
        )
        self._steamdt_batch_dispatched += 1
        return result

    async def _acquire_buff_page(
        self,
    ) -> tuple[
        LiveSteamDTPageResult,
        tuple[TradeUpEnrichedInput, ...],
        int,
    ]:
        if self._buff_listing_provider is None:
            if self._buff_http_client is None:
                self._buff_http_client = httpx.AsyncClient(
                    base_url="https://buff.163.com",
                    timeout=self.config.timeout_seconds,
                    follow_redirects=False,
                    trust_env=False,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "cs2-tradeup-readonly-schema-smoke/1.0",
                    },
                )
            raw_provider: _RawBuffListingProvider = _BudgetedRawListingProvider(
                http_client=self._buff_http_client,
                tracker=self._tracker,
            )
        else:
            raw_provider = _BudgetedInjectedListingProvider(
                delegate=self._buff_listing_provider,
                tracker=self._tracker,
            )
        pipeline = ExistingRecipeFirstAcquisitionPipeline(
            listing_provider=raw_provider,
            identity_resolver=self.buff_identity_resolver,
            metadata_resolver=self.metadata_resolver,
            intrinsic_resolver=self.intrinsic_resolver,
        )
        plan_item = self.case.buff_case.plan_items[0]
        page = await pipeline.acquire_page(
            goods_id=plan_item.goods_id,
            market_hash_name=plan_item.market_hash_name,
        )
        compatible_inputs, incompatible = _partition_family_inputs(
            page,
            plan_item=plan_item,
            case=self.case.buff_case,
        )
        counts = page.counts
        return (
            LiveSteamDTPageResult(
                goods_id=plan_item.goods_id,
                market_hash_name=plan_item.market_hash_name,
                request_status=RUN_STATUS_DISPATCHED,
                listing_count=counts.listings_received,
                candidate_accepted=counts.candidate_accepted,
                metadata_resolved=counts.metadata_resolved,
                family_compatible=len(compatible_inputs),
                family_incompatible=incompatible,
            ),
            compatible_inputs,
            incompatible,
        )

    async def _run_final_valuation(
        self,
        *,
        selection: FamilyConstrainedRecipeSelection,
        concrete_names: tuple[str, ...],
    ) -> tuple[PriceLookupResult, tuple[TradeupResult, ...], tuple[str, ...]]:
        single = self._single_price_fetcher
        if single is None:
            if self._steamdt_http_client is None:
                self._steamdt_http_client = _build_steamdt_http_client(
                    config=self.config
                )
            client = SteamDTHttpClient(
                config=SteamDTClientConfig(
                    base_url=self.config.steamdt_base_url,
                    api_key=self.config.api_key,
                    max_retries=0,
                    dry_run=False,
                ),
                http_client=self._steamdt_http_client,
            )

            async def _live_single(name: str) -> PriceQuote:
                market_data = await get_steamdt_market_data(
                    client=client,
                    market_hash_name=name,
                )
                from app.services.steamdt_buff_price_policy import (
                    select_buff_output_price,
                )

                selected = select_buff_output_price(market_data=market_data)
                return PriceQuote(
                    market_hash_name=selected.market_hash_name,
                    price_cny=selected.sell_price_cny,
                    source=_STRICT_BUFF_SOURCE,
                    raw=None,
                )

            single = _live_single

        provider = _LiveSinglePriceProvider(
            single=single,
            tracker=self,
            cap=self.case.steamdt_final_single_http_cap,
        )
        session = RunScopedValuationSession(
            price_provider=provider,
            valuation_config=ValuationConfig(require_all_prices=True),
            session_id=1,
        )
        plan = await session.prepare_output_prices(concrete_names)
        if (
            plan.requested_names != concrete_names
            or plan.new_live_names != concrete_names
        ):
            raise RecipeFirstSteamDTCaseError(
                "prepared valuation plan does not match concrete output names"
            )
        session_result = await session.resolve_prepared(
            plan,
            list(selection.concrete_outcomes.tradeup_results),
        )
        valuation = session_result.valuation_result
        return (
            valuation.price_lookup_result,
            tuple(valuation.tradeup_results),
            tuple(plan.new_live_names),
        )

    def _validated_contract_holds(
        self,
        *,
        prescreen_quotes: tuple[SteamDTBatchPreScreenQuote, ...],
        page_result: LiveSteamDTPageResult,
        concrete_names: tuple[str, ...],
        final_new_live: tuple[str, ...],
        final_quotes: tuple[PriceQuote, ...],
    ) -> bool:
        prescreen_quote_names = tuple(
            quote.market_hash_name for quote in prescreen_quotes
        )
        final_quote_names = tuple(quote.market_hash_name for quote in final_quotes)
        state = self.request_state
        return (
            prescreen_quote_names == self.case.prescreen_market_hash_names
            and len(set(prescreen_quote_names)) == len(prescreen_quote_names)
            and page_result.request_status == RUN_STATUS_DISPATCHED
            and state.steamdt_batch_attempted == 1
            and state.steamdt_batch_dispatched == 1
            and state.buff_attempted == 1
            and state.buff_dispatched == 1
            and final_new_live == concrete_names
            and final_quote_names == concrete_names
            and all(quote.source == _STRICT_BUFF_SOURCE for quote in final_quotes)
            and state.steamdt_single_attempted == len(concrete_names)
            and state.steamdt_single_dispatched == len(concrete_names)
            and _caps_respected(state, self.case)
        )

    def _build_result(
        self,
        *,
        phases: tuple[LiveSteamDTPhase, ...],
        page_results: tuple[LiveSteamDTPageResult, ...],
        prescreen_quotes: tuple[SteamDTBatchPreScreenQuote, ...],
        prescreen_missing: tuple[str, ...],
        prescreen_failures: tuple[tuple[str, str], ...],
        compatible: int,
        incompatible: int,
        concrete_selection_count: int,
        concrete_output_market_hash_names: tuple[str, ...],
        concrete_search_diagnostics: LiveSteamDTConcreteSearchDiagnostics | None,
        concrete_tradeup_results: tuple[TradeupResult, ...],
        valued_tradeup_results: tuple[TradeupResult, ...],
        structural_fields_preserved: bool | None,
        structural_mismatch_reason: str | None,
        final_quotes: tuple[PriceQuote, ...],
        final_missing: tuple[str, ...],
        final_errors: tuple[str, ...],
        final_new_live: tuple[str, ...],
        classification: str,
    ) -> LiveSteamDTRunResult:
        from app.services.recipe_first_steamdt_live_case import (
            hash_recipe_first_steamdt_case,
        )

        return LiveSteamDTRunResult(
            case_sha256=hash_recipe_first_steamdt_case(self.case),
            repository_commit_oid=self.case.repository_commit_oid,
            family_hash=self.case.buff_case.family_hash,
            family_key=self.case.buff_case.family_key,
            input_rarity=self.case.buff_case.input_rarity,
            stattrak_mode=self.case.buff_case.stattrak_mode.value,
            hard_request_count=self.case.buff_case.hard_request_count,
            static_feasibility_status="feasible",
            prescreen_names=self.case.prescreen_market_hash_names,
            phases=phases,
            page_results=page_results,
            prescreen_quotes=prescreen_quotes,
            prescreen_missing_names=prescreen_missing,
            prescreen_failure_names=prescreen_failures,
            family_compatible_enriched_inputs=compatible,
            family_incompatible_enriched_inputs=incompatible,
            concrete_selection_count=concrete_selection_count,
            concrete_output_market_hash_names=concrete_output_market_hash_names,
            concrete_search_diagnostics=concrete_search_diagnostics,
            concrete_tradeup_results=concrete_tradeup_results,
            valued_tradeup_results=valued_tradeup_results,
            structural_fields_preserved=structural_fields_preserved,
            structural_mismatch_reason=structural_mismatch_reason,
            final_quotes=final_quotes,
            final_missing_names=final_missing,
            final_errors=final_errors,
            final_new_live_names=final_new_live,
            request_state=self.request_state,
            classification=classification,
            schema_version=LIVE_STEAMDT_RESULT_SCHEMA_VERSION,
            buff_http_cap=self.case.buff_http_cap,
            steamdt_batch_http_cap=self.case.steamdt_batch_http_cap,
            steamdt_final_single_http_cap=self.case.steamdt_final_single_http_cap,
            steamdt_total_http_cap=self.case.steamdt_total_http_cap,
        )


@dataclass
class _BudgetedSteamDTBatchTransport:
    client: Any
    tracker: RecipeFirstSteamDTLiveRunner

    async def get_price_batch_with_selection(
        self,
        market_hash_names: list[str],
        *,
        selection_config: object = None,
        avg_prices_by_name: dict[str, Decimal] | None = None,
    ) -> Any:
        if (
            self.tracker._steamdt_batch_dispatch_started
            >= self.tracker.case.steamdt_batch_http_cap
        ):
            raise _BudgetExceeded("steamdt batch cap reached")
        self.tracker._steamdt_batch_dispatch_started += 1
        return await self.client.get_price_batch_with_selection(
            market_hash_names,
            selection_config=selection_config,
            avg_prices_by_name=avg_prices_by_name,
        )


@dataclass
class _BudgetedInjectedListingProvider:
    delegate: _RawBuffListingProvider
    tracker: _BudgetTracker

    async def get_listings(self, goods_id: str) -> list:
        if not self.tracker.begin_attempt():
            raise _BudgetExceeded("BUFF cap reached")
        self.tracker.record_dispatch()
        return await self.delegate.get_listings(goods_id)


@dataclass
class _BudgetedInjectedPayloadClient:
    delegate: _RawPayloadClient
    tracker: _BudgetTracker

    async def fetch_sell_order_payload(self, goods_id: str) -> bytes:
        if not self.tracker.begin_attempt():
            raise _BudgetExceeded("BUFF cap reached")
        self.tracker.record_dispatch()
        return await self.delegate.fetch_sell_order_payload(goods_id)


class _LiveSinglePriceProvider:
    """Bounded exact-name provider with normalized failure shape."""

    def __init__(
        self,
        *,
        single: _SinglePriceFetcher,
        tracker: RecipeFirstSteamDTLiveRunner,
        cap: int,
    ) -> None:
        if type(cap) is not int or cap <= 0:
            raise RecipeFirstSteamDTCaseError("single cap must be positive int")
        self._single = single
        self._tracker = tracker
        self._cap = cap

    async def get_price(self, market_hash_name: str) -> PriceQuote:
        lookup = await self.get_prices([market_hash_name])
        quote = lookup.quotes.get(market_hash_name)
        if quote is None:
            raise RuntimeError("single price unavailable")
        return quote

    async def get_prices(self, names: list[str]) -> PriceLookupResult:
        quotes: dict[str, PriceQuote] = {}
        missing: list[str] = []
        errors: list[str] = []
        for index, name in enumerate(names):
            if self._tracker._steamdt_single_attempted >= self._cap:
                remaining = names[index:]
                missing.extend(remaining)
                errors.extend(
                    f"STEAMDT_SINGLE_FAILED:{remaining_index}:CAP_EXCEEDED"
                    for remaining_index, _ in enumerate(remaining, start=index)
                )
                break
            if self._tracker._steamdt_single_dispatch_started >= self._cap:
                remaining = names[index:]
                missing.extend(remaining)
                errors.extend(
                    f"STEAMDT_SINGLE_FAILED:{remaining_index}:CAP_EXCEEDED"
                    for remaining_index, _ in enumerate(remaining, start=index)
                )
                break
            self._tracker._steamdt_single_attempted += 1
            self._tracker._steamdt_single_dispatch_started += 1
            try:
                quote = await self._single(name)
            except (MemoryError, asyncio.CancelledError):
                raise
            except Exception:
                missing.append(name)
                errors.append(f"STEAMDT_SINGLE_FAILED:{index}")
                continue
            if quote.market_hash_name != name:
                missing.append(name)
                errors.append(f"STEAMDT_SINGLE_IDENTITY_MISMATCH:{index}")
                continue
            quotes[name] = quote
            self._tracker._steamdt_single_dispatched += 1
        return PriceLookupResult(quotes=quotes, missing=missing, errors=errors)


def _validate_runner_authorities(
    *,
    case: object,
    family: object,
    geometry: object,
    finish_index: object,
    solver_config: object,
    enumeration_config: object,
) -> None:
    if type(case) is not RecipeFirstSteamDTCase:
        raise RecipeFirstSteamDTCaseError("case must be RecipeFirstSteamDTCase")
    if type(family) is not RecipeFamily:
        raise RecipeFirstSteamDTCaseError("family must be RecipeFamily")
    if type(geometry) is not RecipeFamilyGeometry:
        raise RecipeFirstSteamDTCaseError("geometry must be RecipeFamilyGeometry")
    if type(finish_index) is not StructuralOutputFinishIndex:
        raise RecipeFirstSteamDTCaseError(
            "finish_index must be StructuralOutputFinishIndex"
        )
    if type(solver_config) is not RecipeSolverConfig:
        raise RecipeFirstSteamDTCaseError(
            "solver_config must be RecipeSolverConfig"
        )
    if type(enumeration_config) is not RecipeEnumerationConfig:
        raise RecipeFirstSteamDTCaseError(
            "enumeration_config must be RecipeEnumerationConfig"
        )
    if (
        family.family_hash != case.buff_case.family_hash
        or family.family_key != case.buff_case.family_key
    ):
        raise RecipeFirstSteamDTCaseError(
            "reconstructed family identity does not match frozen case"
        )
    if family.family_hash != geometry.family_hash:
        raise RecipeFirstSteamDTCaseError(
            "family and geometry hashes must match"
        )
    expected_geometry = compute_recipe_family_geometry(
        family,
        finish_index=finish_index,
    )
    if geometry != expected_geometry:
        raise RecipeFirstSteamDTCaseError(
            "geometry must exactly match family and finish_index"
        )
    if solver_config.input_rarity != family.input_rarity:
        raise RecipeFirstSteamDTCaseError(
            "solver input rarity must match family"
        )
    expected_stattrak = family.stattrak_mode is StatTrakMode.STATTRAK
    if solver_config.target_stattrak is not expected_stattrak:
        raise RecipeFirstSteamDTCaseError(
            "solver StatTrak target must exactly match family"
        )
    if solver_config.target_souvenir is not None:
        raise RecipeFirstSteamDTCaseError(
            "solver Souvenir target must be None"
        )
    if enumeration_config.max_recipe_candidates_returned != 1:
        raise RecipeFirstSteamDTCaseError(
            "Phase16G candidate-return bound must equal 1"
        )
    if enumeration_config.max_candidate_states_explored != 256:
        raise RecipeFirstSteamDTCaseError(
            "Phase16G state-exploration bound must equal 256"
        )


def _partition_family_inputs(
    page: RecipeFirstAcquisitionPage,
    *,
    plan_item: Any,
    case: LiveValidationCase,
) -> tuple[tuple[TradeUpEnrichedInput, ...], int]:
    if (
        page.goods_id != plan_item.goods_id
        or page.market_hash_name != plan_item.market_hash_name
        or len(page.enriched_inputs) != len(page.provenance)
    ):
        raise RecipeFirstSteamDTCaseError(
            "acquisition page does not match frozen plan"
        )
    expected_stattrak = case.stattrak_mode is StatTrakMode.STATTRAK
    represented = {name for name, _ in case.collection_counts}
    compatible: list[TradeUpEnrichedInput] = []
    incompatible = 0
    seen_keys: set[tuple[str, str, str]] = set()
    seen_listing_ids: set[str] = set()

    for enriched, provenance in zip(
        page.enriched_inputs,
        page.provenance,
        strict=True,
    ):
        candidate = enriched.candidate
        item = enriched.input_item
        key = (candidate.source, candidate.goods_id, candidate.listing_id)
        duplicate = key in seen_keys or candidate.listing_id in seen_listing_ids
        seen_keys.add(key)
        seen_listing_ids.add(candidate.listing_id)
        matches = (
            not duplicate
            and candidate.goods_id == plan_item.goods_id
            and candidate.market_hash_name == plan_item.market_hash_name
            and item.market_hash_name == plan_item.market_hash_name
            and item.collection_name == plan_item.collection_name
            and item.collection_name in represented
            and item.rarity == case.input_rarity
            and item.stattrak is expected_stattrak
            and candidate.stattrak is expected_stattrak
            and item.stattrak is candidate.stattrak
            and item.souvenir is candidate.souvenir
            and provenance.source == candidate.source
            and provenance.goods_id == candidate.goods_id
            and provenance.listing_id == candidate.listing_id
            and provenance.asset_id == candidate.asset_id
            and provenance.market_hash_name == candidate.market_hash_name
            and provenance.price_cny == candidate.price_cny
            and provenance.paintwear == candidate.paintwear
            and provenance.stattrak is candidate.stattrak
            and provenance.souvenir is candidate.souvenir
        )
        if matches:
            compatible.append(enriched)
        else:
            incompatible += 1
    return tuple(compatible), incompatible


def _validate_prescreen_result(
    result: object,
    *,
    expected_names: tuple[str, ...],
) -> None:
    if type(result) is not SteamDTBatchPreScreenResult:
        raise RecipeFirstSteamDTCaseError(
            "prescreen returned an invalid result type"
        )
    if result.requested_market_hash_names != expected_names:
        raise RecipeFirstSteamDTCaseError(
            "prescreen requested names do not match the frozen case"
        )
    quote_names = tuple(quote.market_hash_name for quote in result.quotes)
    missing_names = result.missing_market_hash_names
    failure_names = tuple(name for name, _reason in result.terminal_selection_failures)
    expected_set = set(expected_names)
    if (
        len(set(quote_names)) != len(quote_names)
        or len(set(missing_names)) != len(missing_names)
        or len(set(failure_names)) != len(failure_names)
        or not set(quote_names).issubset(expected_set)
        or not set(missing_names).issubset(expected_set)
        or not set(failure_names).issubset(expected_set)
        or set(quote_names) & set(missing_names)
        or set(quote_names) & set(failure_names)
    ):
        raise RecipeFirstSteamDTCaseError(
            "prescreen result identity partition is invalid"
        )


def _redact_search_diagnostics(
    result: FamilyConstrainedRecipeSearchResult,
) -> LiveSteamDTConcreteSearchDiagnostics:
    diagnostics = result.diagnostics
    return LiveSteamDTConcreteSearchDiagnostics(
        family_hash=diagnostics.family_hash,
        eligible_input_count=diagnostics.eligible_input_count,
        retained_input_count=diagnostics.retained_input_count,
        states_explored=diagnostics.states_explored,
        raw_candidates_found=diagnostics.raw_candidates_found,
        unique_candidates_returned=diagnostics.unique_candidates_returned,
        duplicates_suppressed=diagnostics.duplicates_suppressed,
        candidate_limit_reached=diagnostics.candidate_limit_reached,
        exploration_limit_reached=diagnostics.exploration_limit_reached,
    )


def _valid_concrete_selection(
    *,
    selection: FamilyConstrainedRecipeSelection,
    expected_family_hash: str,
    concrete_names: tuple[str, ...],
    concrete_results: tuple[TradeupResult, ...],
) -> bool:
    return (
        selection.family_hash == expected_family_hash
        and selection.concrete_outcomes.family_hash == expected_family_hash
        and 1 <= len(concrete_names) <= 2
        and len(set(concrete_names)) == len(concrete_names)
        and concrete_names
        == tuple(row.output_market_hash_name for row in concrete_results)
        and math.isclose(
            sum(row.probability for row in concrete_results),
            1.0,
            rel_tol=0.0,
            abs_tol=_PROBABILITY_TOLERANCE,
        )
    )


def _compare_structural_fields(
    before: tuple[TradeupResult, ...],
    after: tuple[TradeupResult, ...],
) -> tuple[bool, str | None]:
    if len(before) != len(after):
        return False, "output_count_mismatch"
    for index, (pre, post) in enumerate(zip(before, after, strict=True)):
        if pre.output_market_hash_name != post.output_market_hash_name:
            return False, f"output_name_mismatch:{index}"
        if pre.probability != post.probability:
            return False, f"probability_mismatch:{index}"
        if pre.output_float != post.output_float:
            return False, f"output_float_mismatch:{index}"
        if pre.output_wear != post.output_wear:
            return False, f"output_wear_mismatch:{index}"
    return True, None


def _caps_respected(
    state: LiveSteamDTRequestState,
    case: RecipeFirstSteamDTCase,
) -> bool:
    return (
        state.buff_attempted <= case.buff_http_cap
        and state.buff_dispatched <= case.buff_http_cap
        and state.steamdt_batch_attempted <= case.steamdt_batch_http_cap
        and state.steamdt_batch_dispatched <= case.steamdt_batch_http_cap
        and state.steamdt_single_attempted
        <= case.steamdt_final_single_http_cap
        and state.steamdt_single_dispatched
        <= case.steamdt_final_single_http_cap
        and state.steamdt_batch_dispatched + state.steamdt_single_dispatched
        <= case.steamdt_total_http_cap
    )
