import hashlib
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



def solve_recipes(
    candidates: list[CandidateListing],
    skins: list[SkinMetadata],
    solver_config: RecipeSolverConfig,
    risk_config: RiskFilterConfig,
    liquidity_score: Decimal | None = None,
) -> list[RecipeCandidate]:
    """Build one deterministic greedy recipe and evaluate it end-to-end."""

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
        tradeup_results = calculate_tradeup_results(input_items, output_candidates_by_collection)
    except ValueError:
        return []

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
        paint_seeds=[
            pair.candidate.paint_seed
            for pair in selected_pairs
            if pair.candidate.paint_seed is not None
        ],
    )
    recipe_hash = build_recipe_hash(input_items)

    return [
        RecipeCandidate(
            input_items=input_items,
            tradeup_results=tradeup_results,
            metrics=metrics,
            risk_decision=risk_decision,
            recipe_hash=recipe_hash,
            created_at=datetime.now(UTC),
        )
    ]


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
        key=lambda pair: (
            pair.adjusted_float,
            pair.input_item.price_cny,
            pair.input_item.market_hash_name,
            pair.candidate.listing_id,
        ),
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
