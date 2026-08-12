from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from app.services.live_metadata_catalog import (
    LiveCandidateBinding,
    LiveCandidateClassification,
    LiveSolverBucket,
    LiveSolverBucketKey,
    SkinMetadataCatalog,
    classify_steamapis_snapshot,
)
from app.services.metadata_service import get_next_rarity
from app.services.recipe_solver import (
    ConstructedRecipe,
    ConstructedRecipeSelection,
    RecipeSolverConfig,
    construct_recipe_selections,
)
from app.services.steamapis_offer_pool import SteamApisOfferPoolSnapshot
from app.services.tradeup_engine import InputItem, TradeupResult

_FIXED_ERROR_MESSAGE = "invalid live recipe construction contract"

__all__ = (
    "LiveRecipeConstructionError",
    "LiveConstructedRecipe",
    "LiveRecipeConstructionResult",
    "construct_live_recipes",
)


class LiveRecipeConstructionError(ValueError):
    """A value or operation violated the live construction contract."""

    def __init__(self) -> None:
        super().__init__(_FIXED_ERROR_MESSAGE)


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveConstructedRecipe:
    """One constructed recipe with exact selected source provenance."""

    recipe: ConstructedRecipe
    selected_source_offer_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        try:
            recipe = _copy_recipe(self.recipe)
            if type(self.selected_source_offer_ids) is not tuple:
                raise LiveRecipeConstructionError
            source_offer_ids = tuple(
                _validate_source_offer_id(source_offer_id)
                for source_offer_id in self.selected_source_offer_ids
            )
            if (
                len(source_offer_ids) != len(recipe.input_items)
                or len(source_offer_ids) != len(set(source_offer_ids))
            ):
                raise LiveRecipeConstructionError
            object.__setattr__(self, "recipe", recipe)
            object.__setattr__(self, "selected_source_offer_ids", source_offer_ids)
        except MemoryError:
            raise
        except Exception:
            raise LiveRecipeConstructionError from None


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveRecipeConstructionResult:
    """Complete classification and ordered offline construction results."""

    classification: LiveCandidateClassification
    recipes: tuple[LiveConstructedRecipe, ...]

    def __post_init__(self) -> None:
        try:
            classification = _copy_classification(self.classification)
            if type(self.recipes) is not tuple:
                raise LiveRecipeConstructionError
            recipes = tuple(_copy_live_recipe(recipe) for recipe in self.recipes)
            eligible_ids = {
                binding.source_offer_id for binding in classification.eligible
            }
            selected_ids = [
                source_offer_id
                for recipe in recipes
                for source_offer_id in recipe.selected_source_offer_ids
            ]
            if (
                any(source_offer_id not in eligible_ids for source_offer_id in selected_ids)
                or len(selected_ids) != len(set(selected_ids))
            ):
                raise LiveRecipeConstructionError
            object.__setattr__(self, "classification", classification)
            object.__setattr__(self, "recipes", recipes)
        except MemoryError:
            raise
        except Exception:
            raise LiveRecipeConstructionError from None


def construct_live_recipes(
    *,
    snapshot: SteamApisOfferPoolSnapshot,
    catalog: SkinMetadataCatalog,
    solver_config: RecipeSolverConfig,
) -> LiveRecipeConstructionResult:
    """Construct recipes from one immutable live snapshot without evaluation."""

    try:
        if type(snapshot) is not SteamApisOfferPoolSnapshot:
            raise LiveRecipeConstructionError
        if type(catalog) is not SkinMetadataCatalog:
            raise LiveRecipeConstructionError
        config = _copy_solver_config(solver_config)
        classification = classify_steamapis_snapshot(snapshot, catalog)
        live_recipes: list[LiveConstructedRecipe] = []

        for bucket in classification.buckets:
            if not _matches_config(bucket.key, config):
                continue
            live_recipes.extend(
                _construct_bucket_recipes(
                    bucket=bucket,
                    catalog=catalog,
                    solver_config=config,
                )
            )

        return LiveRecipeConstructionResult(
            classification=classification,
            recipes=tuple(live_recipes),
        )
    except MemoryError:
        raise
    except Exception:
        raise LiveRecipeConstructionError from None


def _construct_bucket_recipes(
    *,
    bucket: LiveSolverBucket,
    catalog: SkinMetadataCatalog,
    solver_config: RecipeSolverConfig,
) -> tuple[LiveConstructedRecipe, ...]:
    listing_bindings = _index_bucket_bindings(bucket)
    next_rarity = get_next_rarity(bucket.key.input_rarity)
    if next_rarity is None:
        return ()

    output_key = LiveSolverBucketKey(
        input_rarity=next_rarity,
        stattrak=bucket.key.stattrak,
        souvenir=bucket.key.souvenir,
    )
    skins = [
        *catalog.get_by_solver_bucket_key(bucket.key),
        *catalog.get_by_solver_bucket_key(output_key),
    ]
    bucket_config = RecipeSolverConfig(
        input_rarity=solver_config.input_rarity,
        input_count=solver_config.input_count,
        sell_fee_rate=solver_config.sell_fee_rate,
        max_candidates_per_collection=solver_config.max_candidates_per_collection,
        target_stattrak=bucket.key.stattrak,
        target_souvenir=bucket.key.souvenir,
    )
    selections = construct_recipe_selections(
        [binding.candidate for binding in bucket.bindings],
        skins,
        bucket_config,
    )
    if type(selections) is not list:
        raise LiveRecipeConstructionError

    return tuple(
        _bind_selection_to_source_ids(selection, listing_bindings)
        for selection in selections
    )


def _index_bucket_bindings(
    bucket: LiveSolverBucket,
) -> dict[str, LiveCandidateBinding]:
    indexed: dict[str, LiveCandidateBinding] = {}
    for binding in bucket.bindings:
        listing_id = binding.candidate.listing_id
        if listing_id in indexed:
            raise LiveRecipeConstructionError
        indexed[listing_id] = binding
    return indexed


def _bind_selection_to_source_ids(
    selection: object,
    listing_bindings: dict[str, LiveCandidateBinding],
) -> LiveConstructedRecipe:
    if type(selection) is not ConstructedRecipeSelection:
        raise LiveRecipeConstructionError
    validated = ConstructedRecipeSelection(
        recipe=selection.recipe,
        selected_listing_ids=selection.selected_listing_ids,
    )
    if len(validated.selected_listing_ids) != 10 or len(
        validated.selected_listing_ids
    ) != len(set(validated.selected_listing_ids)):
        raise LiveRecipeConstructionError

    selected_bindings: list[LiveCandidateBinding] = []
    for listing_id in validated.selected_listing_ids:
        binding = listing_bindings.get(listing_id)
        if binding is None:
            raise LiveRecipeConstructionError
        selected_bindings.append(binding)

    expected_input_items = tuple(
        _binding_input_item(binding) for binding in selected_bindings
    )
    expected_paint_seeds = tuple(
        binding.candidate.paint_seed
        for binding in selected_bindings
        if binding.candidate.paint_seed is not None
    )
    if (
        validated.recipe.input_items != expected_input_items
        or validated.recipe.paint_seeds != expected_paint_seeds
    ):
        raise LiveRecipeConstructionError

    return LiveConstructedRecipe(
        recipe=validated.recipe,
        selected_source_offer_ids=tuple(
            binding.source_offer_id for binding in selected_bindings
        ),
    )


def _binding_input_item(binding: LiveCandidateBinding) -> InputItem:
    candidate = binding.candidate
    skin = binding.skin_metadata
    if candidate.market_hash_name is None or candidate.float_value is None:
        raise LiveRecipeConstructionError
    if skin.collection_name is None:
        raise LiveRecipeConstructionError
    return InputItem(
        market_hash_name=candidate.market_hash_name,
        collection_name=skin.collection_name,
        rarity=skin.rarity,
        actual_float=candidate.float_value,
        min_float=skin.min_float,
        max_float=skin.max_float,
        price_cny=candidate.price_cny,
        stattrak=skin.stattrak,
        souvenir=skin.souvenir,
    )


def _matches_config(
    key: LiveSolverBucketKey,
    config: RecipeSolverConfig,
) -> bool:
    return (
        key.input_rarity == config.input_rarity
        and (
            config.target_stattrak is None
            or key.stattrak == config.target_stattrak
        )
        and (
            config.target_souvenir is None
            or key.souvenir == config.target_souvenir
        )
    )


def _copy_solver_config(value: object) -> RecipeSolverConfig:
    if type(value) is not RecipeSolverConfig:
        raise LiveRecipeConstructionError
    if type(value.input_rarity) is not str:
        raise LiveRecipeConstructionError
    if type(value.input_count) is not int:
        raise LiveRecipeConstructionError
    if type(value.sell_fee_rate) is not Decimal or not value.sell_fee_rate.is_finite():
        raise LiveRecipeConstructionError
    if value.max_candidates_per_collection is not None and type(
        value.max_candidates_per_collection
    ) is not int:
        raise LiveRecipeConstructionError
    if value.target_stattrak is not None and type(value.target_stattrak) is not bool:
        raise LiveRecipeConstructionError
    if value.target_souvenir is not None and type(value.target_souvenir) is not bool:
        raise LiveRecipeConstructionError
    return RecipeSolverConfig(
        input_rarity=str.__str__(value.input_rarity),
        input_count=value.input_count,
        sell_fee_rate=value.sell_fee_rate,
        max_candidates_per_collection=value.max_candidates_per_collection,
        target_stattrak=value.target_stattrak,
        target_souvenir=value.target_souvenir,
    )


def _copy_classification(value: object) -> LiveCandidateClassification:
    if type(value) is not LiveCandidateClassification:
        raise LiveRecipeConstructionError
    return LiveCandidateClassification(
        eligible=value.eligible,
        rejected=value.rejected,
        buckets=value.buckets,
    )


def _copy_live_recipe(value: object) -> LiveConstructedRecipe:
    if type(value) is not LiveConstructedRecipe:
        raise LiveRecipeConstructionError
    return LiveConstructedRecipe(
        recipe=value.recipe,
        selected_source_offer_ids=value.selected_source_offer_ids,
    )


def _copy_recipe(value: object) -> ConstructedRecipe:
    if type(value) is not ConstructedRecipe:
        raise LiveRecipeConstructionError
    return ConstructedRecipe(
        input_items=tuple(_copy_input_item(item) for item in value.input_items),
        tradeup_results=tuple(
            _copy_tradeup_result(result) for result in value.tradeup_results
        ),
        paint_seeds=tuple(value.paint_seeds),
    )


def _copy_input_item(value: object) -> InputItem:
    if type(value) is not InputItem:
        raise LiveRecipeConstructionError
    _validate_exact_string(value.market_hash_name)
    _validate_exact_string(value.collection_name)
    _validate_exact_string(value.rarity)
    _validate_finite_float(value.actual_float)
    _validate_finite_float(value.min_float)
    _validate_finite_float(value.max_float)
    _validate_finite_decimal(value.price_cny)
    if type(value.stattrak) is not bool or type(value.souvenir) is not bool:
        raise LiveRecipeConstructionError
    return InputItem(
        market_hash_name=str.__str__(value.market_hash_name),
        collection_name=str.__str__(value.collection_name),
        rarity=str.__str__(value.rarity),
        actual_float=value.actual_float,
        min_float=value.min_float,
        max_float=value.max_float,
        price_cny=value.price_cny,
        stattrak=value.stattrak,
        souvenir=value.souvenir,
    )


def _copy_tradeup_result(value: object) -> TradeupResult:
    if type(value) is not TradeupResult:
        raise LiveRecipeConstructionError
    _validate_exact_string(value.output_market_hash_name)
    _validate_finite_float(value.probability)
    _validate_finite_float(value.output_float)
    _validate_exact_string(value.output_wear)
    _validate_finite_decimal(value.estimated_price_cny)
    _validate_finite_decimal(value.expected_value_contribution)
    return TradeupResult(
        output_market_hash_name=str.__str__(value.output_market_hash_name),
        probability=value.probability,
        output_float=value.output_float,
        output_wear=str.__str__(value.output_wear),
        estimated_price_cny=value.estimated_price_cny,
        expected_value_contribution=value.expected_value_contribution,
    )


def _validate_source_offer_id(value: object) -> str:
    source_offer_id = _validate_exact_string(value)
    if len(source_offer_id) != 64 or any(
        character not in "0123456789abcdef" for character in source_offer_id
    ):
        raise LiveRecipeConstructionError
    return source_offer_id


def _validate_exact_string(value: object) -> str:
    if type(value) is not str:
        raise LiveRecipeConstructionError
    return str.__str__(value)


def _validate_finite_float(value: object) -> None:
    if type(value) is not float or not math.isfinite(value):
        raise LiveRecipeConstructionError


def _validate_finite_decimal(value: object) -> None:
    if type(value) is not Decimal or not value.is_finite():
        raise LiveRecipeConstructionError
