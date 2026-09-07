"""Phase 17B — Opt-in recipe-first one-shot runtime contract.

This module owns the operator-facing recipe-first one-shot runtime's
immutable typed DTOs:

* ``RecipeFirstRuntimeConfig`` — frozen operational settings consumed by the
  new CLI and the runtime coordinator.
* ``RecipeFirstDiscoveryBudget`` — frozen bounded safety maxima for the
  Phase 17B discovery/prescreen front-half. Defaults are conservative
  placeholders that Phase 17C measurement must revisit; they are NOT
  policy-optimal production values.
* ``RecipeFirstRuntimeCounters`` — frozen per-phase + aggregate counters.
* ``RecipeFirstRuntimePhase`` / ``RecipeFirstRuntimeEvidence`` /
  ``RecipeFirstOperatorRunReport`` — frozen operator-facing terminal,
  evidence, and report DTOs.
* ``RecipeFirstRuntimeTerminalGroup`` /
  ``RecipeFirstRuntimeTerminalCode`` — frozen terminal classification
  groups and codes.
* ``RecipeFirstOutputFormat`` — frozen output format identity.
* ``RecipeFirstRuntimeError`` — frozen exception type for
  operator-blocking or contract failures.

This module does not perform any network or orchestration; it is pure
type contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Final

from app.services.market_universe_builder import StatTrakMode
from app.services.recipe_solver import RecipeEnumerationConfig

__all__ = (
    "EXIT_CODE_CONTRACT_OR_CONFIG",
    "EXIT_CODE_INCOMPLETE_OR_PROVIDER",
    "EXIT_CODE_SUCCESS_OR_NO_OPPORTUNITY",
    "PHASE17B_DISCOVERY_STATE_BUDGET_DEFAULT",
    "PHASE17B_DISCOVERY_PRESCREEN_BATCHES_DEFAULT",
    "PHASE17B_DISCOVERY_PRESCREEN_NAMES_DEFAULT",
    "RecipeFirstRuntimeProductiveInputRarities",
    "RecipeFirstRuntimeProductiveStattrakModes",
    "RecipeFirstDiscoveryBudget",
    "RecipeFirstEvaluationSummary",
    "RecipeFirstOperatorRunReport",
    "RecipeFirstOutputFormat",
    "RecipeFirstRankedFamilySummary",
    "RecipeFirstRuntimeConfig",
    "RecipeFirstRuntimeCounters",
    "RecipeFirstRuntimeError",
    "RecipeFirstRuntimeEvidence",
    "RecipeFirstRuntimePhase",
    "RecipeFirstRuntimeTerminalCode",
    "RecipeFirstRuntimeTerminalGroup",
)


EXIT_CODE_SUCCESS_OR_NO_OPPORTUNITY: Final[int] = 0
EXIT_CODE_INCOMPLETE_OR_PROVIDER: Final[int] = 2
EXIT_CODE_CONTRACT_OR_CONFIG: Final[int] = 3


class RecipeFirstOutputFormat(StrEnum):
    HUMAN = "human"
    JSON = "json"


class RecipeFirstRuntimeTerminalGroup(StrEnum):
    SUCCESS = "success"
    EXPECTED_NO_OPPORTUNITY = "expected_no_opportunity"
    INCOMPLETE_OR_PROVIDER = "incomplete_or_provider"
    CONTRACT_OR_CONFIGURATION = "contract_or_configuration"


class RecipeFirstRuntimeTerminalCode(StrEnum):
    SUCCESS_OPPORTUNITIES_FOUND = "SUCCESS_OPPORTUNITIES_FOUND"
    SUCCESS_NO_QUALIFYING_OPPORTUNITY = "SUCCESS_NO_QUALIFYING_OPPORTUNITY"
    SUCCESS_PREVIEW = "SUCCESS_PREVIEW"
    NO_CONCRETE_SELECTION = "NO_CONCRETE_SELECTION"
    RISK_FILTER_REJECTED = "RISK_FILTER_REJECTED"
    PRESCREEN_INCOMPLETE = "PRESCREEN_INCOMPLETE"
    BUFF_ACQUISITION_INSUFFICIENT = "BUFF_ACQUISITION_INSUFFICIENT"
    FINAL_VALUATION_INCOMPLETE = "FINAL_VALUATION_INCOMPLETE"
    VALUATION_REQUEST_BUDGET_BLOCKED = "VALUATION_REQUEST_BUDGET_BLOCKED"
    EXTERNAL_PROVIDER_FAILURE = "EXTERNAL_PROVIDER_FAILURE"
    CONFIGURATION_BLOCKED = "CONFIGURATION_BLOCKED"
    IDENTITY_INTRINSIC_METADATA_CONTRACT_FAILURE = (
        "IDENTITY_INTRINSIC_METADATA_CONTRACT_FAILURE"
    )
    INTERNAL_CONTRACT_FAILURE = "INTERNAL_CONTRACT_FAILURE"


RecipeFirstRuntimeProductiveInputRarities: Final[tuple[str, ...]] = (
    "Consumer Grade",
    "Industrial Grade",
    "Mil-Spec Grade",
    "Restricted",
    "Classified",
)
RecipeFirstRuntimeProductiveStattrakModes: Final[tuple[StatTrakMode, ...]] = (
    StatTrakMode.NORMAL,
    StatTrakMode.STATTRAK,
)


PHASE17B_DISCOVERY_STATE_BUDGET_DEFAULT: Final[int] = 256
PHASE17B_DISCOVERY_PRESCREEN_NAMES_DEFAULT: Final[int] = 10
PHASE17B_DISCOVERY_PRESCREEN_BATCHES_DEFAULT: Final[int] = 1


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstRuntimeConfig:
    """Frozen operational settings for the opt-in recipe-first one-shot."""

    enabled: bool = False
    preview: bool = False
    stattrak_modes: tuple[StatTrakMode, ...] = RecipeFirstRuntimeProductiveStattrakModes
    input_rarities: tuple[str, ...] = RecipeFirstRuntimeProductiveInputRarities
    collection_allowlist: tuple[str, ...] = ()
    max_targeted_buff_goods_ids: int = 10
    max_final_valuation_requests: int = 5
    sell_fee_rate: Decimal = Decimal("0.025")
    enumeration_config: RecipeEnumerationConfig = RecipeEnumerationConfig()
    cache_backend: str = "inmemory"
    output_format: RecipeFirstOutputFormat = RecipeFirstOutputFormat.HUMAN

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise RecipeFirstRuntimeError("enabled must be bool")
        if type(self.preview) is not bool:
            raise RecipeFirstRuntimeError("preview must be bool")
        if self.enabled is False and self.preview is True:
            raise RecipeFirstRuntimeError(
                "preview requires explicit recipe-first enable"
            )
        if not isinstance(self.stattrak_modes, tuple) or not all(
            isinstance(value, StatTrakMode) for value in self.stattrak_modes
        ):
            raise RecipeFirstRuntimeError("stattrak_modes must be exact StatTrakMode tuple")
        if not self.stattrak_modes:
            raise RecipeFirstRuntimeError("stattrak_modes must not be empty")
        if len(set(self.stattrak_modes)) != len(self.stattrak_modes):
            raise RecipeFirstRuntimeError("stattrak_modes must not contain duplicates")
        if (
            not isinstance(self.input_rarities, tuple)
            or any(type(value) is not str for value in self.input_rarities)
            or not self.input_rarities
        ):
            raise RecipeFirstRuntimeError("input_rarities must be exact non-empty tuple")
        if len(set(self.input_rarities)) != len(self.input_rarities):
            raise RecipeFirstRuntimeError("input_rarities must not contain duplicates")
        for value in self.input_rarities:
            if value not in RecipeFirstRuntimeProductiveInputRarities:
                raise RecipeFirstRuntimeError(
                    f"input rarity {value!r} is not a productive rarity"
                )
        if not isinstance(self.collection_allowlist, tuple) or any(
            type(value) is not str or not value or value != value.strip()
            for value in self.collection_allowlist
        ):
            raise RecipeFirstRuntimeError(
                "collection_allowlist must be exact tuple of non-empty strings"
            )
        if len(set(self.collection_allowlist)) != len(self.collection_allowlist):
            raise RecipeFirstRuntimeError(
                "collection_allowlist must not contain duplicates"
            )
        if (
            type(self.max_targeted_buff_goods_ids) is not int
            or not 1 <= self.max_targeted_buff_goods_ids <= 10
        ):
            raise RecipeFirstRuntimeError(
                "max_targeted_buff_goods_ids must be in [1, 10]"
            )
        if (
            type(self.max_final_valuation_requests) is not int
            or not 1 <= self.max_final_valuation_requests <= 60
        ):
            raise RecipeFirstRuntimeError(
                "max_final_valuation_requests must be in [1, 60]"
            )
        if (
            type(self.sell_fee_rate) is not Decimal
            or not self.sell_fee_rate.is_finite()
            or self.sell_fee_rate < 0
            or self.sell_fee_rate >= 1
        ):
            raise RecipeFirstRuntimeError(
                "sell_fee_rate must be a finite Decimal in [0, 1)"
            )
        if not isinstance(self.enumeration_config, RecipeEnumerationConfig):
            raise RecipeFirstRuntimeError(
                "enumeration_config must be RecipeEnumerationConfig"
            )
        if self.cache_backend not in {"inmemory", "redis"}:
            raise RecipeFirstRuntimeError(
                "cache_backend must be 'inmemory' or 'redis'"
            )
        if not isinstance(self.output_format, RecipeFirstOutputFormat):
            raise RecipeFirstRuntimeError("output_format must be RecipeFirstOutputFormat")


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstDiscoveryBudget:
    """Phase 17B bounded discovery/prescreen safety maxima.

    These are NOT policy-optimal production defaults. Phase 17C
    measurement must revisit every value and the defaults are conservative
    placeholders labeled ``PHASE17B_*``.
    """

    max_family_states_considered: int = PHASE17B_DISCOVERY_STATE_BUDGET_DEFAULT
    max_prescreen_names: int = PHASE17B_DISCOVERY_PRESCREEN_NAMES_DEFAULT
    max_prescreen_batch_dispatches: int = PHASE17B_DISCOVERY_PRESCREEN_BATCHES_DEFAULT

    def __post_init__(self) -> None:
        for field_name in (
            "max_family_states_considered",
            "max_prescreen_names",
            "max_prescreen_batch_dispatches",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 1:
                raise RecipeFirstRuntimeError(
                    f"{field_name} must be a positive int"
                )
        if self.max_family_states_considered > 1_000_000:
            raise RecipeFirstRuntimeError(
                "max_family_states_considered exceeds Phase 17B safety maximum"
            )
        if self.max_prescreen_names > 100:
            raise RecipeFirstRuntimeError(
                "max_prescreen_names exceeds Phase 17B safety maximum"
            )
        if self.max_prescreen_batch_dispatches > 32:
            raise RecipeFirstRuntimeError(
                "max_prescreen_batch_dispatches exceeds Phase 17B safety maximum"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstRuntimeCounters:
    """Frozen per-phase request accounting. Names mirror existing terms."""

    # discovery
    families_visited: int = 0
    families_infeasible: int = 0
    families_contract_failed: int = 0
    families_ranked_retained: int = 0
    families_ranked_excluded: int = 0
    prescreen_logical_requested: int = 0
    prescreen_unique_after_dedupe: int = 0
    prescreen_attempted: int = 0
    prescreen_dispatch_started: int = 0
    prescreen_succeeded: int = 0
    prescreen_missing: int = 0
    prescreen_terminal_selection_failures: int = 0
    prescreen_transport_error_count: int = 0
    prescreen_atomically_blocked: int = 0
    # BUFF acquisition
    buff_attempted: int = 0
    buff_dispatch_started: int = 0
    buff_succeeded: int = 0
    buff_provider_failure: int = 0
    buff_contract_failure: int = 0
    fallback_family_used: bool = False
    # final valuation session (preserves available Phase 14C names)
    run_reuse_hits: int = 0
    cache_hits_fresh_selected: int = 0
    cache_misses: int = 0
    cache_policy_blocked: int = 0
    cache_expired: int = 0
    cache_selection_failures: int = 0
    live_demand: int = 0
    live_attempted: int = 0
    live_succeeded: int = 0
    live_failed: int = 0
    live_atomically_blocked: int = 0
    # aggregates
    evaluations_total: int = 0
    evaluations_valuation_completed: int = 0
    evaluations_risk_rejected: int = 0
    evaluations_budget_blocked: int = 0
    opportunities_found: int = 0

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if name == "fallback_family_used":
                if type(value) is not bool:
                    raise RecipeFirstRuntimeError(
                        "fallback_family_used must be bool"
                    )
                continue
            if type(value) is not int or value < 0:
                raise RecipeFirstRuntimeError(f"{name} must be non-negative int")


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstRankedFamilySummary:
    """One rank slot; safe exact-name + key + rank-only economics."""

    rank: int
    family_key: str
    family_hash: str
    base_estimated_roi: Fraction | None
    base_estimated_profit_cny: Decimal | None
    conservative_estimated_roi: Fraction | None
    conservative_estimated_profit_cny: Decimal | None
    base_known_sell_count_sum: int | None
    targeted_goods_count: int | None
    exclusion_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.rank) is not int or self.rank < 1:
            raise RecipeFirstRuntimeError("rank must be positive int")
        for field_name in ("family_key", "family_hash"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise RecipeFirstRuntimeError(f"{field_name} must be non-empty string")
        if len(self.family_hash) != 64:
            raise RecipeFirstRuntimeError("family_hash must be full SHA-256 hex")
        if not isinstance(self.exclusion_reasons, tuple):
            raise RecipeFirstRuntimeError("exclusion_reasons must be tuple")
        for decimal_field in (
            "base_estimated_profit_cny",
            "conservative_estimated_profit_cny",
        ):
            value = getattr(self, decimal_field)
            if value is not None and not isinstance(value, Decimal):
                raise RecipeFirstRuntimeError(
                    f"{decimal_field} must be Decimal or None"
                )
        for fraction_field in (
            "base_estimated_roi",
            "conservative_estimated_roi",
        ):
            value = getattr(self, fraction_field)
            if value is not None and not isinstance(value, Fraction):
                raise RecipeFirstRuntimeError(
                    f"{fraction_field} must be Fraction or None"
                )
        for field_name in ("base_known_sell_count_sum", "targeted_goods_count"):
            value = getattr(self, field_name)
            if value is not None and (type(value) is not int or value < 0):
                raise RecipeFirstRuntimeError(
                    f"{field_name} must be non-negative int or None"
                )


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstEvaluationSummary:
    """One downstream evaluation wrapped without recomputing domain values."""

    index: int
    valuation_completed: bool
    rejection_reason: str | None
    concrete_input_count: int
    output_names: tuple[str, ...]
    output_probabilities: tuple[float, ...]
    output_floats: tuple[float, ...]
    output_wears: tuple[str, ...]
    final_price_cny: tuple[Decimal, ...]
    final_price_source: tuple[str, ...]
    input_total_cost_cny: Decimal | None
    expected_gross_revenue_cny: Decimal | None
    expected_profit_cny: Decimal | None
    roi: Decimal | None
    profit_probability: float | None
    worst_case_loss_cny: Decimal | None
    risk_passed: bool | None
    risk_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.index) is not int or self.index < 0:
            raise RecipeFirstRuntimeError("evaluation index must be non-negative int")
        if type(self.valuation_completed) is not bool:
            raise RecipeFirstRuntimeError("valuation_completed must be bool")
        if type(self.concrete_input_count) is not int or self.concrete_input_count < 0:
            raise RecipeFirstRuntimeError("concrete_input_count must be non-negative int")
        if not (
            len(self.output_names)
            == len(self.output_probabilities)
            == len(self.output_floats)
            == len(self.output_wears)
        ):
            raise RecipeFirstRuntimeError("evaluation structural rows must align")
        if self.valuation_completed and not (
            len(self.output_names)
            == len(self.final_price_cny)
            == len(self.final_price_source)
        ):
            raise RecipeFirstRuntimeError("completed evaluation prices must align")


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstRuntimePhase:
    """One phase outcome used in the report."""

    name: str
    status: str
    detail: str = ""

    def __post_init__(self) -> None:
        for field_name in ("name", "status"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise RecipeFirstRuntimeError(f"{field_name} must be non-empty string")


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstRuntimeEvidence:
    """Frozen evidence attached to a report.

    Includes only summary evidence that already exists in mature
    service-layer DTOs and safe derived counters.
    """

    prescreen_quote_names: tuple[str, ...]
    prescreen_missing_names: tuple[str, ...]
    prescreen_terminal_selection_failures: tuple[tuple[str, str], ...]
    ranked_families: tuple[RecipeFirstRankedFamilySummary, ...]
    selected_active_family_key: str | None
    selected_active_family_hash: str | None
    fallback_family_key: str | None
    fallback_reason: str | None
    targeted_goods_ids: tuple[str, ...]
    targeted_goods_market_hash_names: tuple[str, ...]
    concrete_input_summary_count: int
    concrete_output_names: tuple[str, ...]
    concrete_output_probabilities: tuple[float, ...]
    concrete_output_floats: tuple[float, ...]
    concrete_output_wears: tuple[str, ...]
    final_quote_market_hash_names: tuple[str, ...]
    final_quote_price_cny: tuple[Decimal, ...]
    final_quote_source: tuple[str, ...]
    evaluations: tuple[RecipeFirstEvaluationSummary, ...]
    selected_family_evaluations_count: int
    selected_family_evaluations_complete: int
    selected_family_opportunities: int
    input_total_cost_cny: Decimal | None
    expected_gross_revenue_cny: Decimal | None
    expected_profit_cny: Decimal | None
    roi: Decimal | None
    profit_probability: float | None
    worst_case_loss_cny: Decimal | None
    risk_passed: bool | None
    risk_reason_codes: tuple[str, ...]
    risk_rejection_reason: str | None

    def __post_init__(self) -> None:
        for field_name in (
            "prescreen_quote_names",
            "prescreen_missing_names",
            "targeted_goods_ids",
            "targeted_goods_market_hash_names",
            "concrete_output_names",
            "concrete_output_probabilities",
            "concrete_output_floats",
            "concrete_output_wears",
            "final_quote_market_hash_names",
            "final_quote_price_cny",
            "final_quote_source",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise RecipeFirstRuntimeError(f"{field_name} must be tuple")
        for value in self.concrete_output_probabilities:
            if type(value) is not float:
                raise RecipeFirstRuntimeError(
                    "concrete_output_probabilities must be float tuple"
                )
        for value in self.concrete_output_floats:
            if type(value) is not float:
                raise RecipeFirstRuntimeError(
                    "concrete_output_floats must be float tuple"
                )
        for value in self.final_quote_price_cny:
            if not isinstance(value, Decimal):
                raise RecipeFirstRuntimeError(
                    "final_quote_price_cny must be Decimal tuple"
                )
        if not isinstance(self.evaluations, tuple) or any(
            type(value) is not RecipeFirstEvaluationSummary
            for value in self.evaluations
        ):
            raise RecipeFirstRuntimeError(
                "evaluations must contain RecipeFirstEvaluationSummary values"
            )
        for name in (
            "concrete_input_summary_count",
            "selected_family_evaluations_count",
            "selected_family_evaluations_complete",
            "selected_family_opportunities",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise RecipeFirstRuntimeError(f"{name} must be non-negative int")
        for name in (
            "input_total_cost_cny",
            "expected_gross_revenue_cny",
            "expected_profit_cny",
            "roi",
            "worst_case_loss_cny",
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Decimal):
                raise RecipeFirstRuntimeError(f"{name} must be Decimal or None")
        if self.profit_probability is not None and type(
            self.profit_probability
        ) is not float:
            raise RecipeFirstRuntimeError(
                "profit_probability must be float or None"
            )
        if self.risk_passed is not None and type(self.risk_passed) is not bool:
            raise RecipeFirstRuntimeError("risk_passed must be bool or None")
        if not isinstance(self.risk_reason_codes, tuple) or any(
            type(value) is not str for value in self.risk_reason_codes
        ):
            raise RecipeFirstRuntimeError("risk_reason_codes must be tuple[str, ...]")
        if self.risk_rejection_reason is not None and type(
            self.risk_rejection_reason
        ) is not str:
            raise RecipeFirstRuntimeError(
                "risk_rejection_reason must be str or None"
            )
        if self.selected_active_family_key is not None and not isinstance(
            self.selected_active_family_key, str
        ):
            raise RecipeFirstRuntimeError("selected_active_family_key must be str or None")
        if self.selected_active_family_hash is not None and (
            not isinstance(self.selected_active_family_hash, str)
            or len(self.selected_active_family_hash) != 64
        ):
            raise RecipeFirstRuntimeError(
                "selected_active_family_hash must be SHA-256 hex or None"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstOperatorRunReport:
    """Operator-facing recipe-first one-shot report DTO.

    Wraps existing service evidence. Does NOT recompute math. Does NOT
    include credentials, raw provider payloads, seller/account data, cookies,
    auth headers, webhook values, or listing/asset IDs.
    """

    mode: str
    run_id: int
    terminal_group: RecipeFirstRuntimeTerminalGroup
    terminal_code: RecipeFirstRuntimeTerminalCode
    config_identity: tuple[str, ...]
    discovery_budget: RecipeFirstDiscoveryBudget
    counters: RecipeFirstRuntimeCounters
    phases: tuple[RecipeFirstRuntimePhase, ...]
    evidence: RecipeFirstRuntimeEvidence
    incompleteness_flags: tuple[str, ...]
    safe_error_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.mode not in {"recipe-first-one-shot", "recipe-first-preview"}:
            raise RecipeFirstRuntimeError(
                "mode must be 'recipe-first-one-shot' or 'recipe-first-preview'"
            )
        if type(self.run_id) is not int or self.run_id < 1:
            raise RecipeFirstRuntimeError("run_id must be positive int")
        if not isinstance(
            self.terminal_group, RecipeFirstRuntimeTerminalGroup
        ):
            raise RecipeFirstRuntimeError(
                "terminal_group must be RecipeFirstRuntimeTerminalGroup"
            )
        if not isinstance(self.terminal_code, RecipeFirstRuntimeTerminalCode):
            raise RecipeFirstRuntimeError(
                "terminal_code must be RecipeFirstRuntimeTerminalCode"
            )
        if not isinstance(self.discovery_budget, RecipeFirstDiscoveryBudget):
            raise RecipeFirstRuntimeError(
                "discovery_budget must be RecipeFirstDiscoveryBudget"
            )
        if not isinstance(self.counters, RecipeFirstRuntimeCounters):
            raise RecipeFirstRuntimeError(
                "counters must be RecipeFirstRuntimeCounters"
            )
        if not isinstance(self.evidence, RecipeFirstRuntimeEvidence):
            raise RecipeFirstRuntimeError(
                "evidence must be RecipeFirstRuntimeEvidence"
            )
        if not isinstance(self.phases, tuple):
            raise RecipeFirstRuntimeError("phases must be tuple")
        if not isinstance(self.config_identity, tuple):
            raise RecipeFirstRuntimeError("config_identity must be tuple")
        for value in self.config_identity:
            if not isinstance(value, str):
                raise RecipeFirstRuntimeError(
                    "config_identity must be tuple[str, ...]"
                )
        if not isinstance(self.incompleteness_flags, tuple) or any(
            type(value) is not str for value in self.incompleteness_flags
        ):
            raise RecipeFirstRuntimeError(
                "incompleteness_flags must be tuple[str, ...]"
            )
        if not isinstance(self.safe_error_codes, tuple):
            raise RecipeFirstRuntimeError("safe_error_codes must be tuple")
        for value in self.safe_error_codes:
            if not isinstance(value, str):
                raise RecipeFirstRuntimeError(
                    "safe_error_codes must be tuple[str, ...]"
                )


class RecipeFirstRuntimeError(RuntimeError):
    """Operator-blocking or contract failure for the recipe-first one-shot."""


def exit_code_for_terminal_group(
    group: RecipeFirstRuntimeTerminalGroup,
) -> int:
    if group in (
        RecipeFirstRuntimeTerminalGroup.SUCCESS,
        RecipeFirstRuntimeTerminalGroup.EXPECTED_NO_OPPORTUNITY,
    ):
        return EXIT_CODE_SUCCESS_OR_NO_OPPORTUNITY
    if group is RecipeFirstRuntimeTerminalGroup.INCOMPLETE_OR_PROVIDER:
        return EXIT_CODE_INCOMPLETE_OR_PROVIDER
    return EXIT_CODE_CONTRACT_OR_CONFIG
