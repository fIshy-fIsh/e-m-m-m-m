from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Protocol

from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputEnricher,
    TradeUpEnrichedInput,
    TradeUpEnrichmentRejectionReason,
    TradeUpInputEnrichmentResult,
    enrich_candidates,
)
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputMetadataResolver as EnrichmentResolver,
)
from app.services.trade_up_input_enrichment import (
    TradeUpInputMetadata as EnrichmentTradeUpInputMetadata,
)
from app.services.tradeup_engine import InputItem

__all__ = (
    "TradeUpInputMetadata",
    "TradeUpInputMetadataResolver",
    "InMemoryTradeUpInputMetadataResolver",
    "candidates_to_input_items",
    "SyntheticBasketConfig",
    "SyntheticBasket",
    "SyntheticScaleCase",
    "build_synthetic_basket",
    "drive_pipeline_path",
    "drive_enrichment_path",
    "compare_partition_paths",
)


@dataclass(frozen=True, kw_only=True, repr=False)
class TradeUpInputMetadata:
    """Synthetic metadata mapping one known market_hash_name to engine fields."""

    market_hash_name: str
    collection_name: str
    rarity: str
    min_float: float
    max_float: float

    def __post_init__(self) -> None:
        for value in (self.market_hash_name, self.collection_name, self.rarity):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError("invalid synthetic trade-up metadata")
        if (
            type(self.min_float) is not float
            or type(self.max_float) is not float
            or not math.isfinite(self.min_float)
            or not math.isfinite(self.max_float)
            or self.min_float < 0
            or self.max_float > 1
            or self.min_float >= self.max_float
        ):
            raise ValueError("invalid synthetic trade-up metadata")


class TradeUpInputMetadataResolver(Protocol):
    """Resolve a market_hash_name to synthetic metadata or None."""

    def resolve(self, market_hash_name: str) -> TradeUpInputMetadata | None:
        """Return one synthetic record or None when unresolved."""


class InMemoryTradeUpInputMetadataResolver:
    """Test/synthetic metadata store. No I/O, no environment, no network."""

    def __init__(self, mapping: Mapping[str, TradeUpInputMetadata]) -> None:
        self._mapping = MappingProxyType(
            {key: value for key, value in mapping.items()}
        )

    def resolve(self, market_hash_name: str) -> TradeUpInputMetadata | None:
        return self._mapping.get(market_hash_name)


def candidates_to_input_items(
    candidates: Iterable[TradeUpInputCandidate],
    metadata_resolver: TradeUpInputMetadataResolver,
) -> list[InputItem]:
    """Convert TradeUpInputCandidates to engine InputItems via synthetic metadata.

    Candidates whose market_hash_name is None (unresolved) or not in the
    resolver are skipped. The returned list preserves the input order.
    """

    items: list[InputItem] = []
    for candidate in candidates:
        if candidate.market_hash_name is None:
            continue
        metadata = metadata_resolver.resolve(candidate.market_hash_name)
        if metadata is None:
            continue
        items.append(
            InputItem(
                market_hash_name=candidate.market_hash_name,
                collection_name=metadata.collection_name,
                rarity=metadata.rarity,
                actual_float=float(candidate.paintwear),
                min_float=metadata.min_float,
                max_float=metadata.max_float,
                price_cny=candidate.price_cny,
                stattrak=False,
                souvenir=False,
            )
        )
    return items


# ---------------------------------------------------------------------------
# Phase 13J-1 — Synthetic-scale validation helpers.
#
# Offline-only deterministic builders used by the scale-validation test suite.
# They never reach a live source. They compose the 13H-0 pipeline and the
# 13I-3 enrichment boundary; they do not mutate either.
# ---------------------------------------------------------------------------


_PIPELINE_SKIP_REASONS: tuple[str, ...] = ("unresolved", "missing_metadata")


@dataclass(frozen=True, kw_only=True, repr=False)
class SyntheticBasketConfig:
    """Closed specification for one deterministic synthetic candidate basket."""

    label: str
    seed: int
    collections: tuple[str, ...]
    inputs_per_collection: int
    price_cny_min: Decimal
    price_cny_max: Decimal
    paintwear_min: float = 0.05
    paintwear_max: float = 0.95
    stattrak_ratio: float = 0.0
    souvenir_ratio: float = 0.0
    unresolved_ratio: float = 0.0
    missing_metadata_ratio: float = 0.0

    def __post_init__(self) -> None:
        if type(self.label) is not str or not self.label or self.label != self.label.strip():
            raise ValueError("invalid synthetic basket config")
        if type(self.seed) is not int:
            raise ValueError("seed must be an int")
        if type(self.collections) is not tuple or not self.collections:
            raise ValueError("collections must be a non-empty tuple")
        for name in self.collections:
            if type(name) is not str or not name or name != name.strip():
                raise ValueError("collections must contain non-empty stripped strings")
        if type(self.inputs_per_collection) is not int or self.inputs_per_collection != 10:
            raise ValueError("inputs_per_collection must be exactly 10")
        if (
            type(self.price_cny_min) is not Decimal
            or type(self.price_cny_max) is not Decimal
            or not self.price_cny_min.is_finite()
            or not self.price_cny_max.is_finite()
            or self.price_cny_min <= 0
            or self.price_cny_max <= self.price_cny_min
        ):
            raise ValueError("price range must be 0 < min < max finite")
        if (
            type(self.paintwear_min) is not float
            or type(self.paintwear_max) is not float
            or not math.isfinite(self.paintwear_min)
            or not math.isfinite(self.paintwear_max)
            or self.paintwear_min < 0.0
            or self.paintwear_max > 1.0
            or self.paintwear_min >= self.paintwear_max
        ):
            raise ValueError("paintwear range must be 0 <= min < max <= 1")
        for ratio in (
            self.stattrak_ratio,
            self.souvenir_ratio,
            self.unresolved_ratio,
            self.missing_metadata_ratio,
        ):
            if type(ratio) is not float or not 0.0 <= ratio <= 1.0:
                raise ValueError("ratios must be floats in [0, 1]")


@dataclass(frozen=True, kw_only=True, repr=False)
class SyntheticBasket:
    """One deterministic synthetic basket: candidates + parallel metadata stores."""

    candidates: tuple[TradeUpInputCandidate, ...]
    metadata: Mapping[str, TradeUpInputMetadata]
    enrichment_metadata: Mapping[str, TradeUpInputMetadata]
    config: SyntheticBasketConfig

    def __post_init__(self) -> None:
        if type(self.candidates) is not tuple:
            raise ValueError("candidates must be an exact tuple")
        if type(self.metadata) is not MappingProxyType:
            raise ValueError("metadata must be an immutable mapping")
        if type(self.enrichment_metadata) is not MappingProxyType:
            raise ValueError("enrichment_metadata must be an immutable mapping")


@dataclass(frozen=True, kw_only=True, repr=False)
class SyntheticScaleCase:
    """One named scenario to run through the dual-path validation."""

    label: str
    basket: SyntheticBasket
    expected_unresolved_count: int
    expected_missing_metadata_count: int


@dataclass(frozen=True, kw_only=True, repr=False)
class PathComparison:
    """Partition comparison between the 13H-0 pipeline and the 13I-3 enrichment."""

    pipeline_kept_count: int
    pipeline_skip_histogram: Mapping[str, int]
    enrichment_kept_count: int
    enrichment_rejected_count: int
    enrichment_rejection_histogram: Mapping[TradeUpEnrichmentRejectionReason, int]
    partition_agreement: bool


def build_synthetic_basket(config: SyntheticBasketConfig) -> SyntheticBasket:
    """Build one deterministic synthetic basket from a closed configuration."""

    metadata_legacy: dict[str, TradeUpInputMetadata] = {}
    metadata_enrichment: dict[str, TradeUpInputMetadata] = {}
    for index, collection in enumerate(config.collections):
        item_template = TradeUpInputMetadata(
            market_hash_name=_item_name(collection, index),
            collection_name=collection,
            rarity="Restricted",
            min_float=config.paintwear_min,
            max_float=config.paintwear_max,
        )
        metadata_legacy[item_template.market_hash_name] = item_template
        metadata_enrichment[item_template.market_hash_name] = item_template

    candidates: list[TradeUpInputCandidate] = []
    rng = random.Random(config.seed)
    known_names = tuple(metadata_legacy.keys())
    total_per_collection = config.inputs_per_collection
    for collection_index, _collection in enumerate(config.collections):
        for slot in range(total_per_collection):
            bucket = rng.random()
            unresolved = bucket < config.unresolved_ratio
            missing = (
                not unresolved
                and bucket
                < config.unresolved_ratio + config.missing_metadata_ratio
            )
            name = _pick_name(rng, collection_index, slot, known_names, unresolved)
            stattrak = (
                not unresolved
                and not missing
                and rng.random() < config.stattrak_ratio
            )
            souvenir = (
                not unresolved
                and not missing
                and rng.random() < config.souvenir_ratio
            )
            listing_id = _listing_id(collection_index, slot, total_per_collection)
            goods_id = _goods_id(collection_index, slot, total_per_collection)
            asset_id = _asset_id(collection_index, slot, total_per_collection)
            paintwear = _draw_paintwear(
                rng,
                config.paintwear_min,
                config.paintwear_max,
            )
            price_cny = _draw_price(
                rng,
                config.price_cny_min,
                config.price_cny_max,
            )
            if missing:
                candidate_name: str | None = _absent_name(
                    rng,
                    collection_index,
                    slot,
                    known_names,
                )
            elif unresolved:
                candidate_name = None
            else:
                candidate_name = name
            candidates.append(
                TradeUpInputCandidate(
                    listing_id=listing_id,
                    goods_id=goods_id,
                    market_hash_name=candidate_name,
                    price_cny=price_cny,
                    paintwear=paintwear,
                    asset_id=asset_id,
                    source="buff",
                    stattrak=stattrak,
                    souvenir=souvenir,
                )
            )

    return SyntheticBasket(
        candidates=tuple(candidates),
        metadata=MappingProxyType(dict(metadata_legacy)),
        enrichment_metadata=MappingProxyType(dict(metadata_enrichment)),
        config=config,
    )


def drive_pipeline_path(basket: SyntheticBasket) -> tuple[list[InputItem], dict[str, int]]:
    """Drive the basket through the 13H-0 pipeline; report redacted skip counts."""

    resolver = InMemoryTradeUpInputMetadataResolver(basket.metadata)
    items: list[InputItem] = []
    skip_histogram: dict[str, int] = {reason: 0 for reason in _PIPELINE_SKIP_REASONS}
    for candidate in basket.candidates:
        if candidate.market_hash_name is None:
            skip_histogram["unresolved"] += 1
            continue
        if resolver.resolve(candidate.market_hash_name) is None:
            skip_histogram["missing_metadata"] += 1
            continue
        partial = candidates_to_input_items([candidate], resolver)
        if partial:
            items.append(partial[0])
    return items, skip_histogram


def drive_enrichment_path(
    basket: SyntheticBasket,
) -> TradeUpInputEnrichmentResult:
    """Drive the basket through the 13I-3 enrichment boundary."""

    enrichment_store: dict[str, EnrichmentTradeUpInputMetadata] = {
        name: _to_enrichment_metadata(metadata)
        for name, metadata in basket.enrichment_metadata.items()
    }
    resolver = EnrichmentResolver(enrichment_store)
    enricher = InMemoryTradeUpInputEnricher(resolver)
    return enrich_candidates(basket.candidates, enricher)


def _to_enrichment_metadata(
    metadata: TradeUpInputMetadata,
) -> EnrichmentTradeUpInputMetadata:
    """Adapt one legacy TradeUpInputMetadata to the enrichment class identity."""

    return EnrichmentTradeUpInputMetadata(
        market_hash_name=metadata.market_hash_name,
        collection_name=metadata.collection_name,
        rarity=metadata.rarity,
        min_float=metadata.min_float,
        max_float=metadata.max_float,
    )


def compare_partition_paths(
    pipeline_items: list[InputItem],
    pipeline_skip_histogram: Mapping[str, int],
    enrichment_result: TradeUpInputEnrichmentResult,
) -> PathComparison:
    """Compare partition counts and reason histograms across the two paths."""

    enrichment_histogram: dict[TradeUpEnrichmentRejectionReason, int] = {
        reason: 0 for reason in TradeUpEnrichmentRejectionReason
    }
    for rejection in enrichment_result.rejected:
        enrichment_histogram[rejection.reason] += 1

    skip_mapping = {
        TradeUpEnrichmentRejectionReason.MARKET_HASH_NAME_UNRESOLVED: (
            pipeline_skip_histogram.get("unresolved", 0)
        ),
        TradeUpEnrichmentRejectionReason.METADATA_NOT_FOUND: (
            pipeline_skip_histogram.get("missing_metadata", 0)
        ),
    }

    agreement = (
        len(pipeline_items) == len(enrichment_result.enriched)
        and skip_mapping[TradeUpEnrichmentRejectionReason.MARKET_HASH_NAME_UNRESOLVED]
        == enrichment_histogram[
            TradeUpEnrichmentRejectionReason.MARKET_HASH_NAME_UNRESOLVED
        ]
        and skip_mapping[TradeUpEnrichmentRejectionReason.METADATA_NOT_FOUND]
        == enrichment_histogram[TradeUpEnrichmentRejectionReason.METADATA_NOT_FOUND]
    )

    return PathComparison(
        pipeline_kept_count=len(pipeline_items),
        pipeline_skip_histogram=MappingProxyType(dict(pipeline_skip_histogram)),
        enrichment_kept_count=len(enrichment_result.enriched),
        enrichment_rejected_count=len(enrichment_result.rejected),
        enrichment_rejection_histogram=MappingProxyType(dict(enrichment_histogram)),
        partition_agreement=agreement,
    )


def _item_name(collection: str, index: int) -> str:
    return f"Synthetic Item | {collection} ({index:02d})"


def _pick_name(
    rng: random.Random,
    collection_index: int,
    slot: int,
    known_names: tuple[str, ...],
    unresolved: bool,
) -> str:
    if unresolved:
        return known_names[(collection_index * 31 + slot) % len(known_names)]
    return known_names[(collection_index * 31 + slot) % len(known_names)]


def _absent_name(
    rng: random.Random,
    collection_index: int,
    slot: int,
    known_names: tuple[str, ...],
) -> str:
    marker = rng.random()
    return (
        f"Synthetic Absent | {collection_index}-{slot}-{int(marker * 1_000_000)}"
    )


def _draw_paintwear(
    rng: random.Random,
    low: float,
    high: float,
) -> Decimal:
    value = rng.uniform(low, high)
    quantized = round(value, 6)
    return Decimal(str(quantized))


def _draw_price(
    rng: random.Random,
    low: Decimal,
    high: Decimal,
) -> Decimal:
    span = float(high - low)
    offset = rng.random() * span
    quantized = round(float(low) + offset, 2)
    return Decimal(str(quantized))


def _listing_id(collection_index: int, slot: int, total: int) -> str:
    return f"synthetic-listing-{collection_index:02d}-{slot:02d}-{total:02d}"


def _goods_id(collection_index: int, slot: int, total: int) -> str:
    return f"synthetic-goods-{collection_index:02d}-{slot:02d}-{total:02d}"


def _asset_id(collection_index: int, slot: int, total: int) -> str:
    return f"synthetic-asset-{collection_index:02d}-{slot:02d}-{total:02d}"


# Re-exported symbol aliases for the validation surface; keeps the public API
# list short while letting the test module find a stable name.
_enriched_item_type = TradeUpEnrichedInput
