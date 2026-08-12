from __future__ import annotations

import math

from app.services.market_scan_service import CandidateListing
from app.services.steamapis_listing import SteamApisListingObservation

_SOURCE = "steamapis:buff163"
_FIXED_ERROR_MESSAGE = "invalid SteamApis candidate adapter contract"
_to_float = float

__all__ = (
    "SteamApisCandidateAdapterError",
    "adapt_steamapis_listing_to_candidate",
)


class SteamApisCandidateAdapterError(ValueError):
    """A SteamApis observation violated the candidate adapter contract."""

    def __init__(self) -> None:
        super().__init__(_FIXED_ERROR_MESSAGE)


def adapt_steamapis_listing_to_candidate(
    observation: SteamApisListingObservation,
) -> CandidateListing:
    """Adapt one validated SteamApis observation without invoking runtime logic."""

    if type(observation) is not SteamApisListingObservation:
        raise SteamApisCandidateAdapterError

    try:
        validated = SteamApisListingObservation(
            source_offer_id=observation.source_offer_id,
            event_type=observation.event_type,
            marketplace=observation.marketplace,
            game=observation.game,
            market_hash_name=observation.market_hash_name,
            purchase_link=observation.purchase_link,
            inspect_link=observation.inspect_link,
            price_cny=observation.price_cny,
            float_value=observation.float_value,
            paint_index=observation.paint_index,
            paint_seed=observation.paint_seed,
            days_trade_locked=observation.days_trade_locked,
            found_at=observation.found_at,
            message_timestamp=observation.message_timestamp,
            stickers=observation.stickers,
        )

        decimal_float = validated.float_value
        if not decimal_float.is_finite() or not 0 <= decimal_float <= 1:
            raise SteamApisCandidateAdapterError
        float_value = _to_float(decimal_float)
        if (
            type(float_value) is not float
            or not math.isfinite(float_value)
            or not 0.0 <= float_value <= 1.0
        ):
            raise SteamApisCandidateAdapterError

        # These compatibility IDs are not BUFF IDs or a SteamApis marketplace ID.
        source_local_id = f"{_SOURCE}:{validated.source_offer_id}"
        return CandidateListing(
            goods_id=source_local_id,
            listing_id=source_local_id,
            market_hash_name=validated.market_hash_name,
            price_cny=validated.price_cny,
            float_value=float_value,
            paint_seed=validated.paint_seed,
            inspect_link=validated.inspect_link,
            source=_SOURCE,
            scanned_at=validated.message_timestamp,
            raw=None,
        )
    except MemoryError:
        raise
    except Exception:
        raise SteamApisCandidateAdapterError from None
