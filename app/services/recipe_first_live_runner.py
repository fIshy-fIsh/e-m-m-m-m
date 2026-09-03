"""Phase 16F — Bounded read-only recipe-first BUFF live validation runner.

The runner performs exactly one anonymous BUFF sell-order page-1/default-sort
HTTP request per frozen plan item, in deterministic order, with at most the
case's :attr:`hard_request_count` total requests. It uses the existing
``BuffAnonymousListingHttpClient`` + ``BuffListingProvider`` +
``ExistingRecipeFirstAcquisitionPipeline`` composition to validate the
recipe-first acquisition interface only.

Strict guarantees:

- zero retry on failure
- zero pagination
- zero fallback family
- one ``httpx.AsyncClient`` per run (caller may inject one)
- finite timeout, ``trust_env=False``, ``follow_redirects=False``
- anonymous headers only
- at most ``hard_request_count`` HTTP dispatches
- ``attempted`` request counter is enforced before HTTP dispatch
- result excludes raw BUFF payload and seller / account / asset data
- pacing sleep between sequential starts (off by default for tests)
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import cast

import httpx

from app.clients.buff_anonymous_listing_client import (
    BUFF_ANONYMOUS_BASE_URL,
    BUFF_ANONYMOUS_USER_AGENT,
    BuffAnonymousListingHttpClient,
    BuffAnonymousListingPayloadClient,
)
from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
    BuffGoodsIdIdentityResolver,
)
from app.services.buff_intrinsic_flag_resolver import (
    BuffListingIntrinsicFlagResolver,
    CanonicalNameIntrinsicFlagResolver,
)
from app.services.buff_listing_provider import BuffListingProvider
from app.services.recipe_first_acquisition import (
    ExistingRecipeFirstAcquisitionPipeline,
    RecipeFirstAcquisitionPage,
)
from app.services.recipe_first_live_case import (
    LiveValidationCase,
    LiveValidationCaseError,
    LiveValidationPlanItem,
    hash_case,
    verify_case_identity,
)
from app.services.trade_up_input_enrichment import TradeUpInputMetadataResolver

__all__ = (
    "LiveValidationPageResult",
    "LiveValidationRequestState",
    "LiveValidationRunResult",
    "LiveValidationRunner",
    "LiveValidationRunnerConfig",
    "RUN_STATUS_BUDGET_EXCEEDED",
    "RUN_STATUS_DISPATCHED",
    "RUN_STATUS_PROVIDER_FAILED",
    "RUN_STATUS_REQUEST_FAILED",
)

_ClockCallable = Callable[[float], Awaitable[None]]

RUN_STATUS_DISPATCHED: str = "dispatched"
RUN_STATUS_REQUEST_FAILED: str = "request_failed"
RUN_STATUS_PROVIDER_FAILED: str = "provider_failed"
RUN_STATUS_BUDGET_EXCEEDED: str = "budget_exceeded"
_VALID_PAGE_STATUSES: frozenset[str] = frozenset(
    {
        RUN_STATUS_DISPATCHED,
        RUN_STATUS_REQUEST_FAILED,
        RUN_STATUS_PROVIDER_FAILED,
        RUN_STATUS_BUDGET_EXCEEDED,
    }
)

_CLASSIFICATION_VALIDATED: str = "validated"
_CLASSIFICATION_INCONCLUSIVE: str = "inconclusive"
_CLASSIFICATION_CONTRACT_FAILURE: str = "contract_failure"
_CLASSIFICATION_IDENTITY_FAILURE: str = "identity_failure"


class _BudgetExceeded(RuntimeError):
    """Raised when an attempted BUFF request exceeds the frozen plan budget."""


@dataclass
class _BudgetTracker:
    attempted: int = 0
    dispatched: int = 0
    budget: int = 0
    exceeded: bool = False

    def begin_attempt(self) -> bool:
        """Reserve one attempt slot. Returns ``True`` when allowed."""

        next_attempted = self.attempted + 1
        if next_attempted > self.budget:
            self.exceeded = True
            return False
        self.attempted = next_attempted
        return True

    def record_dispatch(self) -> None:
        self.dispatched += 1


class _BudgetedPayloadClient:
    """Wraps a delegate payload client and enforces a hard attempt budget."""

    def __init__(
        self,
        *,
        delegate: BuffAnonymousListingPayloadClient,
        tracker: _BudgetTracker,
    ) -> None:
        if not hasattr(delegate, "fetch_sell_order_payload"):
            raise LiveValidationCaseError("delegate must implement fetch_sell_order_payload")
        self._delegate = delegate
        self._tracker = tracker

    async def fetch_sell_order_payload(self, goods_id: str) -> bytes:
        if not self._tracker.begin_attempt():
            raise _BudgetExceeded("attempted BUFF request exceeds frozen plan budget")
        try:
            payload = await self._delegate.fetch_sell_order_payload(goods_id)
        except BaseException:
            raise
        self._tracker.record_dispatch()
        return payload


class _BudgetedRawListingProvider:
    """Wraps the bounded payload client + parser behind ``get_listings``.

    The acquisition pipeline requires a :class:`RawBuffListingPageProvider`
    (object exposing ``async get_listings(goods_id) -> list[BuffListing]``).
    This adapter delegates parsing to :class:`BuffListingProvider` and
    propagates the budget enforcement from the wrapped payload client.
    """

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        tracker: _BudgetTracker,
    ) -> None:
        http_delegate = BuffAnonymousListingHttpClient(http_client)
        budgeted = _BudgetedPayloadClient(
            delegate=http_delegate, tracker=tracker
        )
        self._provider = BuffListingProvider(budgeted)

    async def get_listings(self, goods_id: str) -> list:
        return await self._provider.get_listings(goods_id)


@dataclass(frozen=True, kw_only=True)
class LiveValidationRequestState:
    attempted: int
    dispatched: int
    budget_exceeded: bool


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveValidationPageResult:
    """Redacted per-page outcome. No raw BUFF payload is retained."""

    goods_id: str
    market_hash_name: str
    request_status: str
    listing_count: int
    candidate_accepted: int
    candidate_rejected: int
    metadata_resolved: int
    metadata_unresolved: int
    rejection_histograms: tuple[tuple[str, int], ...]
    error_reason: str | None

    def __post_init__(self) -> None:
        if self.request_status not in _VALID_PAGE_STATUSES:
            raise LiveValidationCaseError(
                f"invalid request_status: {self.request_status!r}"
            )
        for field_value in (
            self.listing_count,
            self.candidate_accepted,
            self.candidate_rejected,
            self.metadata_resolved,
            self.metadata_unresolved,
        ):
            if type(field_value) is not int or field_value < 0:
                raise LiveValidationCaseError("page counters must be non-negative ints")
        if not isinstance(self.rejection_histograms, tuple):
            raise LiveValidationCaseError("rejection_histograms must be a tuple")
        for entry in self.rejection_histograms:
            if (
                type(entry) is not tuple
                or len(entry) != 2
                or type(entry[0]) is not str
                or type(entry[1]) is not int
            ):
                raise LiveValidationCaseError(
                    "rejection_histograms entries must be (str, int)"
                )
        if self.error_reason is not None and type(self.error_reason) is not str:
            raise LiveValidationCaseError("error_reason must be a string or None")


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveValidationRunResult:
    """Redacted run-level outcome with no raw BUFF payload."""

    case_sha256: str
    repository_head_sha: str
    hard_request_count: int
    attempted: int
    dispatched: int
    budget_exceeded: bool
    page_results: tuple[LiveValidationPageResult, ...]
    aggregate_listings_received: int
    aggregate_candidate_accepted: int
    aggregate_metadata_resolved: int
    classification: str

    def __post_init__(self) -> None:
        if type(self.case_sha256) is not str or len(self.case_sha256) != 64:
            raise LiveValidationCaseError("case_sha256 must be SHA-256 hex")
        if type(self.aggregate_listings_received) is not int:
            raise LiveValidationCaseError("aggregate counters must be ints")


@dataclass(frozen=True, kw_only=True)
class LiveValidationRunnerConfig:
    pacing_seconds: float = 2.0
    timeout_seconds: float = 10.0


async def _asyncio_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _immediate_sleep(seconds: float) -> None:
    return None


@dataclass(kw_only=True)
class LiveValidationRunner:
    """Performs one bounded sequential live BUFF page acquisition run.

    A single runner instance performs exactly one :meth:`run` invocation.
    """

    case: LiveValidationCase
    identity_resolver: BuffCommunityIdentityResolver
    metadata_resolver: TradeUpInputMetadataResolver
    intrinsic_resolver: BuffListingIntrinsicFlagResolver | None = None
    config: LiveValidationRunnerConfig | None = None
    http_client: httpx.AsyncClient | None = None

    _config: LiveValidationRunnerConfig = field(init=False)
    _owns_http: bool = field(default=False, init=False)
    _http_client: httpx.AsyncClient | None = field(default=None, init=False)
    _tracker: _BudgetTracker = field(default_factory=_BudgetTracker, init=False)
    _closed: bool = field(default=False, init=False)
    _clock: _ClockCallable = field(default=_asyncio_sleep, init=False)

    def __post_init__(self) -> None:
        if type(self.case) is not LiveValidationCase:
            raise LiveValidationCaseError("case must be LiveValidationCase")
        if not hasattr(self.identity_resolver, "resolve_goods_id"):
            raise LiveValidationCaseError(
                "identity_resolver must expose resolve_goods_id"
            )
        if not hasattr(self.metadata_resolver, "resolve"):
            raise LiveValidationCaseError(
                "metadata_resolver must expose resolve"
            )
        if self.intrinsic_resolver is not None and not hasattr(
            self.intrinsic_resolver, "resolve"
        ):
            raise LiveValidationCaseError(
                "intrinsic_resolver must expose resolve() or be None"
            )
        cfg: LiveValidationRunnerConfig = self.config or LiveValidationRunnerConfig()
        if (
            type(cfg.pacing_seconds) is not float
            or not cfg.pacing_seconds >= 0.0
            or type(cfg.timeout_seconds) is not float
            or not cfg.timeout_seconds > 0.0
        ):
            raise LiveValidationCaseError(
                "pacing_seconds and timeout_seconds must be valid non-negative floats"
            )
        self._config = cfg
        self.config = cfg
        self._owns_http = self.http_client is None
        if self.http_client is not None:
            self._http_client = self.http_client
        self._tracker = _BudgetTracker(budget=self.case.hard_request_count)

    @property
    def request_state(self) -> LiveValidationRequestState:
        return LiveValidationRequestState(
            attempted=self._tracker.attempted,
            dispatched=self._tracker.dispatched,
            budget_exceeded=self._tracker.exceeded,
        )

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_http and self._http_client is not None:
            try:
                await self._http_client.aclose()
            except (MemoryError, asyncio.CancelledError):
                raise
            except Exception:
                pass

    async def run(self) -> LiveValidationRunResult:
        """Execute the frozen plan exactly once."""

        try:
            await verify_case_identity(
                self.case, identity_resolver=self.identity_resolver
            )
        except LiveValidationCaseError:
            return _build_run_result(
                case=self.case,
                page_results=(),
                attempted=self._tracker.attempted,
                dispatched=self._tracker.dispatched,
                budget_exceeded=self._tracker.exceeded,
                aggregate_listings=0,
                aggregate_candidates=0,
                aggregate_metadata=0,
                classification=_CLASSIFICATION_IDENTITY_FAILURE,
            )

        timeout_seconds = self._config.timeout_seconds
        if self._http_client is None:
            self._http_client = _build_http_client(timeout_seconds)
        provider = _BudgetedRawListingProvider(
            http_client=self._http_client, tracker=self._tracker
        )
        pipeline = ExistingRecipeFirstAcquisitionPipeline(
            listing_provider=provider,
            identity_resolver=cast(BuffGoodsIdIdentityResolver, self.identity_resolver),
            metadata_resolver=self.metadata_resolver,
            intrinsic_resolver=self.intrinsic_resolver
            or CanonicalNameIntrinsicFlagResolver(),
        )

        page_results: list[LiveValidationPageResult] = []
        aggregate_listings = 0
        aggregate_candidates = 0
        aggregate_metadata = 0
        plan_items = list(self.case.plan_items)
        last_index = len(plan_items) - 1
        pacing_seconds_value = self._config.pacing_seconds
        for index, plan_item in enumerate(plan_items):
            page_result = await self._acquire_one(
                pipeline=pipeline,
                plan_item=plan_item,
            )
            page_results.append(page_result)
            aggregate_listings += page_result.listing_count
            aggregate_candidates += page_result.candidate_accepted
            aggregate_metadata += page_result.metadata_resolved
            if self._tracker.exceeded:
                break
            if pacing_seconds_value > 0.0 and index < last_index:
                await self._clock(pacing_seconds_value)

        classification = _classify_run(
            page_results=page_results,
            attempted=self._tracker.attempted,
            dispatched=self._tracker.dispatched,
            budget_exceeded=self._tracker.exceeded,
            hard_request_count=self.case.hard_request_count,
        )
        return _build_run_result(
            case=self.case,
            page_results=tuple(page_results),
            attempted=self._tracker.attempted,
            dispatched=self._tracker.dispatched,
            budget_exceeded=self._tracker.exceeded,
            aggregate_listings=aggregate_listings,
            aggregate_candidates=aggregate_candidates,
            aggregate_metadata=aggregate_metadata,
            classification=classification,
        )

    async def _acquire_one(
        self,
        *,
        pipeline: ExistingRecipeFirstAcquisitionPipeline,
        plan_item: LiveValidationPlanItem,
    ) -> LiveValidationPageResult:
        try:
            page: RecipeFirstAcquisitionPage = await pipeline.acquire_page(
                goods_id=plan_item.goods_id,
                market_hash_name=plan_item.market_hash_name,
            )
        except _BudgetExceeded:
            return LiveValidationPageResult(
                goods_id=plan_item.goods_id,
                market_hash_name=plan_item.market_hash_name,
                request_status=RUN_STATUS_BUDGET_EXCEEDED,
                listing_count=0,
                candidate_accepted=0,
                candidate_rejected=0,
                metadata_resolved=0,
                metadata_unresolved=0,
                rejection_histograms=(),
                error_reason="attempted_request_exceeded_frozen_budget",
            )
        except (MemoryError, asyncio.CancelledError):
            raise
        except Exception as exc:
            reason = _classify_exception(exc)
            return LiveValidationPageResult(
                goods_id=plan_item.goods_id,
                market_hash_name=plan_item.market_hash_name,
                request_status=reason,
                listing_count=0,
                candidate_accepted=0,
                candidate_rejected=0,
                metadata_resolved=0,
                metadata_unresolved=0,
                rejection_histograms=(),
                error_reason=reason,
            )
        counts = page.counts
        combined_histograms: list[tuple[str, int]] = []
        for entry in page.candidate_rejection_histogram:
            combined_histograms.append((entry[0], int(entry[1])))
        for entry in page.metadata_rejection_histogram:
            combined_histograms.append((entry[0], int(entry[1])))
        return LiveValidationPageResult(
            goods_id=plan_item.goods_id,
            market_hash_name=plan_item.market_hash_name,
            request_status=RUN_STATUS_DISPATCHED,
            listing_count=counts.listings_received,
            candidate_accepted=counts.candidate_accepted,
            candidate_rejected=counts.candidate_rejected,
            metadata_resolved=counts.metadata_resolved,
            metadata_unresolved=counts.metadata_unresolved,
            rejection_histograms=tuple(combined_histograms),
            error_reason=None,
        )


def _build_http_client(timeout_seconds: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BUFF_ANONYMOUS_BASE_URL,
        timeout=timeout_seconds,
        follow_redirects=False,
        trust_env=False,
        headers={
            "Accept": "application/json",
            "User-Agent": BUFF_ANONYMOUS_USER_AGENT,
        },
    )


def _classify_exception(exc: BaseException) -> str:
    message = str(exc)
    name = type(exc).__name__
    if "acquired listing does not match" in message:
        return RUN_STATUS_PROVIDER_FAILED
    if name == "BuffListingProviderError":
        return RUN_STATUS_PROVIDER_FAILED
    return RUN_STATUS_REQUEST_FAILED


def _classify_run(
    *,
    page_results: Sequence[LiveValidationPageResult],
    attempted: int,
    dispatched: int,
    budget_exceeded: bool,
    hard_request_count: int,
) -> str:
    if budget_exceeded:
        return _CLASSIFICATION_CONTRACT_FAILURE
    if attempted > hard_request_count or dispatched > hard_request_count:
        return _CLASSIFICATION_CONTRACT_FAILURE
    if any(
        result.request_status not in _VALID_PAGE_STATUSES
        for result in page_results
    ):
        return _CLASSIFICATION_CONTRACT_FAILURE
    if any(
        result.request_status == RUN_STATUS_BUDGET_EXCEEDED
        for result in page_results
    ):
        return _CLASSIFICATION_CONTRACT_FAILURE
    if (
        attempted == hard_request_count
        and dispatched == hard_request_count
        and all(
            result.request_status == RUN_STATUS_DISPATCHED
            for result in page_results
        )
        and any(result.metadata_resolved > 0 for result in page_results)
    ):
        return _CLASSIFICATION_VALIDATED
    if attempted <= hard_request_count and dispatched < hard_request_count:
        return _CLASSIFICATION_INCONCLUSIVE
    return _CLASSIFICATION_INCONCLUSIVE


def _build_run_result(
    *,
    case: LiveValidationCase,
    page_results: tuple[LiveValidationPageResult, ...],
    attempted: int,
    dispatched: int,
    budget_exceeded: bool,
    aggregate_listings: int,
    aggregate_candidates: int,
    aggregate_metadata: int,
    classification: str,
) -> LiveValidationRunResult:
    return LiveValidationRunResult(
        case_sha256=hash_case(case),
        repository_head_sha=case.repository_head_sha,
        hard_request_count=case.hard_request_count,
        attempted=attempted,
        dispatched=dispatched,
        budget_exceeded=budget_exceeded,
        page_results=tuple(page_results),
        aggregate_listings_received=aggregate_listings,
        aggregate_candidate_accepted=aggregate_candidates,
        aggregate_metadata_resolved=aggregate_metadata,
        classification=classification,
    )