"""Phase 16D — Approximate RecipeFamily pre-screen economics.

The calculator is pure and consumes only Phase 16B structural probability,
Phase 16C static reachability, exact input identity-float evidence, and an
immutable strict-BUFF price book. It never calls transport, never claims live
quantity or joint float realizability, and never reuses final OpportunityMetrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction

from app.services.prescreen_price_book import PreScreenPriceBook
from app.services.recipe_family import RecipeFamily
from app.services.recipe_family_geometry import RecipeFamilyGeometry
from app.services.static_float_feasibility import (
    InputIdentityFloatEvidence,
    StaticFloatFeasibilityResult,
    StaticFloatFeasibilityStatus,
)

__all__ = (
    "PER_FINISH_REACHABLE_WEAR_ENVELOPE_NOT_JOINT_REALIZABILITY_PROOF",
    "RecipeFamilyPreScreenEconomics",
    "RecipeFamilyPreScreenEconomicsConfig",
    "RecipeFamilyPreScreenEconomicsError",
    "RecipeFamilyPreScreenEconomicsStatus",
    "RecipeFamilyPreScreenScenario",
    "compute_recipe_family_prescreen_economics",
)

PER_FINISH_REACHABLE_WEAR_ENVELOPE_NOT_JOINT_REALIZABILITY_PROOF = (
    "PER_FINISH_REACHABLE_WEAR_ENVELOPE_NOT_JOINT_REALIZABILITY_PROOF"
)
_REPLICATED_INPUT_PRICE_ASSUMPTION = (
    "REPRESENTATIVE_COLLECTION_UNIT_PRICE_REPLICATED_FOR_REQUIRED_COUNT_"
    "WITHOUT_LIVE_QUANTITY_OR_EXECUTABILITY_PROOF"
)
_APPROXIMATE_ONLY_ASSUMPTION = "APPROXIMATE_PRESCREEN_NOT_FINAL_VALUATION"


class RecipeFamilyPreScreenScenario(StrEnum):
    OPTIMISTIC = "optimistic"
    BASE = "base"
    CONSERVATIVE = "conservative"


class RecipeFamilyPreScreenEconomicsStatus(StrEnum):
    COMPLETE = "complete"
    MISSING_REQUIRED_INPUT_PRICE = "missing_required_input_price"
    MISSING_REQUIRED_OUTPUT_PRICE = "missing_required_output_price"
    STATIC_FLOAT_INFEASIBLE = "static_float_infeasible"


class RecipeFamilyPreScreenEconomicsError(ValueError):
    """Economics evidence violated the pure pre-screen contract."""


def _valid_family_hash(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _money(value: Decimal | None, *, field: str) -> None:
    if value is not None and (
        type(value) is not Decimal or not value.is_finite()
    ):
        raise RecipeFamilyPreScreenEconomicsError(
            f"{field} must be a finite Decimal or None"
        )


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFamilyPreScreenEconomicsConfig:
    sell_fee_rate: Decimal

    def __post_init__(self) -> None:
        if (
            type(self.sell_fee_rate) is not Decimal
            or not self.sell_fee_rate.is_finite()
            or self.sell_fee_rate < 0
            or self.sell_fee_rate >= 1
        ):
            raise RecipeFamilyPreScreenEconomicsError(
                "sell_fee_rate must be a finite Decimal in [0, 1)"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFamilyPreScreenEconomics:
    family_hash: str
    scenario_label: RecipeFamilyPreScreenScenario
    status: RecipeFamilyPreScreenEconomicsStatus
    estimated_input_cost_cny: Decimal | None
    estimated_gross_output_ev_cny: Decimal | None
    estimated_net_ev_after_sell_fee_cny: Decimal | None
    estimated_profit_cny: Decimal | None
    estimated_roi: Fraction | None
    required_component_missing_count: int
    alternative_missing_quote_count: int
    known_sell_count_sum: int
    unknown_sell_count_count: int
    assumptions: tuple[str, ...]
    evidence: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _valid_family_hash(self.family_hash):
            raise RecipeFamilyPreScreenEconomicsError(
                "family_hash must be full lowercase SHA-256 hex"
            )
        if type(self.scenario_label) is not RecipeFamilyPreScreenScenario:
            raise RecipeFamilyPreScreenEconomicsError("invalid scenario_label")
        if type(self.status) is not RecipeFamilyPreScreenEconomicsStatus:
            raise RecipeFamilyPreScreenEconomicsError("invalid economics status")
        _money(self.estimated_input_cost_cny, field="estimated_input_cost_cny")
        _money(
            self.estimated_gross_output_ev_cny,
            field="estimated_gross_output_ev_cny",
        )
        _money(
            self.estimated_net_ev_after_sell_fee_cny,
            field="estimated_net_ev_after_sell_fee_cny",
        )
        _money(self.estimated_profit_cny, field="estimated_profit_cny")
        if self.estimated_roi is not None and type(self.estimated_roi) is not Fraction:
            raise RecipeFamilyPreScreenEconomicsError(
                "estimated_roi must be Fraction or None"
            )
        counters = (
            self.required_component_missing_count,
            self.alternative_missing_quote_count,
            self.known_sell_count_sum,
            self.unknown_sell_count_count,
        )
        if any(type(value) is not int or value < 0 for value in counters):
            raise RecipeFamilyPreScreenEconomicsError(
                "economics counters must be non-negative integers"
            )
        for field, values in (
            ("assumptions", self.assumptions),
            ("evidence", self.evidence),
            ("reason_codes", self.reason_codes),
        ):
            if type(values) is not tuple or any(
                type(value) is not str or not value for value in values
            ):
                raise RecipeFamilyPreScreenEconomicsError(
                    f"{field} must be tuple[non-empty str, ...]"
                )
        estimates = (
            self.estimated_input_cost_cny,
            self.estimated_gross_output_ev_cny,
            self.estimated_net_ev_after_sell_fee_cny,
            self.estimated_profit_cny,
            self.estimated_roi,
        )
        if self.status is RecipeFamilyPreScreenEconomicsStatus.COMPLETE:
            if any(value is None for value in estimates):
                raise RecipeFamilyPreScreenEconomicsError(
                    "complete economics requires all estimates"
                )
            if self.required_component_missing_count != 0:
                raise RecipeFamilyPreScreenEconomicsError(
                    "complete economics cannot miss required components"
                )
        elif any(value is not None for value in estimates):
            raise RecipeFamilyPreScreenEconomicsError(
                "incomplete economics must not expose estimates"
            )


def _median(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise RecipeFamilyPreScreenEconomicsError("median requires values")
    ordered = tuple(sorted(values))
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _representative_input_price(
    prices: tuple[Decimal, ...],
    scenario: RecipeFamilyPreScreenScenario,
) -> Decimal:
    if scenario is RecipeFamilyPreScreenScenario.OPTIMISTIC:
        return min(prices)
    if scenario is RecipeFamilyPreScreenScenario.BASE:
        return _median(prices)
    return max(prices)


def _representative_output_price(
    prices: tuple[Decimal, ...],
    scenario: RecipeFamilyPreScreenScenario,
) -> Decimal:
    if scenario is RecipeFamilyPreScreenScenario.OPTIMISTIC:
        return max(prices)
    if scenario is RecipeFamilyPreScreenScenario.BASE:
        return _median(prices)
    return min(prices)


def _decimal_fraction(value: Decimal) -> Fraction:
    if not value.is_finite():
        raise RecipeFamilyPreScreenEconomicsError(
            "cannot convert non-finite Decimal"
        )
    return Fraction(value)


def _incomplete_result(
    *,
    family_hash: str,
    scenario: RecipeFamilyPreScreenScenario,
    status: RecipeFamilyPreScreenEconomicsStatus,
    required_missing: int,
    alternative_missing: int,
    known_sell_count_sum: int,
    unknown_sell_count_count: int,
    evidence: tuple[str, ...],
    reasons: tuple[str, ...],
) -> RecipeFamilyPreScreenEconomics:
    return RecipeFamilyPreScreenEconomics(
        family_hash=family_hash,
        scenario_label=scenario,
        status=status,
        estimated_input_cost_cny=None,
        estimated_gross_output_ev_cny=None,
        estimated_net_ev_after_sell_fee_cny=None,
        estimated_profit_cny=None,
        estimated_roi=None,
        required_component_missing_count=required_missing,
        alternative_missing_quote_count=alternative_missing,
        known_sell_count_sum=known_sell_count_sum,
        unknown_sell_count_count=unknown_sell_count_count,
        assumptions=(
            _REPLICATED_INPUT_PRICE_ASSUMPTION,
            PER_FINISH_REACHABLE_WEAR_ENVELOPE_NOT_JOINT_REALIZABILITY_PROOF,
            _APPROXIMATE_ONLY_ASSUMPTION,
        ),
        evidence=evidence,
        reason_codes=reasons,
    )


def compute_recipe_family_prescreen_economics(
    family: RecipeFamily,
    *,
    geometry: RecipeFamilyGeometry,
    static_feasibility: StaticFloatFeasibilityResult,
    input_evidence: tuple[InputIdentityFloatEvidence, ...],
    price_book: PreScreenPriceBook,
    config: RecipeFamilyPreScreenEconomicsConfig,
) -> tuple[RecipeFamilyPreScreenEconomics, ...]:
    """Compute optimistic/base/conservative approximate family economics."""

    if type(family) is not RecipeFamily:
        raise RecipeFamilyPreScreenEconomicsError("family must be RecipeFamily")
    if type(geometry) is not RecipeFamilyGeometry:
        raise RecipeFamilyPreScreenEconomicsError(
            "geometry must be RecipeFamilyGeometry"
        )
    if type(static_feasibility) is not StaticFloatFeasibilityResult:
        raise RecipeFamilyPreScreenEconomicsError(
            "static_feasibility must be StaticFloatFeasibilityResult"
        )
    if type(price_book) is not PreScreenPriceBook:
        raise RecipeFamilyPreScreenEconomicsError(
            "price_book must be PreScreenPriceBook"
        )
    if type(config) is not RecipeFamilyPreScreenEconomicsConfig:
        raise RecipeFamilyPreScreenEconomicsError(
            "config must be RecipeFamilyPreScreenEconomicsConfig"
        )
    if type(input_evidence) is not tuple or any(
        type(item) is not InputIdentityFloatEvidence for item in input_evidence
    ):
        raise RecipeFamilyPreScreenEconomicsError(
            "input_evidence must contain exact InputIdentityFloatEvidence"
        )
    if not (
        family.family_hash
        == geometry.family_hash
        == static_feasibility.family_hash
    ):
        raise RecipeFamilyPreScreenEconomicsError(
            "family, geometry, and static feasibility hashes must match"
        )

    scenarios = tuple(RecipeFamilyPreScreenScenario)
    assumptions = (
        _REPLICATED_INPUT_PRICE_ASSUMPTION,
        PER_FINISH_REACHABLE_WEAR_ENVELOPE_NOT_JOINT_REALIZABILITY_PROOF,
        _APPROXIMATE_ONLY_ASSUMPTION,
    )
    if static_feasibility.status is not StaticFloatFeasibilityStatus.FEASIBLE:
        return tuple(
            _incomplete_result(
                family_hash=family.family_hash,
                scenario=scenario,
                status=RecipeFamilyPreScreenEconomicsStatus.STATIC_FLOAT_INFEASIBLE,
                required_missing=0,
                alternative_missing=0,
                known_sell_count_sum=0,
                unknown_sell_count_count=0,
                evidence=static_feasibility.diagnostics,
                reasons=("STATIC_FLOAT_INFEASIBLE",),
            )
            for scenario in scenarios
        )

    family_collections = {name for name, _count in family.collection_counts}
    input_by_collection: dict[str, list[InputIdentityFloatEvidence]] = {
        name: [] for name in family_collections
    }
    seen_input_names: set[str] = set()
    for item in input_evidence:
        if item.market_hash_name in seen_input_names:
            raise RecipeFamilyPreScreenEconomicsError(
                "duplicate exact input evidence name"
            )
        seen_input_names.add(item.market_hash_name)
        if item.input_rarity != family.input_rarity:
            raise RecipeFamilyPreScreenEconomicsError(
                "input evidence rarity does not match family"
            )
        expected_stattrak = family.stattrak_mode.value == "stattrak"
        if item.stattrak is not expected_stattrak:
            raise RecipeFamilyPreScreenEconomicsError(
                "input evidence StatTrak mode does not match family"
            )
        if item.collection_name in input_by_collection:
            input_by_collection[item.collection_name].append(item)

    reachable_by_finish: dict[str, list[str]] = {
        outcome.finish_key: [] for outcome in geometry.outcomes
    }
    for reachable in static_feasibility.reachable_outputs:
        if reachable.finish_key in reachable_by_finish:
            reachable_by_finish[reachable.finish_key].append(
                reachable.exact_market_hash_name
            )
    for names in reachable_by_finish.values():
        if len(set(names)) != len(names):
            raise RecipeFamilyPreScreenEconomicsError(
                "duplicate reachable output exact name for one finish"
            )

    missing_input_components = 0
    missing_output_components = 0
    alternative_missing = 0
    known_sell_count_sum = 0
    unknown_sell_count_count = 0
    input_prices: dict[str, tuple[Decimal, ...]] = {}
    output_prices: dict[str, tuple[Decimal, ...]] = {}
    counted_quote_names: set[str] = set()
    evidence_lines: list[str] = []

    for collection_name, _count in family.collection_counts:
        candidates = input_by_collection[collection_name]
        quoted: list[Decimal] = []
        for candidate in candidates:
            quote = price_book.quote_for(candidate.market_hash_name)
            if quote is None:
                alternative_missing += 1
                continue
            quoted.append(quote.sell_price_cny)
            if quote.market_hash_name not in counted_quote_names:
                counted_quote_names.add(quote.market_hash_name)
                if quote.sell_count is None:
                    unknown_sell_count_count += 1
                else:
                    known_sell_count_sum += quote.sell_count
        if not quoted:
            missing_input_components += 1
        else:
            input_prices[collection_name] = tuple(quoted)
        evidence_lines.append(
            f"input_collection:{collection_name}:quoted={len(quoted)}:"
            f"candidates={len(candidates)}"
        )

    probability_by_finish = {
        outcome.finish_key: outcome.probability for outcome in geometry.outcomes
    }
    if len(probability_by_finish) != len(geometry.outcomes):
        raise RecipeFamilyPreScreenEconomicsError("duplicate geometry finish key")
    for finish_key in sorted(probability_by_finish):
        reachable_names = tuple(reachable_by_finish.get(finish_key, ()))
        quoted = []
        for name in reachable_names:
            quote = price_book.quote_for(name)
            if quote is None:
                alternative_missing += 1
                continue
            quoted.append(quote.sell_price_cny)
            if quote.market_hash_name not in counted_quote_names:
                counted_quote_names.add(quote.market_hash_name)
                if quote.sell_count is None:
                    unknown_sell_count_count += 1
                else:
                    known_sell_count_sum += quote.sell_count
        if not quoted:
            missing_output_components += 1
        else:
            output_prices[finish_key] = tuple(quoted)
        evidence_lines.append(
            f"output_finish:{finish_key}:quoted={len(quoted)}:"
            f"reachable={len(reachable_names)}"
        )

    required_missing = missing_input_components + missing_output_components
    reasons: list[str] = []
    if missing_input_components:
        reasons.append("MISSING_REQUIRED_INPUT_PRICE")
    if missing_output_components:
        reasons.append("MISSING_REQUIRED_OUTPUT_PRICE")
    if required_missing:
        status = (
            RecipeFamilyPreScreenEconomicsStatus.MISSING_REQUIRED_INPUT_PRICE
            if missing_input_components
            else RecipeFamilyPreScreenEconomicsStatus.MISSING_REQUIRED_OUTPUT_PRICE
        )
        return tuple(
            _incomplete_result(
                family_hash=family.family_hash,
                scenario=scenario,
                status=status,
                required_missing=required_missing,
                alternative_missing=alternative_missing,
                known_sell_count_sum=known_sell_count_sum,
                unknown_sell_count_count=unknown_sell_count_count,
                evidence=tuple(evidence_lines),
                reasons=tuple(reasons),
            )
            for scenario in scenarios
        )

    results: list[RecipeFamilyPreScreenEconomics] = []
    for scenario in scenarios:
        input_cost = sum(
            (
                _representative_input_price(input_prices[name], scenario)
                * Decimal(count)
                for name, count in family.collection_counts
            ),
            start=Decimal(0),
        )
        if input_cost <= 0:
            raise RecipeFamilyPreScreenEconomicsError(
                "estimated input cost must be positive"
            )
        gross_ev_fraction = sum(
            (
                probability_by_finish[finish_key]
                * _decimal_fraction(
                    _representative_output_price(
                        output_prices[finish_key], scenario
                    )
                )
                for finish_key in sorted(probability_by_finish)
            ),
            start=Fraction(0, 1),
        )
        fee_multiplier_fraction = _decimal_fraction(
            Decimal(1) - config.sell_fee_rate
        )
        input_cost_fraction = _decimal_fraction(input_cost)
        net_ev_fraction = gross_ev_fraction * fee_multiplier_fraction
        profit_fraction = net_ev_fraction - input_cost_fraction
        roi = profit_fraction / input_cost_fraction
        gross_ev = Decimal(gross_ev_fraction.numerator) / Decimal(
            gross_ev_fraction.denominator
        )
        net_ev = Decimal(net_ev_fraction.numerator) / Decimal(
            net_ev_fraction.denominator
        )
        profit = Decimal(profit_fraction.numerator) / Decimal(
            profit_fraction.denominator
        )
        results.append(
            RecipeFamilyPreScreenEconomics(
                family_hash=family.family_hash,
                scenario_label=scenario,
                status=RecipeFamilyPreScreenEconomicsStatus.COMPLETE,
                estimated_input_cost_cny=input_cost,
                estimated_gross_output_ev_cny=gross_ev,
                estimated_net_ev_after_sell_fee_cny=net_ev,
                estimated_profit_cny=profit,
                estimated_roi=roi,
                required_component_missing_count=0,
                alternative_missing_quote_count=alternative_missing,
                known_sell_count_sum=known_sell_count_sum,
                unknown_sell_count_count=unknown_sell_count_count,
                assumptions=assumptions,
                evidence=tuple(evidence_lines),
                reason_codes=(),
            )
        )
    return tuple(results)
