from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.tradeup_engine import InputItem

__all__ = (
    "TradeUpInputMetadata",
    "TradeUpInputMetadataResolver",
    "InMemoryTradeUpInputMetadataResolver",
    "TradeUpEnrichmentRejectionReason",
    "TradeUpEnrichmentRejection",
    "TradeUpEnrichedInput",
    "TradeUpInputEnrichmentResult",
    "TradeUpInputEnricher",
    "InMemoryTradeUpInputEnricher",
    "enrich_candidates",
)


@dataclass(frozen=True, kw_only=True, repr=False)
class TradeUpInputMetadata:
    """Synthetic catalog-row metadata used to enrich one candidate."""

    market_hash_name: str
    collection_name: str
    rarity: str
    min_float: float
    max_float: float

    def __post_init__(self) -> None:
        for value in (self.market_hash_name, self.collection_name, self.rarity):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError("invalid trade-up input metadata")
        if (
            type(self.min_float) is not float
            or type(self.max_float) is not float
            or not math.isfinite(self.min_float)
            or not math.isfinite(self.max_float)
            or self.min_float < 0
            or self.max_float > 1
            or self.min_float >= self.max_float
        ):
            raise ValueError("invalid trade-up input metadata")


class TradeUpInputMetadataResolver(Protocol):
    """Resolve one market_hash_name to its catalog-row metadata, or None."""

    def resolve(self, market_hash_name: str) -> TradeUpInputMetadata | None:
        """Return catalog-row metadata, or None when missing."""


class InMemoryTradeUpInputMetadataResolver:
    """Test/offline resolver backed by an immutable mapping."""

    def __init__(self, mapping: Mapping[str, TradeUpInputMetadata]) -> None:
        self._mapping = MappingProxyType(
            {key: value for key, value in mapping.items()}
        )

    def resolve(self, market_hash_name: str) -> TradeUpInputMetadata | None:
        return self._mapping.get(market_hash_name)


class TradeUpEnrichmentRejectionReason(StrEnum):
    """Stable structural reasons one candidate failed enrichment.

    The vocabulary is closed. `MARKET_HASH_NAME_UNRESOLVED` and
    `METADATA_NOT_FOUND` are the canonical pre-13O reasons.
    `INTRINSIC_FLAG_UNRESOLVED` was added in Phase 13O to surface the
    three-state intrinsic-flag representation (`True` / `False` /
    `None`) without silently coercing `None` to `False`.
    """

    MARKET_HASH_NAME_UNRESOLVED = "market_hash_name_unresolved"
    METADATA_NOT_FOUND = "metadata_not_found"
    INTRINSIC_FLAG_UNRESOLVED = "intrinsic_flag_unresolved"


@dataclass(frozen=True, kw_only=True, repr=False)
class TradeUpEnrichmentRejection:
    """Redacted structural rejection of one candidate at the enrichment boundary."""

    candidate: TradeUpInputCandidate
    reason: TradeUpEnrichmentRejectionReason

    def __post_init__(self) -> None:
        if type(self.candidate) is not TradeUpInputCandidate:
            raise ValueError("candidate must be a TradeUpInputCandidate")
        if type(self.reason) is not TradeUpEnrichmentRejectionReason:
            raise ValueError("reason must be a TradeUpEnrichmentRejectionReason")


@dataclass(frozen=True, kw_only=True, repr=False)
class TradeUpEnrichedInput:
    """One candidate paired with the InputItem produced at the enrichment boundary."""

    candidate: TradeUpInputCandidate
    input_item: InputItem

    def __post_init__(self) -> None:
        if type(self.candidate) is not TradeUpInputCandidate:
            raise ValueError("candidate must be a TradeUpInputCandidate")
        if type(self.input_item) is not InputItem:
            raise ValueError("input_item must be an InputItem")


@dataclass(frozen=True, kw_only=True, repr=False)
class TradeUpInputEnrichmentResult:
    """Aggregate output of one enrichment pass over a candidate sequence."""

    enriched: tuple[TradeUpEnrichedInput, ...]
    rejected: tuple[TradeUpEnrichmentRejection, ...]

    def __post_init__(self) -> None:
        if type(self.enriched) is not tuple:
            raise ValueError("enriched must be an exact tuple")
        if type(self.rejected) is not tuple:
            raise ValueError("rejected must be an exact tuple")
        enriched_items = tuple(enriched for enriched in self.enriched)
        rejected_items = tuple(rejected for rejected in self.rejected)
        if len(enriched_items) != len(set(enriched_items)):
            raise ValueError("enriched candidates must be unique")
        if len(rejected_items) != len(set(rejected_items)):
            raise ValueError("rejected candidates must be unique")


class TradeUpInputEnricher(Protocol):
    """Enrich one candidate using a metadata resolver; preserve candidate ownership."""

    def enrich(
        self,
        candidate: TradeUpInputCandidate,
    ) -> TradeUpEnrichedInput | TradeUpEnrichmentRejection:
        """Produce one enriched input or one rejection."""


class InMemoryTradeUpInputEnricher:
    """Offline enricher that consumes one in-memory metadata resolver."""

    def __init__(
        self,
        metadata_resolver: TradeUpInputMetadataResolver,
    ) -> None:
        self._metadata_resolver = metadata_resolver

    def enrich(
        self,
        candidate: TradeUpInputCandidate,
    ) -> TradeUpEnrichedInput | TradeUpEnrichmentRejection:
        if candidate.market_hash_name is None:
            return TradeUpEnrichmentRejection(
                candidate=candidate,
                reason=TradeUpEnrichmentRejectionReason.MARKET_HASH_NAME_UNRESOLVED,
            )
        # Phase 13O: intrinsic flags are now `bool | None`. A `None`
        # value means the upstream source did not establish the flag;
        # the enricher refuses to coerce `None` to `False` and fails
        # closed with `INTRINSIC_FLAG_UNRESOLVED`. The candidate's
        # constructor already rejected malformed (non-bool, non-None)
        # values, so the only remaining `None` here is the legitimate
        # unknown-source state.
        if candidate.stattrak is None or candidate.souvenir is None:
            return TradeUpEnrichmentRejection(
                candidate=candidate,
                reason=TradeUpEnrichmentRejectionReason.INTRINSIC_FLAG_UNRESOLVED,
            )
        metadata = self._metadata_resolver.resolve(candidate.market_hash_name)
        if metadata is None:
            return TradeUpEnrichmentRejection(
                candidate=candidate,
                reason=TradeUpEnrichmentRejectionReason.METADATA_NOT_FOUND,
            )
        return TradeUpEnrichedInput(
            candidate=candidate,
            input_item=InputItem(
                market_hash_name=candidate.market_hash_name,
                collection_name=metadata.collection_name,
                rarity=metadata.rarity,
                actual_float=float(candidate.paintwear),
                min_float=metadata.min_float,
                max_float=metadata.max_float,
                price_cny=candidate.price_cny,
                stattrak=candidate.stattrak,
                souvenir=candidate.souvenir,
            ),
        )


def enrich_candidates(
    candidates: Iterable[TradeUpInputCandidate],
    enricher: TradeUpInputEnricher,
) -> TradeUpInputEnrichmentResult:
    """Run one enrichment pass and return kept + rejected results in input order."""

    enriched_list: list[TradeUpEnrichedInput] = []
    rejected_list: list[TradeUpEnrichmentRejection] = []
    for candidate in candidates:
        outcome = enricher.enrich(candidate)
        if isinstance(outcome, TradeUpEnrichmentRejection):
            rejected_list.append(outcome)
        else:
            enriched_list.append(outcome)
    return TradeUpInputEnrichmentResult(
        enriched=tuple(enriched_list),
        rejected=tuple(rejected_list),
    )