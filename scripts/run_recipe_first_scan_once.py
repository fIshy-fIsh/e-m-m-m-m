"""Phase 17B — Opt-in recipe-first one-shot CLI.

This is a separate explicit composition root from
``scripts/run_live_scan_once.py``. It:

* requires an explicit ``--enable-recipe-first`` opt-in (else refuses
  pre-network with ``CONFIGURATION_BLOCKED`` and exit 3);
* supports ``--preview`` for deterministic zero-market-network shape
  verification (``SUCCESS_PREVIEW``, exit 0);
* constructs an opt-in ``RecipeFirstRuntimeCoordinator`` exactly once;
* renders either a deterministic human summary or a stable JSON
  document over the ``RecipeFirstOperatorRunReport`` DTO;
* closes all injected resources deterministically through an
  ``AsyncExitStack``;
* performs ZERO SteamDT / BUFF / cache network requests when the
  caller has not supplied external real clients;
* does NOT import the Phase 16G validation harness;
* does NOT import or modify goods-first code.

Production default is OFF. This CLI is opt-in only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import AsyncExitStack
from decimal import Decimal
from pathlib import Path
from typing import cast

import httpx

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clients.buff_anonymous_listing_client import BuffAnonymousListingHttpClient
from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.buff_intrinsic_flag_resolver import CanonicalNameIntrinsicFlagResolver
from app.services.buff_listing_provider import BuffListingProvider
from app.services.market_universe_builder import StatTrakMode
from app.services.price_cache_factory import (
    SteamDTPriceCacheSettings,
    create_steamdt_price_cache_runtime,
)
from app.services.recipe_first_runtime_contract import (
    EXIT_CODE_CONTRACT_OR_CONFIG,
    RecipeFirstDiscoveryBudget,
    RecipeFirstOperatorRunReport,
    RecipeFirstOutputFormat,
    RecipeFirstRuntimeConfig,
    RecipeFirstRuntimeCounters,
    RecipeFirstRuntimeError,
    RecipeFirstRuntimeEvidence,
    RecipeFirstRuntimePhase,
    RecipeFirstRuntimeProductiveInputRarities,
    RecipeFirstRuntimeProductiveStattrakModes,
    RecipeFirstRuntimeTerminalCode,
    RecipeFirstRuntimeTerminalGroup,
    exit_code_for_terminal_group,
)
from app.services.recipe_first_runtime_coordinator import (
    RecipeFirstRuntimeCoordinator,
    RecipeFirstRuntimeCoordinatorError,
)
from app.services.risk_filter import RiskFilterConfig
from app.services.scanner_cached_buff_price_resolver import (
    ScannerCachedBuffPriceResolver,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.steamdt_buff_price_provider import SteamDTBuffPriceProvider
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.valuation_service import ValuationConfig, ValuationService

ARTIFACT_DIR_ENV: str = "RECIPE_FIRST_PHASE17B_ARTIFACT_DIR"
RESULT_FILENAME: str = "phase17b_result.json"

DEFAULT_IDENTITY_SNAPSHOT: Path = Path(
    "data/identity/buff_identity_v1.json"
)
DEFAULT_METADATA_SNAPSHOT: Path = Path(
    "data/metadata/skin_metadata_v1.json"
)
DEFAULT_OUTPUT_FORMAT: RecipeFirstOutputFormat = (
    RecipeFirstOutputFormat.HUMAN
)


class _RecipeFirstScanSettings:
    """Frozen CLI settings; credentials remain environment-owned."""

    def __init__(
        self,
        *,
        identity_snapshot: Path,
        metadata_snapshot: Path,
        steamdt_base_url: str,
        steamdt_api_key: str,
        steamdt_dry_run: bool,
        steamdt_price_cache_backend: str,
        steamdt_price_cache_redis_namespace: str,
        redis_url: str,
        sell_fee_rate: Decimal,
        min_roi: Decimal,
        min_expected_profit_cny: Decimal,
        max_worst_case_loss_pct: Decimal,
        min_profit_probability: float,
        max_input_total_cost_cny: Decimal,
    ) -> None:
        if sell_fee_rate < 0 or sell_fee_rate >= 1:
            raise RecipeFirstRuntimeError("sell_fee_rate must be in [0, 1)")
        self.identity_snapshot = identity_snapshot
        self.metadata_snapshot = metadata_snapshot
        self.steamdt_base_url = steamdt_base_url
        self.steamdt_api_key = steamdt_api_key
        self.steamdt_dry_run = steamdt_dry_run
        self.steamdt_price_cache_backend = steamdt_price_cache_backend
        self.steamdt_price_cache_redis_namespace = (
            steamdt_price_cache_redis_namespace
        )
        self.redis_url = redis_url
        self.sell_fee_rate = sell_fee_rate
        self.min_roi = min_roi
        self.min_expected_profit_cny = min_expected_profit_cny
        self.max_worst_case_loss_pct = max_worst_case_loss_pct
        self.min_profit_probability = min_profit_probability
        self.max_input_total_cost_cny = max_input_total_cost_cny

    @classmethod
    def from_env(
        cls,
        *,
        identity_snapshot: Path,
        metadata_snapshot: Path,
    ) -> _RecipeFirstScanSettings:
        return cls(
            identity_snapshot=identity_snapshot,
            metadata_snapshot=metadata_snapshot,
            steamdt_base_url=os.environ.get(
                "STEAMDT_BASE_URL", "https://open.steamdt.com"
            ),
            steamdt_api_key=os.environ.get("STEAMDT_API_KEY", ""),
            steamdt_dry_run=os.environ.get("STEAMDT_DRY_RUN", "true").strip().lower()
            not in {"0", "false", "no", "off"},
            steamdt_price_cache_backend=os.environ.get(
                "STEAMDT_PRICE_CACHE_BACKEND", "inmemory"
            ),
            steamdt_price_cache_redis_namespace=os.environ.get(
                "STEAMDT_PRICE_CACHE_REDIS_NAMESPACE", "steamdt-price-cache-v1"
            ),
            redis_url=os.environ.get("REDIS_URL", ""),
            sell_fee_rate=Decimal(os.environ.get("RECIPE_FIRST_SELL_FEE_RATE", "0.025")),
            min_roi=Decimal(os.environ.get("RECIPE_FIRST_MIN_ROI", "0.05")),
            min_expected_profit_cny=Decimal(
                os.environ.get("RECIPE_FIRST_MIN_PROFIT", "20.0")
            ),
            max_worst_case_loss_pct=Decimal(
                os.environ.get("RECIPE_FIRST_MAX_LOSS_PCT", "0.25")
            ),
            min_profit_probability=float(
                os.environ.get("RECIPE_FIRST_MIN_PROFIT_PROB", "0.35")
            ),
            max_input_total_cost_cny=Decimal(
                os.environ.get("RECIPE_FIRST_MAX_INPUT_COST", "1000.0")
            ),
        )

    def validate_live(self) -> None:
        if self.steamdt_dry_run:
            raise RecipeFirstRuntimeError("STEAMDT_DRY_RUN must be false")
        if not self.steamdt_api_key:
            raise RecipeFirstRuntimeError("STEAMDT_API_KEY is required")
        if self.steamdt_price_cache_backend not in {"inmemory", "redis"}:
            raise RecipeFirstRuntimeError("unsupported cache backend")
        if (
            self.steamdt_price_cache_backend == "redis"
            and not self.redis_url.strip()
        ):
            raise RecipeFirstRuntimeError(
                "REDIS_URL is required for redis cache backend"
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_recipe_first_scan_once",
        description=(
            "Phase 17B opt-in recipe-first one-shot scan. Production "
            "default is OFF. Requires explicit --enable-recipe-first."
        ),
    )
    parser.add_argument(
        "--enable-recipe-first",
        action="store_true",
        help="Explicit opt-in. Without this flag, the CLI refuses pre-network.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help=(
            "Preview mode: validates pinned snapshots, structural scope, "
            "and discovery budget shape without constructing any external "
            "SteamDT/BUFF/cache client. Requires --enable-recipe-first."
        ),
    )
    parser.add_argument(
        "--identity-snapshot",
        type=Path,
        default=DEFAULT_IDENTITY_SNAPSHOT,
    )
    parser.add_argument(
        "--metadata-snapshot",
        type=Path,
        default=DEFAULT_METADATA_SNAPSHOT,
    )
    parser.add_argument(
        "--input-rarity",
        choices=RecipeFirstRuntimeProductiveInputRarities,
        default=None,
        help=(
            "Override single-stratum input rarity (Phase 17B composes "
            "one stratum; multi-rarity expansion is Phase 17C)."
        ),
    )
    parser.add_argument(
        "--stattrak-mode",
        choices=[value.value for value in RecipeFirstRuntimeProductiveStattrakModes],
        default=None,
        help="Override single-stratum StatTrak mode.",
    )
    parser.add_argument(
        "--collection",
        action="append",
        default=[],
        help="Optional exact collection allowlist.",
    )
    parser.add_argument(
        "--max-targeted-buff-goods-ids",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--max-final-valuation-requests",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--max-recipe-candidates-returned",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--max-candidate-states-explored",
        type=int,
        default=256,
    )
    parser.add_argument(
        "--max-family-states-considered",
        type=int,
        default=256,
    )
    parser.add_argument(
        "--max-prescreen-names",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--max-prescreen-batch-dispatches",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--cache-backend",
        choices=("inmemory", "redis"),
        default="inmemory",
    )
    parser.add_argument(
        "--output-format",
        choices=("human", "json"),
        default=DEFAULT_OUTPUT_FORMAT.value,
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help=(
            "Optional directory to persist the safe result JSON. "
            "Defaults to $RECIPE_FIRST_PHASE17B_ARTIFACT_DIR or /tmp/cs2-phase17b."
        ),
    )
    return parser


def _resolve_stratum_inputs(
    args: argparse.Namespace,
) -> tuple[tuple[str, ...], tuple[StatTrakMode, ...]]:
    input_rarities: tuple[str, ...] = (
        (args.input_rarity,) if args.input_rarity else RecipeFirstRuntimeProductiveInputRarities
    )
    stattrak_modes: tuple[StatTrakMode, ...] = (
        (StatTrakMode(args.stattrak_mode),)
        if args.stattrak_mode
        else RecipeFirstRuntimeProductiveStattrakModes
    )
    return input_rarities, stattrak_modes


def _artifact_root(args: argparse.Namespace) -> Path:
    if args.artifact_dir is not None:
        return Path(args.artifact_dir)
    env_dir = os.environ.get(ARTIFACT_DIR_ENV)
    if env_dir:
        return Path(env_dir)
    return Path(os.environ.get("TEMP", "/tmp")) / "cs2-phase17b"


def _validate_bounded_int(
    *, name: str, value: int, lower: int, upper: int
) -> None:
    if type(value) is not int or not lower <= value <= upper:
        raise RecipeFirstRuntimeError(
            f"{name} must be an int in [{lower}, {upper}]"
        )


def _validate_runtime_config(config: RecipeFirstRuntimeConfig) -> None:
    _validate_bounded_int(
        name="max-targeted-buff-goods-ids",
        value=config.max_targeted_buff_goods_ids,
        lower=1,
        upper=10,
    )
    _validate_bounded_int(
        name="max-final-valuation-requests",
        value=config.max_final_valuation_requests,
        lower=1,
        upper=60,
    )


def _validate_discovery_budget(budget: RecipeFirstDiscoveryBudget) -> None:
    if budget.max_family_states_considered > 1_000_000:
        raise RecipeFirstRuntimeError(
            "max-family-states-considered exceeds Phase 17B safety maximum"
        )
    if budget.max_prescreen_names > 100:
        raise RecipeFirstRuntimeError(
            "max-prescreen-names exceeds Phase 17B safety maximum"
        )
    if budget.max_prescreen_batch_dispatches > 32:
        raise RecipeFirstRuntimeError(
            "max-prescreen-batch-dispatches exceeds Phase 17B safety maximum"
        )


def _resolve_enable(env: Mapping[str, str], args: argparse.Namespace) -> bool:
    del env
    return bool(args.enable_recipe_first)


def _resolve_preview(env: Mapping[str, str], args: argparse.Namespace) -> bool:
    del env
    return bool(args.preview)


def _serialize_report(
    report: RecipeFirstOperatorRunReport,
) -> dict[str, object]:
    """Convert a Report DTO to a JSON-safe dict without recomputing math.

    Decimal / Fraction are serialized deterministically as exact strings.
    Counters and evidence are taken straight from the immutable DTO.
    """

    counters = report.counters
    evidence = report.evidence
    payload: dict[str, object] = {
        "mode": report.mode,
        "run_id": report.run_id,
        "terminal_group": report.terminal_group.value,
        "terminal_code": report.terminal_code.value,
        "config_identity": list(report.config_identity),
        "discovery_budget": {
            "max_family_states_considered": (
                report.discovery_budget.max_family_states_considered
            ),
            "max_prescreen_names": report.discovery_budget.max_prescreen_names,
            "max_prescreen_batch_dispatches": (
                report.discovery_budget.max_prescreen_batch_dispatches
            ),
        },
        "counters": {
            "families_visited": counters.families_visited,
            "families_infeasible": counters.families_infeasible,
            "families_contract_failed": counters.families_contract_failed,
            "families_ranked_retained": counters.families_ranked_retained,
            "families_ranked_excluded": counters.families_ranked_excluded,
            "prescreen_logical_requested": counters.prescreen_logical_requested,
            "prescreen_unique_after_dedupe": (
                counters.prescreen_unique_after_dedupe
            ),
            "prescreen_attempted": counters.prescreen_attempted,
            "prescreen_dispatch_started": counters.prescreen_dispatch_started,
            "prescreen_succeeded": counters.prescreen_succeeded,
            "prescreen_missing": counters.prescreen_missing,
            "prescreen_terminal_selection_failures": (
                counters.prescreen_terminal_selection_failures
            ),
            "prescreen_transport_error_count": (
                counters.prescreen_transport_error_count
            ),
            "prescreen_atomically_blocked": counters.prescreen_atomically_blocked,
            "buff_attempted": counters.buff_attempted,
            "buff_dispatch_started": counters.buff_dispatch_started,
            "buff_succeeded": counters.buff_succeeded,
            "buff_provider_failure": counters.buff_provider_failure,
            "buff_contract_failure": counters.buff_contract_failure,
            "fallback_family_used": counters.fallback_family_used,
            "run_reuse_hits": counters.run_reuse_hits,
            "cache_hits_fresh_selected": counters.cache_hits_fresh_selected,
            "cache_misses": counters.cache_misses,
            "cache_policy_blocked": counters.cache_policy_blocked,
            "cache_expired": counters.cache_expired,
            "cache_selection_failures": counters.cache_selection_failures,
            "live_demand": counters.live_demand,
            "live_attempted": counters.live_attempted,
            "live_succeeded": counters.live_succeeded,
            "live_failed": counters.live_failed,
            "live_atomically_blocked": counters.live_atomically_blocked,
            "evaluations_total": counters.evaluations_total,
            "evaluations_valuation_completed": (
                counters.evaluations_valuation_completed
            ),
            "evaluations_risk_rejected": counters.evaluations_risk_rejected,
            "evaluations_budget_blocked": counters.evaluations_budget_blocked,
            "opportunities_found": counters.opportunities_found,
        },
        "phases": [
            {"name": phase.name, "status": phase.status, "detail": phase.detail}
            for phase in report.phases
        ],
        "evidence": {
            "prescreen_quote_names": list(evidence.prescreen_quote_names),
            "prescreen_missing_names": list(evidence.prescreen_missing_names),
            "prescreen_terminal_selection_failures": [
                list(entry) for entry in evidence.prescreen_terminal_selection_failures
            ],
            "ranked_families": [
                {
                    "rank": summary.rank,
                    "family_key": summary.family_key,
                    "family_hash": summary.family_hash,
                    "base_estimated_roi": (
                        str(summary.base_estimated_roi)
                        if summary.base_estimated_roi is not None
                        else None
                    ),
                    "base_estimated_profit_cny": (
                        str(summary.base_estimated_profit_cny)
                        if summary.base_estimated_profit_cny is not None
                        else None
                    ),
                    "conservative_estimated_roi": (
                        str(summary.conservative_estimated_roi)
                        if summary.conservative_estimated_roi is not None
                        else None
                    ),
                    "conservative_estimated_profit_cny": (
                        str(summary.conservative_estimated_profit_cny)
                        if summary.conservative_estimated_profit_cny is not None
                        else None
                    ),
                    "base_known_sell_count_sum": summary.base_known_sell_count_sum,
                    "targeted_goods_count": summary.targeted_goods_count,
                    "exclusion_reasons": list(summary.exclusion_reasons),
                }
                for summary in evidence.ranked_families
            ],
            "selected_active_family_key": evidence.selected_active_family_key,
            "selected_active_family_hash": evidence.selected_active_family_hash,
            "fallback_family_key": evidence.fallback_family_key,
            "fallback_reason": evidence.fallback_reason,
            "targeted_goods_ids": list(evidence.targeted_goods_ids),
            "targeted_goods_market_hash_names": list(
                evidence.targeted_goods_market_hash_names
            ),
            "concrete_input_summary_count": evidence.concrete_input_summary_count,
            "concrete_output_names": list(evidence.concrete_output_names),
            "concrete_output_probabilities": list(
                evidence.concrete_output_probabilities
            ),
            "concrete_output_floats": list(evidence.concrete_output_floats),
            "concrete_output_wears": list(evidence.concrete_output_wears),
            "final_quote_market_hash_names": list(
                evidence.final_quote_market_hash_names
            ),
            "final_quote_price_cny": [
                str(value) for value in evidence.final_quote_price_cny
            ],
            "final_quote_source": list(evidence.final_quote_source),
            "evaluations": [
                {
                    "index": item.index,
                    "valuation_completed": item.valuation_completed,
                    "rejection_reason": item.rejection_reason,
                    "concrete_input_count": item.concrete_input_count,
                    "output_names": list(item.output_names),
                    "output_probabilities": list(item.output_probabilities),
                    "output_floats": list(item.output_floats),
                    "output_wears": list(item.output_wears),
                    "final_price_cny": [
                        str(value) for value in item.final_price_cny
                    ],
                    "final_price_source": list(item.final_price_source),
                    "input_total_cost_cny": (
                        str(item.input_total_cost_cny)
                        if item.input_total_cost_cny is not None
                        else None
                    ),
                    "expected_gross_revenue_cny": (
                        str(item.expected_gross_revenue_cny)
                        if item.expected_gross_revenue_cny is not None
                        else None
                    ),
                    "expected_profit_cny": (
                        str(item.expected_profit_cny)
                        if item.expected_profit_cny is not None
                        else None
                    ),
                    "roi": str(item.roi) if item.roi is not None else None,
                    "profit_probability": item.profit_probability,
                    "worst_case_loss_cny": (
                        str(item.worst_case_loss_cny)
                        if item.worst_case_loss_cny is not None
                        else None
                    ),
                    "risk_passed": item.risk_passed,
                    "risk_reason_codes": list(item.risk_reason_codes),
                }
                for item in evidence.evaluations
            ],
            "selected_family_evaluations_count": (
                evidence.selected_family_evaluations_count
            ),
            "selected_family_evaluations_complete": (
                evidence.selected_family_evaluations_complete
            ),
            "selected_family_opportunities": (
                evidence.selected_family_opportunities
            ),
            "input_total_cost_cny": (
                str(evidence.input_total_cost_cny)
                if evidence.input_total_cost_cny is not None
                else None
            ),
            "expected_gross_revenue_cny": (
                str(evidence.expected_gross_revenue_cny)
                if evidence.expected_gross_revenue_cny is not None
                else None
            ),
            "expected_profit_cny": (
                str(evidence.expected_profit_cny)
                if evidence.expected_profit_cny is not None
                else None
            ),
            "roi": str(evidence.roi) if evidence.roi is not None else None,
            "profit_probability": evidence.profit_probability,
            "worst_case_loss_cny": (
                str(evidence.worst_case_loss_cny)
                if evidence.worst_case_loss_cny is not None
                else None
            ),
            "risk_passed": evidence.risk_passed,
            "risk_reason_codes": list(evidence.risk_reason_codes),
            "risk_rejection_reason": evidence.risk_rejection_reason,
        },
        "incompleteness_flags": list(report.incompleteness_flags),
        "safe_error_codes": list(report.safe_error_codes),
    }
    return payload


def _render_human(report: RecipeFirstOperatorRunReport) -> str:
    counters = report.counters
    evidence = report.evidence
    lines = [
        f"phase17b_recipe_first_one_shot mode={report.mode}",
        (
            f"terminal_group={report.terminal_group.value} "
            f"terminal_code={report.terminal_code.value}"
        ),
        (
            "counters: "
            f"families_visited={counters.families_visited} "
            f"families_infeasible={counters.families_infeasible} "
            f"families_contract_failed={counters.families_contract_failed} "
            f"prescreen_logical_requested={counters.prescreen_logical_requested} "
            f"prescreen_unique_after_dedupe={counters.prescreen_unique_after_dedupe} "
            f"prescreen_dispatch_started={counters.prescreen_dispatch_started} "
            f"prescreen_succeeded={counters.prescreen_succeeded} "
            f"prescreen_missing={counters.prescreen_missing} "
            f"buff_dispatch_started={counters.buff_dispatch_started} "
            f"buff_succeeded={counters.buff_succeeded} "
            f"live_attempted={counters.live_attempted} "
            f"live_succeeded={counters.live_succeeded} "
            f"evaluations_total={counters.evaluations_total} "
            f"evaluations_valuation_completed="
            f"{counters.evaluations_valuation_completed} "
            f"evaluations_risk_rejected={counters.evaluations_risk_rejected} "
            f"evaluations_budget_blocked={counters.evaluations_budget_blocked} "
            f"opportunities_found={counters.opportunities_found}"
        ),
        (
            "evidence: "
            f"selected_active_family_key={evidence.selected_active_family_key} "
            f"selected_active_family_hash={evidence.selected_active_family_hash} "
            f"fallback_family_key={evidence.fallback_family_key} "
            f"concrete_input_summary_count={evidence.concrete_input_summary_count} "
            f"concrete_output_count={len(evidence.concrete_output_names)} "
            f"final_quote_count={len(evidence.final_quote_market_hash_names)} "
            f"incompleteness_flags={','.join(report.incompleteness_flags) or 'none'}"
        ),
    ]
    return "\n".join(lines)


def _render_json(report: RecipeFirstOperatorRunReport) -> str:
    payload = _serialize_report(report)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _print_lines(printer: Callable[[str], None], *lines: str) -> None:
    for line in lines:
        printer(line)


def _build_preview_report(
    *,
    args: argparse.Namespace,
    config: RecipeFirstRuntimeConfig,
    discovery_budget: RecipeFirstDiscoveryBudget,
    config_identity: tuple[str, ...],
) -> RecipeFirstOperatorRunReport:
    """Build an offline preview without any market/cache client construction."""

    from app.services.recipe_family import RecipeFamilyGenerator

    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        args.identity_snapshot
    )
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(
        args.metadata_snapshot
    )
    finish_index = StructuralOutputFinishIndex.from_skins(metadata.skins)
    generator = RecipeFamilyGenerator.from_catalogs(
        skins=metadata.skins,
        identity_resolver=identity,
        finish_index=finish_index,
        input_rarity=config.input_rarities[0],
        stattrak_mode=config.stattrak_modes[0],
    )
    first_family = next(generator.iter_families(), None)
    visited = 1 if first_family is not None else 0
    family_count = generator.count()
    evidence = RecipeFirstRuntimeEvidence(
        prescreen_quote_names=(),
        prescreen_missing_names=(),
        prescreen_terminal_selection_failures=(),
        ranked_families=(),
        selected_active_family_key=None,
        selected_active_family_hash=None,
        fallback_family_key=None,
        fallback_reason=None,
        targeted_goods_ids=(),
        targeted_goods_market_hash_names=(),
        concrete_input_summary_count=0,
        concrete_output_names=(),
        concrete_output_probabilities=(),
        concrete_output_floats=(),
        concrete_output_wears=(),
        final_quote_market_hash_names=(),
        final_quote_price_cny=(),
        final_quote_source=(),
        evaluations=(),
        selected_family_evaluations_count=0,
        selected_family_evaluations_complete=0,
        selected_family_opportunities=0,
        input_total_cost_cny=None,
        expected_gross_revenue_cny=None,
        expected_profit_cny=None,
        roi=None,
        profit_probability=None,
        worst_case_loss_cny=None,
        risk_passed=None,
        risk_reason_codes=(),
        risk_rejection_reason=None,
    )
    counters = RecipeFirstRuntimeCounters(
        families_visited=visited,
        families_infeasible=0,
        families_contract_failed=0,
        prescreen_logical_requested=0,
        prescreen_unique_after_dedupe=0,
        prescreen_dispatch_started=0,
        prescreen_succeeded=0,
        prescreen_missing=0,
        prescreen_terminal_selection_failures=0,
        prescreen_transport_error_count=0,
        prescreen_atomically_blocked=0,
    )
    phases = (
        RecipeFirstRuntimePhase(
            name="preview",
            status="ok",
            detail=(
                f"stratum_family_count={family_count} "
                f"first_family_hash="
                f"{first_family.family_hash if first_family is not None else 'none'} "
                "zero SteamDT client; zero BUFF client; zero cache network "
                "client; zero market I/O attempted"
            ),
        ),
    )
    return RecipeFirstOperatorRunReport(
        mode="recipe-first-preview",
        run_id=1,
        terminal_group=RecipeFirstRuntimeTerminalGroup.SUCCESS,
        terminal_code=RecipeFirstRuntimeTerminalCode.SUCCESS_PREVIEW,
        config_identity=config_identity,
        discovery_budget=discovery_budget,
        counters=counters,
        phases=phases,
        evidence=evidence,
        incompleteness_flags=(),
        safe_error_codes=(),
    )


def _build_refused_report(reason_code: str) -> RecipeFirstOperatorRunReport:
    """Build a refusal report without constructing any external client."""

    return RecipeFirstOperatorRunReport(
        mode="recipe-first-one-shot",
        run_id=1,
        terminal_group=RecipeFirstRuntimeTerminalGroup.CONTRACT_OR_CONFIGURATION,
        terminal_code=RecipeFirstRuntimeTerminalCode.CONFIGURATION_BLOCKED,
        config_identity=(f"reason={reason_code}",),
        discovery_budget=RecipeFirstDiscoveryBudget(),
        counters=RecipeFirstRuntimeCounters(),
        phases=(
            RecipeFirstRuntimePhase(
                name="preflight",
                status="refused",
                detail=reason_code,
            ),
        ),
        evidence=RecipeFirstRuntimeEvidence(
            prescreen_quote_names=(),
            prescreen_missing_names=(),
            prescreen_terminal_selection_failures=(),
            ranked_families=(),
            selected_active_family_key=None,
            selected_active_family_hash=None,
            fallback_family_key=None,
            fallback_reason=None,
            targeted_goods_ids=(),
            targeted_goods_market_hash_names=(),
            concrete_input_summary_count=0,
            concrete_output_names=(),
            concrete_output_probabilities=(),
            concrete_output_floats=(),
            concrete_output_wears=(),
            final_quote_market_hash_names=(),
            final_quote_price_cny=(),
            final_quote_source=(),
            evaluations=(),
            selected_family_evaluations_count=0,
            selected_family_evaluations_complete=0,
            selected_family_opportunities=0,
            input_total_cost_cny=None,
            expected_gross_revenue_cny=None,
            expected_profit_cny=None,
            roi=None,
            profit_probability=None,
            worst_case_loss_cny=None,
            risk_passed=None,
            risk_reason_codes=(),
            risk_rejection_reason=None,
        ),
        incompleteness_flags=(
            RecipeFirstRuntimeTerminalCode.CONFIGURATION_BLOCKED.value,
        ),
        safe_error_codes=(reason_code,),
    )


def _build_runtime_config(
    *,
    args: argparse.Namespace,
    preview: bool,
    sell_fee_rate: Decimal,
) -> RecipeFirstRuntimeConfig:
    from app.services.recipe_solver import RecipeEnumerationConfig

    input_rarities, stattrak_modes = _resolve_stratum_inputs(args)
    return RecipeFirstRuntimeConfig(
        enabled=True,
        preview=preview,
        stattrak_modes=stattrak_modes,
        input_rarities=input_rarities,
        collection_allowlist=tuple(args.collection),
        max_targeted_buff_goods_ids=args.max_targeted_buff_goods_ids,
        max_final_valuation_requests=args.max_final_valuation_requests,
        sell_fee_rate=sell_fee_rate,
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=args.max_recipe_candidates_returned,
            max_candidate_states_explored=args.max_candidate_states_explored,
        ),
        cache_backend=args.cache_backend,
        output_format=RecipeFirstOutputFormat(args.output_format),
    )


def _build_discovery_budget(args: argparse.Namespace) -> RecipeFirstDiscoveryBudget:
    return RecipeFirstDiscoveryBudget(
        max_family_states_considered=args.max_family_states_considered,
        max_prescreen_names=args.max_prescreen_names,
        max_prescreen_batch_dispatches=args.max_prescreen_batch_dispatches,
    )


async def _run_live_composition(
    *,
    args: argparse.Namespace,
    settings: _RecipeFirstScanSettings,
) -> RecipeFirstOperatorRunReport:
    """Compose the real opt-in one-shot runtime.

    Phase 17B tests replace this function or inject service seams and never
    execute its market clients. Future separately authorized live validation
    exercises this exact composition rather than the Phase 16G harness.
    """

    from app.services.steamdt_cached_price_resolver import SteamDTPriceCacheReader

    config = _build_runtime_config(
        args=args,
        preview=False,
        sell_fee_rate=settings.sell_fee_rate,
    )
    _validate_runtime_config(config)
    discovery_budget = _build_discovery_budget(args)
    _validate_discovery_budget(discovery_budget)
    settings.validate_live()

    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        settings.identity_snapshot
    )
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(
        settings.metadata_snapshot
    )
    finish_index = StructuralOutputFinishIndex.from_skins(metadata.skins)
    risk = RiskFilterConfig(
        min_roi=settings.min_roi,
        min_expected_profit_cny=settings.min_expected_profit_cny,
        max_worst_case_loss_pct=settings.max_worst_case_loss_pct,
        min_profit_probability=settings.min_profit_probability,
        max_input_total_cost_cny=settings.max_input_total_cost_cny,
    )

    async with AsyncExitStack() as stack:
        cache_runtime = await create_steamdt_price_cache_runtime(
            settings=cast(SteamDTPriceCacheSettings, settings)
        )
        stack.push_async_callback(cache_runtime.aclose)
        cached_resolver = ScannerCachedBuffPriceResolver(
            cast(SteamDTPriceCacheReader, cache_runtime.cache)
        )

        buff_http = await stack.enter_async_context(
            httpx.AsyncClient(
                base_url="https://buff.163.com",
                timeout=10.0,
                follow_redirects=False,
                trust_env=False,
                headers={"Accept": "application/json"},
            )
        )
        steamdt_http = await stack.enter_async_context(
            httpx.AsyncClient(
                base_url=settings.steamdt_base_url,
                timeout=10.0,
                follow_redirects=False,
                trust_env=False,
                headers={"Accept": "application/json"},
            )
        )
        steamdt = SteamDTHttpClient(
            SteamDTClientConfig(
                base_url=settings.steamdt_base_url,
                api_key=settings.steamdt_api_key,
                max_retries=0,
                dry_run=False,
            ),
            steamdt_http,
        )
        valuation = ValuationService(
            SteamDTBuffPriceProvider(steamdt),
            ValuationConfig(require_all_prices=True),
        )
        listing_provider = BuffListingProvider(
            BuffAnonymousListingHttpClient(buff_http)
        )
        coordinator = RecipeFirstRuntimeCoordinator(
            config=config,
            discovery_budget=discovery_budget,
            identity_resolver=identity,
            metadata_resolver=metadata,
            finish_index=finish_index,
            prescreen_transport=steamdt,
            listing_provider=listing_provider,
            valuation_service=valuation,
            risk_config=risk,
            cached_price_resolver=cached_resolver,
            intrinsic_resolver=CanonicalNameIntrinsicFlagResolver(),
        )
        return await coordinator.run_once()


async def _execute(args: argparse.Namespace) -> int:
    env = dict(os.environ)
    printer = print
    if not _resolve_enable(env, args):
        report = _build_refused_report("enable_required")
        _print_lines(
            printer,
            "phase17b_execute: refused",
            "reason: enable_required",
            "market_io_executed: no",
        )
        _persist_if_requested(report, args)
        return EXIT_CODE_CONTRACT_OR_CONFIG

    input_rarities, stattrak_modes = _resolve_stratum_inputs(args)
    preview = _resolve_preview(env, args)
    config_identity = (
        "enabled=true",
        f"preview={preview}",
        f"rarities={','.join(input_rarities)}",
        f"stattrak_modes={','.join(value.value for value in stattrak_modes)}",
        f"collection_allowlist_size={len(args.collection)}",
        f"max_targeted_buff_goods_ids={args.max_targeted_buff_goods_ids}",
        f"max_final_valuation_requests={args.max_final_valuation_requests}",
        f"enumeration_candidates={args.max_recipe_candidates_returned}",
        f"enumeration_states={args.max_candidate_states_explored}",
        f"cache_backend={args.cache_backend}",
        f"output_format={args.output_format}",
    )

    if preview:
        try:
            discovery_budget = _build_discovery_budget(args)
            _validate_discovery_budget(discovery_budget)
            preview_config = _build_runtime_config(
                args=args,
                preview=True,
                sell_fee_rate=Decimal("0.025"),
            )
            _validate_runtime_config(preview_config)
            report = _build_preview_report(
                args=args,
                config=preview_config,
                discovery_budget=discovery_budget,
                config_identity=config_identity,
            )
        except (RecipeFirstRuntimeError, ValueError) as exc:
            report = _build_refused_report(type(exc).__name__)
            _print_lines(
                printer,
                "phase17b_execute: refused",
                f"reason: {type(exc).__name__}",
                "market_io_executed: no",
            )
            _persist_if_requested(report, args)
            return EXIT_CODE_CONTRACT_OR_CONFIG
        _print_lines(
            printer,
            "phase17b_execute: complete",
            "terminal: SUCCESS_PREVIEW",
            "market_io_executed: no",
        )
        _print_rendered(report, args, printer)
        _persist_if_requested(report, args)
        return 0

    try:
        settings = _RecipeFirstScanSettings.from_env(
            identity_snapshot=args.identity_snapshot,
            metadata_snapshot=args.metadata_snapshot,
        )
        report = await _run_live_composition(
            args=args,
            settings=settings,
        )
    except (
        RecipeFirstRuntimeError,
        RecipeFirstRuntimeCoordinatorError,
        ValueError,
    ) as exc:
        report = _build_refused_report(type(exc).__name__)
        _print_lines(
            printer,
            "phase17b_execute: failed",
            f"reason: {type(exc).__name__}",
            "market_io_executed: no",
        )
        _persist_if_requested(report, args)
        return EXIT_CODE_CONTRACT_OR_CONFIG

    _print_lines(
        printer,
        "phase17b_execute: complete",
        f"terminal_group={report.terminal_group.value}",
        f"terminal_code={report.terminal_code.value}",
        f"families_visited={report.counters.families_visited}",
        f"buff_dispatch_started={report.counters.buff_dispatch_started}",
        f"live_attempted={report.counters.live_attempted}",
        f"opportunities_found={report.counters.opportunities_found}",
        (
            "market_io_executed: yes"
            if (
                report.counters.prescreen_dispatch_started > 0
                or report.counters.buff_dispatch_started > 0
                or report.counters.live_attempted > 0
            )
            else "market_io_executed: no"
        ),
    )
    _print_rendered(report, args, printer)
    _persist_if_requested(report, args)
    return exit_code_for_terminal_group(report.terminal_group)


def _print_rendered(
    report: RecipeFirstOperatorRunReport,
    args: argparse.Namespace,
    printer: Callable[[str], None],
) -> None:
    if args.output_format == "json":
        printer(_render_json(report))
    else:
        printer(_render_human(report))


def _persist_if_requested(
    report: RecipeFirstOperatorRunReport,
    args: argparse.Namespace,
) -> None:
    if args.artifact_dir is None and not os.environ.get(ARTIFACT_DIR_ENV):
        return
    root = _artifact_root(args)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    target = root / RESULT_FILENAME
    payload = _serialize_report(report)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return asyncio.run(_execute(args))


if __name__ == "__main__":
    raise SystemExit(main())
