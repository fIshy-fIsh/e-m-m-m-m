"""Phase 17C — Recipe-first runtime offline end-to-end integration.

Exercises the actual Phase17B operator-facing composition root and the
real :class:`RecipeFirstRuntimeCoordinator` end to end. All SteamDT, BUFF,
network-cache, and risk seams are fake and zero-network. The CLI is
invoked through its public ``main`` path.
"""

from __future__ import annotations

import asyncio
import dataclasses
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.clients.steamdt_client import SteamDTBatchPriceResult
from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.buff_listing_provider import BuffListing
from app.services.market_universe_builder import StatTrakMode
from app.services.price_cache import (
    CachedPriceSnapshot,
    InMemoryPriceCache,
    NormalizedPriceCandidate,
    PriceCacheKey,
    PriceCacheLookup,
    PriceCachePolicy,
    PriceCacheReadPolicy,
    PriceCacheState,
)
from app.services.price_provider import PriceLookupResult, PriceQuote
from app.services.recipe_family import build_recipe_family
from app.services.recipe_first_runtime_contract import (
    RecipeFirstDiscoveryBudget,
    RecipeFirstOperatorRunReport,
    RecipeFirstOutputFormat,
    RecipeFirstRuntimeConfig,
    RecipeFirstRuntimeTerminalCode,
    RecipeFirstRuntimeTerminalGroup,
)
from app.services.recipe_first_runtime_coordinator import (
    RecipeFirstRuntimeCoordinator,
    RecipeFirstRuntimeCoordinatorError,
)
from app.services.recipe_solver import RecipeEnumerationConfig
from app.services.redis_price_cache import PriceCacheBackendError
from app.services.risk_filter import RiskFilterConfig
from app.services.scanner_cached_buff_price_resolver import (
    ScannerCachedBuffPriceResolver,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.static_float_feasibility import (
    build_input_identity_float_evidence,
)
from app.services.steamdt_batch_prescreen import (
    SteamDTBatchPreScreenDiagnostics,
    SteamDTBatchPreScreenQuote,
    SteamDTBatchPreScreenResult,
)
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.targeted_buff_scan_plan import (
    TargetedBuffScanDecision,
    TargetedBuffScanItem,
    TargetedBuffScanPlan,
)
from app.services.tradeup_engine import TradeupResult
from app.services.valuation_service import ValuationConfig, ValuationService
from scripts import run_recipe_first_scan_once as cli

ROOT = Path(__file__).resolve().parent.parent
IDENTITY_PATH = ROOT / "data" / "identity" / "buff_identity_v1.json"
METADATA_PATH = ROOT / "data" / "metadata" / "skin_metadata_v1.json"
PHOENIX_HASH = (
    "45bfd0f0d3e7405588acdcf742d980577eed4963382c2fde31632fc43db52516"
)
PHOENIX_KEY = "45bfd0f0d3e7405588acdcf7"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _BatchTransport:
    raise_error: Exception | None = None
    platform: str = "BUFF"
    sell_price: str = "1000"

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def get_price_batch_with_selection(
        self,
        market_hash_names: list[str],
        *,
        selection_config: Any = None,
        avg_prices_by_name: dict[str, Decimal] | None = None,
    ) -> SteamDTBatchPriceResult:
        self.calls.append(tuple(market_hash_names))
        if self.raise_error is not None:
            raise self.raise_error
        rows = []
        for name in market_hash_names:
            rows.append(
                {
                    "marketHashName": name,
                    "dataList": [
                        {
                            "platform": self.platform,
                            "platformItemId": "1",
                            "sellPrice": self.sell_price,
                            "sellCount": 100,
                            "biddingPrice": "9999",
                            "biddingCount": 1,
                            "updateTime": "opaque-fixture",
                        }
                    ],
                }
            )
        return SteamDTBatchPriceResult(
            quotes={},
            missing=[],
            raw={"success": True, "data": rows},
        )


class _ListingProvider:
    def __init__(self, listings: dict[str, list[BuffListing]]) -> None:
        self._listings = listings
        self.calls: list[str] = []

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        self.calls.append(goods_id)
        return list(self._listings.get(goods_id, ()))


class _CatalogListingProvider:
    def __init__(self, identity, metadata) -> None:
        self.identity = identity
        self.metadata = metadata
        self.calls: list[str] = []

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        self.calls.append(goods_id)
        resolved = await self.identity.resolve_goods_id(goods_id)
        assert resolved is not None
        row = self.metadata.resolve(resolved.market_hash_name)
        assert row is not None
        midpoint = (
            Decimal(str(row.min_float)) + Decimal(str(row.max_float))
        ) / 2
        return [
            BuffListing(
                listing_id=f"listing-{goods_id}",
                goods_id=goods_id,
                market_hash_name=None,
                price_cny=Decimal("1"),
                paintwear=midpoint,
                asset_id=f"asset-{goods_id}",
                paintseed=1,
            )
        ]


class _FailingListingProvider:
    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        raise RuntimeError("network detail must never leak")


class _ContractMismatchListingProvider:
    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        return [
            BuffListing(
                listing_id="contract-mismatch",
                goods_id="wrong-goods-id",
                market_hash_name=None,
                price_cny=Decimal("1"),
                paintwear=Decimal("0.2"),
                asset_id="contract-mismatch-asset",
                paintseed=1,
            )
        ]


class _FinalPriceProvider:
    def __init__(
        self,
        *,
        prices_by_name: dict[str, Decimal] | None = None,
        prices: Decimal = Decimal("1000"),
        fail: bool = False,
        identity_mismatch: bool = False,
    ) -> None:
        self._prices = prices_by_name
        self._default = prices
        self.fail = fail
        self.identity_mismatch = identity_mismatch
        self.calls: list[tuple[str, ...]] = []

    async def get_price(self, market_hash_name: str) -> PriceQuote:
        result = await self.get_prices([market_hash_name])
        return result.quotes[market_hash_name]

    async def get_prices(self, names: list[str]) -> PriceLookupResult:
        self.calls.append(tuple(names))
        if self.fail:
            return PriceLookupResult(
                quotes={}, missing=list(names), errors=["safe"]
            )
        quotes: dict[str, PriceQuote] = {}
        for name in names:
            price = (
                self._prices.get(name)
                if self._prices is not None
                else None
            ) or self._default
            quote_name = (
                "WRONG::" + name if self.identity_mismatch else name
            )
            quotes[name] = PriceQuote(
                market_hash_name=quote_name,
                price_cny=price,
                source="steamdt:buff",
                raw=None,
            )
        return PriceLookupResult(
            quotes=quotes, missing=[], errors=[]
        )


# ---------------------------------------------------------------------------
# Authoritative phase17C report fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def phase17c_report() -> RecipeFirstOperatorRunReport:
    """One deterministic Phase17C authoritative report.

    The runtime is exercised through ``RecipeFirstRuntimeCoordinator`` with
    fake market seams; the report is captured and reused by most tests so
    assertions stay exact and offline-only.
    """

    return asyncio.run(_build_phase17c_report_async())


async def _build_phase17c_report_async() -> RecipeFirstOperatorRunReport:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    listings = _phoenix_listings(metadata)
    listing_provider = _ListingProvider(listings)
    final_provider = _FinalPriceProvider(prices=Decimal("1000"))
    cache = InMemoryPriceCache()
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=transport,
        listing_provider=listing_provider,
        final_provider=final_provider,
        cached_resolver=ScannerCachedBuffPriceResolver(cache),
    )
    return await coordinator.run_once()


def _pinned():
    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        IDENTITY_PATH
    )
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(METADATA_PATH)
    finish_index = StructuralOutputFinishIndex.from_skins(metadata.skins)
    return identity, metadata, finish_index


def _phoenix_family():
    return build_recipe_family(
        input_rarity="Classified",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Phoenix Collection", 10),),
    )


def _deterministic_prescreen(
    *, metadata: PinnedSkinMetadataResolver
) -> SteamDTBatchPreScreenResult:
    from app.services.static_float_feasibility import compute_static_float_feasibility

    family = build_recipe_family(
        input_rarity="Classified",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Phoenix Collection", 10),),
    )
    finish_index = StructuralOutputFinishIndex.from_skins(metadata.skins)
    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        IDENTITY_PATH
    )
    feasibility = compute_static_float_feasibility(
        family,
        skins=metadata.skins,
        identity_resolver=identity,
        finish_index=finish_index,
    )
    reachable = feasibility.reachable_outputs
    input_evidence = build_input_identity_float_evidence(
        skins=metadata.skins,
        identity_resolver=identity,
        input_rarity=family.input_rarity,
        stattrak_mode=family.stattrak_mode,
        represented_collections=tuple(
            name for name, _count in family.collection_counts
        ),
    )
    rows: list[SteamDTBatchPreScreenQuote] = []
    selected_names: list[str] = []
    for evidence in input_evidence:
        quote = SteamDTBatchPreScreenQuote(
            market_hash_name=evidence.market_hash_name,
            sell_price_cny=Decimal("186.0"),
            sell_count=7946,
            update_time="opaque-fixture",
        )
        rows.append(quote)
        selected_names.append(evidence.market_hash_name)
    for output in reachable:
        if output.exact_market_hash_name not in selected_names:
            quote = SteamDTBatchPreScreenQuote(
                market_hash_name=output.exact_market_hash_name,
                sell_price_cny=Decimal("524.49"),
                sell_count=22,
                update_time="opaque-fixture",
            )
            rows.append(quote)
            selected_names.append(output.exact_market_hash_name)
    return SteamDTBatchPreScreenResult(
        requested_market_hash_names=tuple(selected_names),
        quotes=tuple(rows),
        missing_market_hash_names=(),
        terminal_selection_failures=(),
        diagnostics=SteamDTBatchPreScreenDiagnostics(
            logical_requested_names=len(selected_names),
            unique_names=len(selected_names),
            duplicates_suppressed=0,
            chunk_count=1,
            transport_attempted_names=len(selected_names),
            selected_names=len(rows),
            missing_names=0,
            terminal_selection_failures=0,
            transport_errors=(),
        ),
    )


def _phoenix_listings(
    metadata: PinnedSkinMetadataResolver,
) -> dict[str, list[BuffListing]]:
    listings: dict[str, list[BuffListing]] = {}
    for goods_id in ("33960",):
        for index in range(10):
            listings.setdefault(goods_id, []).append(
                BuffListing(
                    listing_id=f"listing-{goods_id}-{index}",
                    goods_id=goods_id,
                    market_hash_name=None,
                    price_cny=Decimal("186"),
                    paintwear=Decimal("0.10") + Decimal(index) * Decimal("0.06"),
                    asset_id=f"asset-{goods_id}-{index}",
                    paintseed=index,
                )
            )
    return listings


def _build_coordinator(
    *,
    identity,
    metadata,
    finish_index,
    transport,
    listing_provider,
    final_provider,
    cached_resolver,
):
    family = _phoenix_family()
    config = RecipeFirstRuntimeConfig(
        enabled=True,
        preview=False,
        input_rarities=("Classified",),
        stattrak_modes=(StatTrakMode.NORMAL,),
        collection_allowlist=("The Phoenix Collection",),
        max_targeted_buff_goods_ids=10,
        max_final_valuation_requests=5,
        sell_fee_rate=Decimal("0.025"),
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=1,
            max_candidate_states_explored=256,
        ),
        cache_backend="inmemory",
        output_format=RecipeFirstOutputFormat.JSON,
    )
    budget = RecipeFirstDiscoveryBudget(
        max_family_states_considered=1,
        max_prescreen_names=100,
        max_prescreen_batch_dispatches=10,
    )
    valuation = ValuationService(
        final_provider, ValuationConfig(require_all_prices=True)
    )
    risk = RiskFilterConfig(
        min_roi=Decimal("-100"),
        min_expected_profit_cny=Decimal("-10000"),
        max_worst_case_loss_pct=Decimal("100"),
        min_profit_probability=0.0,
        max_input_total_cost_cny=Decimal("1000000"),
    )
    return RecipeFirstRuntimeCoordinator(
        config=config,
        discovery_budget=budget,
        identity_resolver=identity,
        metadata_resolver=metadata,
        finish_index=finish_index,
        prescreen_transport=transport,
        listing_provider=listing_provider,
        valuation_service=valuation,
        risk_config=risk,
        cached_price_resolver=cached_resolver,
        family_iterator_factory=lambda _generator: iter((family,)),
    )


# ---------------------------------------------------------------------------
# Scenario 1: preview success, zero provider/client construction
# ---------------------------------------------------------------------------


def test_cli_preview_does_not_construct_external_clients(monkeypatch) -> None:
    def forbidden_sync(*args, **kwargs):
        raise AssertionError("external client construction forbidden")

    async def forbidden_async(*args, **kwargs):
        raise AssertionError("network cache construction forbidden")

    monkeypatch.setattr(cli.httpx, "AsyncClient", forbidden_sync)
    monkeypatch.setattr(cli, "SteamDTHttpClient", forbidden_sync)
    monkeypatch.setattr(cli, "BuffAnonymousListingHttpClient", forbidden_sync)
    monkeypatch.setattr(
        cli, "create_steamdt_price_cache_runtime", forbidden_async
    )
    rc = cli.main(
        [
            "--enable-recipe-first",
            "--preview",
            "--input-rarity",
            "Classified",
            "--stattrak-mode",
            "normal",
        ]
    )
    assert rc == 0


def test_cli_no_enable_is_refused_before_provider_construction(
    monkeypatch, tmp_path
) -> None:
    def forbidden_sync(*args, **kwargs):
        raise AssertionError("client construction forbidden")

    async def forbidden_async(*args, **kwargs):
        raise AssertionError("network cache construction forbidden")

    monkeypatch.setattr(cli.httpx, "AsyncClient", forbidden_sync)
    monkeypatch.setattr(cli, "SteamDTHttpClient", forbidden_sync)
    monkeypatch.setattr(cli, "BuffAnonymousListingHttpClient", forbidden_sync)
    monkeypatch.setattr(
        cli, "create_steamdt_price_cache_runtime", forbidden_async
    )
    rc = cli.main(["--artifact-dir", str(tmp_path)])
    assert rc == 3
    assert "CONFIGURATION_BLOCKED" in (
        tmp_path / cli.RESULT_FILENAME
    ).read_text(encoding="utf-8")


def test_cli_full_success_path_maps_report_to_json_exit_zero(
    monkeypatch,
    capsys,
) -> None:
    report = asyncio.run(_build_phase17c_report_async())
    calls = 0

    async def injected(**_kwargs):
        nonlocal calls
        calls += 1
        return report

    monkeypatch.setattr(cli, "_run_live_composition", injected)
    monkeypatch.setenv("STEAMDT_API_KEY", "offline-fixture")
    monkeypatch.setenv("STEAMDT_DRY_RUN", "false")
    rc = cli.main(
        [
            "--enable-recipe-first",
            "--output-format",
            "json",
            "--input-rarity",
            "Classified",
            "--stattrak-mode",
            "normal",
        ]
    )
    assert rc == 0
    assert calls == 1
    output = capsys.readouterr().out
    assert "SUCCESS_OPPORTUNITIES_FOUND" in output
    assert '"terminal_group":"success"' in output


def test_cli_full_failure_path_maps_report_to_exit_two(
    monkeypatch,
    capsys,
) -> None:
    base = asyncio.run(_build_phase17c_report_async())
    report = dataclasses.replace(
        base,
        terminal_group=RecipeFirstRuntimeTerminalGroup.INCOMPLETE_OR_PROVIDER,
        terminal_code=RecipeFirstRuntimeTerminalCode.FINAL_VALUATION_INCOMPLETE,
        incompleteness_flags=("FINAL_VALUATION_INCOMPLETE",),
    )
    calls = 0

    async def injected(**_kwargs):
        nonlocal calls
        calls += 1
        return report

    monkeypatch.setattr(cli, "_run_live_composition", injected)
    monkeypatch.setenv("STEAMDT_API_KEY", "offline-fixture")
    monkeypatch.setenv("STEAMDT_DRY_RUN", "false")
    rc = cli.main(
        [
            "--enable-recipe-first",
            "--output-format",
            "human",
        ]
    )
    assert rc == 2
    assert calls == 1
    output = capsys.readouterr().out
    assert "FINAL_VALUATION_INCOMPLETE" in output
    assert "incompleteness_flags=FINAL_VALUATION_INCOMPLETE" in output


# ---------------------------------------------------------------------------
# Scenario 2: full opportunity passes risk
# ---------------------------------------------------------------------------


def test_full_opportunity_passes_risk(phase17c_report) -> None:
    assert (
        phase17c_report.terminal_code
        is RecipeFirstRuntimeTerminalCode.SUCCESS_OPPORTUNITIES_FOUND
    )
    assert (
        phase17c_report.terminal_group
        is RecipeFirstRuntimeTerminalGroup.SUCCESS
    )
    assert phase17c_report.evidence.risk_passed is True
    assert phase17c_report.evidence.input_total_cost_cny == Decimal("1860")
    assert phase17c_report.evidence.expected_gross_revenue_cny == Decimal("1000")
    assert phase17c_report.evidence.expected_profit_cny == Decimal("-885.0000")
    assert (
        phase17c_report.evidence.targeted_goods_ids
        == tuple(phase17c_report.evidence.targeted_goods_ids)
    )
    assert all(
        source == "steamdt:buff"
        for source in phase17c_report.evidence.final_quote_source
    )


# ---------------------------------------------------------------------------
# Scenario 3: complete evaluation rejected by risk
# ---------------------------------------------------------------------------


def test_complete_evaluation_rejected_by_risk(monkeypatch) -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    listings = _phoenix_listings(metadata)
    listing_provider = _ListingProvider(listings)
    final_provider = _FinalPriceProvider(
        prices_by_name={
            q.market_hash_name: Decimal("1000")
            for q in _deterministic_prescreen(metadata=metadata).quotes
        }
    )
    strict_risk = RiskFilterConfig(
        min_roi=Decimal("1000"),
        min_expected_profit_cny=Decimal("1000000"),
        max_worst_case_loss_pct=Decimal("100"),
        min_profit_probability=0.0,
        max_input_total_cost_cny=Decimal("10000000"),
    )
    family = _phoenix_family()
    config = RecipeFirstRuntimeConfig(
        enabled=True,
        preview=False,
        input_rarities=("Classified",),
        stattrak_modes=(StatTrakMode.NORMAL,),
        collection_allowlist=("The Phoenix Collection",),
        max_targeted_buff_goods_ids=10,
        max_final_valuation_requests=5,
        sell_fee_rate=Decimal("0.025"),
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=1,
            max_candidate_states_explored=256,
        ),
        cache_backend="inmemory",
        output_format=RecipeFirstOutputFormat.JSON,
    )
    budget = RecipeFirstDiscoveryBudget(
        max_family_states_considered=1,
        max_prescreen_names=100,
        max_prescreen_batch_dispatches=10,
    )
    valuation = ValuationService(
        final_provider, ValuationConfig(require_all_prices=True)
    )
    coordinator = RecipeFirstRuntimeCoordinator(
        config=config,
        discovery_budget=budget,
        identity_resolver=identity,
        metadata_resolver=metadata,
        finish_index=finish_index,
        prescreen_transport=transport,
        listing_provider=listing_provider,
        valuation_service=valuation,
        risk_config=strict_risk,
        family_iterator_factory=lambda _generator: iter((family,)),
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.RISK_FILTER_REJECTED
    )
    assert (
        report.terminal_group
        is RecipeFirstRuntimeTerminalGroup.EXPECTED_NO_OPPORTUNITY
    )
    assert report.evidence.risk_passed is False
    assert report.evidence.risk_reason_codes


# ---------------------------------------------------------------------------
# Scenario 4: no concrete selection
# ---------------------------------------------------------------------------


def test_no_concrete_selection_when_collection_disjoint() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    listing_provider = _ListingProvider(_phoenix_listings(metadata))
    final_provider = _FinalPriceProvider()
    config = RecipeFirstRuntimeConfig(
        enabled=True,
        preview=False,
        input_rarities=("Classified",),
        stattrak_modes=(StatTrakMode.NORMAL,),
        collection_allowlist=("The Chroma Collection",),
        max_targeted_buff_goods_ids=10,
        max_final_valuation_requests=5,
        sell_fee_rate=Decimal("0.025"),
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=1,
            max_candidate_states_explored=256,
        ),
        cache_backend="inmemory",
        output_format=RecipeFirstOutputFormat.JSON,
    )
    budget = RecipeFirstDiscoveryBudget(
        max_family_states_considered=1,
        max_prescreen_names=100,
        max_prescreen_batch_dispatches=10,
    )
    valuation = ValuationService(
        final_provider, ValuationConfig(require_all_prices=True)
    )
    risk = RiskFilterConfig(
        min_roi=Decimal("-100"),
        min_expected_profit_cny=Decimal("-10000"),
        max_worst_case_loss_pct=Decimal("100"),
        min_profit_probability=0.0,
        max_input_total_cost_cny=Decimal("1000000"),
    )
    coordinator = RecipeFirstRuntimeCoordinator(
        config=config,
        discovery_budget=budget,
        identity_resolver=identity,
        metadata_resolver=metadata,
        finish_index=finish_index,
        prescreen_transport=transport,
        listing_provider=listing_provider,
        valuation_service=valuation,
        risk_config=risk,
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.NO_CONCRETE_SELECTION
    )
    assert report.counters.families_visited >= 1


# ---------------------------------------------------------------------------
# Scenario 5: prescreen incomplete (BUFF selector failed)
# ---------------------------------------------------------------------------


def test_prescreen_incomplete_when_strict_selector_fails() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport(sell_price="0")
    listing_provider = _ListingProvider(_phoenix_listings(metadata))
    final_provider = _FinalPriceProvider()
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=transport,
        listing_provider=listing_provider,
        final_provider=final_provider,
        cached_resolver=None,
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.PRESCREEN_INCOMPLETE
    )
    assert report.counters.prescreen_terminal_selection_failures > 0
    assert report.counters.buff_dispatch_started == 0
    assert listing_provider.calls == []


# ---------------------------------------------------------------------------
# Scenario 6: BUFF acquisition insufficient
# ---------------------------------------------------------------------------


def test_buff_acquisition_insufficient_when_listing_returns_fewer_than_ten() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    short_listings = {"33960": []}
    listing_provider = _ListingProvider(short_listings)
    final_provider = _FinalPriceProvider()
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=transport,
        listing_provider=listing_provider,
        final_provider=final_provider,
        cached_resolver=None,
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.BUFF_ACQUISITION_INSUFFICIENT
    )
    assert 1 <= len(listing_provider.calls) <= 10
    assert len(set(listing_provider.calls)) == len(listing_provider.calls)
    assert "33960" in listing_provider.calls


# ---------------------------------------------------------------------------
# Scenario 7: identity/intrinsic/metadata contract failure
# ---------------------------------------------------------------------------


def test_identity_contract_failure_classifies_correctly() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=transport,
        listing_provider=_ContractMismatchListingProvider(),
        final_provider=_FinalPriceProvider(),
        cached_resolver=None,
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.IDENTITY_INTRINSIC_METADATA_CONTRACT_FAILURE
    )
    assert report.counters.buff_dispatch_started >= 1
    assert report.counters.buff_contract_failure == 0


# ---------------------------------------------------------------------------
# Scenario 8: final valuation incomplete
# ---------------------------------------------------------------------------


def test_final_valuation_incomplete_skips_metrics() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    listing_provider = _ListingProvider(_phoenix_listings(metadata))
    final_provider = _FinalPriceProvider(fail=True)
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=transport,
        listing_provider=listing_provider,
        final_provider=final_provider,
        cached_resolver=None,
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.FINAL_VALUATION_INCOMPLETE
    )
    assert report.evidence.input_total_cost_cny is None
    assert report.evidence.expected_gross_revenue_cny is None
    assert report.evidence.risk_passed is None


# ---------------------------------------------------------------------------
# Scenario 9: final NEW-LIVE atomic budget block
# ---------------------------------------------------------------------------


def test_final_atomic_one_over_cap_dispatches_zero() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    listing_provider = _ListingProvider(_phoenix_listings(metadata))
    final_provider = _FinalPriceProvider()
    family = _phoenix_family()
    config = RecipeFirstRuntimeConfig(
        enabled=True,
        preview=False,
        input_rarities=("Classified",),
        stattrak_modes=(StatTrakMode.NORMAL,),
        collection_allowlist=("The Phoenix Collection",),
        max_targeted_buff_goods_ids=10,
        max_final_valuation_requests=1,
        sell_fee_rate=Decimal("0.025"),
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=1,
            max_candidate_states_explored=256,
        ),
        cache_backend="inmemory",
        output_format=RecipeFirstOutputFormat.JSON,
    )
    budget = RecipeFirstDiscoveryBudget(
        max_family_states_considered=1,
        max_prescreen_names=100,
        max_prescreen_batch_dispatches=10,
    )
    valuation = ValuationService(
        final_provider, ValuationConfig(require_all_prices=True)
    )
    risk = RiskFilterConfig(
        min_roi=Decimal("-100"),
        min_expected_profit_cny=Decimal("-10000"),
        max_worst_case_loss_pct=Decimal("100"),
        min_profit_probability=0.0,
        max_input_total_cost_cny=Decimal("1000000"),
    )
    coordinator = RecipeFirstRuntimeCoordinator(
        config=config,
        discovery_budget=budget,
        identity_resolver=identity,
        metadata_resolver=metadata,
        finish_index=finish_index,
        prescreen_transport=transport,
        listing_provider=listing_provider,
        valuation_service=valuation,
        risk_config=risk,
        family_iterator_factory=lambda _generator: iter((family,)),
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.VALUATION_REQUEST_BUDGET_BLOCKED
    )
    assert report.counters.evaluations_budget_blocked > 0
    assert final_provider.calls == []
    assert report.evidence.input_total_cost_cny is None


def test_final_duplicate_exact_output_no_duplicate_live_call() -> None:
    from app.services.scanner_valuation_session import RunScopedValuationSession

    calls: list[tuple[str, ...]] = []

    class _Provider:
        async def get_price(self, name: str) -> PriceQuote:
            calls.append((name,))
            return PriceQuote(
                market_hash_name=name,
                price_cny=Decimal("1000"),
                source="steamdt:buff",
                raw=None,
            )

        async def get_prices(self, names: list[str]) -> PriceLookupResult:
            calls.append(tuple(names))
            quotes = {
                n: PriceQuote(
                    market_hash_name=n,
                    price_cny=Decimal("1000"),
                    source="steamdt:buff",
                    raw=None,
                )
                for n in names
            }
            return PriceLookupResult(quotes=quotes, missing=[], errors=[])

    session = RunScopedValuationSession(
        price_provider=_Provider(),
        valuation_config=ValuationConfig(require_all_prices=True),
        session_id=1,
    )
    rows = [
        TradeupResult(
            output_market_hash_name="AUG | Chameleon (Field-Tested)",
            probability=0.5,
            output_float=0.2,
            output_wear="Field-Tested",
            estimated_price_cny=Decimal("0"),
            expected_value_contribution=Decimal("0"),
        ),
        TradeupResult(
            output_market_hash_name="AUG | Chameleon (Field-Tested)",
            probability=0.5,
            output_float=0.2,
            output_wear="Field-Tested",
            estimated_price_cny=Decimal("0"),
            expected_value_contribution=Decimal("0"),
        ),
    ]

    async def run() -> None:
        plan = await session.prepare_output_prices(
            ["AUG | Chameleon (Field-Tested)", "AUG | Chameleon (Field-Tested)"]
        )
        await session.resolve_prepared(plan, rows)

    asyncio.run(run())
    assert calls == [("AUG | Chameleon (Field-Tested)",)]


# ---------------------------------------------------------------------------
# Scenario 10/13: provider transport / final failure
# ---------------------------------------------------------------------------


def test_steamdt_batch_provider_failure_classifies_external() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport(raise_error=RuntimeError("network detail must never leak"))
    listing_provider = _ListingProvider(_phoenix_listings(metadata))
    final_provider = _FinalPriceProvider()
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=transport,
        listing_provider=listing_provider,
        final_provider=final_provider,
        cached_resolver=None,
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.EXTERNAL_PROVIDER_FAILURE
    )
    assert report.counters.prescreen_transport_error_count >= 1
    assert listing_provider.calls == []


def test_final_provider_failure_classifies_external() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    listing_provider = _ListingProvider(_phoenix_listings(metadata))
    final_provider = _FinalPriceProvider(fail=True)
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=transport,
        listing_provider=listing_provider,
        final_provider=final_provider,
        cached_resolver=None,
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.FINAL_VALUATION_INCOMPLETE
    )
    assert report.counters.live_failed >= 1


# ---------------------------------------------------------------------------
# Scenario 11/12: BUFF provider failure before/after lock
# ---------------------------------------------------------------------------


def test_buff_provider_failure_before_lock_never_falls_back() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    listing_provider = _FailingListingProvider()
    final_provider = _FinalPriceProvider()
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=transport,
        listing_provider=listing_provider,
        final_provider=final_provider,
        cached_resolver=None,
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.EXTERNAL_PROVIDER_FAILURE
    )
    assert coordinator.buff_dispatch_started >= 1
    assert coordinator.fallback_used is False


def test_buff_contract_failure_after_lock_never_falls_back() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    listing_provider = _ContractMismatchListingProvider()
    final_provider = _FinalPriceProvider()
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=transport,
        listing_provider=listing_provider,
        final_provider=final_provider,
        cached_resolver=None,
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.IDENTITY_INTRINSIC_METADATA_CONTRACT_FAILURE
    )
    assert coordinator.buff_dispatch_started >= 1
    assert coordinator.fallback_used is False


# ---------------------------------------------------------------------------
# Scenario 14: internal invariant failure (selection discriminator raises)
# ---------------------------------------------------------------------------


def test_internal_invariant_failure_is_distinct_from_external(monkeypatch) -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    listing_provider = _ListingProvider(_phoenix_listings(metadata))
    final_provider = _FinalPriceProvider()

    from app.services.recipe_first_scanner_orchestrator import (
        RecipeFirstScannerOrchestrator,
    )

    def boom(self, *args, **kwargs):
        raise ValueError("internal invariant violated")

    monkeypatch.setattr(RecipeFirstScannerOrchestrator, "run_once", boom)

    config = RecipeFirstRuntimeConfig(
        enabled=True,
        preview=False,
        input_rarities=("Classified",),
        stattrak_modes=(StatTrakMode.NORMAL,),
        collection_allowlist=("The Phoenix Collection",),
        max_targeted_buff_goods_ids=10,
        max_final_valuation_requests=5,
        sell_fee_rate=Decimal("0.025"),
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=1,
            max_candidate_states_explored=256,
        ),
        cache_backend="inmemory",
        output_format=RecipeFirstOutputFormat.JSON,
    )
    budget = RecipeFirstDiscoveryBudget(
        max_family_states_considered=1,
        max_prescreen_names=100,
        max_prescreen_batch_dispatches=10,
    )
    valuation = ValuationService(
        final_provider, ValuationConfig(require_all_prices=True)
    )
    risk = RiskFilterConfig(
        min_roi=Decimal("-100"),
        min_expected_profit_cny=Decimal("-10000"),
        max_worst_case_loss_pct=Decimal("100"),
        min_profit_probability=0.0,
        max_input_total_cost_cny=Decimal("1000000"),
    )
    coordinator = RecipeFirstRuntimeCoordinator(
        config=config,
        discovery_budget=budget,
        identity_resolver=identity,
        metadata_resolver=metadata,
        finish_index=finish_index,
        prescreen_transport=transport,
        listing_provider=listing_provider,
        valuation_service=valuation,
        risk_config=risk,
        family_iterator_factory=lambda _generator: iter((_phoenix_family(),)),
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.INTERNAL_CONTRACT_FAILURE
    )


# ---------------------------------------------------------------------------
# Scenario 15/16: pre-BUFF fallback before lock and forbidden after lock
# ---------------------------------------------------------------------------


def test_pre_buff_fallback_success_and_post_lock_forbidden() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    listing_provider = _CatalogListingProvider(identity, metadata)
    final_provider = _FinalPriceProvider()
    coordinator = RecipeFirstRuntimeCoordinator(
        config=RecipeFirstRuntimeConfig(
            enabled=True,
            preview=False,
            input_rarities=("Classified",),
            stattrak_modes=(StatTrakMode.NORMAL,),
            collection_allowlist=(),
            max_targeted_buff_goods_ids=10,
            max_final_valuation_requests=5,
            sell_fee_rate=Decimal("0.025"),
            enumeration_config=RecipeEnumerationConfig(
                max_recipe_candidates_returned=1,
                max_candidate_states_explored=256,
            ),
            cache_backend="inmemory",
            output_format=RecipeFirstOutputFormat.JSON,
        ),
        discovery_budget=RecipeFirstDiscoveryBudget(
            max_family_states_considered=3,
            max_prescreen_names=100,
            max_prescreen_batch_dispatches=10,
        ),
        identity_resolver=identity,
        metadata_resolver=metadata,
        finish_index=finish_index,
        prescreen_transport=transport,
        listing_provider=listing_provider,
        valuation_service=ValuationService(
            final_provider, ValuationConfig(require_all_prices=True)
        ),
        risk_config=RiskFilterConfig(
            min_roi=Decimal("-100"),
            min_expected_profit_cny=Decimal("-10000"),
            max_worst_case_loss_pct=Decimal("100"),
            min_profit_probability=0.0,
            max_input_total_cost_cny=Decimal("1000000"),
        ),
        pre_buff_active_validator=lambda _plan: False,
    )
    report = asyncio.run(coordinator.run_once())
    assert coordinator.fallback_used is True
    assert len(report.evidence.ranked_families) == 2
    assert report.evidence.selected_active_family_key == (
        report.evidence.ranked_families[1].family_key
    )
    assert report.evidence.fallback_reason == "fallback_consumed_before_buff"
    assert coordinator.buff_dispatch_started > 0

    with pytest.raises(
        RecipeFirstRuntimeCoordinatorError, match="fallback"
    ):
        coordinator._resolve_pre_buff_fallback(
            decision=_build_decision(coordinator, family=_phoenix_family()),
            plans_by_key=_plans(coordinator, family=_phoenix_family()),
        )


def _build_decision(coordinator, *, family):
    del coordinator
    plan = TargetedBuffScanPlan(
        family_hash=family.family_hash,
        items=(
            TargetedBuffScanItem(
                market_hash_name="AK-47 | Redline (Field-Tested)",
                goods_id="33960",
                collection_name="The Phoenix Collection",
                collection_role="primary",
                priority_within_collection=1,
            ),
        ),
        stattrak_mode=family.stattrak_mode,
        priority=1,
        hard_request_count=1,
        unresolved_identity_count=0,
        diagnostics=("fixture",),
    )
    return TargetedBuffScanDecision(
        ranked_family_keys=(family.family_key, "f" * 24),
        active_family_key=family.family_key,
        active_plan=plan,
        fallback_family_key="f" * 24,
        hard_request_cap=10,
        diagnostics=("fixture",),
    )


def _plans(coordinator, *, family):
    del coordinator
    plan_b = TargetedBuffScanPlan(
        family_hash="f" * 64,
        items=(
            TargetedBuffScanItem(
                market_hash_name="B",
                goods_id="2",
                collection_name="The Phoenix Collection",
                collection_role="primary",
                priority_within_collection=1,
            ),
        ),
        stattrak_mode=family.stattrak_mode,
        priority=2,
        hard_request_count=1,
        unresolved_identity_count=0,
        diagnostics=("fixture",),
    )
    return {family.family_key: None, "f" * 24: plan_b}


# ---------------------------------------------------------------------------
# Scenario 17: FRESH_ONLY cache matrix
# ---------------------------------------------------------------------------


class _OutcomeCacheReader:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.calls: list[tuple[str, PriceCacheReadPolicy]] = []
        self.writes = 0

    async def get(
        self,
        key: PriceCacheKey,
        *,
        read_policy: PriceCacheReadPolicy = PriceCacheReadPolicy.FRESH_ONLY,
    ) -> PriceCacheLookup:
        self.calls.append((key.market_hash_name, read_policy))
        if self.mode == "backend_error":
            raise PriceCacheBackendError("get", "offline-fixture")
        if self.mode == "miss":
            return PriceCacheLookup.missing(key)
        if self.mode == "expired":
            return PriceCacheLookup(
                key=key,
                hit=False,
                state=PriceCacheState.EXPIRED,
                snapshot=None,
                age=timedelta(minutes=10),
                needs_refresh=True,
                policy_blocked=False,
                expired=True,
            )
        if self.mode == "policy_blocked":
            return PriceCacheLookup(
                key=key,
                hit=False,
                state=PriceCacheState.STALE,
                snapshot=None,
                age=timedelta(minutes=2),
                needs_refresh=True,
                policy_blocked=True,
                expired=False,
            )
        if self.mode == "selection_failure":
            now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
            snapshot = CachedPriceSnapshot(
                key=key,
                candidates=(
                    NormalizedPriceCandidate(
                        platform="STEAM",
                        platform_item_id="1",
                        sell_price_cny=Decimal("1000"),
                        sell_count=10,
                        bidding_price_cny=None,
                        bidding_count=None,
                        source_update_time="opaque",
                    ),
                ),
                observed_at=now,
                stored_at=now,
                policy=PriceCachePolicy(fresh_ttl=timedelta(minutes=5)),
            )
            return PriceCacheLookup(
                key=key,
                hit=True,
                state=PriceCacheState.FRESH,
                snapshot=snapshot,
                age=timedelta(0),
                needs_refresh=False,
                policy_blocked=False,
                expired=False,
            )
        return PriceCacheLookup.missing(key)

    async def put(self, snapshot: CachedPriceSnapshot) -> object:
        self.writes += 1
        raise AssertionError("runtime must not write cache")


def _seed_cache(
    cache: InMemoryPriceCache,
    *,
    names: tuple[str, ...],
    price: Decimal,
    policy: PriceCachePolicy,
    observed_at: datetime,
) -> None:
    for name in names:
        snapshot = CachedPriceSnapshot(
            key=PriceCacheKey(market_hash_name=name),
            candidates=(
                NormalizedPriceCandidate(
                    platform="BUFF",
                    platform_item_id="1",
                    sell_price_cny=price,
                    sell_count=10,
                    bidding_price_cny=None,
                    bidding_count=None,
                    source_update_time="opaque",
                ),
            ),
            observed_at=observed_at,
            stored_at=observed_at,
            policy=policy,
        )
        # Synchronous put: InMemoryPriceCache.put is async, but tests use
        # asyncio.run for each put.
        asyncio.run(cache.put(snapshot))


def test_fresh_cache_hit_avoids_new_live() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    listing_provider = _ListingProvider(_phoenix_listings(metadata))

    final_provider_calls: list[tuple[str, ...]] = []

    class _FinalProvider:
        async def get_price(self, name: str) -> PriceQuote:
            final_provider_calls.append((name,))
            return PriceQuote(
                market_hash_name=name,
                price_cny=Decimal("1234"),
                source="steamdt:buff",
                raw=None,
            )

        async def get_prices(self, names: list[str]) -> PriceLookupResult:
            for n in names:
                final_provider_calls.append((n,))
            quotes = {
                n: PriceQuote(
                    market_hash_name=n,
                    price_cny=Decimal("1234"),
                    source="steamdt:buff",
                    raw=None,
                )
                for n in names
            }
            return PriceLookupResult(quotes=quotes, missing=[], errors=[])

    now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=lambda: now)
    _seed_cache(
        cache,
        names=(
            "AUG | Chameleon (Field-Tested)",
            "AWP | Asiimov (Battle-Scarred)",
        ),
        price=Decimal("1000"),
        policy=PriceCachePolicy(
            fresh_ttl=timedelta(minutes=5),
            stale_ttl=timedelta(0),
            stale_grace_ttl=timedelta(0),
        ),
        observed_at=now - timedelta(seconds=1),
    )
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=transport,
        listing_provider=listing_provider,
        final_provider=_FinalProvider(),
        cached_resolver=ScannerCachedBuffPriceResolver(cache),
    )
    report = asyncio.run(coordinator.run_once())
    assert report.counters.cache_hits_fresh_selected == 2
    assert final_provider_calls == []


def test_expired_cache_triggers_new_live() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    listing_provider = _ListingProvider(_phoenix_listings(metadata))

    final_provider_calls: list[str] = []

    class _FinalProvider:
        async def get_price(self, name: str) -> PriceQuote:
            final_provider_calls.append(name)
            return PriceQuote(
                market_hash_name=name,
                price_cny=Decimal("1234"),
                source="steamdt:buff",
                raw=None,
            )

        async def get_prices(self, names: list[str]) -> PriceLookupResult:
            final_provider_calls.extend(names)
            quotes = {
                n: PriceQuote(
                    market_hash_name=n,
                    price_cny=Decimal("1234"),
                    source="steamdt:buff",
                    raw=None,
                )
                for n in names
            }
            return PriceLookupResult(quotes=quotes, missing=[], errors=[])

    now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=lambda: now)
    _seed_cache(
        cache,
        names=("AUG | Chameleon (Field-Tested)",),
        price=Decimal("1000"),
        policy=PriceCachePolicy(
            fresh_ttl=timedelta(seconds=1),
            stale_ttl=timedelta(0),
            stale_grace_ttl=timedelta(0),
        ),
        observed_at=now - timedelta(seconds=2),
    )
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=transport,
        listing_provider=listing_provider,
        final_provider=_FinalProvider(),
        cached_resolver=ScannerCachedBuffPriceResolver(cache),
    )
    report = asyncio.run(coordinator.run_once())
    assert final_provider_calls  # NEW-LIVE happened
    assert report.counters.cache_expired >= 1


@pytest.mark.parametrize(
    ("mode", "counter_name"),
    [
        ("miss", "cache_misses"),
        ("expired", "cache_expired"),
        ("policy_blocked", "cache_policy_blocked"),
    ],
)
def test_cache_nonfresh_outcomes_become_new_live_without_write(
    mode: str,
    counter_name: str,
) -> None:
    identity, metadata, finish_index = _pinned()
    reader = _OutcomeCacheReader(mode)
    final = _FinalPriceProvider()
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=_BatchTransport(),
        listing_provider=_ListingProvider(_phoenix_listings(metadata)),
        final_provider=final,
        cached_resolver=ScannerCachedBuffPriceResolver(reader),
    )
    report = asyncio.run(coordinator.run_once())
    assert getattr(report.counters, counter_name) > 0
    assert report.counters.live_demand > 0
    assert final.calls
    assert reader.writes == 0
    assert all(
        policy is PriceCacheReadPolicy.FRESH_ONLY
        for _name, policy in reader.calls
    )


def test_cache_selection_failure_is_terminal_and_not_live_fallback() -> None:
    identity, metadata, finish_index = _pinned()
    reader = _OutcomeCacheReader("selection_failure")
    final = _FinalPriceProvider()
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=_BatchTransport(),
        listing_provider=_ListingProvider(_phoenix_listings(metadata)),
        final_provider=final,
        cached_resolver=ScannerCachedBuffPriceResolver(reader),
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.FINAL_VALUATION_INCOMPLETE
    )
    assert report.counters.cache_selection_failures > 0
    assert report.counters.live_demand == 0
    assert final.calls == []
    assert reader.writes == 0


def test_cache_backend_failure_is_infrastructure_terminal() -> None:
    identity, metadata, finish_index = _pinned()
    reader = _OutcomeCacheReader("backend_error")
    final = _FinalPriceProvider()
    coordinator = _build_coordinator(
        identity=identity,
        metadata=metadata,
        finish_index=finish_index,
        transport=_BatchTransport(),
        listing_provider=_ListingProvider(_phoenix_listings(metadata)),
        final_provider=final,
        cached_resolver=ScannerCachedBuffPriceResolver(reader),
    )
    report = asyncio.run(coordinator.run_once())
    assert (
        report.terminal_code
        is RecipeFirstRuntimeTerminalCode.EXTERNAL_PROVIDER_FAILURE
    )
    assert "PriceCacheBackendError" in report.safe_error_codes
    assert final.calls == []
    assert coordinator.fallback_used is False
    assert reader.writes == 0


# ---------------------------------------------------------------------------
# Scenario 18: deterministic repeated run with byte-identical normalized JSON
# ---------------------------------------------------------------------------


def test_deterministic_repeated_run_has_byte_identical_normalized_json() -> None:
    identity, metadata, finish_index = _pinned()
    transport = _BatchTransport()
    listing_provider = _ListingProvider(_phoenix_listings(metadata))
    final_provider = _FinalPriceProvider(
        prices_by_name={
            q.market_hash_name: Decimal("1000")
            for q in _deterministic_prescreen(metadata=metadata).quotes
        }
    )

    def _run_once():
        coordinator = _build_coordinator(
            identity=identity,
            metadata=metadata,
            finish_index=finish_index,
            transport=transport,
            listing_provider=listing_provider,
            final_provider=final_provider,
            cached_resolver=None,
        )
        return asyncio.run(coordinator.run_once())

    def normalize(payload: dict[str, object]) -> dict[str, object]:
        # Volatile-only normalization: replace run ID and concrete timing.
        for key in list(payload):
            if key == "run_id":
                payload[key] = "NORMALIZED"
        return payload

    first = normalize(cli._serialize_report(_run_once()))
    second = normalize(cli._serialize_report(_run_once()))
    assert first == second


# ---------------------------------------------------------------------------
# Scenario 19: goods-first regression unchanged
# ---------------------------------------------------------------------------


def test_goods_first_authorities_byte_stable_from_phase17a() -> None:
    expected = {
        "app/services/scanner_orchestrator.py": (
            "06bb4fe5654c72bc3540904f6982c1e0672f276d"
        ),
        "scripts/run_live_scan_once.py": (
            "e0f8773fe4b9a81c96a3b23877a07c60a6dfc871"
        ),
    }
    for relative, expected_blob in expected.items():
        current = subprocess.check_output(
            ("git", "hash-object", relative), text=True
        ).strip()
        assert current == expected_blob


# ---------------------------------------------------------------------------
# Offline measurement counters
# ---------------------------------------------------------------------------


def test_offline_measurement_counters_recorded(phase17c_report) -> None:
    counters = phase17c_report.counters
    evidence = phase17c_report.evidence
    assert counters.families_visited == 1
    assert counters.families_infeasible == 0
    assert counters.families_contract_failed == 0
    assert counters.families_ranked_retained == 1
    assert counters.families_ranked_excluded == 0
    assert counters.prescreen_dispatch_started >= 1
    assert counters.prescreen_succeeded == counters.prescreen_unique_after_dedupe
    assert counters.buff_dispatch_started == counters.buff_succeeded
    assert counters.buff_succeeded >= 1
    assert counters.buff_succeeded <= counters.buff_dispatch_started
    assert counters.buff_dispatch_started <= 10
    assert counters.opportunities_found >= 1
    assert len(evidence.targeted_goods_ids) == counters.buff_succeeded
    assert len(evidence.targeted_goods_ids) >= 1
    assert len(evidence.concrete_output_names) >= 1
    assert sum(evidence.concrete_output_probabilities) == pytest.approx(1.0)
