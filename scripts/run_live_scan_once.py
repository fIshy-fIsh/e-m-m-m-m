"""Run ONE bounded live read-only opportunity scan and exit.

Example:

    py -3.13 scripts/run_live_scan_once.py --goods-id 33960

The command performs ONE scan cycle only. It never logs in to BUFF,
uses no cookies, performs no marketplace writes, and does not place
orders or execute trades.

Normal pytest never runs this script. Manual execution is an explicit
live read-only smoke.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from contextlib import AsyncExitStack
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.clients.buff_anonymous_listing_client import BuffAnonymousListingHttpClient
from app.clients.steamdt_client import SteamDTClientConfig, SteamDTHttpClient
from app.services.buff_community_identity_resolver import BuffCommunityIdentityResolver
from app.services.buff_listing_provider import BuffListingProvider
from app.services.market_universe_builder import (
    BoundedMarketUniverseBuilderError,
    MarketUniverseResult,
    MarketUniverseSpec,
    SouvenirInclusion,
    StatTrakMode,
    UniverseAllocationStrategy,
    build_universe_goods_ids,
)
from app.services.price_cache_factory import (
    SteamDTPriceCacheCompositionError,
    create_steamdt_price_cache_runtime,
)
from app.services.recipe_solver import (
    DEFAULT_MAX_CANDIDATE_STATES_EXPLORED,
    DEFAULT_MAX_RECIPE_CANDIDATES_RETURNED,
    RecipeEnumerationConfig,
    RecipeSolverConfig,
)
from app.services.risk_filter import RiskFilterConfig
from app.services.scanner_cached_buff_price_resolver import (
    ScannerCachedBuffPriceResolver,
)
from app.services.scanner_orchestrator import LiveScannerOrchestrator, ScannerRunResult
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.steamdt_buff_price_provider import SteamDTBuffPriceProvider
from app.services.steamdt_cached_price_resolver import SteamDTPriceCacheReader
from app.services.valuation_service import ValuationConfig, ValuationService

DEFAULT_IDENTITY_SNAPSHOT = Path("data/identity/buff_identity_v1.json")
DEFAULT_METADATA_SNAPSHOT = Path("data/metadata/skin_metadata_v1.json")
DEFAULT_MAX_VALUATION_REQUESTS = 5


class LiveValuationConfigurationError(RuntimeError):
    """Live valuation prerequisites are not satisfied."""


class LiveScanSettings(BaseSettings):
    """Narrow CLI settings loaded from the existing `.env` mechanism.

    `extra="ignore"` lets the CLI coexist with unrelated project
    settings that it does not consume. This keeps credentials in `.env`
    while avoiding a global Settings dependency for a one-shot script.
    Redis settings are consumed only when the optional price-cache
    backend is explicitly set to `redis`.
    """

    steamdt_base_url: str = "https://open.steamdt.com"
    steamdt_api_key: str = ""
    steamdt_dry_run: bool = True
    steamdt_price_cache_backend: str = "inmemory"
    steamdt_price_cache_redis_namespace: str = "steamdt-price-cache-v1"
    redis_url: str = ""
    sell_fee_rate: float = 0.025
    min_roi: float = 0.05
    min_expected_profit_cny: float = 20.0
    max_worst_case_loss_pct: float = 0.25
    min_profit_probability: float = 0.35
    max_input_total_cost_cny: float = 1000.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


VALID_RARITIES: tuple[str, ...] = (
    "Consumer Grade",
    "Industrial Grade",
    "Mil-Spec Grade",
    "Restricted",
    "Classified",
)
VALID_STATTRAK_MODES: tuple[str, ...] = ("normal", "stattrak")
VALID_SOUVENIR_POLICIES: tuple[str, ...] = ("include", "exclude")
VALID_ALLOCATION_STRATEGIES: tuple[str, ...] = ("breadth", "cohort-depth")
DEFAULT_TARGET_COHORT_COUNT: int = 3
UNIVERSE_HARD_MAX: int = 10


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="READ ONLY: run one bounded BUFF opportunity scan and exit"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--goods-id",
        action="append",
        default=None,
        help="BUFF goods_id to scan (repeatable; max 10; deduplicated in order)",
    )
    source.add_argument(
        "--auto-universe",
        action="store_true",
        help=(
            "Build the bounded goods-id universe from the pinned identity "
            "and metadata catalogs instead of supplying manual IDs"
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
        "--rarity",
        choices=VALID_RARITIES,
        default="Restricted",
        help="Productive input rarity (excludes Covert)",
    )
    parser.add_argument(
        "--stattrak-mode",
        choices=VALID_STATTRAK_MODES,
        default="normal",
        help="Homogeneous StatTrak mode for the bounded universe (auto-universe only)",
    )
    parser.add_argument(
        "--souvenir",
        choices=VALID_SOUVENIR_POLICIES,
        default="include",
        help="Souvenir input inclusion policy (auto-universe only)",
    )
    parser.add_argument(
        "--collection",
        action="append",
        default=[],
        help="Exact collection allowlist (repeatable; auto-universe only)",
    )
    parser.add_argument(
        "--max-goods-ids",
        type=int,
        default=UNIVERSE_HARD_MAX,
        help="Maximum auto-universe goods IDs to scan (1..10; auto-universe only)",
    )
    parser.add_argument(
        "--allocation",
        choices=VALID_ALLOCATION_STRATEGIES,
        default=None,
        help=(
            "Auto-universe allocation strategy; defaults to breadth "
            "(auto-universe only)"
        ),
    )
    parser.add_argument(
        "--target-cohorts",
        type=int,
        default=None,
        help=(
            "Number of collection-local cohorts for cohort-depth allocation; "
            "defaults to 3"
        ),
    )
    parser.add_argument(
        "--universe-preview",
        action="store_true",
        help="Print the auto-universe plan and exit before any network/client work",
    )
    parser.add_argument(
        "--max-valuation-requests",
        type=int,
        default=DEFAULT_MAX_VALUATION_REQUESTS,
        help="Hard cap for NEW LIVE SteamDT exact-name demand (1..60)",
    )
    parser.add_argument(
        "--max-recipe-candidates-returned",
        type=int,
        default=DEFAULT_MAX_RECIPE_CANDIDATES_RETURNED,
        help="Bound on structural recipe candidates returned by scanner enumeration",
    )
    parser.add_argument(
        "--max-candidate-states-explored",
        type=int,
        default=DEFAULT_MAX_CANDIDATE_STATES_EXPLORED,
        help="Bound on candidate search states explored by scanner enumeration",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the human summary",
    )
    return parser


def validate_live_valuation_config(
    settings: LiveScanSettings,
    *,
    max_valuation_requests: int,
) -> None:
    """Fail closed unless live SteamDT valuation is explicitly configured."""
    failures: list[str] = []
    if settings.steamdt_dry_run:
        failures.append("STEAMDT_DRY_RUN must be false")
    if not settings.steamdt_api_key:
        failures.append("STEAMDT_API_KEY is required")
    if type(max_valuation_requests) is not int or not 1 <= max_valuation_requests <= 60:
        failures.append("max valuation requests must be an integer in [1, 60]")
    if failures:
        raise LiveValuationConfigurationError("; ".join(failures))


def build_steamdt_http_client(
    settings: LiveScanSettings,
) -> httpx.AsyncClient:
    """Build the persistent SteamDT HTTP client with the configured base URL.

    SteamDTHttpClient sends relative endpoint paths when an AsyncClient
    is injected, so the borrowed client must carry `base_url`.
    """
    return httpx.AsyncClient(
        base_url=settings.steamdt_base_url,
        timeout=10.0,
    )


async def run_live_scan_once(
    args: argparse.Namespace,
    *,
    settings: LiveScanSettings,
    price_cache: SteamDTPriceCacheReader,
    enumeration_config: RecipeEnumerationConfig,
) -> ScannerRunResult:
    """Construct live dependencies, run ONE scan, close clients, return result."""
    identity_resolver = BuffCommunityIdentityResolver.from_snapshot_path(
        args.identity_snapshot
    )
    metadata_resolver = PinnedSkinMetadataResolver.from_snapshot_path(
        args.metadata_snapshot
    )
    cached_price_resolver = ScannerCachedBuffPriceResolver(price_cache)

    async with AsyncExitStack() as stack:
        buff_http = httpx.AsyncClient(timeout=10.0)
        stack.push_async_callback(buff_http.aclose)
        steamdt_http = build_steamdt_http_client(settings)
        stack.push_async_callback(steamdt_http.aclose)

        buff_client = BuffAnonymousListingHttpClient(buff_http)
        listing_provider = BuffListingProvider(buff_client)

        steamdt_client = SteamDTHttpClient(
            SteamDTClientConfig(
                base_url=settings.steamdt_base_url,
                api_key=settings.steamdt_api_key or None,
                dry_run=settings.steamdt_dry_run,
                rate_limit_policies=(SteamDTClientConfig().rate_limit_policies),
            ),
            steamdt_http,
        )
        price_provider = SteamDTBuffPriceProvider(steamdt_client)
        valuation_service = ValuationService(
            price_provider,
            ValuationConfig(),
        )

        trading = settings
        orchestrator = LiveScannerOrchestrator(
            listing_provider=listing_provider,
            identity_resolver=identity_resolver,
            metadata_resolver=metadata_resolver,
            valuation_service=valuation_service,
            cached_price_resolver=cached_price_resolver,
            max_valuation_requests_per_run=args.max_valuation_requests,
            enumeration_config=enumeration_config,
            solver_config=RecipeSolverConfig(
                input_rarity=args.rarity,
                input_count=10,
                sell_fee_rate=Decimal(str(trading.sell_fee_rate)),
            ),
            risk_config=RiskFilterConfig(
                min_roi=Decimal(str(trading.min_roi)),
                min_expected_profit_cny=Decimal(
                    str(trading.min_expected_profit_cny)
                ),
                max_worst_case_loss_pct=Decimal(
                    str(trading.max_worst_case_loss_pct)
                ),
                min_profit_probability=trading.min_profit_probability,
                max_input_total_cost_cny=Decimal(
                    str(trading.max_input_total_cost_cny)
                ),
            ),
        )
        return await orchestrator.run_once(args.goods_id)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {
            key: _to_jsonable(item)
            for key, item in asdict(value).items()
        }
    return value


def print_human(result: ScannerRunResult) -> None:
    counters = result.counters
    print("LIVE READ-ONLY SCAN")
    print()
    print(f"goods ids requested:        {counters.goods_ids_requested}")
    print(f"goods ids succeeded:        {counters.goods_ids_succeeded}")
    print(f"goods ids failed:           {counters.goods_ids_failed}")
    print(f"listings received:          {counters.listings_received}")
    print()
    print(f"candidates accepted:        {counters.candidate_accepted}")
    print(f"candidates rejected:        {counters.candidate_rejected}")
    print(f"metadata resolved:          {counters.metadata_resolved}")
    print(f"metadata unresolved:        {counters.metadata_unresolved}")
    print(f"InputItems created:         {counters.input_items_created}")
    print()
    print(f"recipes evaluated:          {counters.recipes_evaluated}")
    print(f"recipes fully valued:       {counters.recipes_fully_valued}")
    print(f"recipes valuation failed:   {counters.recipes_valuation_failed}")
    print(f"recipes rejected:           {counters.recipes_rejected}")
    print(f"opportunities found:        {counters.opportunities_found}")
    print()
    print(
        f"logical valuation requests attempted: {counters.valuation_requests_attempted}"
    )
    print(
        f"logical valuation requests succeeded: {counters.valuation_requests_succeeded}"
    )
    print(f"logical valuation requests failed:    {counters.valuation_requests_failed}")
    print(
        f"logical valuation requests blocked:   {counters.valuation_requests_blocked}"
    )
    print()
    print(f"run reuse hits:              {counters.run_reuse_hits}")
    print(f"run reuse successes:         {counters.run_reuse_successes}")
    print(f"run reuse failures:          {counters.run_reuse_failures}")
    print()
    print(f"cache fresh hits:            {counters.cache_hits_fresh_selected}")
    print(f"cache misses:                {counters.cache_misses}")
    print(f"cache policy blocked:        {counters.cache_policy_blocked}")
    print(f"cache expired:               {counters.cache_expired}")
    print(f"cache selection failures:    {counters.cache_selection_failures}")
    print()
    print(f"live demand:                 {counters.live_demand}")
    print(f"live attempted:              {counters.live_attempted}")
    print(f"live succeeded:              {counters.live_succeeded}")
    print(f"live failed:                 {counters.live_failed}")
    print(f"live atomically blocked:     {counters.live_atomically_blocked}")
    print()
    for index, evaluation in enumerate(result.recipe_evaluations, start=1):
        print(f"Recipe {index}:")
        print(
            "  outputs requested: "
            + ", ".join(evaluation.output_market_hash_names_requested)
        )
        print(f"  prices resolved: {evaluation.valuation_prices_resolved}")
        print(f"  missing: {len(evaluation.missing_market_hash_names)}")
        print(f"  errors: {len(evaluation.price_errors)}")
        print(f"  valuation completed: {evaluation.valuation_completed}")
        if evaluation.metrics is not None:
            metrics = evaluation.metrics
            print(f"  input cost: {metrics.input_total_cost_cny}")
            print(f"  expected value: {metrics.expected_revenue_cny}")
            print(f"  expected profit: {metrics.expected_profit_cny}")
            print(f"  ROI: {metrics.roi}")
            print(f"  profit probability: {metrics.profit_probability}")
            print(f"  worst case: {metrics.worst_case_profit_cny}")
            print(f"  best case: {metrics.best_case_profit_cny}")
        if evaluation.risk_decision is not None:
            decision = evaluation.risk_decision
            print(f"  risk passed: {decision.passed}")
            print("  risk rejection reasons: " + "; ".join(decision.reasons))
        print()
    if not result.opportunities:
        print("0 opportunities found in this bounded live run.")
        return
    print("Top opportunities:")
    for index, opportunity in enumerate(result.opportunities[:5], start=1):
        metrics = opportunity.metrics
        print(
            f"{index}. input cost CNY={metrics.input_total_cost_cny} "
            f"expected profit CNY={metrics.expected_profit_cny} "
            f"ROI={metrics.roi} risk passed={opportunity.risk_decision.passed}"
        )
        print(
            "   listings: "
            + ", ".join(opportunity.recipe.selected_listing_ids)
        )
        print(
            "   outputs: "
            + ", ".join(
                result.output_market_hash_name
                for result in opportunity.valued_tradeup_results
            )
        )


def print_effective_config(
    settings: LiveScanSettings,
    *,
    max_valuation_requests: int,
) -> None:
    """Print non-secret live valuation and risk configuration."""
    print("LIVE VALUATION CONFIG")
    print(f"SteamDT dry_run:             {settings.steamdt_dry_run}")
    print(f"SteamDT API key present:    {bool(settings.steamdt_api_key)}")
    print(f"NEW LIVE exact-name cap:     {max_valuation_requests}")
    print(f"price-cache backend:         {settings.steamdt_price_cache_backend}")
    print(f"sell_fee_rate:              {settings.sell_fee_rate}")
    print(f"min_roi:                    {settings.min_roi}")
    print(f"min_expected_profit_cny:    {settings.min_expected_profit_cny}")
    print(f"max_worst_case_loss_pct:    {settings.max_worst_case_loss_pct}")
    print(f"min_profit_probability:     {settings.min_profit_probability}")
    print(f"max_input_total_cost_cny:   {settings.max_input_total_cost_cny}")
    print()


def _build_market_universe_spec(args: argparse.Namespace) -> MarketUniverseSpec:
    if not args.auto_universe:
        raise BoundedMarketUniverseBuilderError(reason="unsupported_allocation")
    if (
        type(args.max_goods_ids) is not int
        or args.max_goods_ids < 1
        or args.max_goods_ids > UNIVERSE_HARD_MAX
    ):
        raise BoundedMarketUniverseBuilderError(reason="universe_over_hard_max")
    if args.stattrak_mode not in VALID_STATTRAK_MODES:
        raise BoundedMarketUniverseBuilderError(reason="unsupported_rarity")
    if args.souvenir not in VALID_SOUVENIR_POLICIES:
        raise BoundedMarketUniverseBuilderError(reason="unsupported_rarity")

    allocation_value = args.allocation or UniverseAllocationStrategy.BREADTH.value
    if allocation_value not in VALID_ALLOCATION_STRATEGIES:
        raise BoundedMarketUniverseBuilderError(reason="unsupported_allocation")
    allocation_strategy = UniverseAllocationStrategy(allocation_value)
    target_cohort_count = (
        DEFAULT_TARGET_COHORT_COUNT
        if args.target_cohorts is None
        else args.target_cohorts
    )
    if (
        allocation_strategy is UniverseAllocationStrategy.BREADTH
        and args.target_cohorts is not None
    ):
        raise BoundedMarketUniverseBuilderError(
            reason="invalid_target_cohort_count"
        )

    return MarketUniverseSpec(
        rarity=args.rarity,
        stattrak_mode=(
            StatTrakMode.STATTRAK
            if args.stattrak_mode == "stattrak"
            else StatTrakMode.NORMAL
        ),
        souvenir_inclusion=(
            SouvenirInclusion.EXCLUDE
            if args.souvenir == "exclude"
            else SouvenirInclusion.INCLUDE
        ),
        cap=args.max_goods_ids,
        collection_allowlist=tuple(args.collection),
        allocation_strategy=allocation_strategy,
        target_cohort_count=target_cohort_count,
    )


def _build_market_universe(
    args: argparse.Namespace,
    *,
    identity_resolver: BuffCommunityIdentityResolver,
    metadata_resolver: PinnedSkinMetadataResolver,
) -> MarketUniverseResult:
    spec = _build_market_universe_spec(args)
    return build_universe_goods_ids(
        identity_resolver=identity_resolver,
        metadata_resolver=metadata_resolver,
        spec=spec,
    )


def print_universe_preview(
    result: MarketUniverseResult,
    *,
    max_valuation_requests: int,
) -> None:
    print("AUTO UNIVERSE PREVIEW")
    print(f"input rarity:               {result.spec.rarity}")
    print(f"stattrak mode:              {result.spec.stattrak_mode.value}")
    print(f"souvenir policy:            {result.spec.souvenir_inclusion.value}")
    print(f"allocation strategy:        {result.spec.allocation_strategy.value}")
    print(f"target cohort count:        {result.spec.target_cohort_count}")
    print(
        "collection allowlist:       "
        + (", ".join(result.spec.collection_allowlist) or "(all)")
    )
    print(f"cap:                        {result.spec.cap}")
    print(f"selected goods_ids:         {len(result.goods_ids)}")
    print(f"NEW LIVE exact-name cap:     {max_valuation_requests}")
    print(f"max BUFF requests (upper):  {len(result.goods_ids)}")
    print()
    diagnostics = result.diagnostics
    print("CATALOG DIAGNOSTICS")
    print(f"  metadata rows:            {diagnostics.catalog_metadata_rows}")
    print(f"  identity rows:            {diagnostics.catalog_identity_rows}")
    print(f"  eligible before bound:    {diagnostics.eligible_before_bound}")
    print(f"  excluded no identity:     {diagnostics.excluded_no_identity}")
    print(f"  excluded no metadata:     {diagnostics.excluded_no_metadata}")
    print(f"  excluded invalid rarity:  {diagnostics.excluded_invalid_rarity}")
    print(f"  excluded no collection:   {diagnostics.excluded_no_collection}")
    print(f"  excluded no valid output: {diagnostics.excluded_no_valid_output}")
    print(f"  excluded intrinsic policy:{diagnostics.excluded_intrinsic_policy}")
    print(f"  excluded by allowlist:    {diagnostics.excluded_by_allowlist}")
    print(f"  eligible cohorts:         {diagnostics.eligible_cohort_count}")
    print(f"  selected cohorts:         {diagnostics.selected_cohort_count}")
    print()
    print("SELECTED COHORT ALLOCATION")
    for index, cohort in enumerate(diagnostics.selected_cohorts, start=1):
        key = cohort.key
        print(
            f"  {index}. collection={key.collection_name} rarity={key.rarity} "
            f"stattrak={key.stattrak}"
        )
        print(
            "     catalog capacity="
            f"{cohort.catalog_capacity} normal={cohort.normal_identity_count} "
            f"souvenir={cohort.souvenir_identity_count} "
            f"canonical outputs={cohort.canonical_output_count} "
            f"allocated={cohort.allocated_slots}"
        )
        for entry in cohort.selected_entries:
            print(
                f"     goods_id={entry.goods_id} souvenir={entry.souvenir} "
                f"market_hash_name={entry.market_hash_name}"
            )
    print()
    print("SELECTED TARGETS")
    for index, entry in enumerate(result.selected_entries, start=1):
        print(
            f"  {index}. goods_id={entry.goods_id} "
            f"collection={entry.collection_name} "
            f"market_hash_name={entry.market_hash_name}"
        )


def _universe_preview_to_jsonable(
    result: MarketUniverseResult,
    *,
    max_valuation_requests: int,
) -> dict[str, object]:
    diagnostics = result.diagnostics
    return {
        "kind": "live_scan_universe_preview",
        "spec": {
            "rarity": result.spec.rarity,
            "stattrak_mode": result.spec.stattrak_mode.value,
            "souvenir_policy": result.spec.souvenir_inclusion.value,
            "allocation_strategy": result.spec.allocation_strategy.value,
            "target_cohort_count": result.spec.target_cohort_count,
            "cap": result.spec.cap,
            "collection_allowlist": list(result.spec.collection_allowlist),
        },
        "selected_count": len(result.goods_ids),
        "selected_goods_ids": list(result.goods_ids),
        "selected_market_hash_names": list(result.selected_market_hash_names),
        "selected_entries": [
            {
                "goods_id": entry.goods_id,
                "market_hash_name": entry.market_hash_name,
                "collection": entry.collection_name,
                "rarity": entry.rarity,
                "stattrak": entry.stattrak,
                "souvenir": entry.souvenir,
            }
            for entry in result.selected_entries
        ],
        "catalog_diagnostics": {
            "metadata_rows": diagnostics.catalog_metadata_rows,
            "identity_rows": diagnostics.catalog_identity_rows,
            "eligible_before_bound": diagnostics.eligible_before_bound,
            "excluded_no_identity": diagnostics.excluded_no_identity,
            "excluded_no_metadata": diagnostics.excluded_no_metadata,
            "excluded_invalid_rarity": diagnostics.excluded_invalid_rarity,
            "excluded_no_collection": diagnostics.excluded_no_collection,
            "excluded_no_valid_output": diagnostics.excluded_no_valid_output,
            "excluded_intrinsic_policy": diagnostics.excluded_intrinsic_policy,
            "excluded_by_allowlist": diagnostics.excluded_by_allowlist,
            "allocation_strategy": diagnostics.allocation_strategy.value,
            "target_cohort_count": diagnostics.target_cohort_count,
            "eligible_cohort_count": diagnostics.eligible_cohort_count,
            "selected_cohort_count": diagnostics.selected_cohort_count,
            "selected_cohorts": [
                {
                    "collection": cohort.key.collection_name,
                    "rarity": cohort.key.rarity,
                    "stattrak": cohort.key.stattrak,
                    "catalog_capacity": cohort.catalog_capacity,
                    "normal_identity_count": cohort.normal_identity_count,
                    "souvenir_identity_count": cohort.souvenir_identity_count,
                    "canonical_output_count": cohort.canonical_output_count,
                    "allocated_slots": cohort.allocated_slots,
                    "selected_identities": [
                        {
                            "goods_id": entry.goods_id,
                            "market_hash_name": entry.market_hash_name,
                            "souvenir": entry.souvenir,
                        }
                        for entry in cohort.selected_entries
                    ],
                }
                for cohort in diagnostics.selected_cohorts
            ],
        },
        "preflight": {
            "max_buff_requests": len(result.goods_ids),
            "max_steamdt_valuation_requests": max_valuation_requests,
        },
        "http_clients_constructed": False,
        "http_requests_sent": 0,
    }


def run_universe_preview(args: argparse.Namespace) -> int:
    """Build the auto-universe, print it, and exit BEFORE any client work."""
    identity_resolver = BuffCommunityIdentityResolver.from_snapshot_path(
        args.identity_snapshot
    )
    metadata_resolver = PinnedSkinMetadataResolver.from_snapshot_path(
        args.metadata_snapshot
    )
    result = _build_market_universe(
        args,
        identity_resolver=identity_resolver,
        metadata_resolver=metadata_resolver,
    )
    if args.json:
        print(
            json.dumps(
                _universe_preview_to_jsonable(
                    result, max_valuation_requests=args.max_valuation_requests
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    else:
        print_universe_preview(
            result, max_valuation_requests=args.max_valuation_requests
        )
    return 0


async def _main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        enumeration_config = RecipeEnumerationConfig(
            max_recipe_candidates_returned=(
                args.max_recipe_candidates_returned
            ),
            max_candidate_states_explored=args.max_candidate_states_explored,
        )
    except ValueError as exc:
        print("RECIPE_ENUMERATION_BLOCKED_BY_CONFIGURATION")
        print(str(exc))
        return 2
    if not args.auto_universe and (
        args.allocation is not None or args.target_cohorts is not None
    ):
        print("AUTO_UNIVERSE_OPTION_REQUIRES_AUTO_UNIVERSE")
        return 2
    if args.universe_preview:
        if not args.auto_universe:
            print("UNIVERSE_PREVIEW_REQUIRES_AUTO_UNIVERSE")
            return 2
        try:
            return run_universe_preview(args)
        except BoundedMarketUniverseBuilderError as exc:
            print("MARKET_UNIVERSE_BUILDER_BLOCKED")
            print(f"reason: {exc.reason}")
            return 2
        except (
            BuffCommunityIdentityResolver.__class__,
            PinnedSkinMetadataResolver.__class__,
        ):
            return 2
    if args.auto_universe:
        if args.max_valuation_requests > 20:
            args.max_valuation_requests = 20
        try:
            identity_resolver = BuffCommunityIdentityResolver.from_snapshot_path(
                args.identity_snapshot
            )
            metadata_resolver = PinnedSkinMetadataResolver.from_snapshot_path(
                args.metadata_snapshot
            )
            universe = _build_market_universe(
                args,
                identity_resolver=identity_resolver,
                metadata_resolver=metadata_resolver,
            )
        except BoundedMarketUniverseBuilderError as exc:
            print("MARKET_UNIVERSE_BUILDER_BLOCKED")
            print(f"reason: {exc.reason}")
            return 2
        args.goods_id = list(universe.goods_ids)
        if not args.json:
            print_universe_preview(
                universe, max_valuation_requests=args.max_valuation_requests
            )
    settings = LiveScanSettings()
    try:
        validate_live_valuation_config(
            settings,
            max_valuation_requests=args.max_valuation_requests,
        )
    except LiveValuationConfigurationError as exc:
        print("LIVE_VALUATION_BLOCKED_BY_CONFIGURATION")
        print(str(exc))
        return 2
    try:
        cache_runtime = await create_steamdt_price_cache_runtime(settings)
    except SteamDTPriceCacheCompositionError as exc:
        print("LIVE_PRICE_CACHE_BLOCKED_BY_CONFIGURATION")
        print(str(exc))
        return 2

    async with cache_runtime:
        if not args.json:
            print_effective_config(
                settings,
                max_valuation_requests=args.max_valuation_requests,
            )
        result = await run_live_scan_once(
            args,
            settings=settings,
            price_cache=cache_runtime.cache,
            enumeration_config=enumeration_config,
        )
    if args.json:
        print(json.dumps(_to_jsonable(result), ensure_ascii=False, sort_keys=True))
    else:
        print_human(result)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
