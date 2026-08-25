from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

from app.services.market_scan_service import CandidateListing
from app.services.metadata_models import SkinMetadata
from app.services.metadata_service import get_next_rarity
from app.services.recipe_solver import (
    ConstructedRecipe,
    ConstructedRecipeSelection,
    RecipeSolverConfig,
    construct_recipe_selections,
)
from app.services.trade_up_input_enrichment import TradeUpEnrichedInput

_FIXED_ERROR = "invalid scanner recipe composition"

__all__ = (
    "ScannerRecipeCompositionError",
    "construct_scanner_recipe_selections",
    "is_current_standard_trade_up_output_eligible",
)


class ScannerRecipeCompositionError(ValueError):
    """Scanner recipe construction violated the compatibility contract."""

    def __init__(self) -> None:
        super().__init__(_FIXED_ERROR)


def is_current_standard_trade_up_output_eligible(
    *,
    skin: SkinMetadata,
    result_stattrak: bool,
) -> bool:
    """Return whether a canonical item can be a current standard output.

    Since Valve's May 21, 2026 rule change, standard trade-up outputs are
    never Souvenir. StatTrak remains an independent result mode and must
    match the homogeneous StatTrak mode of the inputs.
    """
    if type(skin) is not SkinMetadata or type(result_stattrak) is not bool:
        raise ScannerRecipeCompositionError
    return skin.souvenir is False and skin.stattrak is result_stattrak


def construct_scanner_recipe_selections(
    *,
    enriched_inputs: Sequence[TradeUpEnrichedInput],
    canonical_skins: Sequence[SkinMetadata],
    solver_config: RecipeSolverConfig,
) -> list[ConstructedRecipeSelection]:
    """Construct current-rule recipes without changing Protected Core.

    The protected solver still implements the historical rule that normal
    and Souvenir inputs cannot mix. This boundary therefore presents an
    internal eligibility view where the input Souvenir bit is false, gives
    the solver canonical non-Souvenir output rows only, and then restores
    the exact candidate-owned InputItems before returning. No projected
    InputItem can leave this function.
    """
    try:
        config = _copy_solver_config(solver_config)
        enriched = _validate_enriched_inputs(enriched_inputs)
        skins, skin_index = _validate_canonical_skins(canonical_skins)
        _validate_input_metadata(enriched, skin_index)

        filtered = _filter_candidate_owned_intrinsics(enriched, config)
        result: list[ConstructedRecipeSelection] = []
        for stattrak_mode in (False, True):
            bucket = tuple(
                item
                for item in filtered
                if item.candidate.stattrak is stattrak_mode
            )
            if len(bucket) < config.input_count:
                continue
            projection = _build_solver_projection(
                enriched_inputs=bucket,
                canonical_skins=skins,
                skin_index=skin_index,
                solver_config=config,
                stattrak_mode=stattrak_mode,
            )
            if not projection:
                continue
            compatibility_config = RecipeSolverConfig(
                input_rarity=config.input_rarity,
                input_count=config.input_count,
                sell_fee_rate=config.sell_fee_rate,
                max_candidates_per_collection=(
                    config.max_candidates_per_collection
                ),
                target_stattrak=stattrak_mode,
                target_souvenir=False,
            )
            selections = construct_recipe_selections(
                _to_legacy_candidates(bucket),
                projection,
                compatibility_config,
            )
            if type(selections) is not list:
                raise ScannerRecipeCompositionError
            result.extend(
                _rehydrate_selection(selection, bucket)
                for selection in selections
            )
        return result
    except MemoryError:
        raise
    except ScannerRecipeCompositionError:
        raise
    except Exception:
        raise ScannerRecipeCompositionError from None


def _copy_solver_config(value: object) -> RecipeSolverConfig:
    if type(value) is not RecipeSolverConfig:
        raise ScannerRecipeCompositionError
    return RecipeSolverConfig(
        input_rarity=value.input_rarity,
        input_count=value.input_count,
        sell_fee_rate=value.sell_fee_rate,
        max_candidates_per_collection=value.max_candidates_per_collection,
        target_stattrak=value.target_stattrak,
        target_souvenir=value.target_souvenir,
    )


def _validate_enriched_inputs(
    values: Sequence[TradeUpEnrichedInput],
) -> tuple[TradeUpEnrichedInput, ...]:
    if not isinstance(values, Sequence):
        raise ScannerRecipeCompositionError
    enriched = tuple(values)
    if any(type(value) is not TradeUpEnrichedInput for value in enriched):
        raise ScannerRecipeCompositionError
    listing_ids = tuple(value.candidate.listing_id for value in enriched)
    if len(listing_ids) != len(set(listing_ids)):
        raise ScannerRecipeCompositionError
    for value in enriched:
        candidate = value.candidate
        item = value.input_item
        if (
            candidate.market_hash_name is None
            or candidate.stattrak is None
            or candidate.souvenir is None
            or item.market_hash_name != candidate.market_hash_name
            or item.price_cny != candidate.price_cny
            or item.actual_float != float(candidate.paintwear)
            or item.stattrak is not candidate.stattrak
            or item.souvenir is not candidate.souvenir
        ):
            raise ScannerRecipeCompositionError
    return enriched


def _validate_canonical_skins(
    values: Sequence[SkinMetadata],
) -> tuple[tuple[SkinMetadata, ...], dict[str, SkinMetadata]]:
    if not isinstance(values, Sequence):
        raise ScannerRecipeCompositionError
    skins = tuple(values)
    if any(type(skin) is not SkinMetadata for skin in skins):
        raise ScannerRecipeCompositionError
    index: dict[str, SkinMetadata] = {}
    for skin in skins:
        if skin.market_hash_name in index:
            raise ScannerRecipeCompositionError
        index[skin.market_hash_name] = skin
    return skins, index


def _validate_input_metadata(
    enriched_inputs: Sequence[TradeUpEnrichedInput],
    skin_index: dict[str, SkinMetadata],
) -> None:
    for enriched in enriched_inputs:
        candidate = enriched.candidate
        item = enriched.input_item
        assert candidate.market_hash_name is not None
        skin = skin_index.get(candidate.market_hash_name)
        if skin is None:
            raise ScannerRecipeCompositionError
        if (
            skin.market_hash_name != item.market_hash_name
            or skin.collection_name != item.collection_name
            or skin.rarity != item.rarity
            or skin.min_float != item.min_float
            or skin.max_float != item.max_float
            or skin.stattrak is not candidate.stattrak
            or skin.souvenir is not candidate.souvenir
        ):
            raise ScannerRecipeCompositionError


def _filter_candidate_owned_intrinsics(
    enriched_inputs: Sequence[TradeUpEnrichedInput],
    solver_config: RecipeSolverConfig,
) -> tuple[TradeUpEnrichedInput, ...]:
    return tuple(
        enriched
        for enriched in enriched_inputs
        if (
            solver_config.target_stattrak is None
            or enriched.candidate.stattrak is solver_config.target_stattrak
        )
        and (
            solver_config.target_souvenir is None
            or enriched.candidate.souvenir is solver_config.target_souvenir
        )
    )


def _build_solver_projection(
    *,
    enriched_inputs: Sequence[TradeUpEnrichedInput],
    canonical_skins: Sequence[SkinMetadata],
    skin_index: dict[str, SkinMetadata],
    solver_config: RecipeSolverConfig,
    stattrak_mode: bool,
) -> list[SkinMetadata]:
    next_rarity = get_next_rarity(solver_config.input_rarity)
    if next_rarity is None:
        return []

    input_names = {
        enriched.candidate.market_hash_name for enriched in enriched_inputs
    }
    represented_collections = {
        enriched.input_item.collection_name for enriched in enriched_inputs
    }
    input_rows = [
        replace(skin_index[name], souvenir=False)
        for name in input_names
        if name is not None
    ]
    output_rows = [
        skin
        for skin in canonical_skins
        if skin.collection_name in represented_collections
        and skin.rarity == next_rarity
        and is_current_standard_trade_up_output_eligible(
            skin=skin,
            result_stattrak=stattrak_mode,
        )
    ]
    return [*input_rows, *output_rows]


def _to_legacy_candidates(
    enriched_inputs: Sequence[TradeUpEnrichedInput],
) -> list[CandidateListing]:
    now = datetime.now(UTC)
    return [
        CandidateListing(
            goods_id=enriched.candidate.goods_id,
            listing_id=enriched.candidate.listing_id,
            market_hash_name=enriched.candidate.market_hash_name,
            price_cny=enriched.candidate.price_cny,
            float_value=enriched.input_item.actual_float,
            paint_seed=None,
            inspect_link=None,
            source=enriched.candidate.source,
            scanned_at=now,
            raw=None,
        )
        for enriched in enriched_inputs
    ]


def _rehydrate_selection(
    value: object,
    enriched_inputs: Sequence[TradeUpEnrichedInput],
) -> ConstructedRecipeSelection:
    if type(value) is not ConstructedRecipeSelection:
        raise ScannerRecipeCompositionError
    index = {
        enriched.candidate.listing_id: enriched
        for enriched in enriched_inputs
    }
    if (
        len(value.selected_listing_ids) != len(set(value.selected_listing_ids))
        or len(value.selected_listing_ids) != len(value.recipe.input_items)
    ):
        raise ScannerRecipeCompositionError

    selected: list[TradeUpEnrichedInput] = []
    for listing_id in value.selected_listing_ids:
        enriched = index.get(listing_id)
        if enriched is None:
            raise ScannerRecipeCompositionError
        selected.append(enriched)

    canonical_items = tuple(enriched.input_item for enriched in selected)
    projected_items = tuple(
        replace(item, souvenir=False) for item in canonical_items
    )
    if value.recipe.input_items != projected_items:
        raise ScannerRecipeCompositionError

    return ConstructedRecipeSelection(
        recipe=ConstructedRecipe(
            input_items=canonical_items,
            tradeup_results=value.recipe.tradeup_results,
            paint_seeds=value.recipe.paint_seeds,
        ),
        selected_listing_ids=value.selected_listing_ids,
    )
