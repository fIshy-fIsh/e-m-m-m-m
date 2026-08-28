from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.services.live_metadata_catalog import (
    LiveCandidateBinding,
    LiveCandidateClassification,
    LiveSolverBucket,
    LiveSolverBucketKey,
)
from app.services.live_recipe_construction import (
    LiveConstructedRecipe,
    LiveRecipeConstructionResult,
)
from app.services.market_scan_service import CandidateListing
from app.services.metadata_models import SkinMetadata
from app.services.recipe_solver import (
    ConstructedRecipeSelection,
    RecipeSolverConfig,
    construct_recipe_selections,
)
from app.services.risk_filter import RiskFilterConfig

_FIXED_ERROR_MESSAGE = "invalid SteamDT BUFF live recipe fixture contract"
_COMPATIBILITY_SOURCE = "steamapis:buff163"
_INPUT_MARKET_HASH_NAME = "Synthetic SteamDT BUFF Fixture Input"
_COLLECTION_NAME = "Synthetic SteamDT BUFF Fixture Collection"
_INPUT_RARITY = "Restricted"
_OUTPUT_RARITY = "Classified"
_INPUT_FLOAT = 0.0625
_FIXED_SCANNED_AT = datetime(2026, 8, 15, tzinfo=UTC)
_SOURCE_IDS = tuple(f"{index:064x}" for index in range(1, 11))
_PAINT_SEEDS = tuple(range(1001, 1011))

STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME = (
    "M4A4 | Desolate Space (Factory New)"
)

__all__ = (
    "SteamDTBuffLiveRecipeFixtureError",
    "SteamDTBuffLiveRecipeFixture",
    "STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME",
    "build_steamdt_buff_live_recipe_fixture",
    "build_verified_steamdt_buff_live_recipe_fixture",
)


class SteamDTBuffLiveRecipeFixtureError(ValueError):
    """A value violated the deterministic synthetic fixture contract."""

    def __init__(self) -> None:
        super().__init__(_FIXED_ERROR_MESSAGE)


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamDTBuffLiveRecipeFixture:
    """Detached construction and configs for one synthetic one-output recipe."""

    construction_result: LiveRecipeConstructionResult
    solver_config: RecipeSolverConfig
    risk_config: RiskFilterConfig

    def __post_init__(self) -> None:
        try:
            construction = _copy_construction_result(self.construction_result)
            solver = _copy_solver_config(self.solver_config)
            risk = _copy_risk_config(self.risk_config)
            _validate_fixture_contract(construction, solver, risk)
            object.__setattr__(self, "construction_result", construction)
            object.__setattr__(self, "solver_config", solver)
            object.__setattr__(self, "risk_config", risk)
        except MemoryError:
            raise
        except Exception:
            raise SteamDTBuffLiveRecipeFixtureError from None


@dataclass(frozen=True, kw_only=True)
class _FixtureInputs:
    candidates: tuple[CandidateListing, ...]
    input_skin: SkinMetadata
    output_skin: SkinMetadata
    source_id_by_listing_id: dict[str, str]


def build_steamdt_buff_live_recipe_fixture(
    *,
    output_market_hash_name: str,
) -> SteamDTBuffLiveRecipeFixture:
    """Build one deterministic synthetic recipe through production authorities."""

    try:
        output_name = _validate_output_market_hash_name(output_market_hash_name)
        solver = _build_solver_config()
        risk = _build_risk_config()
        inputs = _build_fixture_inputs(output_name)
        selections = construct_recipe_selections(
            list(inputs.candidates),
            [inputs.input_skin, inputs.output_skin],
            solver,
        )
        selection = _validate_selection(selections, inputs)
        construction = _build_live_construction(selection, inputs)
        fixture = SteamDTBuffLiveRecipeFixture(
            construction_result=construction,
            solver_config=solver,
            risk_config=risk,
        )
        derived_name = fixture.construction_result.recipes[0].recipe.tradeup_results[
            0
        ].output_market_hash_name
        if derived_name != inputs.output_skin.market_hash_name:
            raise SteamDTBuffLiveRecipeFixtureError
        return fixture
    except MemoryError:
        raise
    except SteamDTBuffLiveRecipeFixtureError:
        raise
    except Exception:
        raise SteamDTBuffLiveRecipeFixtureError from None


def build_verified_steamdt_buff_live_recipe_fixture(
) -> SteamDTBuffLiveRecipeFixture:
    """Build the deterministic fixture with the verified output identity."""

    return build_steamdt_buff_live_recipe_fixture(
        output_market_hash_name=(
            STEAMDT_BUFF_LIVE_RECIPE_VERIFIED_OUTPUT_MARKET_HASH_NAME
        )
    )


def _validate_output_market_hash_name(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or value == _INPUT_MARKET_HASH_NAME
    ):
        raise SteamDTBuffLiveRecipeFixtureError
    return str.__str__(value)


def _build_solver_config() -> RecipeSolverConfig:
    return RecipeSolverConfig(
        input_rarity=_INPUT_RARITY,
        input_count=10,
        sell_fee_rate=Decimal("0.025"),
        max_candidates_per_collection=10,
        target_stattrak=False,
        target_souvenir=False,
    )


def _build_risk_config() -> RiskFilterConfig:
    return RiskFilterConfig(
        min_roi=Decimal("-1"),
        min_expected_profit_cny=Decimal("-1000"),
        max_worst_case_loss_pct=Decimal("1"),
        min_profit_probability=0.0,
        max_input_total_cost_cny=Decimal("55.00"),
        min_liquidity_score=None,
        exclude_souvenir=False,
        exclude_stattrak=False,
        exclude_special_pattern_seeds=None,
    )


def _build_fixture_inputs(output_market_hash_name: str) -> _FixtureInputs:
    input_skin = SkinMetadata(
        market_hash_name=_INPUT_MARKET_HASH_NAME,
        name=_INPUT_MARKET_HASH_NAME,
        weapon=None,
        rarity=_INPUT_RARITY,
        category=None,
        collection_name=_COLLECTION_NAME,
        min_float=0.0,
        max_float=1.0,
        stattrak=False,
        souvenir=False,
        paint_index=None,
        raw=None,
    )
    output_skin = SkinMetadata(
        market_hash_name=output_market_hash_name,
        name=output_market_hash_name,
        weapon=None,
        rarity=_OUTPUT_RARITY,
        category=None,
        collection_name=_COLLECTION_NAME,
        min_float=0.0,
        max_float=1.0,
        stattrak=False,
        souvenir=False,
        paint_index=None,
        raw=None,
    )

    candidates: list[CandidateListing] = []
    source_id_by_listing_id: dict[str, str] = {}
    for index, (source_id, paint_seed) in enumerate(
        zip(_SOURCE_IDS, _PAINT_SEEDS, strict=True),
        start=1,
    ):
        compatibility_id = f"{_COMPATIBILITY_SOURCE}:{source_id}"
        candidate = CandidateListing(
            goods_id=compatibility_id,
            listing_id=compatibility_id,
            market_hash_name=_INPUT_MARKET_HASH_NAME,
            price_cny=Decimal(f"{index}.00"),
            float_value=_INPUT_FLOAT,
            paint_seed=paint_seed,
            inspect_link=None,
            source=_COMPATIBILITY_SOURCE,
            scanned_at=_FIXED_SCANNED_AT,
            raw=None,
        )
        candidates.append(candidate)
        source_id_by_listing_id[candidate.listing_id] = source_id

    return _FixtureInputs(
        candidates=tuple(candidates),
        input_skin=input_skin,
        output_skin=output_skin,
        source_id_by_listing_id=source_id_by_listing_id,
    )


def _validate_selection(
    value: object,
    inputs: _FixtureInputs,
) -> ConstructedRecipeSelection:
    if type(value) is not list or len(value) != 1:
        raise SteamDTBuffLiveRecipeFixtureError
    selection = value[0]
    if type(selection) is not ConstructedRecipeSelection:
        raise SteamDTBuffLiveRecipeFixtureError
    listing_ids = selection.selected_listing_ids
    if (
        len(listing_ids) != 10
        or len(listing_ids) != len(set(listing_ids))
        or any(listing_id not in inputs.source_id_by_listing_id for listing_id in listing_ids)
    ):
        raise SteamDTBuffLiveRecipeFixtureError
    return selection


def _build_live_construction(
    selection: ConstructedRecipeSelection,
    inputs: _FixtureInputs,
) -> LiveRecipeConstructionResult:
    bindings = tuple(
        LiveCandidateBinding(
            source_offer_id=inputs.source_id_by_listing_id[candidate.listing_id],
            candidate=candidate,
            skin_metadata=inputs.input_skin,
        )
        for candidate in inputs.candidates
    )
    key = LiveSolverBucketKey(
        input_rarity=_INPUT_RARITY,
        stattrak=False,
        souvenir=False,
    )
    classification = LiveCandidateClassification(
        eligible=bindings,
        rejected=(),
        buckets=(
            LiveSolverBucket(
                key=key,
                bindings=bindings,
                affected_collections=frozenset({_COLLECTION_NAME}),
            ),
        ),
    )
    selected_source_ids = tuple(
        inputs.source_id_by_listing_id[listing_id]
        for listing_id in selection.selected_listing_ids
    )
    return LiveRecipeConstructionResult(
        classification=classification,
        recipes=(
            LiveConstructedRecipe(
                recipe=selection.recipe,
                selected_source_offer_ids=selected_source_ids,
            ),
        ),
    )


def _validate_fixture_contract(
    construction: LiveRecipeConstructionResult,
    solver: RecipeSolverConfig,
    risk: RiskFilterConfig,
) -> None:
    if solver != _build_solver_config() or risk != _build_risk_config():
        raise SteamDTBuffLiveRecipeFixtureError
    if (
        len(construction.classification.eligible) != 10
        or construction.classification.rejected
        or len(construction.classification.buckets) != 1
        or len(construction.recipes) != 1
    ):
        raise SteamDTBuffLiveRecipeFixtureError

    bucket = construction.classification.buckets[0]
    expected_key = LiveSolverBucketKey(
        input_rarity=_INPUT_RARITY,
        stattrak=False,
        souvenir=False,
    )
    if (
        bucket.key != expected_key
        or bucket.affected_collections != frozenset({_COLLECTION_NAME})
        or tuple(binding.source_offer_id for binding in bucket.bindings)
        != _SOURCE_IDS
    ):
        raise SteamDTBuffLiveRecipeFixtureError

    live_recipe = construction.recipes[0]
    recipe = live_recipe.recipe
    if (
        len(recipe.input_items) != 10
        or live_recipe.selected_source_offer_ids != _SOURCE_IDS
        or len(set(live_recipe.selected_source_offer_ids)) != 10
        or recipe.paint_seeds != _PAINT_SEEDS
        or recipe.input_total_cost_cny != Decimal("55.00")
        or len(recipe.tradeup_results) != 1
    ):
        raise SteamDTBuffLiveRecipeFixtureError

    bindings_by_source_id = {
        binding.source_offer_id: binding
        for binding in construction.classification.eligible
    }
    for item, source_id in zip(
        recipe.input_items,
        live_recipe.selected_source_offer_ids,
        strict=True,
    ):
        binding = bindings_by_source_id.get(source_id)
        if binding is None:
            raise SteamDTBuffLiveRecipeFixtureError
        candidate = binding.candidate
        skin = binding.skin_metadata
        if (
            item.market_hash_name != candidate.market_hash_name
            or item.collection_name != skin.collection_name
            or item.rarity != skin.rarity
            or item.actual_float != candidate.float_value
            or item.min_float != skin.min_float
            or item.max_float != skin.max_float
            or item.price_cny != candidate.price_cny
            or item.stattrak != skin.stattrak
            or item.souvenir != skin.souvenir
            or candidate.scanned_at != _FIXED_SCANNED_AT
            or candidate.inspect_link is not None
            or candidate.raw is not None
        ):
            raise SteamDTBuffLiveRecipeFixtureError

    result = recipe.tradeup_results[0]
    canonical_output_names = {
        output.output_market_hash_name for output in recipe.tradeup_results
    }
    if (
        len(canonical_output_names) != 1
        or not result.output_market_hash_name
        or result.output_market_hash_name != result.output_market_hash_name.strip()
        or result.probability != 1.0
        or not math.isfinite(result.output_float)
        or not 0 <= result.output_float <= 1
        or not result.output_wear.strip()
        or result.estimated_price_cny != Decimal("0")
        or result.expected_value_contribution != Decimal("0")
    ):
        raise SteamDTBuffLiveRecipeFixtureError


def _copy_construction_result(value: object) -> LiveRecipeConstructionResult:
    if type(value) is not LiveRecipeConstructionResult:
        raise SteamDTBuffLiveRecipeFixtureError
    return LiveRecipeConstructionResult(
        classification=value.classification,
        recipes=value.recipes,
    )


def _copy_solver_config(value: object) -> RecipeSolverConfig:
    if type(value) is not RecipeSolverConfig:
        raise SteamDTBuffLiveRecipeFixtureError
    return RecipeSolverConfig(
        input_rarity=value.input_rarity,
        input_count=value.input_count,
        sell_fee_rate=value.sell_fee_rate,
        max_candidates_per_collection=value.max_candidates_per_collection,
        target_stattrak=value.target_stattrak,
        target_souvenir=value.target_souvenir,
    )


def _copy_risk_config(value: object) -> RiskFilterConfig:
    if type(value) is not RiskFilterConfig:
        raise SteamDTBuffLiveRecipeFixtureError
    excluded_seeds = (
        None
        if value.exclude_special_pattern_seeds is None
        else set(value.exclude_special_pattern_seeds)
    )
    return RiskFilterConfig(
        min_roi=value.min_roi,
        min_expected_profit_cny=value.min_expected_profit_cny,
        max_worst_case_loss_pct=value.max_worst_case_loss_pct,
        min_profit_probability=value.min_profit_probability,
        max_input_total_cost_cny=value.max_input_total_cost_cny,
        min_liquidity_score=value.min_liquidity_score,
        exclude_souvenir=value.exclude_souvenir,
        exclude_stattrak=value.exclude_stattrak,
        exclude_special_pattern_seeds=excluded_seeds,
    )
