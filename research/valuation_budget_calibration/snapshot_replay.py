"""Fully offline replay of strict COMPLETE representative snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.recipe_solver import RecipeEnumerationConfig, RecipeSolverConfig
from app.services.scanner_recipe_composition import (
    enumerate_scanner_recipe_selections,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputEnricher,
    TradeUpEnrichedInput,
    TradeUpEnrichmentRejection,
)
from research.valuation_budget_calibration.measurement import (
    measure_output_name_sequences,
)
from research.valuation_budget_calibration.snapshot_protocol import (
    DEFAULT_CANDIDATE_STATES,
    DEFAULT_RECIPE_CANDIDATES,
    file_sha256,
)
from research.valuation_budget_calibration.snapshot_schema import (
    ObservationStatus,
    RepresentativeSnapshot,
    load_snapshot,
)
from research.valuation_budget_calibration.snapshot_storage import (
    verify_snapshot_hash,
)

_FIXED_ERROR = "representative snapshot replay failed"


class SnapshotReplayError(ValueError):
    """Snapshot cannot enter policy-facing offline replay."""

    def __init__(self, *, reason: str) -> None:
        super().__init__(_FIXED_ERROR)
        self.reason = reason


@dataclass(frozen=True, kw_only=True)
class SnapshotReplayResult:
    snapshot_id: str
    input_rarity: str
    stattrak_mode: str
    recipe_count: int
    run_unique_output_names: int
    per_recipe_unique_output_names: tuple[tuple[str, ...], ...]
    per_recipe_unique_counts: tuple[int, ...]
    recipe_2_incremental_new_names: int | None
    cross_recipe_overlap_count: int
    reuse_ratio_numerator: int
    reuse_ratio_denominator: int
    composition_states_explored: int
    participating_collections_by_recipe: tuple[tuple[str, ...], ...]

    @property
    def reuse_ratio(self) -> Fraction:
        return Fraction(
            self.reuse_ratio_numerator,
            self.reuse_ratio_denominator,
        )


def replay_snapshot_path(
    *,
    snapshot_path: Path,
    metadata_snapshot_path: Path,
    identity_snapshot_path: Path,
    expected_snapshot_sha256: str | None = None,
) -> SnapshotReplayResult:
    if expected_snapshot_sha256 is not None:
        verify_snapshot_hash(snapshot_path, expected_snapshot_sha256)
    snapshot = load_snapshot(snapshot_path)
    _verify_provenance(
        snapshot,
        metadata_snapshot_path=metadata_snapshot_path,
        identity_snapshot_path=identity_snapshot_path,
    )
    BuffCommunityIdentityResolver.from_snapshot_path(identity_snapshot_path)
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(
        metadata_snapshot_path
    )
    return replay_snapshot(snapshot=snapshot, metadata_resolver=metadata)


def replay_snapshot(
    *,
    snapshot: RepresentativeSnapshot,
    metadata_resolver: PinnedSkinMetadataResolver,
) -> SnapshotReplayResult:
    """Replay one strict COMPLETE snapshot with no external providers."""

    if snapshot.observation_status is not ObservationStatus.COMPLETE:
        raise SnapshotReplayError(reason="snapshot_not_complete")
    enricher = InMemoryTradeUpInputEnricher(metadata_resolver)
    enriched: list[TradeUpEnrichedInput] = []
    for page in snapshot.pages:
        for listing in page.listings:
            if listing.replay_status != "INCLUDED":
                raise SnapshotReplayError(reason="replay_listing_excluded")
            candidate = TradeUpInputCandidate(
                listing_id=listing.listing_reference,
                goods_id=listing.goods_id,
                market_hash_name=listing.market_hash_name,
                price_cny=Decimal(listing.price_cny),
                paintwear=Decimal(listing.paintwear),
                asset_id=listing.asset_reference,
                source=listing.source,
                stattrak=listing.stattrak,
                souvenir=listing.souvenir,
            )
            outcome = enricher.enrich(candidate)
            if isinstance(outcome, TradeUpEnrichmentRejection):
                raise SnapshotReplayError(reason="replay_enrichment_failed")
            if type(outcome) is not TradeUpEnrichedInput:
                raise SnapshotReplayError(reason="replay_enrichment_failed")
            enriched.append(outcome)

    composition = enumerate_scanner_recipe_selections(
        enriched_inputs=tuple(enriched),
        canonical_skins=metadata_resolver.skins,
        solver_config=RecipeSolverConfig(
            input_rarity=snapshot.stratum.input_rarity,
            input_count=10,
            sell_fee_rate=Decimal("0.025"),
        ),
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=DEFAULT_RECIPE_CANDIDATES,
            max_candidate_states_explored=DEFAULT_CANDIDATE_STATES,
        ),
    )
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
    return SnapshotReplayResult(
        snapshot_id=snapshot.snapshot_id,
        input_rarity=snapshot.stratum.input_rarity,
        stattrak_mode=snapshot.stratum.stattrak_mode,
        recipe_count=measurement.recipe_count,
        run_unique_output_names=measurement.run_unique_output_names,
        per_recipe_unique_output_names=measurement.per_recipe_unique_names,
        per_recipe_unique_counts=(
            measurement.per_recipe_unique_requested_output_name_counts
        ),
        recipe_2_incremental_new_names=(
            measurement.recipe_2_incremental_new_names
        ),
        cross_recipe_overlap_count=measurement.cross_recipe_overlap_count,
        reuse_ratio_numerator=measurement.reuse_ratio.numerator,
        reuse_ratio_denominator=measurement.reuse_ratio.denominator,
        composition_states_explored=composition.diagnostics.states_explored,
        participating_collections_by_recipe=participating,
    )


def _verify_provenance(
    snapshot: RepresentativeSnapshot,
    *,
    metadata_snapshot_path: Path,
    identity_snapshot_path: Path,
) -> None:
    provenance = snapshot.provenance
    if (
        Path(provenance.metadata_snapshot_path).as_posix()
        != provenance.metadata_snapshot_path
        or Path(provenance.identity_snapshot_path).as_posix()
        != provenance.identity_snapshot_path
        or not metadata_snapshot_path.as_posix().endswith(
            provenance.metadata_snapshot_path
        )
        or not identity_snapshot_path.as_posix().endswith(
            provenance.identity_snapshot_path
        )
        or file_sha256(metadata_snapshot_path)
        != provenance.metadata_snapshot_sha256
        or file_sha256(identity_snapshot_path)
        != provenance.identity_snapshot_sha256
    ):
        raise SnapshotReplayError(reason="pinned_provenance_mismatch")
