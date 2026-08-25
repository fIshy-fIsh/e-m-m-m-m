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
    build_universe_goods_ids,
)
from app.services.recipe_solver import RecipeSolverConfig
from app.services.risk_filter import RiskFilterConfig
from app.services.scanner_orchestrator import LiveScannerOrchestrator, ScannerRunResult
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.steamdt_buff_price_provider import SteamDTBuffPriceProvider
from app.services.valuation_service import ValuationConfig, ValuationService

DEFAULT_IDENTITY_SNAPSHOT = Path("data/identity/buff_identity_v1.json")
DEFAULT_METADATA_SNAPSHOT = Path("data/metadata/skin_metadata_v1.json")
DEFAULT_MAX_VALUATION_REQUESTS = 5


class LiveValuationConfigurationError(RuntimeError):
    """Live valuation prerequisites are not satisfied."""


class LiveScanSettings(BaseSettings):
    """Narrow CLI settings loaded from the existing `.env` mechanism.

    `extra="ignore"` lets the CLI coexist with unrelated project
    settings that it does not consume (database, Redis, legacy smoke
    flags). This keeps credentials in `.env` while avoiding a global
    Settings dependency for a one-shot script.
    """

    steamdt_base_url: str = "https://open.steamdt.com"
    steamdt_api_key: str = ""
    steamdt_dry_run: bool = True
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
        "--universe-preview",
        action="store_true",
        help="Print the auto-universe plan and exit before any network/client work",
    )
    parser.add_argument(
        "--max-valuation-requests",
        type=int,
        default=DEFAULT_MAX_VALUATION_REQUESTS,
        help="Hard cap for unique SteamDT output-price requests (1..60)",
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


async def run_live_scan_once(args: argparse.Namespace) -> ScannerRunResult:
    """Construct live dependencies, run ONE scan, close clients, return result."""
    settings = LiveScanSettings()
    validate_live_valuation_config(
        settings,
        max_valuation_requests=args.max_valuation_requests,
    )

    identity_resolver = BuffCommunityIdentityResolver.from_snapshot_path(
        args.identity_snapshot
    )
    metadata_resolver = PinnedSkinMetadataResolver.from_snapshot_path(
        args.metadata_snapshot
    )

    buff_http = httpx.AsyncClient(timeout=10.0)
    steamdt_http = build_steamdt_http_client(settings)
    try:
        buff_client = BuffAnonymousListingHttpClient(buff_http)
        listing_provider = BuffListingProvider(buff_client)

        steamdt_client = SteamDTHttpClient(
            SteamDTClientConfig(
                base_url=settings.steamdt_base_url,
                api_key=settings.steamdt_api_key or None,
                dry_run=settings.steamdt_dry_run,
                rate_limit_policies=(
                    SteamDTClientConfig().rate_limit_policies
                ),
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
            max_valuation_requests_per_run=args.max_valuation_requests,
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
    finally:
        await buff_http.aclose()
        await steamdt_http.aclose()


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
    print(f"valuation requests attempted: {counters.valuation_requests_attempted}")
    print(f"valuation requests succeeded: {counters.valuation_requests_succeeded}")
    print(f"valuation requests failed:    {counters.valuation_requests_failed}")
    print(f"valuation requests blocked:   {counters.valuation_requests_blocked}")
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
    print(f"max valuation requests:     {max_valuation_requests}")
    print(f"sell_fee_rate:              {settings.sell_fee_rate}")
    print(f"min_roi:                    {settings.min_roi}")
    print(f"min_expected_profit_cny:    {settings.min_expected_profit_cny}")
    print(f"max_worst_case_loss_pct:    {settings.max_worst_case_loss_pct}")
    print(f"min_profit_probability:     {settings.min_profit_probability}")
    print(f"max_input_total_cost_cny:   {settings.max_input_total_cost_cny}")
    print()


def _build_market_universe_spec(args: argparse.Namespace) -> MarketUniverseSpec:
    if not args.auto_universe:
        raise BoundedMarketUniverseBuilderError(reason="unsupported_rarity")
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
    print(
        "collection allowlist:       "
        + (", ".join(result.spec.collection_allowlist) or "(all)")
    )
    print(f"cap:                        {result.spec.cap}")
    print(f"selected goods_ids:         {len(result.goods_ids)}")
    print(f"logical valuation cap:      {max_valuation_requests}")
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
    print()
    print("SELECTED TARGETS")
    for index, (goods_id, market_hash_name) in enumerate(
        zip(result.goods_ids, result.selected_market_hash_names, strict=False),
        start=1,
    ):
        print(f"  {index}. goods_id={goods_id} market_hash_name={market_hash_name}")


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
            "cap": result.spec.cap,
            "collection_allowlist": list(result.spec.collection_allowlist),
        },
        "selected_count": len(result.goods_ids),
        "selected_goods_ids": list(result.goods_ids),
        "selected_market_hash_names": list(result.selected_market_hash_names),
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
    if not args.json:
        print_effective_config(
            settings,
            max_valuation_requests=args.max_valuation_requests,
        )
    result = await run_live_scan_once(args)
    if args.json:
        print(json.dumps(_to_jsonable(result), ensure_ascii=False, sort_keys=True))
    else:
        print_human(result)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
