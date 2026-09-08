"""Phase 17B zero-network opt-in recipe-first runtime coverage.

All market seams are in-memory fakes. The real coordinator composes pinned
family/geometry/feasibility, strict batch pre-screen selection, Top-2 ranking,
targeted planning, acquisition/enrichment, family-constrained search,
run-scoped final valuation, EV, and risk.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import islice
from pathlib import Path

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
    PriceCachePolicy,
)
from app.services.price_provider import PriceLookupResult, PriceQuote
from app.services.recipe_family import RecipeFamilyGenerator, build_recipe_family
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
    RecipeFirstRuntimeTerminalCode,
    RecipeFirstRuntimeTerminalGroup,
    exit_code_for_terminal_group,
)
from app.services.recipe_first_runtime_coordinator import (
    RecipeFirstRuntimeCoordinator,
    RecipeFirstRuntimeCoordinatorError,
)
from app.services.recipe_solver import RecipeEnumerationConfig
from app.services.risk_filter import RiskFilterConfig
from app.services.scanner_cached_buff_price_resolver import (
    ScannerCachedBuffPriceResolver,
)
from app.services.scanner_valuation_session import RunScopedValuationSession
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
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


def _family():
    return build_recipe_family(
        input_rarity="Classified",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Phoenix Collection", 10),),
    )


def _pinned():
    identity = BuffCommunityIdentityResolver.from_snapshot_path(IDENTITY_PATH)
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(METADATA_PATH)
    finish_index = StructuralOutputFinishIndex.from_skins(metadata.skins)
    return identity, metadata, finish_index


class _BatchTransport:
    def __init__(
        self,
        *,
        fail: bool = False,
        platform: str = "BUFF",
        sell: object = "100",
        duplicate_buff: bool = False,
    ) -> None:
        self.fail = fail
        self.platform = platform
        self.sell = sell
        self.duplicate_buff = duplicate_buff
        self.calls: list[tuple[str, ...]] = []

    async def get_price_batch_with_selection(
        self,
        market_hash_names: list[str],
        *,
        selection_config: object = None,
        avg_prices_by_name: object = None,
    ) -> SteamDTBatchPriceResult:
        self.calls.append(tuple(market_hash_names))
        if self.fail:
            raise RuntimeError("raw upstream detail must never leak")
        rows = []
        for name in market_hash_names:
            platform_row = {
                "platform": self.platform,
                "platformItemId": "1",
                "sellPrice": self.sell,
                "sellCount": 100,
                "biddingPrice": "999",
                "biddingCount": 1,
                "updateTime": "opaque",
            }
            data_list = [platform_row]
            if self.duplicate_buff:
                data_list.append(dict(platform_row))
            rows.append({"marketHashName": name, "dataList": data_list})
        return SteamDTBatchPriceResult(
            quotes={},
            missing=[],
            raw={"success": True, "data": rows},
        )


class _PinnedListingProvider:
    def __init__(self, identity, metadata, *, fail: bool = False) -> None:
        self.identity = identity
        self.metadata = metadata
        self.fail = fail
        self.calls: list[str] = []

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        self.calls.append(goods_id)
        if self.fail:
            raise RuntimeError("provider detail must not leak")
        resolved = await self.identity.resolve_goods_id(goods_id)
        assert resolved is not None
        row = self.metadata.resolve(resolved.market_hash_name)
        assert row is not None
        midpoint = (Decimal(str(row.min_float)) + Decimal(str(row.max_float))) / 2
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


class _RecordingPriceProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, ...]] = []

    async def get_price(self, market_hash_name: str) -> PriceQuote:
        result = await self.get_prices([market_hash_name])
        return result.quotes[market_hash_name]

    async def get_prices(self, names: list[str]) -> PriceLookupResult:
        self.calls.append(tuple(names))
        if self.fail:
            return PriceLookupResult(quotes={}, missing=list(names), errors=["safe"])
        return PriceLookupResult(
            quotes={
                name: PriceQuote(
                    market_hash_name=name,
                    price_cny=Decimal("1000"),
                    source="steamdt:buff",
                    raw=None,
                )
                for name in names
            },
            missing=[],
            errors=[],
        )


def _risk(*, passes: bool) -> RiskFilterConfig:
    return RiskFilterConfig(
        min_roi=Decimal("-100") if passes else Decimal("1000"),
        min_expected_profit_cny=Decimal("-100000"),
        max_worst_case_loss_pct=Decimal("100000"),
        min_profit_probability=0.0,
        max_input_total_cost_cny=Decimal("1000000"),
    )


def _config(
    *,
    enabled: bool = True,
    final_cap: int = 5,
    targeted_cap: int = 10,
    sell_fee: str = "0.025",
) -> RecipeFirstRuntimeConfig:
    return RecipeFirstRuntimeConfig(
        enabled=enabled,
        preview=False,
        input_rarities=("Classified",),
        stattrak_modes=(StatTrakMode.NORMAL,),
        collection_allowlist=("The Phoenix Collection",),
        max_targeted_buff_goods_ids=targeted_cap,
        max_final_valuation_requests=final_cap,
        sell_fee_rate=Decimal(sell_fee),
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=1,
            max_candidate_states_explored=256,
        ),
        cache_backend="inmemory",
        output_format=RecipeFirstOutputFormat.JSON,
    )


def _coordinator(
    *,
    config: RecipeFirstRuntimeConfig | None = None,
    budget: RecipeFirstDiscoveryBudget | None = None,
    batch: _BatchTransport | None = None,
    listing: _PinnedListingProvider | None = None,
    final_provider: _RecordingPriceProvider | None = None,
    risk_passes: bool = True,
    active_validator=None,
    family_iterator=None,
    cached=None,
):
    identity, metadata, finish_index = _pinned()
    batch = batch or _BatchTransport()
    listing = listing or _PinnedListingProvider(identity, metadata)
    final_provider = final_provider or _RecordingPriceProvider()
    family = _family()

    def one_family(_generator: RecipeFamilyGenerator):
        yield family

    coordinator = RecipeFirstRuntimeCoordinator(
        config=config or _config(),
        discovery_budget=budget
        or RecipeFirstDiscoveryBudget(
            max_family_states_considered=1,
            max_prescreen_names=100,
            max_prescreen_batch_dispatches=10,
        ),
        identity_resolver=identity,
        metadata_resolver=metadata,
        finish_index=finish_index,
        prescreen_transport=batch,
        listing_provider=listing,
        valuation_service=ValuationService(
            final_provider,
            ValuationConfig(require_all_prices=True),
        ),
        risk_config=_risk(passes=risk_passes),
        cached_price_resolver=cached,
        pre_buff_active_validator=active_validator,
        family_iterator_factory=family_iterator or one_family,
    )
    return coordinator, batch, listing, final_provider


def _empty_evidence() -> RecipeFirstRuntimeEvidence:
    return RecipeFirstRuntimeEvidence(
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


def _report() -> RecipeFirstOperatorRunReport:
    return RecipeFirstOperatorRunReport(
        mode="recipe-first-one-shot",
        run_id=1,
        terminal_group=RecipeFirstRuntimeTerminalGroup.SUCCESS,
        terminal_code=RecipeFirstRuntimeTerminalCode.SUCCESS_OPPORTUNITIES_FOUND,
        config_identity=("enabled=true",),
        discovery_budget=RecipeFirstDiscoveryBudget(),
        counters=RecipeFirstRuntimeCounters(opportunities_found=1),
        phases=(RecipeFirstRuntimePhase(name="done", status="ok"),),
        evidence=_empty_evidence(),
        incompleteness_flags=(),
        safe_error_codes=(),
    )


def test_runtime_contract_defaults_and_exit_policy() -> None:
    config = RecipeFirstRuntimeConfig()
    assert config.enabled is False
    assert config.max_final_valuation_requests == 5
    assert config.max_targeted_buff_goods_ids == 10
    assert config.cache_backend == "inmemory"
    assert exit_code_for_terminal_group(RecipeFirstRuntimeTerminalGroup.SUCCESS) == 0
    assert (
        exit_code_for_terminal_group(
            RecipeFirstRuntimeTerminalGroup.EXPECTED_NO_OPPORTUNITY
        )
        == 0
    )
    assert (
        exit_code_for_terminal_group(
            RecipeFirstRuntimeTerminalGroup.INCOMPLETE_OR_PROVIDER
        )
        == 2
    )
    assert (
        exit_code_for_terminal_group(
            RecipeFirstRuntimeTerminalGroup.CONTRACT_OR_CONFIGURATION
        )
        == 3
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_family_states_considered": 0},
        {"max_family_states_considered": 1_000_001},
        {"max_prescreen_names": 0},
        {"max_prescreen_names": 101},
        {"max_prescreen_batch_dispatches": 0},
        {"max_prescreen_batch_dispatches": 33},
    ],
)
def test_discovery_budget_fails_closed(kwargs) -> None:
    with pytest.raises(RecipeFirstRuntimeError):
        RecipeFirstDiscoveryBudget(**kwargs)


def test_coordinator_requires_explicit_enabled_config() -> None:
    with pytest.raises(RecipeFirstRuntimeCoordinatorError, match="enabled"):
        _coordinator(config=_config(enabled=False))


def test_invalid_collection_scope_fails_before_prescreen() -> None:
    with pytest.raises(RecipeFirstRuntimeCoordinatorError, match="collection"):
        _coordinator(
            config=RecipeFirstRuntimeConfig(
                enabled=True,
                input_rarities=("Classified",),
                stattrak_modes=(StatTrakMode.NORMAL,),
                collection_allowlist=("Not A Pinned Collection",),
            )
        )


def test_family_geometry_contract_failure_stops_before_prescreen() -> None:
    def invalid_family(_generator):
        yield object()

    coordinator, batch, listing, final = _coordinator(
        family_iterator=invalid_family
    )
    report = asyncio.run(coordinator.run_once())
    assert report.terminal_code is (
        RecipeFirstRuntimeTerminalCode.INTERNAL_CONTRACT_FAILURE
    )
    assert report.counters.families_contract_failed == 1
    assert batch.calls == []
    assert listing.calls == []
    assert final.calls == []


def test_cli_without_enable_refuses_before_live_composition(
    monkeypatch, capsys, tmp_path
) -> None:
    calls = 0

    async def forbidden(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("must not construct clients")

    monkeypatch.setattr(cli, "_run_live_composition", forbidden)
    rc = cli.main(["--artifact-dir", str(tmp_path)])
    assert rc == EXIT_CODE_CONTRACT_OR_CONFIG
    assert calls == 0
    assert "CONFIGURATION_BLOCKED" in (
        tmp_path / cli.RESULT_FILENAME
    ).read_text(encoding="utf-8")
    assert "enable_required" in capsys.readouterr().out


def test_cli_preview_is_zero_market_and_cache_client_construction(
    monkeypatch, capsys
) -> None:
    async def forbidden(**kwargs):
        raise AssertionError("live composition must not be called")

    monkeypatch.setattr(cli, "_run_live_composition", forbidden)
    rc = cli.main(
        [
            "--enable-recipe-first",
            "--preview",
            "--input-rarity",
            "Classified",
            "--stattrak-mode",
            "normal",
            "--collection",
            "The Phoenix Collection",
            "--output-format",
            "json",
        ]
    )
    assert rc == 0
    output = capsys.readouterr().out
    assert "SUCCESS_PREVIEW" in output
    assert '"prescreen_dispatch_started":0' in output
    assert '"buff_dispatch_started":0' in output


def test_cli_preview_constructs_no_http_or_network_cache_client(
    monkeypatch,
) -> None:
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


def test_cli_preview_invalid_config_blocks_before_live_composition(monkeypatch) -> None:
    calls = 0

    async def forbidden(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError

    monkeypatch.setattr(cli, "_run_live_composition", forbidden)
    rc = cli.main(
        [
            "--enable-recipe-first",
            "--preview",
            "--max-targeted-buff-goods-ids",
            "0",
        ]
    )
    assert rc == 3
    assert calls == 0


def test_cli_live_config_blocks_before_http_client_construction(
    monkeypatch,
) -> None:
    calls = 0

    def forbidden(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("HTTP client must not be constructed")

    monkeypatch.setattr(cli.httpx, "AsyncClient", forbidden)
    monkeypatch.setenv("STEAMDT_DRY_RUN", "true")
    monkeypatch.delenv("STEAMDT_API_KEY", raising=False)
    rc = cli.main(["--enable-recipe-first"])
    assert rc == 3
    assert calls == 0


def test_human_json_render_same_report_and_are_safe() -> None:
    report = _report()
    payload = cli._serialize_report(report)
    rendered_json = cli._render_json(report)
    rendered_human = cli._render_human(report)
    assert json.loads(rendered_json) == payload
    assert report.terminal_code.value in rendered_human
    lowered = (rendered_json + rendered_human).lower()
    for forbidden in (
        "api_key",
        "authorization",
        "cookie",
        "raw_payload",
        "seller",
        "account",
        "webhook",
        "listing_id",
        "asset_id",
    ):
        assert forbidden not in lowered


def test_discovery_is_lazy_and_exactly_state_bounded() -> None:
    yielded = 0
    family = _family()

    def bounded(_generator):
        nonlocal yielded
        while True:
            yielded += 1
            if yielded > 1:
                raise AssertionError("family iterator over-read state cap")
            yield family

    coordinator, batch, _, _ = _coordinator(
        budget=RecipeFirstDiscoveryBudget(
            max_family_states_considered=1,
            max_prescreen_names=1,
            max_prescreen_batch_dispatches=1,
        ),
        family_iterator=bounded,
    )
    report = asyncio.run(coordinator.run_once())
    assert yielded == 1
    assert report.counters.families_visited == 1
    assert report.terminal_code is RecipeFirstRuntimeTerminalCode.PRESCREEN_INCOMPLETE
    assert batch.calls == []


@pytest.mark.parametrize(
    ("max_names", "max_batches"),
    [(1, 32), (100, 1)],
)
def test_prescreen_admission_is_atomic(max_names, max_batches) -> None:
    coordinator, batch, listing, final = _coordinator(
        budget=RecipeFirstDiscoveryBudget(
            max_family_states_considered=1,
            max_prescreen_names=max_names,
            max_prescreen_batch_dispatches=max_batches,
        )
    )
    report = asyncio.run(coordinator.run_once())
    assert report.terminal_code is RecipeFirstRuntimeTerminalCode.PRESCREEN_INCOMPLETE
    assert report.counters.prescreen_atomically_blocked > 0
    assert report.counters.prescreen_dispatch_started == 0
    assert batch.calls == []
    assert listing.calls == []
    assert final.calls == []


def test_prescreen_dispatch_start_consumed_on_transport_failure() -> None:
    coordinator, batch, listing, _ = _coordinator(
        batch=_BatchTransport(fail=True)
    )
    report = asyncio.run(coordinator.run_once())
    assert report.terminal_code is RecipeFirstRuntimeTerminalCode.EXTERNAL_PROVIDER_FAILURE
    assert report.counters.prescreen_dispatch_started == len(batch.calls)
    assert len(batch.calls) == 2
    assert len({name for call in batch.calls for name in call}) == sum(
        len(call) for call in batch.calls
    )
    assert report.counters.prescreen_transport_error_count == len(batch.calls)
    assert listing.calls == []
    assert "raw upstream detail" not in repr(report)


@pytest.mark.parametrize(
    "transport",
    [
        _BatchTransport(platform="STEAM"),
        _BatchTransport(sell="0"),
        _BatchTransport(duplicate_buff=True),
    ],
)
def test_strict_prescreen_failures_are_incomplete_and_never_reach_buff(
    transport,
) -> None:
    coordinator, _, listing, final = _coordinator(batch=transport)
    report = asyncio.run(coordinator.run_once())
    assert report.terminal_code is RecipeFirstRuntimeTerminalCode.PRESCREEN_INCOMPLETE
    assert report.counters.prescreen_terminal_selection_failures > 0
    assert listing.calls == []
    assert final.calls == []


def test_real_coordinator_reaches_real_downstream_and_reports_existing_values() -> None:
    coordinator, batch, listing, final = _coordinator(risk_passes=True)
    report = asyncio.run(coordinator.run_once())
    assert report.terminal_code is RecipeFirstRuntimeTerminalCode.SUCCESS_OPPORTUNITIES_FOUND
    assert report.evidence.selected_active_family_key == PHOENIX_KEY
    assert report.evidence.selected_active_family_hash == PHOENIX_HASH
    assert report.counters.families_visited == 1
    assert report.counters.families_ranked_retained == 1
    assert report.counters.prescreen_dispatch_started == len(batch.calls)
    assert 1 <= len(report.evidence.targeted_goods_ids) <= 10
    assert report.counters.buff_dispatch_started == len(listing.calls)
    assert report.counters.buff_dispatch_started <= 10
    assert report.evidence.concrete_input_summary_count == 10
    assert report.evidence.concrete_output_names
    assert sum(report.evidence.concrete_output_probabilities) == pytest.approx(1.0)
    assert report.evidence.final_quote_market_hash_names == (
        report.evidence.concrete_output_names
    )
    assert all(source == "steamdt:buff" for source in report.evidence.final_quote_source)
    assert final.calls
    assert report.evidence.input_total_cost_cny == Decimal("10")
    assert report.evidence.expected_gross_revenue_cny is not None
    assert report.evidence.expected_profit_cny is not None
    assert report.evidence.roi is not None
    assert report.evidence.risk_passed is True
    assert len(report.evidence.evaluations) == (
        report.evidence.selected_family_evaluations_count
    )
    assert report.evidence.evaluations[0].expected_profit_cny == (
        report.evidence.expected_profit_cny
    )


def test_fresh_only_cache_hits_avoid_new_live_final_dispatch() -> None:
    first, _, _, _ = _coordinator()
    first_report = asyncio.run(first.run_once())
    names = first_report.evidence.concrete_output_names
    assert names

    now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=lambda: now)

    async def seed() -> None:
        for name in names:
            snapshot = CachedPriceSnapshot(
                key=PriceCacheKey(market_hash_name=name),
                candidates=(
                    NormalizedPriceCandidate(
                        platform="BUFF",
                        platform_item_id="1",
                        sell_price_cny=Decimal("1000"),
                        sell_count=100,
                        bidding_price_cny=None,
                        bidding_count=None,
                        source_update_time="opaque",
                    ),
                ),
                observed_at=now - timedelta(seconds=1),
                stored_at=now - timedelta(seconds=1),
                policy=PriceCachePolicy(fresh_ttl=timedelta(minutes=5)),
            )
            await cache.put(snapshot)

    asyncio.run(seed())
    final = _RecordingPriceProvider()
    second, _, _, _ = _coordinator(
        final_provider=final,
        cached=ScannerCachedBuffPriceResolver(cache),
    )
    report = asyncio.run(second.run_once())
    assert report.counters.cache_hits_fresh_selected == len(names)
    assert report.counters.live_demand == 0
    assert report.counters.live_attempted == 0
    assert final.calls == []
    assert report.evidence.final_quote_market_hash_names == names
    assert all(
        source == "steamdt:buff"
        for source in report.evidence.final_quote_source
    )


def test_real_streaming_top_two_and_fallback_before_buff() -> None:
    def first_three(generator: RecipeFamilyGenerator):
        return islice(generator.iter_families(), 3)

    config = replace(_config(), collection_allowlist=())
    coordinator, batch, listing, _ = _coordinator(
        config=config,
        budget=RecipeFirstDiscoveryBudget(
            max_family_states_considered=3,
            max_prescreen_names=100,
            max_prescreen_batch_dispatches=10,
        ),
        active_validator=lambda _plan: False,
        family_iterator=first_three,
    )
    report = asyncio.run(coordinator.run_once())
    assert report.counters.families_visited == 3
    assert report.counters.families_ranked_retained == 2
    assert len(report.evidence.ranked_families) == 2
    assert report.evidence.selected_active_family_key == (
        report.evidence.ranked_families[1].family_key
    )
    assert report.evidence.fallback_reason == "fallback_consumed_before_buff"
    assert coordinator.fallback_used is True
    assert report.counters.fallback_family_used is True
    assert report.evidence.targeted_goods_ids == tuple(listing.calls)
    assert len(batch.calls) <= 10


def test_prescreen_and_final_price_authorities_are_separate() -> None:
    coordinator, _, _, _ = _coordinator()
    report = asyncio.run(coordinator.run_once())
    assert report.evidence.prescreen_quote_names
    assert report.evidence.final_quote_market_hash_names
    assert all(
        value == Decimal("1000")
        for value in report.evidence.final_quote_price_cny
    )
    assert all(
        source == "steamdt:buff"
        for source in report.evidence.final_quote_source
    )


def test_final_atomic_one_over_cap_dispatches_zero() -> None:
    final = _RecordingPriceProvider()
    coordinator, _, _, final = _coordinator(
        config=_config(final_cap=1), final_provider=final
    )
    report = asyncio.run(coordinator.run_once())
    assert report.terminal_code is (
        RecipeFirstRuntimeTerminalCode.VALUATION_REQUEST_BUDGET_BLOCKED
    )
    assert report.counters.live_atomically_blocked > 0
    assert final.calls == []
    assert report.evidence.input_total_cost_cny is None


def test_duplicate_exact_output_name_uses_one_final_live_request() -> None:
    provider = _RecordingPriceProvider()
    session = RunScopedValuationSession(
        price_provider=provider,
        valuation_config=ValuationConfig(require_all_prices=True),
        session_id=17,
    )
    name = "AUG | Chameleon (Field-Tested)"
    rows = [
        TradeupResult(
            output_market_hash_name=name,
            probability=0.5,
            output_float=0.2,
            output_wear="Field-Tested",
            estimated_price_cny=Decimal("0"),
            expected_value_contribution=Decimal("0"),
        ),
        TradeupResult(
            output_market_hash_name=name,
            probability=0.5,
            output_float=0.2,
            output_wear="Field-Tested",
            estimated_price_cny=Decimal("0"),
            expected_value_contribution=Decimal("0"),
        ),
    ]

    async def run() -> None:
        plan = await session.prepare_output_prices([name, name])
        assert plan.requested_names == (name,)
        await session.resolve_prepared(plan, rows)

    asyncio.run(run())
    assert provider.calls == [(name,)]


def test_final_incomplete_skips_metrics_risk_and_opportunity() -> None:
    final = _RecordingPriceProvider(fail=True)
    coordinator, _, _, _ = _coordinator(final_provider=final)
    report = asyncio.run(coordinator.run_once())
    assert report.terminal_code is RecipeFirstRuntimeTerminalCode.FINAL_VALUATION_INCOMPLETE
    assert report.evidence.expected_gross_revenue_cny is None
    assert report.evidence.risk_passed is None
    assert report.counters.opportunities_found == 0


def test_risk_reject_is_expected_no_opportunity() -> None:
    coordinator, _, _, _ = _coordinator(risk_passes=False)
    report = asyncio.run(coordinator.run_once())
    assert report.terminal_code is RecipeFirstRuntimeTerminalCode.RISK_FILTER_REJECTED
    assert report.terminal_group is (
        RecipeFirstRuntimeTerminalGroup.EXPECTED_NO_OPPORTUNITY
    )
    assert report.evidence.risk_passed is False
    assert report.evidence.risk_reason_codes


def test_valuation_budget_block_takes_precedence_over_buff_page_failure() -> None:
    config = replace(_config(), max_final_valuation_requests=1)
    coordinator, _, _, _ = _coordinator(config=config)
    report = asyncio.run(coordinator.run_once())
    assert report.terminal_code is (
        RecipeFirstRuntimeTerminalCode.VALUATION_REQUEST_BUDGET_BLOCKED
    )
    assert report.counters.evaluations_budget_blocked > 0


def test_provider_failure_after_buff_lock_never_falls_back() -> None:
    identity, metadata, _ = _pinned()
    listing = _PinnedListingProvider(identity, metadata, fail=True)
    coordinator, _, _, _ = _coordinator(listing=listing)
    report = asyncio.run(coordinator.run_once())
    assert report.terminal_code is RecipeFirstRuntimeTerminalCode.EXTERNAL_PROVIDER_FAILURE
    assert report.counters.buff_dispatch_started == len(listing.calls)
    assert 1 <= len(listing.calls) <= 10
    assert len(set(listing.calls)) == len(listing.calls)
    assert coordinator.buff_dispatch_started == len(listing.calls)
    assert coordinator.fallback_used is False


def test_fallback_before_buff_and_lock_rules() -> None:
    coordinator, _, _, _ = _coordinator(active_validator=lambda _plan: False)
    family = _family()
    plan_a = TargetedBuffScanPlan(
        family_hash=family.family_hash,
        items=(
            TargetedBuffScanItem(
                market_hash_name="A",
                goods_id="1",
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
    other_hash = "f" * 64
    plan_b = TargetedBuffScanPlan(
        family_hash=other_hash,
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
    decision = TargetedBuffScanDecision(
        ranked_family_keys=(family.family_key, other_hash[:24]),
        active_family_key=family.family_key,
        active_plan=plan_a,
        fallback_family_key=other_hash[:24],
        hard_request_cap=10,
        diagnostics=("fixture",),
    )
    plans = {family.family_key: plan_a, other_hash[:24]: plan_b}
    switched = coordinator._resolve_pre_buff_fallback(
        decision=decision, plans_by_key=plans
    )
    assert switched.active_family_key == other_hash[:24]
    assert coordinator.fallback_used is True
    assert switched.fallback_family_key is None

    coordinator._lock_active_family()
    with pytest.raises(RecipeFirstRuntimeCoordinatorError, match="fallback"):
        coordinator._resolve_pre_buff_fallback(
            decision=decision, plans_by_key=plans
        )


def test_contract_failure_in_active_validator_never_falls_back() -> None:
    def fail(_plan):
        raise ValueError("contract")

    coordinator, _, _, _ = _coordinator(active_validator=fail)
    family = _family()
    plan = TargetedBuffScanPlan(
        family_hash=family.family_hash,
        items=(
            TargetedBuffScanItem(
                market_hash_name="A",
                goods_id="1",
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
    decision = TargetedBuffScanDecision(
        ranked_family_keys=(family.family_key,),
        active_family_key=family.family_key,
        active_plan=plan,
        fallback_family_key=None,
        hard_request_cap=10,
        diagnostics=("fixture",),
    )
    with pytest.raises(RecipeFirstRuntimeCoordinatorError):
        coordinator._resolve_pre_buff_fallback(
            decision=decision,
            plans_by_key={family.family_key: plan},
        )
    assert coordinator.fallback_used is False


def test_phase16g_harness_is_not_imported_by_runtime_sources() -> None:
    paths = (
        ROOT / "app" / "services" / "recipe_first_runtime_contract.py",
        ROOT / "app" / "services" / "recipe_first_runtime_coordinator.py",
        ROOT / "scripts" / "run_recipe_first_scan_once.py",
    )
    forbidden = (
        "recipe_first_steamdt_live_runner",
        "run_live_recipe_first_steamdt_validation",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source


def test_phase16g_harness_has_no_production_runtime_importer() -> None:
    """Project-wide import-graph search: nothing under the production runtime
    tree may import the Phase16G validation harness.
    """

    targets = ("app", "scripts")
    forbidden = (
        "recipe_first_steamdt_live_runner",
        "run_live_recipe_first_steamdt_validation",
    )
    excluded_harnesses = {
        Path("app/services/recipe_first_steamdt_live_runner.py"),
        Path("scripts/run_live_recipe_first_steamdt_validation.py"),
    }
    offenders: list[str] = []
    for base in targets:
        root = ROOT / base
        for path in root.rglob("*.py"):
            relative = path.relative_to(ROOT)
            if relative in excluded_harnesses:
                continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path.relative_to(ROOT)}: {token}")
                    break
    assert not offenders, offenders


def test_goods_first_authorities_are_byte_stable_from_phase17a() -> None:
    # Immutable Phase17A-frozen goods-first authority blobs. These exact
    # identities keep the regression portable in depth-1 CI checkouts.
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


def test_runtime_source_has_no_loop_scheduler_or_buy_action() -> None:
    source = (
        ROOT / "scripts" / "run_recipe_first_scan_once.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in (
        "apscheduler",
        "auto_buy",
        "auto_trade",
        "while true",
        "while 1",
        "run_live_recipe_first_steamdt_validation",
    ):
        assert forbidden not in source
