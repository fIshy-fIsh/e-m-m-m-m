from dataclasses import dataclass
from decimal import Decimal

from app.services.ev_service import OpportunityMetrics
from app.services.tradeup_engine import InputItem

ROI_BELOW_MINIMUM = "ROI_BELOW_MINIMUM"
EXPECTED_PROFIT_BELOW_MINIMUM = "EXPECTED_PROFIT_BELOW_MINIMUM"
WORST_CASE_LOSS_TOO_HIGH = "WORST_CASE_LOSS_TOO_HIGH"
PROFIT_PROBABILITY_BELOW_MINIMUM = "PROFIT_PROBABILITY_BELOW_MINIMUM"
INPUT_COST_TOO_HIGH = "INPUT_COST_TOO_HIGH"
LIQUIDITY_SCORE_MISSING = "LIQUIDITY_SCORE_MISSING"
LIQUIDITY_SCORE_TOO_LOW = "LIQUIDITY_SCORE_TOO_LOW"
SOUVENIR_EXCLUDED = "SOUVENIR_EXCLUDED"
STATTRAK_EXCLUDED = "STATTRAK_EXCLUDED"
SPECIAL_PATTERN_SEED_EXCLUDED = "SPECIAL_PATTERN_SEED_EXCLUDED"


@dataclass(frozen=True)
class RiskFilterConfig:
    """Configuration thresholds for the conservative V1 opportunity filter."""

    min_roi: Decimal
    min_expected_profit_cny: Decimal
    max_worst_case_loss_pct: Decimal
    min_profit_probability: float
    max_input_total_cost_cny: Decimal
    min_liquidity_score: Decimal | None = None
    exclude_souvenir: bool = False
    exclude_stattrak: bool = False
    exclude_special_pattern_seeds: set[int] | None = None


@dataclass(frozen=True)
class RiskDecision:
    """Decision output for whether an opportunity passes the V1 risk filter."""

    passed: bool
    reasons: list[str]
    reason_codes: list[str]
    risk_score: Decimal



def evaluate_opportunity(
    metrics: OpportunityMetrics,
    input_items: list[InputItem],
    config: RiskFilterConfig,
    liquidity_score: Decimal | None = None,
    paint_seeds: list[int] | None = None,
) -> RiskDecision:
    """Evaluate whether an opportunity passes the conservative V1 risk filter."""

    reasons: list[str] = []
    reason_codes: list[str] = []
    raw_risk_score = Decimal("0")

    if metrics.roi < config.min_roi:
        _append_reason(
            reasons,
            reason_codes,
            "ROI is below the configured minimum.",
            ROI_BELOW_MINIMUM,
        )
        raw_risk_score += Decimal("20")

    if metrics.expected_profit_cny < config.min_expected_profit_cny:
        _append_reason(
            reasons,
            reason_codes,
            "Expected profit is below the configured minimum.",
            EXPECTED_PROFIT_BELOW_MINIMUM,
        )
        raw_risk_score += Decimal("15")

    worst_case_loss_pct = _calculate_worst_case_loss_pct(metrics)
    if worst_case_loss_pct > config.max_worst_case_loss_pct:
        _append_reason(
            reasons,
            reason_codes,
            "Worst-case loss percentage is too high.",
            WORST_CASE_LOSS_TOO_HIGH,
        )
        raw_risk_score += Decimal("25")

    if metrics.profit_probability < config.min_profit_probability:
        _append_reason(
            reasons,
            reason_codes,
            "Profit probability is below the configured minimum.",
            PROFIT_PROBABILITY_BELOW_MINIMUM,
        )
        raw_risk_score += Decimal("15")

    if metrics.input_total_cost_cny > config.max_input_total_cost_cny:
        _append_reason(
            reasons,
            reason_codes,
            "Input total cost exceeds the configured maximum.",
            INPUT_COST_TOO_HIGH,
        )
        raw_risk_score += Decimal("10")

    if config.min_liquidity_score is not None:
        if liquidity_score is None:
            _append_reason(
                reasons,
                reason_codes,
                "Liquidity score is required but missing.",
                LIQUIDITY_SCORE_MISSING,
            )
            raw_risk_score += Decimal("10")
        elif liquidity_score < config.min_liquidity_score:
            _append_reason(
                reasons,
                reason_codes,
                "Liquidity score is below the configured minimum.",
                LIQUIDITY_SCORE_TOO_LOW,
            )
            raw_risk_score += Decimal("10")

    if config.exclude_souvenir and any(item.souvenir for item in input_items):
        _append_reason(
            reasons,
            reason_codes,
            "Souvenir inputs are excluded by configuration.",
            SOUVENIR_EXCLUDED,
        )
        raw_risk_score += Decimal("5")

    if config.exclude_stattrak and any(item.stattrak for item in input_items):
        _append_reason(
            reasons,
            reason_codes,
            "StatTrak inputs are excluded by configuration.",
            STATTRAK_EXCLUDED,
        )
        raw_risk_score += Decimal("5")

    if _has_excluded_special_pattern_seed(config.exclude_special_pattern_seeds, paint_seeds):
        _append_reason(
            reasons,
            reason_codes,
            "One or more paint seeds are excluded by configuration.",
            SPECIAL_PATTERN_SEED_EXCLUDED,
        )
        raw_risk_score += Decimal("5")

    passed = not reason_codes
    risk_score = Decimal("0") if passed else min(raw_risk_score, Decimal("100"))

    return RiskDecision(
        passed=passed,
        reasons=reasons,
        reason_codes=reason_codes,
        risk_score=risk_score,
    )



def _append_reason(
    reasons: list[str],
    reason_codes: list[str],
    reason: str,
    reason_code: str,
) -> None:
    """Append a human-readable reason and machine-readable code."""

    reasons.append(reason)
    reason_codes.append(reason_code)



def _calculate_worst_case_loss_pct(metrics: OpportunityMetrics) -> Decimal:
    """Calculate worst-case loss percentage from opportunity metrics."""

    if metrics.worst_case_profit_cny >= 0:
        return Decimal("0")

    return abs(metrics.worst_case_profit_cny) / metrics.input_total_cost_cny



def _has_excluded_special_pattern_seed(
    excluded_seeds: set[int] | None,
    paint_seeds: list[int] | None,
) -> bool:
    """Return whether any provided paint seed is excluded by configuration."""

    if not excluded_seeds or not paint_seeds:
        return False

    return any(seed in excluded_seeds for seed in paint_seeds)
