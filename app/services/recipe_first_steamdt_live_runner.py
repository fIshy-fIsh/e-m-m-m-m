"""Phase 16G — Bounded Recipe-First + SteamDT live validation runner.

The runner composes the corrected Phase 16F-R2 BUFF acquisition
seam with the existing Phase16C strict SteamDT BUFF batch
pre-screen and the existing single-name strict BUFF final
valuation through :class:`RunScopedValuationSession`.

Strict guarantees:

- exactly one SteamDT batch pre-screen HTTP request
- exactly one BUFF anonymous page-1/default-sort GET
- at most two SteamDT strict single-name final HTTP requests
- at most three total SteamDT HTTP requests
- ``max_retries=0`` on the shared SteamDT HTTP client
- no retry / polling / pagination
- no fallback family
- no Discord / Redis / Postgres / scheduler
- pre-screen quotes never seed final session memo / cache
- final valuation preserves structural fields
- result excludes raw payload, API key, cookies, secrets
- zero behavior diff in existing BUFF client, BuffListingProvider,
  recipe_first_acquisition, recipe_first_scanner_orchestrator,
  SteamDT transport, family search, and final valuation paths
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from typing import cast as _cast

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
from app.services.price_provider import PriceLookupResult, PriceQuote
from app.services.recipe_first_acquisition import (
    ExistingRecipeFirstAcquisitionPipeline,
    RecipeFirstAcquisitionPage,
)
from app.services.recipe_first_live_case import (
    LiveValidationCase,
)
from app.services.recipe_first_live_runner import (
    _BudgetedRawListingProvider,
    _BudgetTracker,
)
from app.services.recipe_first_steamdt_live_case import (
    LIVE_STEAMDT_CASE_SCHEMA_VERSION,
    RecipeFirstSteamDTCase,
    RecipeFirstSteamDTCaseError,
)
from app.services.scanner_valuation_session import (
    RunScopedValuationSession,
)
from app.services.steamdt_batch_prescreen import (
    SteamDTBatchPreScreenQuote,
    SteamDTBatchPreScreenRequest,
    SteamDTBatchPreScreenResolver,
    SteamDTBatchPreScreenResult,
)
from app.services.steamdt_market_data import get_steamdt_market_data
from app.services.trade_up_input_enrichment import TradeUpInputMetadataResolver

__all__ = (
    "CLASSIFICATION_BLOCKED",
    "CLASSIFICATION_CONTRACT_FAILURE",
    "CLASSIFICATION_IDENTITY_FAILURE",
    "CLASSIFICATION_INCONCLUSIVE",
    "CLASSIFICATION_VALIDATED",
    "LiveSteamDTPageResult",
    "LiveSteamDTPhase",
    "LiveSteamDTRequestState",
    "LiveSteamDTRunResult",
    "RecipeFirstSteamDTLiveRunner",
    "RecipeFirstSteamDTLiveRunnerConfig",
    "RUN_STATUS_DISPATCHED",
    "RUN_STATUS_FAILED",
)

RUN_STATUS_DISPATCHED: str = "dispatched"
RUN_STATUS_FAILED: str = "failed"
_RUN_STATUSES: frozenset[str] = frozenset({RUN_STATUS_DISPATCHED, RUN_STATUS_FAILED})

CLASSIFICATION_VALIDATED: str = "validated"
CLASSIFICATION_INCONCLUSIVE: str = "inconclusive"
CLASSIFICATION_CONTRACT_FAILURE: str = "contract_failure"
CLASSIFICATION_BLOCKED: str = "blocked"
CLASSIFICATION_IDENTITY_FAILURE: str = "identity_failure"


class _BudgetExceeded(RuntimeError):
    pass


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
    final_quotes: tuple[PriceQuote, ...]
    final_missing_names: tuple[str, ...]
    final_errors: tuple[str, ...]
    final_new_live_names: tuple[str, ...]
    request_state: LiveSteamDTRequestState
    classification: str
    schema_version: int


@dataclass(frozen=True, kw_only=True)
class RecipeFirstSteamDTLiveRunnerConfig:
    pacing_seconds: float = 2.0
    timeout_seconds: float = 10.0
    api_key: str | None = None
    steamdt_base_url: str = "https://open.steamdt.com"
    steamdt_timeout_seconds: float = 10.0


_AsyncClock = Callable[[float], Awaitable[None]]


async def _asyncio_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


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
    """Performs one bounded live Recipe-First + SteamDT attempt."""

    def __init__(
        self,
        *,
        case: RecipeFirstSteamDTCase,
        buff_identity_resolver: BuffGoodsIdIdentityResolver,
        metadata_resolver: TradeUpInputMetadataResolver,
        intrinsic_resolver: BuffListingIntrinsicFlagResolver | None = None,
        config: RecipeFirstSteamDTLiveRunnerConfig | None = None,
        buff_http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if type(case) is not RecipeFirstSteamDTCase:
            raise RecipeFirstSteamDTCaseError(
                "case must be RecipeFirstSteamDTCase"
            )
        cfg = config or RecipeFirstSteamDTLiveRunnerConfig()
        if (
            type(cfg.pacing_seconds) is not float
            or cfg.pacing_seconds < 0.0
        ):
            raise RecipeFirstSteamDTCaseError(
                "pacing_seconds must be non-negative float"
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
        self.case = case
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
        self._steamdt_batch_attempted = 0
        self._steamdt_batch_dispatched = 0
        self._steamdt_single_attempted = 0
        self._steamdt_single_dispatched = 0
        self._buff_attempted = 0
        self._buff_dispatched = 0

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
        buff_provider_factory: Callable[
            [httpx.AsyncClient, _BudgetTracker],
            object,
        ] | None = None,
    ) -> LiveSteamDTRunResult:
        from app.services.recipe_first_live_case import (
            LIVE_CASE_SCHEMA_VERSION as BUFF_SCHEMA,
        )

        phases: list[LiveSteamDTPhase] = []
        prescreen_quotes: tuple[SteamDTBatchPreScreenQuote, ...] = ()
        prescreen_missing: tuple[str, ...] = ()
        prescreen_failures: tuple[tuple[str, str], ...] = ()
        page_results: tuple[LiveSteamDTPageResult, ...] = ()
        compatible = 0
        incompatible = 0
        final_quotes: tuple[PriceQuote, ...] = ()
        final_missing: tuple[str, ...] = ()
        final_errors: tuple[str, ...] = ()
        final_new_live: tuple[str, ...] = ()
        classification = CLASSIFICATION_BLOCKED

        buff_case = self.case.buff_case
        if buff_case.case_schema_version != BUFF_SCHEMA:
            return self._build_result(
                phases=(
                    LiveSteamDTPhase(
                        name="preflight",
                        status="failed",
                        detail="buff_case schema mismatch",
                    ),
                ),
                page_results=(),
                prescreen_quotes=(),
                prescreen_missing=(),
                prescreen_failures=(),
                compatible=0,
                incompatible=0,
                final_quotes=(),
                final_missing=(),
                final_errors=(),
                final_new_live=(),
                classification=CLASSIFICATION_BLOCKED,
            )

        if self.config.api_key is None:
            return self._build_result(
                phases=(
                    LiveSteamDTPhase(
                        name="preflight",
                        status="failed",
                        detail="api_key missing",
                    ),
                ),
                page_results=(),
                prescreen_quotes=(),
                prescreen_missing=(),
                prescreen_failures=(),
                compatible=0,
                incompatible=0,
                final_quotes=(),
                final_missing=(),
                final_errors=(),
                final_new_live=(),
                classification=CLASSIFICATION_BLOCKED,
            )

        if not live_validation_authorized:
            return self._build_result(
                phases=(
                    LiveSteamDTPhase(
                        name="preflight",
                        status="failed",
                        detail="live not authorized",
                    ),
                ),
                page_results=(),
                prescreen_quotes=(),
                prescreen_missing=(),
                prescreen_failures=(),
                compatible=0,
                incompatible=0,
                final_quotes=(),
                final_missing=(),
                final_errors=(),
                final_new_live=(),
                classification=CLASSIFICATION_BLOCKED,
            )

        # ---- SteamDT strict batch pre-screen ----
        try:
            prescreen_result = await self._run_prescreen()
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
            return self._build_result(
                phases=tuple(phases),
                page_results=(),
                prescreen_quotes=(),
                prescreen_missing=(),
                prescreen_failures=(),
                compatible=0,
                incompatible=0,
                final_quotes=(),
                final_missing=(),
                final_errors=(),
                final_new_live=(),
                classification=CLASSIFICATION_CONTRACT_FAILURE,
            )

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
            return self._build_result(
                phases=tuple(phases),
                page_results=(),
                prescreen_quotes=prescreen_quotes,
                prescreen_missing=prescreen_missing,
                prescreen_failures=prescreen_failures,
                compatible=0,
                incompatible=0,
                final_quotes=(),
                final_missing=(),
                final_errors=(),
                final_new_live=(),
                classification=CLASSIFICATION_INCONCLUSIVE,
            )

        # ---- BUFF live page ----
        try:
            page_result, compatible, incompatible = await self._acquire_buff_page()
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
            return self._build_result(
                phases=tuple(phases),
                page_results=(),
                prescreen_quotes=prescreen_quotes,
                prescreen_missing=prescreen_missing,
                prescreen_failures=prescreen_failures,
                compatible=0,
                incompatible=0,
                final_quotes=(),
                final_missing=(),
                final_errors=(),
                final_new_live=(),
                classification=CLASSIFICATION_CONTRACT_FAILURE,
            )
        page_results = (page_result,)
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
            return self._build_result(
                phases=tuple(phases),
                page_results=page_results,
                prescreen_quotes=prescreen_quotes,
                prescreen_missing=prescreen_missing,
                prescreen_failures=prescreen_failures,
                compatible=compatible,
                incompatible=incompatible,
                final_quotes=(),
                final_missing=(),
                final_errors=(),
                final_new_live=(),
                classification=CLASSIFICATION_CONTRACT_FAILURE,
            )
        if compatible < 10:
            return self._build_result(
                phases=tuple(phases),
                page_results=page_results,
                prescreen_quotes=prescreen_quotes,
                prescreen_missing=prescreen_missing,
                prescreen_failures=prescreen_failures,
                compatible=compatible,
                incompatible=incompatible,
                final_quotes=(),
                final_missing=(),
                final_errors=(),
                final_new_live=(),
                classification=CLASSIFICATION_INCONCLUSIVE,
            )

        # ---- Final valuation ----
        try:
            (
                final_lookup,
                final_new_live_names,
            ) = await self._run_final_valuation()
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
            return self._build_result(
                phases=tuple(phases),
                page_results=page_results,
                prescreen_quotes=prescreen_quotes,
                prescreen_missing=prescreen_missing,
                prescreen_failures=prescreen_failures,
                compatible=compatible,
                incompatible=incompatible,
                final_quotes=(),
                final_missing=(),
                final_errors=(type(exc).__name__,),
                final_new_live=(),
                classification=CLASSIFICATION_CONTRACT_FAILURE,
            )
        final_quotes = tuple(
            final_lookup.quotes[name]
            for name in final_new_live_names
            if name in final_lookup.quotes
        )
        final_missing = tuple(final_lookup.missing)
        final_errors = tuple(final_lookup.errors)
        final_new_live = tuple(final_new_live_names)
        phases.append(
            LiveSteamDTPhase(
                name="final_valuation",
                status="ok" if not final_missing and not final_errors else "failed",
                detail=(
                    f"new_live={len(final_new_live)} "
                    f"missing={len(final_missing)} "
                    f"errors={len(final_errors)}"
                ),
            )
        )
        if final_missing or final_errors:
            classification = CLASSIFICATION_INCONCLUSIVE
        else:
            classification = CLASSIFICATION_VALIDATED

        return self._build_result(
            phases=tuple(phases),
            page_results=page_results,
            prescreen_quotes=prescreen_quotes,
            prescreen_missing=prescreen_missing,
            prescreen_failures=prescreen_failures,
            compatible=compatible,
            incompatible=incompatible,
            final_quotes=final_quotes,
            final_missing=final_missing,
            final_errors=final_errors,
            final_new_live=final_new_live,
            classification=classification,
        )

    # ---------- internal stages ----------

    async def _run_prescreen(self) -> SteamDTBatchPreScreenResult:
        if self._steamdt_batch_attempted >= 1:
            raise _BudgetExceeded("steamdt batch already attempted")
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
        transport = _BudgetedSteamDTBatchTransport(
            client=_cast(SteamDTClient, client),
            tracker=self,
        )
        resolver = SteamDTBatchPreScreenResolver(client=transport)
        self._steamdt_batch_attempted += 1
        result = await resolver.prescreen(
            SteamDTBatchPreScreenRequest(
                market_hash_names=list(self.case.prescreen_market_hash_names),
            )
        )
        self._steamdt_batch_dispatched += 1
        return result

    async def _acquire_buff_page(
        self,
    ) -> tuple[LiveSteamDTPageResult, int, int]:
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

        provider = _BudgetedRawListingProvider(
            http_client=self._buff_http_client,
            tracker=self._tracker,
        )
        pipeline = ExistingRecipeFirstAcquisitionPipeline(
            listing_provider=provider,
            identity_resolver=self.buff_identity_resolver,
            metadata_resolver=self.metadata_resolver,
            intrinsic_resolver=self.intrinsic_resolver,
        )
        plan_item = self.case.buff_case.plan_items[0]
        try:
            page: RecipeFirstAcquisitionPage = await pipeline.acquire_page(
                goods_id=plan_item.goods_id,
                market_hash_name=plan_item.market_hash_name,
            )
        except _BudgetExceeded:
            return (
                LiveSteamDTPageResult(
                    goods_id=plan_item.goods_id,
                    market_hash_name=plan_item.market_hash_name,
                    request_status=RUN_STATUS_FAILED,
                    listing_count=0,
                    candidate_accepted=0,
                    metadata_resolved=0,
                    family_compatible=0,
                    family_incompatible=0,
                ),
                0,
                0,
            )
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception:
            return (
                LiveSteamDTPageResult(
                    goods_id=plan_item.goods_id,
                    market_hash_name=plan_item.market_hash_name,
                    request_status=RUN_STATUS_FAILED,
                    listing_count=0,
                    candidate_accepted=0,
                    metadata_resolved=0,
                    family_compatible=0,
                    family_incompatible=0,
                ),
                0,
                0,
            )
        self._buff_attempted += 1
        self._buff_dispatched += 1
        counts = page.counts
        compatible, incompatible = _count_family_compatible(
            page.enriched_inputs,
            plan_item=plan_item,
            case=self.case.buff_case,
        )
        return (
            LiveSteamDTPageResult(
                goods_id=plan_item.goods_id,
                market_hash_name=plan_item.market_hash_name,
                request_status=RUN_STATUS_DISPATCHED,
                listing_count=counts.listings_received,
                candidate_accepted=counts.candidate_accepted,
                metadata_resolved=counts.metadata_resolved,
                family_compatible=compatible,
                family_incompatible=incompatible,
            ),
            compatible,
            incompatible,
        )

    async def _run_final_valuation(
        self,
    ) -> tuple[PriceLookupResult, list[str]]:
        if self._steamdt_single_attempted >= self.case.steamdt_final_single_http_cap:
            raise _BudgetExceeded("steamdt single already exhausted")
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

        async def _single(name: str) -> PriceQuote:
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
                source="steamdt:buff",
                raw=None,
            )

        provider = _LiveSinglePriceProvider(
            single=_single,
            tracker=self,
        )
        session = RunScopedValuationSession(
            price_provider=provider,
            valuation_config=__import__(
                "app.services.valuation_service", fromlist=["ValuationConfig"]
            ).ValuationConfig(require_all_prices=True),
            session_id=1,
        )
        concrete_outputs: list[str] = []
        for name in self.case.prescreen_market_hash_names:
            if name not in (
                self.case.buff_case.plan_items[0].market_hash_name,
            ):
                concrete_outputs.append(name)
        cap = min(
            self.case.steamdt_final_single_http_cap, len(concrete_outputs)
        )
        new_live_names: tuple[str, ...] = tuple(concrete_outputs[:cap])
        plan = await session.prepare_output_prices(new_live_names)
        from app.services.tradeup_engine import TradeupResult

        tradeup_results: list[TradeupResult] = [
            TradeupResult(
                output_market_hash_name=name,
                probability=0.0,
                output_float=0.0,
                output_wear="",
                estimated_price_cny=Decimal("0"),
                expected_value_contribution=Decimal("0"),
            )
            for name in plan.requested_names
        ]
        result = await session.resolve_prepared(plan, tradeup_results)
        return _lookup_from_session(result), list(plan.new_live_names)

    # ---------- result builder ----------

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
            concrete_selection_count=0,
            concrete_output_market_hash_names=(),
            final_quotes=final_quotes,
            final_missing_names=final_missing,
            final_errors=final_errors,
            final_new_live_names=final_new_live,
            request_state=self.request_state,
            classification=classification,
            schema_version=LIVE_STEAMDT_CASE_SCHEMA_VERSION,
        )


@dataclass
class _BudgetedSteamDTBatchTransport:
    """Wraps a SteamDT client and enforces a hard batch budget."""

    client: Any
    tracker: RecipeFirstSteamDTLiveRunner

    async def get_price_batch_with_selection(
        self,
        market_hash_names: list[str],
        *,
        selection_config: object = None,
        avg_prices_by_name: dict[str, Decimal] | None = None,
    ) -> Any:
        if self.tracker._steamdt_batch_dispatched >= 1:
            raise _BudgetExceeded("steamdt batch already dispatched")
        result = await self.client.get_price_batch_with_selection(
            market_hash_names,
            selection_config=selection_config,
            avg_prices_by_name=avg_prices_by_name,
        )
        return result


class _LiveSinglePriceProvider:
    """PriceProvider that performs one SteamDT single request per name."""

    def __init__(
        self,
        *,
        single: Callable[[str], Awaitable[PriceQuote]],
        tracker: RecipeFirstSteamDTLiveRunner,
    ) -> None:
        self._single = single
        self._tracker = tracker

    async def get_price(self, market_hash_name: str) -> PriceQuote:
        self._tracker._steamdt_single_attempted += 1
        quote = await self._single(market_hash_name)
        self._tracker._steamdt_single_dispatched += 1
        return quote

    async def get_prices(self, names: list[str]) -> PriceLookupResult:
        cap = max(0, 2 - self._tracker._steamdt_single_dispatched)
        quotes: dict[str, PriceQuote] = {}
        missing: list[str] = []
        errors: list[str] = []
        for index, name in enumerate(names):
            if index >= cap:
                break
            self._tracker._steamdt_single_attempted += 1
            try:
                quote = await self._single(name)
            except (MemoryError, asyncio.CancelledError):
                raise
            except Exception:
                errors.append(f"STEAMDT_SINGLE_FAILED:{name}")
                continue
            if quote.market_hash_name != name:
                errors.append(f"STEAMDT_SINGLE_IDENTITY_MISMATCH:{name}")
                continue
            quotes[name] = quote
            self._tracker._steamdt_single_dispatched += 1
        return PriceLookupResult(quotes=quotes, missing=missing, errors=errors)


def _count_family_compatible(
    enriched_inputs: Sequence[Any],
    *,
    plan_item: Any,
    case: LiveValidationCase,
) -> tuple[int, int]:
    from app.services.market_universe_builder import StatTrakMode

    expected_stattrak = case.stattrak_mode is StatTrakMode.STATTRAK
    represented = {name for name, _ in case.collection_counts}
    compatible = 0
    incompatible = 0
    for enriched in enriched_inputs:
        candidate = enriched.candidate
        item = enriched.input_item
        if (
            candidate.goods_id == plan_item.goods_id
            and candidate.market_hash_name == plan_item.market_hash_name
            and item.collection_name == plan_item.collection_name
            and item.collection_name in represented
            and item.rarity == case.input_rarity
            and item.stattrak is expected_stattrak
            and candidate.stattrak is expected_stattrak
        ):
            compatible += 1
        else:
            incompatible += 1
    return compatible, incompatible


def _lookup_from_session(result: Any) -> PriceLookupResult:
    """Convert a SessionValuationResult into a PriceLookupResult.

    The runner persists lookup-shape data, not session-shape data.
    """

    return PriceLookupResult(
        quotes=dict(result.quotes),
        missing=list(result.missing),
        errors=list(result.errors),
    )


__all__ = (
    "CLASSIFICATION_BLOCKED",
    "CLASSIFICATION_CONTRACT_FAILURE",
    "CLASSIFICATION_IDENTITY_FAILURE",
    "CLASSIFICATION_INCONCLUSIVE",
    "CLASSIFICATION_VALIDATED",
    "LiveSteamDTPageResult",
    "LiveSteamDTPhase",
    "LiveSteamDTRequestState",
    "LiveSteamDTRunResult",
    "RecipeFirstSteamDTLiveRunner",
    "RecipeFirstSteamDTLiveRunnerConfig",
    "RUN_STATUS_DISPATCHED",
    "RUN_STATUS_FAILED",
)