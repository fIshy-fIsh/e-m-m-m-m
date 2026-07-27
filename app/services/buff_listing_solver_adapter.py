from __future__ import annotations

import math

from app.services.buff_listing_facts import BuffListingFactsLookupStatus
from app.services.buff_listing_qualification import (
    BuffListingQualificationResult,
    BuffListingQualificationStatus,
)
from app.services.market_scan_service import CandidateListing


class BuffListingSolverAdapterError(ValueError):
    """A qualified listing violated the solver adapter contract."""

    def __init__(self) -> None:
        super().__init__("invalid BUFF listing solver adapter contract")


def adapt_qualified_buff_listing(
    qualification_result: BuffListingQualificationResult,
) -> CandidateListing:
    """Adapt one qualified BUFF listing without invoking solver logic."""

    try:
        if type(qualification_result) is not BuffListingQualificationResult:
            raise BuffListingSolverAdapterError

        validated = BuffListingQualificationResult(
            candidate=qualification_result.candidate,
            policy=qualification_result.policy,
            lookup_result=qualification_result.lookup_result,
            decision=qualification_result.decision,
        )
        candidate = validated.candidate
        lookup_result = validated.lookup_result
        decision = validated.decision

        if (
            validated.status is not BuffListingQualificationStatus.QUALIFIED
            or lookup_result.status is not BuffListingFactsLookupStatus.FOUND
            or lookup_result.facts is None
            or decision is None
            or not decision.is_eligible
            or decision.candidate != candidate
            or decision.facts != lookup_result.facts
            or decision.policy != validated.policy
            or candidate.goods_id is None
            or candidate.float_value is None
            or candidate.available_quantity
            < validated.policy.min_available_quantity
        ):
            raise BuffListingSolverAdapterError

        float_value = float(candidate.float_value)
        if not math.isfinite(float_value) or not 0.0 <= float_value <= 1.0:
            raise BuffListingSolverAdapterError

        return CandidateListing(
            goods_id=candidate.goods_id,
            listing_id=candidate.listing_id,
            market_hash_name=candidate.market_hash_name,
            price_cny=candidate.buy_price_cny,
            float_value=float_value,
            paint_seed=candidate.paint_seed,
            inspect_link=None,
            source="buff",
            scanned_at=candidate.observed_at,
            raw=None,
        )
    except MemoryError:
        raise
    except Exception:
        raise BuffListingSolverAdapterError from None
