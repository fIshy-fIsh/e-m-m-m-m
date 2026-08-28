import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.services.ev_service import OpportunityMetrics, calculate_opportunity_metrics
from app.services.market_scan_service import CandidateListing
from app.services.metadata_models import SkinMetadata
from app.services.metadata_service import build_output_candidates_by_collection
from app.services.risk_filter import RiskDecision, RiskFilterConfig, evaluate_opportunity
from app.services.tradeup_engine import InputItem, TradeupResult, calculate_tradeup_results
from app.utils.float_math import calculate_adjusted_float

DEFAULT_MAX_RECIPE_CANDIDATES_RETURNED = 2
HARD_MAX_RECIPE_CANDIDATES_RETURNED = 6
DEFAULT_MAX_CANDIDATE_STATES_EXPLORED = 256
HARD_MAX_CANDIDATE_STATES_EXPLORED = 1_024

RecipeListingKey = tuple[str, str, str]
RecipeSelectionKey = tuple[RecipeListingKey, ...]


@dataclass(frozen=True, kw_only=True)
class RecipeEnumerationConfig:
    """Finite bounds for deterministic recipe candidate enumeration."""

    max_recipe_candidates_returned: int = (
        DEFAULT_MAX_RECIPE_CANDIDATES_RETURNED
    )
    max_candidate_states_explored: int = (
        DEFAULT_MAX_CANDIDATE_STATES_EXPLORED
    )

    def __post_init__(self) -> None:
        candidates = self.max_recipe_candidates_returned
        states = self.max_candidate_states_explored
        if (
            type(candidates) is not int
            or not 1 <= candidates <= HARD_MAX_RECIPE_CANDIDATES_RETURNED
        ):
            raise ValueError(
                "max_recipe_candidates_returned must be an integer in [1, 6]"
            )
        if (
            type(states) is not int
            or not 1 <= states <= HARD_MAX_CANDIDATE_STATES_EXPLORED
        ):
            raise ValueError(
                "max_candidate_states_explored must be an integer in [1, 1024]"
            )
        if states < candidates:
            raise ValueError(
                "max_candidate_states_explored must be greater than or equal to "
                "max_recipe_candidates_returned"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeEnumerationDiagnostics:
    """Exact structural accounting for one bounded enumeration call."""

    eligible_input_count: int
    retained_input_count: int
    theoretical_radius_one_states: int
    states_explored: int
    raw_candidates_found: int
    unique_candidates_returned: int
    duplicates_suppressed: int
    engine_rejected_states: int
    baseline_state_rejected: bool
    candidate_limit_reached: bool
    exploration_limit_reached: bool


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeEnumerationResult:
    """Ordered bounded recipe selections and their structural diagnostics."""

    selections: tuple["ConstructedRecipeSelection", ...]
    diagnostics: RecipeEnumerationDiagnostics


@dataclass(frozen=True)
class RecipeSolverConfig:
    """Configuration for deterministic V1 recipe solving."""

    input_rarity: str
    input_count: int = 10
    sell_fee_rate: Decimal = Decimal("0")
    max_candidates_per_collection: int | None = None
    target_stattrak: bool | None = None
    target_souvenir: bool | None = None

    def __post_init__(self) -> None:
        if not self.input_rarity.strip():
            raise ValueError("input_rarity cannot be empty")
        if self.input_count != 10:
            raise ValueError("input_count must be exactly 10")
        if self.sell_fee_rate < 0:
            raise ValueError("sell_fee_rate must be greater than or equal to 0")
        if self.sell_fee_rate >= 1:
            raise ValueError("sell_fee_rate must be less than 1")
        if (
            self.max_candidates_per_collection is not None
            and self.max_candidates_per_collection <= 0
        ):
            raise ValueError("max_candidates_per_collection must be greater than 0")


@dataclass(frozen=True, kw_only=True, repr=False)
class ConstructedRecipe:
    """A complete recipe construction without opportunity evaluation."""

    input_items: tuple[InputItem, ...]
    tradeup_results: tuple[TradeupResult, ...]
    paint_seeds: tuple[int, ...]

    def __post_init__(self) -> None:
        if type(self.input_items) is not tuple or any(
            type(item) is not InputItem for item in self.input_items
        ):
            raise ValueError("input_items must be an exact tuple of InputItem values")
        if len(self.input_items) != 10:
            raise ValueError("input_items must contain exactly 10 items")
        if type(self.tradeup_results) is not tuple or any(
            type(result) is not TradeupResult for result in self.tradeup_results
        ):
            raise ValueError(
                "tradeup_results must be an exact tuple of TradeupResult values"
            )
        if not self.tradeup_results:
            raise ValueError("tradeup_results cannot be empty")
        if type(self.paint_seeds) is not tuple or any(
            type(seed) is not int for seed in self.paint_seeds
        ):
            raise ValueError("paint_seeds must be an exact tuple of integer values")

    @property
    def input_total_cost_cny(self) -> Decimal:
        return sum(
            (item.price_cny for item in self.input_items),
            start=Decimal("0"),
        )


@dataclass(frozen=True, kw_only=True, repr=False)
class ConstructedRecipeSelection:
    """A constructed recipe paired with its exact selected listing identities."""

    recipe: ConstructedRecipe
    selected_listing_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.recipe) is not ConstructedRecipe:
            raise ValueError("recipe must be an exact ConstructedRecipe")
        if type(self.selected_listing_ids) is not tuple or any(
            not isinstance(listing_id, str) or not listing_id.strip()
            for listing_id in self.selected_listing_ids
        ):
            raise ValueError(
                "selected_listing_ids must be an exact tuple of non-empty strings"
            )
        if len(self.selected_listing_ids) != len(self.recipe.input_items):
            raise ValueError(
                "selected_listing_ids must align exactly with recipe input_items"
            )
        object.__setattr__(
            self,
            "selected_listing_ids",
            tuple(str.__str__(listing_id) for listing_id in self.selected_listing_ids),
        )


@dataclass(frozen=True)
class RecipeCandidate:
    """A complete V1 recipe candidate with downstream calculation results."""

    input_items: list[InputItem]
    tradeup_results: list[TradeupResult]
    metrics: OpportunityMetrics
    risk_decision: RiskDecision
    recipe_hash: str
    created_at: datetime

    def __post_init__(self) -> None:
        if len(self.input_items) != 10:
            raise ValueError("input_items must contain exactly 10 items")
        if not self.tradeup_results:
            raise ValueError("tradeup_results cannot be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")



def construct_recipes(
    candidates: list[CandidateListing],
    skins: list[SkinMetadata],
    solver_config: RecipeSolverConfig,
) -> list[ConstructedRecipe]:
    """Build deterministic recipes without EV or risk evaluation."""

    return [
        selection.recipe
        for selection in construct_recipe_selections(
            candidates,
            skins,
            solver_config,
        )
    ]


def construct_recipe_selections(
    candidates: list[CandidateListing],
    skins: list[SkinMetadata],
    solver_config: RecipeSolverConfig,
) -> list[ConstructedRecipeSelection]:
    """Build recipes with exact source-agnostic selected listing identities."""

    skin_lookup = {skin.market_hash_name: skin for skin in skins}
    eligible_pairs = _build_eligible_pairs(candidates, skin_lookup, solver_config)
    if not eligible_pairs:
        return []

    eligible_pairs = _sort_pairs(eligible_pairs)
    eligible_pairs = _apply_max_candidates_per_collection(
        eligible_pairs,
        solver_config.max_candidates_per_collection,
    )

    if len(eligible_pairs) < solver_config.input_count:
        return []

    selected_pairs = eligible_pairs[: solver_config.input_count]
    input_items = [pair.input_item for pair in selected_pairs]

    output_candidates_by_collection = build_output_candidates_by_collection(
        skins=skins,
        input_rarity=solver_config.input_rarity,
    )
    if not output_candidates_by_collection:
        return []

    try:
        tradeup_results = calculate_tradeup_results(
            input_items,
            output_candidates_by_collection,
        )
    except ValueError:
        return []

    recipe = ConstructedRecipe(
        input_items=tuple(input_items),
        tradeup_results=tuple(tradeup_results),
        paint_seeds=tuple(
            pair.candidate.paint_seed
            for pair in selected_pairs
            if pair.candidate.paint_seed is not None
        ),
    )
    return [
        ConstructedRecipeSelection(
            recipe=recipe,
            selected_listing_ids=tuple(
                pair.candidate.listing_id for pair in selected_pairs
            ),
        )
    ]


def enumerate_recipe_selections(
    candidates: list[CandidateListing],
    skins: list[SkinMetadata],
    solver_config: RecipeSolverConfig,
    *,
    enumeration_config: RecipeEnumerationConfig,
) -> RecipeEnumerationResult:
    """Enumerate a bounded deterministic neighborhood around the legacy state."""

    if type(enumeration_config) is not RecipeEnumerationConfig:
        raise TypeError("enumeration_config must be a RecipeEnumerationConfig")

    skin_lookup = {skin.market_hash_name: skin for skin in skins}
    eligible_pairs = _build_eligible_pairs(candidates, skin_lookup, solver_config)
    eligible_input_count = len(eligible_pairs)
    _validate_unique_offer_keys(eligible_pairs)

    retained_pairs = _apply_max_candidates_per_collection(
        _sort_pairs(eligible_pairs),
        solver_config.max_candidates_per_collection,
    )
    retained_input_count = len(retained_pairs)
    theoretical_states = _theoretical_radius_one_states(retained_input_count)
    if theoretical_states == 0:
        return _enumeration_result(
            selections=[],
            eligible_input_count=eligible_input_count,
            retained_input_count=retained_input_count,
            theoretical_radius_one_states=0,
            states_explored=0,
            duplicates_suppressed=0,
            engine_rejected_states=0,
            baseline_state_rejected=False,
            candidate_limit_reached=False,
            exploration_limit_reached=False,
        )

    output_candidates_by_collection = build_output_candidates_by_collection(
        skins=skins,
        input_rarity=solver_config.input_rarity,
    )
    if not output_candidates_by_collection:
        return _enumeration_result(
            selections=[],
            eligible_input_count=eligible_input_count,
            retained_input_count=retained_input_count,
            theoretical_radius_one_states=theoretical_states,
            states_explored=0,
            duplicates_suppressed=0,
            engine_rejected_states=0,
            baseline_state_rejected=False,
            candidate_limit_reached=False,
            exploration_limit_reached=False,
        )

    selections: list[ConstructedRecipeSelection] = []
    seen_keys: set[RecipeSelectionKey] = set()
    states_explored = 0
    duplicates_suppressed = 0
    engine_rejected_states = 0
    baseline_state_rejected = False
    candidate_limit_reached = False
    exploration_limit_reached = False

    for state_number, selected_pairs in enumerate(_iter_radius_one_states(retained_pairs)):
        if states_explored >= enumeration_config.max_candidate_states_explored:
            exploration_limit_reached = states_explored < theoretical_states
            break
        states_explored += 1
        selection_key = _recipe_selection_key(selected_pairs)
        if selection_key in seen_keys:
            duplicates_suppressed += 1
            continue
        seen_keys.add(selection_key)

        input_items = [pair.input_item for pair in selected_pairs]
        try:
            tradeup_results = calculate_tradeup_results(
                input_items,
                output_candidates_by_collection,
            )
        except ValueError:
            engine_rejected_states += 1
            if state_number == 0:
                baseline_state_rejected = True
            continue

        selections.append(_build_selection(selected_pairs, tradeup_results))
        if len(selections) >= enumeration_config.max_recipe_candidates_returned:
            candidate_limit_reached = states_explored < theoretical_states
            break

    return _enumeration_result(
        selections=selections,
        eligible_input_count=eligible_input_count,
        retained_input_count=retained_input_count,
        theoretical_radius_one_states=theoretical_states,
        states_explored=states_explored,
        duplicates_suppressed=duplicates_suppressed,
        engine_rejected_states=engine_rejected_states,
        baseline_state_rejected=baseline_state_rejected,
        candidate_limit_reached=candidate_limit_reached,
        exploration_limit_reached=exploration_limit_reached,
    )


def solve_recipes(
    candidates: list[CandidateListing],
    skins: list[SkinMetadata],
    solver_config: RecipeSolverConfig,
    risk_config: RiskFilterConfig,
    liquidity_score: Decimal | None = None,
) -> list[RecipeCandidate]:
    """Build deterministic recipes and evaluate each opportunity end-to-end."""

    constructed_recipes = construct_recipes(candidates, skins, solver_config)
    recipes: list[RecipeCandidate] = []

    for construction in constructed_recipes:
        input_items = list(construction.input_items)
        tradeup_results = list(construction.tradeup_results)
        metrics = calculate_opportunity_metrics(
            input_items=input_items,
            tradeup_results=tradeup_results,
            sell_fee_rate=solver_config.sell_fee_rate,
        )
        risk_decision = evaluate_opportunity(
            metrics=metrics,
            input_items=input_items,
            config=risk_config,
            liquidity_score=liquidity_score,
            paint_seeds=list(construction.paint_seeds),
        )
        recipe_hash = build_recipe_hash(input_items)
        recipes.append(
            RecipeCandidate(
                input_items=input_items,
                tradeup_results=tradeup_results,
                metrics=metrics,
                risk_decision=risk_decision,
                recipe_hash=recipe_hash,
                created_at=datetime.now(UTC),
            )
        )

    return recipes


@dataclass(frozen=True)
class _EligiblePair:
    """Internal pairing of a market candidate with normalized metadata and input item."""

    candidate: CandidateListing
    skin: SkinMetadata
    input_item: InputItem
    adjusted_float: float



def build_recipe_hash(input_items: list[InputItem]) -> str:
    """Build a stable SHA-256 hash for one recipe's sorted input items."""

    sorted_items = sorted(
        input_items,
        key=lambda item: (
            item.market_hash_name,
            item.actual_float,
            item.price_cny,
        ),
    )
    hash_source = "|".join(
        f"{item.market_hash_name}::{item.collection_name}::{item.actual_float}::"
        f"{item.price_cny}::{item.stattrak}::{item.souvenir}"
        for item in sorted_items
    )
    return hashlib.sha256(hash_source.encode("utf-8")).hexdigest()



def _build_eligible_pairs(
    candidates: list[CandidateListing],
    skin_lookup: dict[str, SkinMetadata],
    solver_config: RecipeSolverConfig,
) -> list[_EligiblePair]:
    """Convert candidate listings into eligible normalized input items."""

    eligible_pairs: list[_EligiblePair] = []

    for candidate in candidates:
        if candidate.market_hash_name is None:
            continue

        skin = skin_lookup.get(candidate.market_hash_name)
        if skin is None:
            continue
        if skin.collection_name is None:
            continue
        if skin.rarity != solver_config.input_rarity:
            continue
        if candidate.float_value is None:
            continue
        if (
            solver_config.target_stattrak is not None
            and skin.stattrak != solver_config.target_stattrak
        ):
            continue
        if (
            solver_config.target_souvenir is not None
            and skin.souvenir != solver_config.target_souvenir
        ):
            continue

        try:
            adjusted_float = calculate_adjusted_float(
                actual_float=candidate.float_value,
                min_float=skin.min_float,
                max_float=skin.max_float,
            )
        except ValueError:
            continue

        input_item = InputItem(
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
        eligible_pairs.append(
            _EligiblePair(
                candidate=candidate,
                skin=skin,
                input_item=input_item,
                adjusted_float=adjusted_float,
            )
        )

    return eligible_pairs



def _sort_pairs(pairs: list[_EligiblePair]) -> list[_EligiblePair]:
    """Sort eligible pairs by deterministic greedy priority."""

    return sorted(
        pairs,
        key=_pair_sort_key,
    )



def _apply_max_candidates_per_collection(
    pairs: list[_EligiblePair],
    max_candidates_per_collection: int | None,
) -> list[_EligiblePair]:
    """Limit how many sorted candidates may be retained per collection."""

    if max_candidates_per_collection is None:
        return pairs

    counts_by_collection: dict[str, int] = {}
    filtered: list[_EligiblePair] = []

    for pair in pairs:
        collection_name = pair.input_item.collection_name
        current_count = counts_by_collection.get(collection_name, 0)
        if current_count >= max_candidates_per_collection:
            continue
        counts_by_collection[collection_name] = current_count + 1
        filtered.append(pair)

    return filtered


def _offer_key(pair: _EligiblePair) -> RecipeListingKey:
    candidate = pair.candidate
    return (candidate.source, candidate.goods_id, candidate.listing_id)


def _validate_unique_offer_keys(pairs: list[_EligiblePair]) -> None:
    seen: set[RecipeListingKey] = set()
    for pair in pairs:
        key = _offer_key(pair)
        if key in seen:
            raise ValueError("duplicate recipe offer identity")
        seen.add(key)


def _recipe_selection_key(
    selected_pairs: tuple[_EligiblePair, ...],
) -> RecipeSelectionKey:
    keys = tuple(sorted(_offer_key(pair) for pair in selected_pairs))
    if len(keys) != 10 or len(set(keys)) != 10:
        raise ValueError("invalid recipe selection identity")
    return keys


def _theoretical_radius_one_states(retained_input_count: int) -> int:
    if retained_input_count < 10:
        return 0
    return 1 + 10 * (retained_input_count - 10)


def _iter_radius_one_states(
    retained_pairs: list[_EligiblePair],
) -> Iterator[tuple[_EligiblePair, ...]]:
    baseline = tuple(retained_pairs[:10])
    yield baseline
    retained_input_count = len(retained_pairs)
    for rank_loss in range(1, retained_input_count):
        for reserve_rank in range(10, retained_input_count):
            dropped_rank = reserve_rank - rank_loss
            if not 0 <= dropped_rank < 10:
                continue
            selected = tuple(
                pair
                for index, pair in enumerate(baseline)
                if index != dropped_rank
            ) + (retained_pairs[reserve_rank],)
            yield tuple(sorted(selected, key=_pair_sort_key))


def _pair_sort_key(pair: _EligiblePair) -> tuple[object, ...]:
    return (
        pair.adjusted_float,
        pair.input_item.price_cny,
        pair.input_item.market_hash_name,
        pair.candidate.listing_id,
    )


def _build_selection(
    selected_pairs: tuple[_EligiblePair, ...],
    tradeup_results: list[TradeupResult],
) -> ConstructedRecipeSelection:
    recipe = ConstructedRecipe(
        input_items=tuple(pair.input_item for pair in selected_pairs),
        tradeup_results=tuple(tradeup_results),
        paint_seeds=tuple(
            pair.candidate.paint_seed
            for pair in selected_pairs
            if pair.candidate.paint_seed is not None
        ),
    )
    return ConstructedRecipeSelection(
        recipe=recipe,
        selected_listing_ids=tuple(
            pair.candidate.listing_id for pair in selected_pairs
        ),
    )


def _enumeration_result(
    *,
    selections: list[ConstructedRecipeSelection],
    eligible_input_count: int,
    retained_input_count: int,
    theoretical_radius_one_states: int,
    states_explored: int,
    duplicates_suppressed: int,
    engine_rejected_states: int,
    baseline_state_rejected: bool,
    candidate_limit_reached: bool,
    exploration_limit_reached: bool,
) -> RecipeEnumerationResult:
    selection_tuple = tuple(selections)
    return RecipeEnumerationResult(
        selections=selection_tuple,
        diagnostics=RecipeEnumerationDiagnostics(
            eligible_input_count=eligible_input_count,
            retained_input_count=retained_input_count,
            theoretical_radius_one_states=theoretical_radius_one_states,
            states_explored=states_explored,
            raw_candidates_found=len(selection_tuple),
            unique_candidates_returned=len(selection_tuple),
            duplicates_suppressed=duplicates_suppressed,
            engine_rejected_states=engine_rejected_states,
            baseline_state_rejected=baseline_state_rejected,
            candidate_limit_reached=candidate_limit_reached,
            exploration_limit_reached=exploration_limit_reached,
        ),
    )
