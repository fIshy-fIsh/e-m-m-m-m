"""Deterministic offline catalog census and scanner replay corpus.

This module reads only repository-pinned normalized snapshots and calls the
existing market-universe builder plus bounded scanner recipe composition. It
contains no HTTP, provider, cache, Redis, environment, or credential path.
Synthetic offer ordering is structural test input, not a market-frequency
model.
"""

from __future__ import annotations

import hashlib
import itertools
import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.market_universe_builder import (
    BoundedMarketUniverseBuilderError,
    MarketUniverseEntry,
    MarketUniverseSpec,
    SouvenirInclusion,
    StatTrakMode,
    UniverseAllocationStrategy,
    build_universe_goods_ids,
)
from app.services.metadata_models import RarityOrder, SkinMetadata
from app.services.metadata_service import get_next_rarity
from app.services.recipe_solver import RecipeEnumerationConfig, RecipeSolverConfig
from app.services.scanner_recipe_composition import (
    enumerate_scanner_recipe_selections,
    is_current_standard_trade_up_output_eligible,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputEnricher,
    enrich_candidates,
)
from research.valuation_budget_calibration.measurement import (
    measure_output_name_sequences,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IDENTITY_SNAPSHOT = REPOSITORY_ROOT / "data/identity/buff_identity_v1.json"
DEFAULT_METADATA_SNAPSHOT = REPOSITORY_ROOT / "data/metadata/skin_metadata_v1.json"
DEFAULT_ENUMERATION_CONFIG = RecipeEnumerationConfig(
    max_recipe_candidates_returned=2,
    max_candidate_states_explored=256,
)
INPUT_RARITIES = RarityOrder.ORDER[:-1]
REPLAY_SEEDS = (11, 23, 37, 53)
REPLAY_PATTERNS = (
    "single_cohort_high_reuse",
    "single_to_two_incremental",
    "mixed_two_high_reuse",
    "two_cohort_rotation",
    "mixed_three_high_reuse",
    "mixed_three_rotation",
)
EMPTY_CACHE_FRESH_RUN_INTERPRETATION = (
    "With an empty persistent cache and a fresh run memo, "
    "run_unique_output_names equals theoretical NEW-LIVE exact-name demand "
    "when every required output price must be fetched successfully."
)


@dataclass(frozen=True, kw_only=True)
class CatalogProvenance:
    identity_path: str
    identity_sha256: str
    identity_commit: str
    identity_count: int
    metadata_path: str
    metadata_sha256: str
    metadata_count: int


@dataclass(frozen=True, kw_only=True)
class CohortCensusRecord:
    input_rarity: str
    stattrak: bool
    collection_name: str
    input_identity_count: int
    output_unique_names: tuple[str, ...]

    @property
    def output_unique_name_count(self) -> int:
        return len(self.output_unique_names)


@dataclass(frozen=True, kw_only=True)
class StructuralMaximum:
    input_rarity: str
    stattrak: bool
    collections: tuple[str, ...]
    input_identity_capacity: int
    output_unique_name_count: int


@dataclass(frozen=True, kw_only=True)
class ReplayObservation:
    case_id: str
    seed: int
    ordering_pattern: str
    input_rarity: str
    stattrak: bool
    universe_goods_id_count: int
    universe_cohorts: tuple[str, ...]
    participating_collections_by_recipe: tuple[tuple[str, ...], ...]
    recipe_count: int
    per_recipe_unique_requested_output_name_counts: tuple[int, ...]
    run_unique_output_names: int
    cross_recipe_overlap_count: int
    recipe_2_incremental_new_names: int | None
    reuse_ratio_numerator: int
    reuse_ratio_denominator: int
    composition_states_explored: int


@dataclass(frozen=True, kw_only=True)
class SkippedReplayCase:
    input_rarity: str
    stattrak: bool
    reason: str


@dataclass(frozen=True, kw_only=True)
class CalibrationCorpus:
    provenance: CatalogProvenance
    census: tuple[CohortCensusRecord, ...]
    structural_maximum: StructuralMaximum
    default_universe_structural_maximum: StructuralMaximum
    observations: tuple[ReplayObservation, ...]
    skipped_cases: tuple[SkippedReplayCase, ...]


def build_calibration_corpus(
    *,
    identity_snapshot: Path = DEFAULT_IDENTITY_SNAPSHOT,
    metadata_snapshot: Path = DEFAULT_METADATA_SNAPSHOT,
) -> CalibrationCorpus:
    """Build the complete deterministic offline calibration corpus."""

    identity = BuffCommunityIdentityResolver.from_snapshot_path(identity_snapshot)
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(metadata_snapshot)
    provenance = CatalogProvenance(
        identity_path=_relative_path(identity_snapshot),
        identity_sha256=_sha256(identity_snapshot),
        identity_commit=identity.metadata.commit,
        identity_count=len(identity.identities),
        metadata_path=_relative_path(metadata_snapshot),
        metadata_sha256=_sha256(metadata_snapshot),
        metadata_count=len(metadata.skins),
    )
    census = build_structural_census(
        identity_resolver=identity,
        metadata_resolver=metadata,
    )
    structural_maximum = _find_structural_maximum(census)
    observations, skipped, default_maximum = build_replay_corpus(
        identity_resolver=identity,
        metadata_resolver=metadata,
    )
    return CalibrationCorpus(
        provenance=provenance,
        census=census,
        structural_maximum=structural_maximum,
        default_universe_structural_maximum=default_maximum,
        observations=observations,
        skipped_cases=skipped,
    )


def build_structural_census(
    *,
    identity_resolver: BuffCommunityIdentityResolver,
    metadata_resolver: PinnedSkinMetadataResolver,
) -> tuple[CohortCensusRecord, ...]:
    """Census eligible input cohorts and exact next-rarity output pools."""

    identity_names = {name for name, _goods_id in identity_resolver.identities}
    records: list[CohortCensusRecord] = []
    for rarity in INPUT_RARITIES:
        next_rarity = get_next_rarity(rarity)
        assert next_rarity is not None
        for stattrak in (False, True):
            collections = sorted(
                {
                    skin.collection_name
                    for skin in metadata_resolver.skins
                    if skin.market_hash_name in identity_names
                    and skin.rarity == rarity
                    and skin.stattrak is stattrak
                    and skin.collection_name is not None
                }
            )
            for collection_name in collections:
                outputs = _eligible_output_names(
                    metadata_resolver.skins,
                    collection_name=collection_name,
                    next_rarity=next_rarity,
                    stattrak=stattrak,
                )
                if not outputs:
                    continue
                try:
                    universe = build_universe_goods_ids(
                        identity_resolver=identity_resolver,
                        metadata_resolver=metadata_resolver,
                        spec=MarketUniverseSpec(
                            rarity=rarity,
                            stattrak_mode=_mode(stattrak),
                            souvenir_inclusion=SouvenirInclusion.INCLUDE,
                            cap=1,
                            collection_allowlist=(collection_name,),
                            allocation_strategy=(
                                UniverseAllocationStrategy.COHORT_DEPTH
                            ),
                            target_cohort_count=1,
                        ),
                    )
                except BoundedMarketUniverseBuilderError as exc:
                    if exc.reason == "universe_empty":
                        continue
                    raise
                cohort = universe.diagnostics.selected_cohorts[0]
                if cohort.canonical_output_count != len(outputs):
                    raise ValueError("census output count diverged from universe builder")
                records.append(
                    CohortCensusRecord(
                        input_rarity=rarity,
                        stattrak=stattrak,
                        collection_name=collection_name,
                        input_identity_count=cohort.catalog_capacity,
                        output_unique_names=outputs,
                    )
                )
    return tuple(
        sorted(
            records,
            key=lambda record: (
                INPUT_RARITIES.index(record.input_rarity),
                record.stattrak,
                record.collection_name,
            ),
        )
    )


def build_replay_corpus(
    *,
    identity_resolver: BuffCommunityIdentityResolver,
    metadata_resolver: PinnedSkinMetadataResolver,
) -> tuple[
    tuple[ReplayObservation, ...],
    tuple[SkippedReplayCase, ...],
    StructuralMaximum,
]:
    """Replay real default composition over deterministic synthetic orderings."""

    observations: list[ReplayObservation] = []
    skipped: list[SkippedReplayCase] = []
    default_structures: list[StructuralMaximum] = []
    for rarity in INPUT_RARITIES:
        for stattrak in (False, True):
            try:
                universe = build_universe_goods_ids(
                    identity_resolver=identity_resolver,
                    metadata_resolver=metadata_resolver,
                    spec=MarketUniverseSpec(
                        rarity=rarity,
                        stattrak_mode=_mode(stattrak),
                        souvenir_inclusion=SouvenirInclusion.INCLUDE,
                        cap=10,
                        allocation_strategy=(
                            UniverseAllocationStrategy.COHORT_DEPTH
                        ),
                        target_cohort_count=3,
                    ),
                )
            except BoundedMarketUniverseBuilderError as exc:
                if exc.reason != "universe_empty":
                    raise
                skipped.append(
                    SkippedReplayCase(
                        input_rarity=rarity,
                        stattrak=stattrak,
                        reason="no_eligible_default_cohort_depth_universe",
                    )
                )
                continue
            if len(universe.goods_ids) != 10:
                skipped.append(
                    SkippedReplayCase(
                        input_rarity=rarity,
                        stattrak=stattrak,
                        reason="default_universe_has_fewer_than_10_goods_ids",
                    )
                )
                continue
            cohort_names = tuple(
                cohort.key.collection_name
                for cohort in universe.diagnostics.selected_cohorts
            )
            if len(cohort_names) < 3:
                skipped.append(
                    SkippedReplayCase(
                        input_rarity=rarity,
                        stattrak=stattrak,
                        reason="default_universe_has_fewer_than_3_cohorts",
                    )
                )
                continue
            output_names = tuple(
                dict.fromkeys(
                    name
                    for collection in cohort_names
                    for name in _eligible_output_names(
                        metadata_resolver.skins,
                        collection_name=collection,
                        next_rarity=get_next_rarity(rarity) or "",
                        stattrak=stattrak,
                    )
                )
            )
            default_structures.append(
                StructuralMaximum(
                    input_rarity=rarity,
                    stattrak=stattrak,
                    collections=cohort_names,
                    input_identity_capacity=sum(
                        cohort.catalog_capacity
                        for cohort in universe.diagnostics.selected_cohorts
                    ),
                    output_unique_name_count=len(output_names),
                )
            )
            for seed_index, seed in enumerate(REPLAY_SEEDS):
                rotated_cohorts = (
                    cohort_names[seed_index % len(cohort_names) :]
                    + cohort_names[: seed_index % len(cohort_names)]
                )
                for pattern in REPLAY_PATTERNS:
                    observation = _run_replay_case(
                        rarity=rarity,
                        stattrak=stattrak,
                        seed=seed,
                        pattern=pattern,
                        role_collections=rotated_cohorts,
                        selected_entries=universe.selected_entries,
                        metadata_resolver=metadata_resolver,
                    )
                    observations.append(observation)
    if not observations or not default_structures:
        raise ValueError("calibration replay corpus is empty")
    default_maximum = max(
        default_structures,
        key=lambda value: (
            value.output_unique_name_count,
            value.input_rarity,
            value.stattrak,
            value.collections,
        ),
    )
    return tuple(observations), tuple(skipped), default_maximum


def _run_replay_case(
    *,
    rarity: str,
    stattrak: bool,
    seed: int,
    pattern: str,
    role_collections: tuple[str, ...],
    selected_entries: tuple[MarketUniverseEntry, ...],
    metadata_resolver: PinnedSkinMetadataResolver,
) -> ReplayObservation:
    planned_collections = _planned_collections(pattern, role_collections)
    candidates = _build_candidates(
        selected_entries=selected_entries,
        planned_collections=planned_collections,
        seed=seed,
        pattern=pattern,
        metadata_resolver=metadata_resolver,
    )
    enrichment = enrich_candidates(
        candidates,
        InMemoryTradeUpInputEnricher(metadata_resolver),
    )
    if enrichment.rejected:
        raise ValueError("offline replay candidate unexpectedly failed enrichment")
    composition = enumerate_scanner_recipe_selections(
        enriched_inputs=enrichment.enriched,
        canonical_skins=metadata_resolver.skins,
        solver_config=RecipeSolverConfig(
            input_rarity=rarity,
            input_count=10,
            sell_fee_rate=Decimal("0.025"),
        ),
        enumeration_config=DEFAULT_ENUMERATION_CONFIG,
    )
    if len(composition.selections) != 2:
        raise ValueError("offline replay did not return default two candidates")
    output_sequences = tuple(
        tuple(
            result.output_market_hash_name
            for result in selection.recipe.tradeup_results
        )
        for selection in composition.selections
    )
    measurement = measure_output_name_sequences(output_sequences)
    participating = tuple(
        tuple(
            dict.fromkeys(
                item.collection_name for item in selection.recipe.input_items
            )
        )
        for selection in composition.selections
    )
    diagnostics = composition.diagnostics
    return ReplayObservation(
        case_id=f"{rarity}|{'stattrak' if stattrak else 'normal'}|{pattern}|{seed}",
        seed=seed,
        ordering_pattern=pattern,
        input_rarity=rarity,
        stattrak=stattrak,
        universe_goods_id_count=len(selected_entries),
        universe_cohorts=tuple(
            dict.fromkeys(entry.collection_name for entry in selected_entries)
        ),
        participating_collections_by_recipe=participating,
        recipe_count=measurement.recipe_count,
        per_recipe_unique_requested_output_name_counts=(
            measurement.per_recipe_unique_requested_output_name_counts
        ),
        run_unique_output_names=measurement.run_unique_output_names,
        cross_recipe_overlap_count=measurement.cross_recipe_overlap_count,
        recipe_2_incremental_new_names=(
            measurement.recipe_2_incremental_new_names
        ),
        reuse_ratio_numerator=measurement.reuse_ratio.numerator,
        reuse_ratio_denominator=measurement.reuse_ratio.denominator,
        composition_states_explored=diagnostics.states_explored,
    )


def _planned_collections(
    pattern: str,
    roles: tuple[str, ...],
) -> tuple[str, ...]:
    if len(roles) < 3:
        raise ValueError("replay patterns require three collection roles")
    a, b, c = roles[:3]
    plans = {
        "single_cohort_high_reuse": (a,) * 11,
        "single_to_two_incremental": (a,) * 10 + (b,),
        "mixed_two_high_reuse": (a,) * 5 + (b,) * 5 + (a,),
        "two_cohort_rotation": (a,) * 9 + (b, c),
        "mixed_three_high_reuse": (a,) * 4 + (b,) * 3 + (c,) * 3 + (a,),
        "mixed_three_rotation": (a,) * 8 + (b, c, b),
    }
    try:
        return plans[pattern]
    except KeyError as exc:
        raise ValueError("unsupported replay ordering pattern") from exc


def _build_candidates(
    *,
    selected_entries: tuple[MarketUniverseEntry, ...],
    planned_collections: tuple[str, ...],
    seed: int,
    pattern: str,
    metadata_resolver: PinnedSkinMetadataResolver,
) -> tuple[TradeUpInputCandidate, ...]:
    entries_by_collection: dict[str, list[MarketUniverseEntry]] = defaultdict(list)
    for entry in selected_entries:
        entries_by_collection[entry.collection_name].append(entry)
    rng = random.Random(f"phase15a|{seed}|{pattern}")
    for entries in entries_by_collection.values():
        rng.shuffle(entries)
    usage: dict[str, int] = defaultdict(int)
    candidates: list[TradeUpInputCandidate] = []
    for rank, collection_name in enumerate(planned_collections):
        entries = entries_by_collection[collection_name]
        entry = entries[usage[collection_name] % len(entries)]
        usage[collection_name] += 1
        candidates.append(
            _candidate_for_rank(
                entry=entry,
                metadata_resolver=metadata_resolver,
                rank=rank,
                seed=seed,
                suffix=f"primary-{rank:02d}",
                normalized_float=Decimal("0.05")
                + Decimal(rank) / Decimal("1000"),
            )
        )
    for index, entry in enumerate(selected_entries):
        candidates.append(
            _candidate_for_rank(
                entry=entry,
                metadata_resolver=metadata_resolver,
                rank=len(planned_collections) + index,
                seed=seed,
                suffix=f"tail-{index:02d}",
                normalized_float=Decimal("0.70")
                + Decimal(index) / Decimal("100"),
            )
        )
    return tuple(candidates)


def _candidate_for_rank(
    *,
    entry: MarketUniverseEntry,
    metadata_resolver: PinnedSkinMetadataResolver,
    rank: int,
    seed: int,
    suffix: str,
    normalized_float: Decimal,
) -> TradeUpInputCandidate:
    metadata = metadata_resolver.resolve(entry.market_hash_name)
    if metadata is None:
        raise ValueError("selected universe entry has no metadata")
    minimum = Decimal(str(metadata.min_float))
    maximum = Decimal(str(metadata.max_float))
    paintwear = minimum + normalized_float * (maximum - minimum)
    return TradeUpInputCandidate(
        listing_id=f"phase15a-{seed}-{suffix}-{entry.goods_id}",
        goods_id=entry.goods_id,
        market_hash_name=entry.market_hash_name,
        price_cny=Decimal("10") + Decimal(rank) / Decimal("1000"),
        paintwear=paintwear,
        asset_id=f"phase15a-asset-{seed}-{suffix}-{entry.goods_id}",
        source="phase15a-offline-replay",
        stattrak=entry.stattrak,
        souvenir=entry.souvenir,
    )


def _find_structural_maximum(
    census: Sequence[CohortCensusRecord],
) -> StructuralMaximum:
    best: StructuralMaximum | None = None
    grouped: dict[tuple[str, bool], list[CohortCensusRecord]] = defaultdict(list)
    for record in census:
        grouped[(record.input_rarity, record.stattrak)].append(record)
    for (rarity, stattrak), records in grouped.items():
        for count in (1, 2, 3):
            for combination in itertools.combinations(records, count):
                if sum(record.input_identity_count for record in combination) < 10:
                    continue
                names = {
                    name
                    for record in combination
                    for name in record.output_unique_names
                }
                candidate = StructuralMaximum(
                    input_rarity=rarity,
                    stattrak=stattrak,
                    collections=tuple(
                        record.collection_name for record in combination
                    ),
                    input_identity_capacity=sum(
                        record.input_identity_count for record in combination
                    ),
                    output_unique_name_count=len(names),
                )
                if best is None or (
                    candidate.output_unique_name_count,
                    candidate.input_identity_capacity,
                    candidate.input_rarity,
                    candidate.stattrak,
                    candidate.collections,
                ) > (
                    best.output_unique_name_count,
                    best.input_identity_capacity,
                    best.input_rarity,
                    best.stattrak,
                    best.collections,
                ):
                    best = candidate
    if best is None:
        raise ValueError("structural census has no constructible cohort combination")
    return best


def _eligible_output_names(
    skins: Sequence[SkinMetadata],
    *,
    collection_name: str,
    next_rarity: str,
    stattrak: bool,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                skin.market_hash_name
                for skin in skins
                if skin.collection_name == collection_name
                and skin.rarity == next_rarity
                and is_current_standard_trade_up_output_eligible(
                    skin=skin,
                    result_stattrak=stattrak,
                )
            }
        )
    )


def _mode(stattrak: bool) -> StatTrakMode:
    return StatTrakMode.STATTRAK if stattrak else StatTrakMode.NORMAL


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()
