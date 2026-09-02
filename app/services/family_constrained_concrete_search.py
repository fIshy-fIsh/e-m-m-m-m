"""Phase 16E — Dedicated family-count-preserving concrete search.

The recipe-first path reuses ``RecipeEnumerationConfig`` bounds and the mature
``ConstructedRecipe`` / ``ConstructedRecipeSelection`` DTOs, but not the
legacy unconstrained/wear-row enumerator. Every state preserves exact family
collection quotas by replacing one selected listing only with a reserve from
the same collection.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Final

from app.services.family_concrete_tradeup_results import (
    ConcreteFamilyTradeupResults,
    build_concrete_family_tradeup_results,
)
from app.services.recipe_family import RecipeFamily, StatTrakMode
from app.services.recipe_family_geometry import RecipeFamilyGeometry
from app.services.recipe_solver import (
    ConstructedRecipe,
    ConstructedRecipeSelection,
    RecipeEnumerationConfig,
    RecipeSolverConfig,
)
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.trade_up_input_enrichment import TradeUpEnrichedInput
from app.services.tradeup_engine import InputItem
from app.utils.float_math import calculate_adjusted_float

__all__ = (
    "FamilyConstrainedConcreteSearchError",
    "FamilyConstrainedRecipeSearchDiagnostics",
    "FamilyConstrainedRecipeSearchResult",
    "FamilyConstrainedRecipeSelection",
    "search_family_constrained_recipes",
)

_INPUT_COUNT: Final[int] = 10


class FamilyConstrainedConcreteSearchError(ValueError):
    """Family-constrained concrete search failed closed."""


@dataclass(frozen=True, kw_only=True, repr=False)
class FamilyConstrainedRecipeSelection:
    """Compatibility selection plus exact finish-level concrete outputs."""

    family_hash: str
    selection: ConstructedRecipeSelection
    concrete_outcomes: ConcreteFamilyTradeupResults

    def __post_init__(self) -> None:
        if (
            type(self.family_hash) is not str
            or len(self.family_hash) != 64
            or any(ch not in "0123456789abcdef" for ch in self.family_hash)
        ):
            raise FamilyConstrainedConcreteSearchError(
                "family_hash must be full lowercase SHA-256 hex"
            )
        if type(self.selection) is not ConstructedRecipeSelection:
            raise FamilyConstrainedConcreteSearchError(
                "selection must be ConstructedRecipeSelection"
            )
        if type(self.concrete_outcomes) is not ConcreteFamilyTradeupResults:
            raise FamilyConstrainedConcreteSearchError(
                "concrete_outcomes must be ConcreteFamilyTradeupResults"
            )
        if self.concrete_outcomes.family_hash != self.family_hash:
            raise FamilyConstrainedConcreteSearchError(
                "concrete outcome family hash must match selection family"
            )
        if self.selection.recipe.tradeup_results != (
            self.concrete_outcomes.tradeup_results
        ):
            raise FamilyConstrainedConcreteSearchError(
                "nested compatibility recipe must contain finish-level results"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class FamilyConstrainedRecipeSearchDiagnostics:
    family_hash: str
    eligible_input_count: int
    retained_input_count: int
    candidate_count_by_collection: tuple[tuple[str, int], ...]
    theoretical_radius_one_states: int
    states_explored: int
    raw_candidates_found: int
    unique_candidates_returned: int
    duplicates_suppressed: int
    candidate_limit_reached: bool
    exploration_limit_reached: bool

    def __post_init__(self) -> None:
        counters = (
            self.eligible_input_count,
            self.retained_input_count,
            self.theoretical_radius_one_states,
            self.states_explored,
            self.raw_candidates_found,
            self.unique_candidates_returned,
            self.duplicates_suppressed,
        )
        if any(type(value) is not int or value < 0 for value in counters):
            raise FamilyConstrainedConcreteSearchError(
                "search counters must be non-negative integers"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class FamilyConstrainedRecipeSearchResult:
    selections: tuple[FamilyConstrainedRecipeSelection, ...]
    diagnostics: FamilyConstrainedRecipeSearchDiagnostics


@dataclass(frozen=True, kw_only=True, repr=False)
class _EligibleInput:
    enriched: TradeUpEnrichedInput
    adjusted_float: float

    @property
    def listing_key(self) -> tuple[str, str, str]:
        candidate = self.enriched.candidate
        return (candidate.source, candidate.goods_id, candidate.listing_id)

    @property
    def input_item(self) -> InputItem:
        return self.enriched.input_item


def search_family_constrained_recipes(
    family: RecipeFamily,
    *,
    geometry: RecipeFamilyGeometry,
    finish_index: StructuralOutputFinishIndex,
    enriched_inputs: Sequence[TradeUpEnrichedInput],
    solver_config: RecipeSolverConfig,
    enumeration_config: RecipeEnumerationConfig,
) -> FamilyConstrainedRecipeSearchResult:
    """Enumerate baseline + bounded same-collection radius-one alternatives."""

    _validate_inputs(
        family,
        geometry=geometry,
        finish_index=finish_index,
        enriched_inputs=enriched_inputs,
        solver_config=solver_config,
        enumeration_config=enumeration_config,
    )
    expected_stattrak = family.stattrak_mode is StatTrakMode.STATTRAK
    represented = dict(family.collection_counts)
    eligible: list[_EligibleInput] = []
    seen_listing_keys: set[tuple[str, str, str]] = set()
    for enriched in enriched_inputs:
        candidate = enriched.candidate
        item = enriched.input_item
        if (
            candidate.market_hash_name is None
            or candidate.stattrak is None
            or candidate.souvenir is None
            or item.collection_name not in represented
            or item.rarity != family.input_rarity
            or item.stattrak is not expected_stattrak
        ):
            continue
        if (
            item.market_hash_name != candidate.market_hash_name
            or item.price_cny != candidate.price_cny
            or item.actual_float != float(candidate.paintwear)
            or item.stattrak is not candidate.stattrak
            or item.souvenir is not candidate.souvenir
        ):
            raise FamilyConstrainedConcreteSearchError(
                "enriched input is inconsistent with candidate-owned identity"
            )
        listing_key = (
            candidate.source,
            candidate.goods_id,
            candidate.listing_id,
        )
        if listing_key in seen_listing_keys:
            raise FamilyConstrainedConcreteSearchError(
                "duplicate listing provenance"
            )
        seen_listing_keys.add(listing_key)
        try:
            adjusted = calculate_adjusted_float(
                actual_float=item.actual_float,
                min_float=item.min_float,
                max_float=item.max_float,
            )
        except ValueError:
            continue
        eligible.append(_EligibleInput(enriched=enriched, adjusted_float=adjusted))

    eligible_count = len(eligible)
    eligible.sort(key=_candidate_sort_key)
    retained = _apply_collection_cap(
        eligible,
        solver_config.max_candidates_per_collection,
    )
    by_collection: dict[str, list[_EligibleInput]] = {
        name: [] for name in represented
    }
    for entry in retained:
        by_collection[entry.input_item.collection_name].append(entry)
    collection_counts = tuple(
        (name, len(by_collection[name])) for name, _required in family.collection_counts
    )
    if any(
        len(by_collection[name]) < required
        for name, required in family.collection_counts
    ):
        return _result(
            family=family,
            selections=(),
            eligible_input_count=eligible_count,
            retained_input_count=len(retained),
            candidate_count_by_collection=collection_counts,
            theoretical_radius_one_states=0,
            states_explored=0,
            raw_candidates_found=0,
            duplicates_suppressed=0,
            candidate_limit_reached=False,
            exploration_limit_reached=False,
        )

    baseline_by_collection = {
        name: tuple(by_collection[name][:required])
        for name, required in family.collection_counts
    }
    states = _iter_family_states(
        family,
        by_collection=by_collection,
        baseline_by_collection=baseline_by_collection,
    )
    theoretical = 1 + sum(
        required * (len(by_collection[name]) - required)
        for name, required in family.collection_counts
    )
    selections: list[FamilyConstrainedRecipeSelection] = []
    seen_selection_keys: set[tuple[tuple[str, str, str], ...]] = set()
    states_explored = 0
    duplicates_suppressed = 0
    candidate_limit_reached = False
    exploration_limit_reached = False
    raw_candidates_found = 0

    for state in states:
        if states_explored >= enumeration_config.max_candidate_states_explored:
            exploration_limit_reached = states_explored < theoretical
            break
        states_explored += 1
        key = tuple(sorted(entry.listing_key for entry in state))
        if key in seen_selection_keys:
            duplicates_suppressed += 1
            continue
        seen_selection_keys.add(key)
        concrete = build_concrete_family_tradeup_results(
            family,
            geometry=geometry,
            finish_index=finish_index,
            selected_input_items=tuple(entry.input_item for entry in state),
        )
        raw_candidates_found += 1
        selections.append(_build_selection(family, state, concrete))
        if len(selections) >= enumeration_config.max_recipe_candidates_returned:
            candidate_limit_reached = states_explored < theoretical
            break

    return _result(
        family=family,
        selections=tuple(selections),
        eligible_input_count=eligible_count,
        retained_input_count=len(retained),
        candidate_count_by_collection=collection_counts,
        theoretical_radius_one_states=theoretical,
        states_explored=states_explored,
        raw_candidates_found=raw_candidates_found,
        duplicates_suppressed=duplicates_suppressed,
        candidate_limit_reached=candidate_limit_reached,
        exploration_limit_reached=exploration_limit_reached,
    )


def _validate_inputs(
    family: object,
    *,
    geometry: object,
    finish_index: object,
    enriched_inputs: object,
    solver_config: object,
    enumeration_config: object,
) -> None:
    if type(family) is not RecipeFamily:
        raise FamilyConstrainedConcreteSearchError("family must be RecipeFamily")
    if type(geometry) is not RecipeFamilyGeometry:
        raise FamilyConstrainedConcreteSearchError(
            "geometry must be RecipeFamilyGeometry"
        )
    if type(finish_index) is not StructuralOutputFinishIndex:
        raise FamilyConstrainedConcreteSearchError(
            "finish_index must be StructuralOutputFinishIndex"
        )
    if not isinstance(enriched_inputs, Sequence) or any(
        type(value) is not TradeUpEnrichedInput for value in enriched_inputs
    ):
        raise FamilyConstrainedConcreteSearchError(
            "enriched_inputs must contain exact TradeUpEnrichedInput values"
        )
    if type(solver_config) is not RecipeSolverConfig:
        raise FamilyConstrainedConcreteSearchError(
            "solver_config must be RecipeSolverConfig"
        )
    if type(enumeration_config) is not RecipeEnumerationConfig:
        raise FamilyConstrainedConcreteSearchError(
            "enumeration_config must be RecipeEnumerationConfig"
        )
    if family.family_hash != geometry.family_hash:
        raise FamilyConstrainedConcreteSearchError(
            "family and geometry hashes must match"
        )
    if solver_config.input_rarity != family.input_rarity:
        raise FamilyConstrainedConcreteSearchError(
            "solver input rarity must match family"
        )
    expected_stattrak = family.stattrak_mode is StatTrakMode.STATTRAK
    if (
        solver_config.target_stattrak is not None
        and solver_config.target_stattrak is not expected_stattrak
    ):
        raise FamilyConstrainedConcreteSearchError(
            "solver StatTrak target conflicts with family"
        )
    # A normal recipe family may contain normal and Souvenir inputs. A
    # caller-supplied target_souvenir would improperly make Souvenir structural.
    if solver_config.target_souvenir is not None:
        raise FamilyConstrainedConcreteSearchError(
            "recipe-first search does not accept a Souvenir family target"
        )


def _candidate_sort_key(entry: _EligibleInput) -> tuple[object, ...]:
    item = entry.input_item
    return (
        entry.adjusted_float,
        item.price_cny,
        item.market_hash_name,
        entry.enriched.candidate.source,
        entry.enriched.candidate.goods_id,
        entry.enriched.candidate.listing_id,
    )


def _apply_collection_cap(
    entries: list[_EligibleInput],
    cap: int | None,
) -> list[_EligibleInput]:
    if cap is None:
        return list(entries)
    counts: dict[str, int] = {}
    retained: list[_EligibleInput] = []
    for entry in entries:
        name = entry.input_item.collection_name
        if counts.get(name, 0) >= cap:
            continue
        counts[name] = counts.get(name, 0) + 1
        retained.append(entry)
    return retained


def _iter_family_states(
    family: RecipeFamily,
    *,
    by_collection: dict[str, list[_EligibleInput]],
    baseline_by_collection: dict[str, tuple[_EligibleInput, ...]],
) -> Iterator[tuple[_EligibleInput, ...]]:
    baseline = tuple(
        entry
        for name, _required in family.collection_counts
        for entry in baseline_by_collection[name]
    )
    yield baseline
    offsets: dict[str, int] = {}
    offset = 0
    for name, required in family.collection_counts:
        offsets[name] = offset
        offset += required
    for name, required in family.collection_counts:
        reserves = by_collection[name][required:]
        # Mature radius-one preference: increasing rank loss
        # ``reserve_rank - dropped_local_index``; then reserve rank and
        # dropped rank. Replacement never crosses a collection boundary.
        replacements = sorted(
            (
                (
                    reserve_rank - dropped_local_index,
                    reserve_rank,
                    dropped_local_index,
                    reserve,
                )
                for reserve_rank, reserve in enumerate(
                    reserves,
                    start=required,
                )
                for dropped_local_index in range(required)
            ),
            key=lambda value: (value[0], value[1], value[2]),
        )
        for _rank_loss, _reserve_rank, dropped_local_index, reserve in replacements:
            dropped_global_index = offsets[name] + dropped_local_index
            state = list(baseline)
            state[dropped_global_index] = reserve
            yield tuple(state)


def _build_selection(
    family: RecipeFamily,
    state: tuple[_EligibleInput, ...],
    concrete: ConcreteFamilyTradeupResults,
) -> FamilyConstrainedRecipeSelection:
    input_items = tuple(entry.input_item for entry in state)
    listing_ids = tuple(entry.enriched.candidate.listing_id for entry in state)
    if len(set(listing_ids)) != _INPUT_COUNT:
        raise FamilyConstrainedConcreteSearchError(
            "selection listing identities must be unique"
        )
    if Counter(item.collection_name for item in input_items) != dict(
        family.collection_counts
    ):
        raise FamilyConstrainedConcreteSearchError(
            "selection collection counts drifted from family"
        )
    recipe = ConstructedRecipe(
        input_items=input_items,
        tradeup_results=concrete.tradeup_results,
        paint_seeds=(),
    )
    return FamilyConstrainedRecipeSelection(
        family_hash=family.family_hash,
        selection=ConstructedRecipeSelection(
            recipe=recipe,
            selected_listing_ids=listing_ids,
        ),
        concrete_outcomes=concrete,
    )


def _result(
    *,
    family: RecipeFamily,
    selections: tuple[FamilyConstrainedRecipeSelection, ...],
    eligible_input_count: int,
    retained_input_count: int,
    candidate_count_by_collection: tuple[tuple[str, int], ...],
    theoretical_radius_one_states: int,
    states_explored: int,
    raw_candidates_found: int,
    duplicates_suppressed: int,
    candidate_limit_reached: bool,
    exploration_limit_reached: bool,
) -> FamilyConstrainedRecipeSearchResult:
    return FamilyConstrainedRecipeSearchResult(
        selections=selections,
        diagnostics=FamilyConstrainedRecipeSearchDiagnostics(
            family_hash=family.family_hash,
            eligible_input_count=eligible_input_count,
            retained_input_count=retained_input_count,
            candidate_count_by_collection=candidate_count_by_collection,
            theoretical_radius_one_states=theoretical_radius_one_states,
            states_explored=states_explored,
            raw_candidates_found=raw_candidates_found,
            unique_candidates_returned=len(selections),
            duplicates_suppressed=duplicates_suppressed,
            candidate_limit_reached=candidate_limit_reached,
            exploration_limit_reached=exploration_limit_reached,
        ),
    )
