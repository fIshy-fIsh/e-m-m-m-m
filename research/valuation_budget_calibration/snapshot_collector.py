"""Research-only one-observation collector for the frozen snapshot protocol."""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.services.buff_community_identity_resolver import BuffGoodsIdIdentityResolver
from app.services.buff_identity_listing_provider import (
    BuffIdentityBindingError,
    bind_identity_to_provider,
)
from app.services.buff_intrinsic_flag_listing_provider import (
    bind_intrinsic_flags_to_provider,
)
from app.services.buff_intrinsic_flag_resolver import (
    CanonicalNameIntrinsicFlagResolver,
    IntrinsicFlagInputError,
)
from app.services.buff_listing_candidate_adapter import (
    CandidateAdapterRejection,
    convert_buff_listing_to_candidate,
)
from app.services.buff_listing_intrinsic_flags import BuffListingIntrinsicFlags
from app.services.buff_listing_provider import (
    BuffListing,
    BuffListingProviderError,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputEnricher,
    TradeUpEnrichedInput,
    TradeUpEnrichmentRejection,
)
from research.valuation_budget_calibration.snapshot_protocol import (
    MINIMUM_REQUEST_START_INTERVAL_SECONDS,
    ObservationPlan,
    PlannedGood,
    format_utc_timestamp,
)
from research.valuation_budget_calibration.snapshot_schema import (
    AcquisitionSummary,
    ObservationStatus,
    PageStatus,
    RepresentativeSnapshot,
    SnapshotListing,
    SnapshotPage,
    SnapshotPlannedGood,
    SnapshotProvenance,
    SnapshotStratum,
    canonical_decimal,
    parse_snapshot_payload,
)

_FIXED_ERROR = "representative snapshot collection failed"


class SnapshotCollectionError(RuntimeError):
    """Collector failed before a truthful snapshot could be materialized."""

    def __init__(self, *, reason: str) -> None:
        super().__init__(_FIXED_ERROR)
        self.reason = reason


class ListingPageProvider(Protocol):
    async def get_listings(self, goods_id: str) -> list[BuffListing]: ...


class _ResolvedPageProvider:
    """Borrow one already-fetched page; performs no I/O and one exact return."""

    def __init__(self, *, goods_id: str, listings: list[BuffListing]) -> None:
        self._goods_id = goods_id
        self._listings = tuple(listings)
        self.calls = 0

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        if goods_id != self._goods_id or self.calls != 0:
            raise SnapshotCollectionError(reason="PROVENANCE_MISMATCH")
        self.calls += 1
        return list(self._listings)


@dataclass(frozen=True, kw_only=True)
class CollectionResult:
    snapshot: RepresentativeSnapshot
    request_count: int


async def collect_observation(
    *,
    plan: ObservationPlan,
    listing_provider: ListingPageProvider,
    identity_resolver: BuffGoodsIdIdentityResolver,
    metadata_resolver: PinnedSkinMetadataResolver,
    provenance: SnapshotProvenance,
    request_interval_seconds: float = MINIMUM_REQUEST_START_INTERVAL_SECONDS,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    utc_now: Callable[[], datetime] | None = None,
) -> CollectionResult:
    """Collect exactly one planned observation, sequentially and without retry."""

    if len(plan.planned_goods) != 10:
        raise SnapshotCollectionError(reason="UNIVERSE_NOT_EXACTLY_TEN")
    if (
        type(request_interval_seconds) is not float
        or request_interval_seconds < MINIMUM_REQUEST_START_INTERVAL_SECONDS
    ):
        raise SnapshotCollectionError(reason="invalid_request_interval")
    now = utc_now or (lambda: datetime.now(UTC))
    observed = _timestamp_now(now)
    request_count = 0
    pages: list[SnapshotPage] = []
    last_start: float | None = None

    enricher = InMemoryTradeUpInputEnricher(metadata_resolver)

    for planned in plan.planned_goods:
        if last_start is not None:
            remaining = request_interval_seconds - (monotonic() - last_start)
            if remaining > 0:
                await sleeper(remaining)
        last_start = monotonic()
        request_count += 1
        try:
            raw_listings = await listing_provider.get_listings(planned.goods_id)
        except (MemoryError, asyncio.CancelledError):
            raise
        except BuffListingProviderError as exc:
            pages.append(
                _failed_page(
                    planned,
                    status=_provider_failure_status(exc),
                    reason=(
                        "LISTING_FETCH_FAILED"
                        if exc.reason == "request_failed"
                        else "LISTING_RESPONSE_INVALID"
                    ),
                    detail=exc.reason,
                )
            )
            continue
        except Exception:
            pages.append(
                _failed_page(
                    planned,
                    status=PageStatus.FETCH_FAILED,
                    reason="LISTING_FETCH_FAILED",
                    detail="request_failed",
                )
            )
            continue
        if type(raw_listings) is not list or any(
            type(listing) is not BuffListing for listing in raw_listings
        ):
            pages.append(
                _failed_page(
                    planned,
                    status=PageStatus.PARSE_FAILED,
                    reason="LISTING_RESPONSE_INVALID",
                    detail="response_schema_invalid",
                )
            )
            continue

        page_provider = _ResolvedPageProvider(
            goods_id=planned.goods_id,
            listings=raw_listings,
        )
        identity_provider = bind_identity_to_provider(
            page_provider,
            identity_resolver,
        )
        intrinsic_provider = bind_intrinsic_flags_to_provider(
            identity_provider,
            CanonicalNameIntrinsicFlagResolver(),
        )
        try:
            flagged = await intrinsic_provider.get_listings(planned.goods_id)
            if page_provider.calls != 1:
                raise SnapshotCollectionError(reason="PROVENANCE_MISMATCH")
        except (MemoryError, asyncio.CancelledError):
            raise
        except BuffIdentityBindingError as exc:
            pages.append(
                _failed_page(
                    planned,
                    status=PageStatus.BINDING_FAILED,
                    reason="IDENTITY_CONFLICT",
                    detail=(
                        exc.reason
                        if exc.reason
                        in {
                            "resolver_goods_id_mismatch",
                            "listing_goods_id_mismatch",
                            "market_hash_name_conflict",
                        }
                        else None
                    ),
                )
            )
            continue
        except IntrinsicFlagInputError:
            pages.append(
                _failed_page(
                    planned,
                    status=PageStatus.BINDING_FAILED,
                    reason="INTRINSIC_CONFLICT",
                    detail=None,
                )
            )
            continue
        except Exception:
            pages.append(
                _failed_page(
                    planned,
                    status=PageStatus.BINDING_FAILED,
                    reason="PROVENANCE_MISMATCH",
                    detail=None,
                )
            )
            continue

        normalized: list[SnapshotListing] = []
        invalid = False
        for listing in flagged:
            outcome = _normalize_listing(
                listing=listing,
                planned=planned,
                enricher=enricher,
            )
            if outcome is None:
                invalid = True
                break
            normalized.append(outcome)
        if invalid:
            pages.append(
                _failed_page(
                    planned,
                    status=PageStatus.BINDING_FAILED,
                    reason="PROVENANCE_MISMATCH",
                    detail=None,
                )
            )
            continue
        pages.append(
            SnapshotPage(
                goods_id=planned.goods_id,
                universe_rank=planned.universe_rank,
                cohort_collection=planned.cohort_collection,
                cohort_rarity=planned.rarity,
                cohort_stattrak=planned.stattrak,
                acquisition_status=(
                    PageStatus.SUCCESS if normalized else PageStatus.EMPTY
                ),
                failure_reason=None,
                failure_detail_code=None,
                listings=tuple(normalized),
            )
        )

    completed = _timestamp_now(now)
    status = _observation_status(tuple(pages))
    summary = _build_summary(tuple(pages))
    snapshot = RepresentativeSnapshot(
        campaign_id=plan.spec.campaign_id,
        snapshot_id=plan.snapshot_id,
        nominal_slot_utc=plan.spec.nominal_slot_utc,
        scheduled_for_utc=plan.scheduled_for_utc,
        observed_at_utc=observed,
        capture_completed_at_utc=completed,
        observation_status=status,
        stratum=SnapshotStratum(
            input_rarity=plan.spec.input_rarity,
            stattrak_mode=plan.spec.stattrak_mode,
            souvenir_inclusion="include",
        ),
        provenance=provenance,
        selected_cohort_count=plan.selected_cohort_count,
        planned_goods=tuple(
            SnapshotPlannedGood(**item.to_payload()) for item in plan.planned_goods
        ),
        acquisition_summary=summary,
        pages=tuple(pages),
    )
    validated = parse_snapshot_payload(snapshot.to_payload())
    return CollectionResult(snapshot=validated, request_count=request_count)


def _normalize_listing(
    *,
    listing: object,
    planned: PlannedGood,
    enricher: InMemoryTradeUpInputEnricher,
) -> SnapshotListing | None:
    if not isinstance(listing, BuffListingIntrinsicFlags):
        return None
    if (
        listing.goods_id != planned.goods_id
        or listing.market_hash_name != planned.market_hash_name
        or listing.stattrak is not planned.stattrak
        or listing.souvenir is not planned.souvenir
    ):
        return None
    candidate_outcome = convert_buff_listing_to_candidate(listing)  # type: ignore[arg-type]
    if isinstance(candidate_outcome, CandidateAdapterRejection):
        return None
    if type(candidate_outcome) is not TradeUpInputCandidate:
        return None
    enrichment = enricher.enrich(candidate_outcome)
    if isinstance(enrichment, TradeUpEnrichmentRejection):
        return None
    if type(enrichment) is not TradeUpEnrichedInput:
        return None
    item = enrichment.input_item
    if (
        item.market_hash_name != planned.market_hash_name
        or item.collection_name != planned.cohort_collection
        or item.rarity != planned.rarity
        or item.stattrak is not planned.stattrak
        or item.souvenir is not planned.souvenir
    ):
        return None
    return SnapshotListing(
        listing_reference=listing.listing_id,
        listing_reference_kind="anonymous_item_id_compatibility",
        asset_reference=listing.asset_id,
        goods_id=listing.goods_id,
        market_hash_name=listing.market_hash_name,
        price_cny=canonical_decimal(listing.price_cny),
        paintwear=canonical_decimal(listing.paintwear),
        paintseed=listing.paintseed,
        stattrak=listing.stattrak,
        souvenir=listing.souvenir,
        rarity=item.rarity,
        collection_name=item.collection_name,
        source=listing.source,
        identity_status="RESOLVED",
        intrinsic_status="RESOLVED",
        metadata_status="RESOLVED",
        candidate_status="ACCEPTED",
        replay_status="INCLUDED",
        rejection_reason=None,
    )


def _provider_failure_status(exc: BuffListingProviderError) -> PageStatus:
    return (
        PageStatus.FETCH_FAILED
        if exc.reason == "request_failed"
        else PageStatus.PARSE_FAILED
    )


def _failed_page(
    planned: PlannedGood,
    *,
    status: PageStatus,
    reason: str,
    detail: str | None,
) -> SnapshotPage:
    return SnapshotPage(
        goods_id=planned.goods_id,
        universe_rank=planned.universe_rank,
        cohort_collection=planned.cohort_collection,
        cohort_rarity=planned.rarity,
        cohort_stattrak=planned.stattrak,
        acquisition_status=status,
        failure_reason=reason,
        failure_detail_code=detail,
        listings=(),
    )


def _observation_status(pages: tuple[SnapshotPage, ...]) -> ObservationStatus:
    statuses = {page.acquisition_status for page in pages}
    if PageStatus.BINDING_FAILED in statuses:
        return ObservationStatus.INVALID
    if statuses & {PageStatus.FETCH_FAILED, PageStatus.PARSE_FAILED}:
        return ObservationStatus.PARTIAL
    return ObservationStatus.COMPLETE


def _build_summary(pages: tuple[SnapshotPage, ...]) -> AcquisitionSummary:
    listings = tuple(listing for page in pages for listing in page.listings)
    reasons: Counter[str] = Counter()
    for page in pages:
        if page.failure_reason is not None:
            reasons[page.failure_reason] += 1
        for listing in page.listings:
            if listing.rejection_reason is not None:
                reasons[listing.rejection_reason] += 1
    return AcquisitionSummary(
        pages_requested=len(pages),
        pages_completed=sum(
            page.acquisition_status in (PageStatus.SUCCESS, PageStatus.EMPTY)
            for page in pages
        ),
        pages_nonempty=sum(
            page.acquisition_status is PageStatus.SUCCESS for page in pages
        ),
        pages_empty=sum(
            page.acquisition_status is PageStatus.EMPTY for page in pages
        ),
        pages_failed=sum(
            page.acquisition_status
            in (
                PageStatus.FETCH_FAILED,
                PageStatus.PARSE_FAILED,
                PageStatus.BINDING_FAILED,
            )
            for page in pages
        ),
        listings_received=len(listings),
        identity_resolved=len(listings),
        identity_unresolved=0,
        intrinsic_resolved=len(listings),
        intrinsic_unresolved=0,
        metadata_resolved=len(listings),
        metadata_not_found=0,
        metadata_not_attempted=0,
        candidate_accepted=len(listings),
        candidate_rejected=0,
        replay_included=len(listings),
        replay_excluded=0,
        reason_counts=tuple(sorted(reasons.items())),
    )


def _timestamp_now(now: Callable[[], datetime]) -> str:
    value = now()
    if type(value) is not datetime or value.tzinfo is None:
        raise SnapshotCollectionError(reason="invalid_collector_clock")
    normalized = value.astimezone(UTC).replace(microsecond=0)
    return format_utc_timestamp(normalized)
