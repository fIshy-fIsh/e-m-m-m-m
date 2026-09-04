"""Phase 16G — Bounded Recipe-First + SteamDT live validation runner tests.

These tests exercise the offline-only Phase 16G runner module using
fakes. The runner is never wired to a real HTTP transport. Any test
that requires a network call would FAIL; here, the fakes record the
exact dispatch/attempt flow and validate the runner's contract.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.market_universe_builder import StatTrakMode
from app.services.price_provider import PriceLookupResult, PriceQuote
from app.services.recipe_first_live_case import (
    LiveValidationPlanItem,
    freeze_case,
)
from app.services.recipe_first_steamdt_live_case import (
    RecipeFirstSteamDTCase,
    RecipeFirstSteamDTCaseError,
    freeze_recipe_first_steamdt_case,
)
from app.services.recipe_first_steamdt_live_runner import (
    CLASSIFICATION_BLOCKED,
    CLASSIFICATION_CONTRACT_FAILURE,
    CLASSIFICATION_INCONCLUSIVE,
    CLASSIFICATION_VALIDATED,
    RUN_STATUS_DISPATCHED,
    RecipeFirstSteamDTLiveRunner,
    RecipeFirstSteamDTLiveRunnerConfig,
)

ROOT = Path(__file__).resolve().parent.parent


def _buff_case() -> object:
    return freeze_case(
        repository_commit_oid="f" * 40,
        case_purpose="Phase 16G test",
        family_hash="a" * 64,
        family_key="a" * 24,
        input_rarity="Classified",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Phoenix Collection", 10),),
        plan_items=(
            LiveValidationPlanItem(
                market_hash_name="AK-47 | Redline (Field-Tested)",
                goods_id="33960",
                collection_name="The Phoenix Collection",
                priority_within_collection=1,
            ),
        ),
    )


def _phase16g_case(
    *,
    prescreen_names: Sequence[str] = ("AK-47 | Redline (Field-Tested)",),
) -> RecipeFirstSteamDTCase:
    return freeze_recipe_first_steamdt_case(
        repository_commit_oid="f" * 40,
        buff_case=_buff_case(),
        prescreen_market_hash_names=tuple(prescreen_names),
    )


class _FakeBuffResolver:
    async def resolve_goods_id(self, goods_id):
        from app.services.buff_item_identity import BuffItemIdentity

        if goods_id == "33960":
            return BuffItemIdentity(
                market_hash_name="AK-47 | Redline (Field-Tested)",
                goods_id="33960",
            )
        return None


class _FakeMetaResolver:
    def resolve(self, market_hash_name):
        from app.services.trade_up_input_enrichment import TradeUpInputMetadata

        if market_hash_name == "AK-47 | Redline (Field-Tested)":
            return TradeUpInputMetadata(
                market_hash_name=market_hash_name,
                collection_name="The Phoenix Collection",
                rarity="Classified",
                min_float=0.1,
                max_float=0.7,
            )
        return None


@dataclass
class _FakeSteamDTBatchTransport:
    """In-memory fake for the SteamDT batch transport."""

    quotes: dict[str, tuple[Decimal, int | None, str | None]]
    requested_calls: int = 0

    async def get_price_batch_with_selection(
        self, names, *, selection_config=None, avg_prices_by_name=None
    ):
        from app.services.steamdt_batch_prescreen import (
            SteamDTBatchPricePlatformQuote,
            SteamDTBatchPriceResult,
        )
        self.requested_calls += 1
        platforms: list = []
        for name in names:
            if name not in self.quotes:
                continue
            sell, sell_count, update_time = self.quotes[name]
            quote = SteamDTBatchPricePlatformQuote(
                market_hash_name=name,
                platform="buff",
                sell_price_cny=sell,
                sell_count=sell_count,
                update_time=update_time,
            )
            platforms.append(quote)
        return SteamDTBatchPriceResult(
            market_hash_names=list(names),
            platform_quotes=tuple(platforms),
            raw={"data": [{"marketHashName": name} for name in names]},
        )


@dataclass
class _FakeSteamDTSingle:
    quote: PriceQuote | None = None
    calls: list[str] = None

    async def fetch_single(self, name: str) -> PriceQuote:

        if self.calls is None:
            self.calls = []
        self.calls.append(name)
        if self.quote is None:
            self.quote = PriceQuote(
                market_hash_name=name,
                price_cny=Decimal("100"),
                source="steamdt:buff",
                raw=None,
            )
        return self.quote


def test_runner_construction_rejects_invalid_case() -> None:
    with pytest.raises(RecipeFirstSteamDTCaseError):
        RecipeFirstSteamDTLiveRunner(
            case="not-a-case",  # type: ignore[arg-type]
            buff_identity_resolver=_FakeBuffResolver(),
            metadata_resolver=_FakeMetaResolver(),
        )


def test_runner_construction_rejects_invalid_pacing() -> None:
    with pytest.raises(RecipeFirstSteamDTCaseError, match="pacing"):
        RecipeFirstSteamDTLiveRunner(
            case=_phase16g_case(),
            buff_identity_resolver=_FakeBuffResolver(),
            metadata_resolver=_FakeMetaResolver(),
            config=RecipeFirstSteamDTLiveRunnerConfig(
                api_key="k",
                pacing_seconds=-1.0,
            ),
        )


def test_runner_blocks_when_api_key_missing() -> None:
    runner = RecipeFirstSteamDTLiveRunner(
        case=_phase16g_case(),
        buff_identity_resolver=_FakeBuffResolver(),
        metadata_resolver=_FakeMetaResolver(),
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key=None),
    )
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_BLOCKED
    assert result.request_state.buff_dispatched == 0
    assert result.request_state.steamdt_batch_dispatched == 0
    assert result.request_state.steamdt_single_dispatched == 0


def test_runner_blocks_when_live_unauthorized() -> None:
    runner = RecipeFirstSteamDTLiveRunner(
        case=_phase16g_case(),
        buff_identity_resolver=_FakeBuffResolver(),
        metadata_resolver=_FakeMetaResolver(),
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key="k"),
    )
    result = asyncio.run(runner.run(live_validation_authorized=False))
    assert result.classification == CLASSIFICATION_BLOCKED


def test_runner_classifies_inconclusive_when_prescreen_missing_name() -> None:
    runner = RecipeFirstSteamDTLiveRunner(
        case=_phase16g_case(
            prescreen_names=(
                "AK-47 | Redline (Field-Tested)",
                "AK-47 | Redline (Minimal Wear)",
            )
        ),
        buff_identity_resolver=_FakeBuffResolver(),
        metadata_resolver=_FakeMetaResolver(),
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key="k"),
    )
    runner._steamdt_http_client = object()  # placeholder; won't be used
    runner._run_prescreen = lambda: _raise_async(NotImplementedError("replaced"))

    async def _fake_prescreen() -> object:
        from app.services.steamdt_batch_prescreen import (
            SteamDTBatchPreScreenDiagnostics,
            SteamDTBatchPreScreenResult,
            SteamDTBuffPreScreenQuote,
        )

        return SteamDTBatchPreScreenResult(
            requested_market_hash_names=("AK-47 | Redline (Field-Tested)",),
            quotes=(
                SteamDTBuffPreScreenQuote(
                    market_hash_name="AK-47 | Redline (Field-Tested)",
                    sell_price_cny=Decimal("10"),
                    sell_count=1,
                    update_time="opaque",
                ),
            ),
            missing_market_hash_names=("AK-47 | Redline (Minimal Wear)",),
            terminal_selection_failures=(),
            diagnostics=SteamDTBatchPreScreenDiagnostics(
                logical_requested_names=2,
                unique_names=2,
                duplicates_suppressed=0,
                chunk_count=1,
                transport_attempted_names=2,
                selected_names=1,
                missing_names=1,
                terminal_selection_failures=0,
                transport_errors=(),
            ),
        )

    runner._run_prescreen = _fake_prescreen  # type: ignore[assignment]
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_INCONCLUSIVE
    assert result.prescreen_missing_names == ("AK-47 | Redline (Minimal Wear)",)


def test_runner_classifies_contract_failure_on_prescreen_transport_error() -> None:
    runner = RecipeFirstSteamDTLiveRunner(
        case=_phase16g_case(),
        buff_identity_resolver=_FakeBuffResolver(),
        metadata_resolver=_FakeMetaResolver(),
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key="k"),
    )

    async def _fake_prescreen() -> object:
        raise RuntimeError("transport exploded")

    runner._run_prescreen = _fake_prescreen  # type: ignore[assignment]
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_CONTRACT_FAILURE


def test_runner_classifies_validated_when_all_stages_pass() -> None:
    runner = RecipeFirstSteamDTLiveRunner(
        case=_phase16g_case(
            prescreen_names=(
                "AK-47 | Redline (Field-Tested)",
                "AK-47 | Redline (Minimal Wear)",
            )
        ),
        buff_identity_resolver=_FakeBuffResolver(),
        metadata_resolver=_FakeMetaResolver(),
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key="k"),
    )

    async def _fake_prescreen() -> object:
        from app.services.steamdt_batch_prescreen import (
            SteamDTBatchPreScreenDiagnostics,
            SteamDTBatchPreScreenResult,
            SteamDTBuffPreScreenQuote,
        )

        return SteamDTBatchPreScreenResult(
            requested_market_hash_names=(
                "AK-47 | Redline (Field-Tested)",
                "AK-47 | Redline (Minimal Wear)",
            ),
            quotes=tuple(
                SteamDTBuffPreScreenQuote(
                    market_hash_name=name,
                    sell_price_cny=Decimal("10"),
                    sell_count=1,
                    update_time="opaque",
                )
                for name in (
                    "AK-47 | Redline (Field-Tested)",
                    "AK-47 | Redline (Minimal Wear)",
                )
            ),
            missing_market_hash_names=(),
            terminal_selection_failures=(),
            diagnostics=SteamDTBatchPreScreenDiagnostics(
                logical_requested_names=2,
                unique_names=2,
                duplicates_suppressed=0,
                chunk_count=1,
                transport_attempted_names=2,
                selected_names=2,
                missing_names=0,
                terminal_selection_failures=0,
                transport_errors=(),
            ),
        )

    async def _fake_buff_page():
        from app.services.recipe_first_steamdt_live_runner import LiveSteamDTPageResult

        return (
            LiveSteamDTPageResult(
                goods_id="33960",
                market_hash_name="AK-47 | Redline (Field-Tested)",
                request_status=RUN_STATUS_DISPATCHED,
                listing_count=10,
                candidate_accepted=10,
                metadata_resolved=10,
                family_compatible=10,
                family_incompatible=0,
            ),
            10,
            0,
        )

    async def _fake_final():
        lookup = PriceLookupResult(
            quotes={
                "AK-47 | Redline (Minimal Wear)": PriceQuote(
                    market_hash_name="AK-47 | Redline (Minimal Wear)",
                    price_cny=Decimal("20"),
                    source="steamdt:buff",
                    raw=None,
                )
            },
            missing=[],
            errors=[],
        )
        return lookup, ["AK-47 | Redline (Minimal Wear)"]

    runner._run_prescreen = _fake_prescreen  # type: ignore[assignment]
    runner._acquire_buff_page = _fake_buff_page  # type: ignore[assignment]
    runner._run_final_valuation = _fake_final  # type: ignore[assignment]
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_VALIDATED
    assert result.family_compatible_enriched_inputs == 10
    assert len(result.final_quotes) == 1
    assert result.final_new_live_names == ("AK-47 | Redline (Minimal Wear)",)


def test_runner_classifies_inconclusive_when_final_missing() -> None:
    runner = RecipeFirstSteamDTLiveRunner(
        case=_phase16g_case(
            prescreen_names=(
                "AK-47 | Redline (Field-Tested)",
                "AK-47 | Redline (Minimal Wear)",
            )
        ),
        buff_identity_resolver=_FakeBuffResolver(),
        metadata_resolver=_FakeMetaResolver(),
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key="k"),
    )

    async def _fake_prescreen() -> object:
        from app.services.steamdt_batch_prescreen import (
            SteamDTBatchPreScreenDiagnostics,
            SteamDTBatchPreScreenResult,
            SteamDTBuffPreScreenQuote,
        )

        return SteamDTBatchPreScreenResult(
            requested_market_hash_names=(
                "AK-47 | Redline (Field-Tested)",
                "AK-47 | Redline (Minimal Wear)",
            ),
            quotes=tuple(
                SteamDTBuffPreScreenQuote(
                    market_hash_name=name,
                    sell_price_cny=Decimal("10"),
                    sell_count=1,
                    update_time="opaque",
                )
                for name in (
                    "AK-47 | Redline (Field-Tested)",
                    "AK-47 | Redline (Minimal Wear)",
                )
            ),
            missing_market_hash_names=(),
            terminal_selection_failures=(),
            diagnostics=SteamDTBatchPreScreenDiagnostics(
                logical_requested_names=2,
                unique_names=2,
                duplicates_suppressed=0,
                chunk_count=1,
                transport_attempted_names=2,
                selected_names=2,
                missing_names=0,
                terminal_selection_failures=0,
                transport_errors=(),
            ),
        )

    async def _fake_buff_page():
        from app.services.recipe_first_steamdt_live_runner import LiveSteamDTPageResult

        return (
            LiveSteamDTPageResult(
                goods_id="33960",
                market_hash_name="AK-47 | Redline (Field-Tested)",
                request_status=RUN_STATUS_DISPATCHED,
                listing_count=10,
                candidate_accepted=10,
                metadata_resolved=10,
                family_compatible=10,
                family_incompatible=0,
            ),
            10,
            0,
        )

    async def _fake_final():
        return (
            PriceLookupResult(quotes={}, missing=["Missing"], errors=[]),
            ["AK-47 | Redline (Minimal Wear)"],
        )

    runner._run_prescreen = _fake_prescreen  # type: ignore[assignment]
    runner._acquire_buff_page = _fake_buff_page  # type: ignore[assignment]
    runner._run_final_valuation = _fake_final  # type: ignore[assignment]
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_INCONCLUSIVE


def test_runner_classifies_inconclusive_when_compatible_below_ten() -> None:
    runner = RecipeFirstSteamDTLiveRunner(
        case=_phase16g_case(
            prescreen_names=(
                "AK-47 | Redline (Field-Tested)",
                "AK-47 | Redline (Minimal Wear)",
            )
        ),
        buff_identity_resolver=_FakeBuffResolver(),
        metadata_resolver=_FakeMetaResolver(),
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key="k"),
    )

    async def _fake_prescreen() -> object:
        from app.services.steamdt_batch_prescreen import (
            SteamDTBatchPreScreenDiagnostics,
            SteamDTBatchPreScreenResult,
            SteamDTBuffPreScreenQuote,
        )

        return SteamDTBatchPreScreenResult(
            requested_market_hash_names=(
                "AK-47 | Redline (Field-Tested)",
                "AK-47 | Redline (Minimal Wear)",
            ),
            quotes=tuple(
                SteamDTBuffPreScreenQuote(
                    market_hash_name=name,
                    sell_price_cny=Decimal("10"),
                    sell_count=1,
                    update_time="opaque",
                )
                for name in (
                    "AK-47 | Redline (Field-Tested)",
                    "AK-47 | Redline (Minimal Wear)",
                )
            ),
            missing_market_hash_names=(),
            terminal_selection_failures=(),
            diagnostics=SteamDTBatchPreScreenDiagnostics(
                logical_requested_names=2,
                unique_names=2,
                duplicates_suppressed=0,
                chunk_count=1,
                transport_attempted_names=2,
                selected_names=2,
                missing_names=0,
                terminal_selection_failures=0,
                transport_errors=(),
            ),
        )

    async def _fake_buff_page():
        from app.services.recipe_first_steamdt_live_runner import LiveSteamDTPageResult

        return (
            LiveSteamDTPageResult(
                goods_id="33960",
                market_hash_name="AK-47 | Redline (Field-Tested)",
                request_status=RUN_STATUS_DISPATCHED,
                listing_count=3,
                candidate_accepted=3,
                metadata_resolved=3,
                family_compatible=3,
                family_incompatible=0,
            ),
            3,
            0,
        )

    runner._run_prescreen = _fake_prescreen  # type: ignore[assignment]
    runner._acquire_buff_page = _fake_buff_page  # type: ignore[assignment]
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_INCONCLUSIVE
    assert result.family_compatible_enriched_inputs == 3


def test_runner_classifies_contract_failure_on_family_incompatible() -> None:
    runner = RecipeFirstSteamDTLiveRunner(
        case=_phase16g_case(
            prescreen_names=(
                "AK-47 | Redline (Field-Tested)",
                "AK-47 | Redline (Minimal Wear)",
            )
        ),
        buff_identity_resolver=_FakeBuffResolver(),
        metadata_resolver=_FakeMetaResolver(),
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key="k"),
    )

    async def _fake_prescreen() -> object:
        from app.services.steamdt_batch_prescreen import (
            SteamDTBatchPreScreenDiagnostics,
            SteamDTBatchPreScreenResult,
            SteamDTBuffPreScreenQuote,
        )

        return SteamDTBatchPreScreenResult(
            requested_market_hash_names=(
                "AK-47 | Redline (Field-Tested)",
                "AK-47 | Redline (Minimal Wear)",
            ),
            quotes=tuple(
                SteamDTBuffPreScreenQuote(
                    market_hash_name=name,
                    sell_price_cny=Decimal("10"),
                    sell_count=1,
                    update_time="opaque",
                )
                for name in (
                    "AK-47 | Redline (Field-Tested)",
                    "AK-47 | Redline (Minimal Wear)",
                )
            ),
            missing_market_hash_names=(),
            terminal_selection_failures=(),
            diagnostics=SteamDTBatchPreScreenDiagnostics(
                logical_requested_names=2,
                unique_names=2,
                duplicates_suppressed=0,
                chunk_count=1,
                transport_attempted_names=2,
                selected_names=2,
                missing_names=0,
                terminal_selection_failures=0,
                transport_errors=(),
            ),
        )

    async def _fake_buff_page():
        from app.services.recipe_first_steamdt_live_runner import LiveSteamDTPageResult

        return (
            LiveSteamDTPageResult(
                goods_id="33960",
                market_hash_name="AK-47 | Redline (Field-Tested)",
                request_status=RUN_STATUS_DISPATCHED,
                listing_count=10,
                candidate_accepted=10,
                metadata_resolved=10,
                family_compatible=9,
                family_incompatible=1,
            ),
            9,
            1,
        )

    runner._run_prescreen = _fake_prescreen  # type: ignore[assignment]
    runner._acquire_buff_page = _fake_buff_page  # type: ignore[assignment]
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_CONTRACT_FAILURE


def test_runner_steamdt_counters_initialize_to_zero() -> None:
    runner = RecipeFirstSteamDTLiveRunner(
        case=_phase16g_case(),
        buff_identity_resolver=_FakeBuffResolver(),
        metadata_resolver=_FakeMetaResolver(),
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key="k"),
    )
    assert runner.request_state.steamdt_batch_attempted == 0
    assert runner.request_state.steamdt_batch_dispatched == 0
    assert runner.request_state.steamdt_single_attempted == 0
    assert runner.request_state.steamdt_single_dispatched == 0


def test_runner_result_excludes_raw_payload() -> None:
    runner = RecipeFirstSteamDTLiveRunner(
        case=_phase16g_case(),
        buff_identity_resolver=_FakeBuffResolver(),
        metadata_resolver=_FakeMetaResolver(),
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key="k"),
    )
    result = asyncio.run(runner.run(live_validation_authorized=False))
    rendered = repr(result).encode("utf-8")
    for forbidden in (
        b"listing_id=",
        b"asset_id=",
        b"paintwear=",
        b"price_cny=Decimal",
        b"seller=",
        b"api_key=",
    ):
        assert forbidden not in rendered, f"forbidden token {forbidden!r} leaked"


def test_runner_aclose_is_idempotent() -> None:
    runner = RecipeFirstSteamDTLiveRunner(
        case=_phase16g_case(),
        buff_identity_resolver=_FakeBuffResolver(),
        metadata_resolver=_FakeMetaResolver(),
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key="k"),
    )
    asyncio.run(runner.aclose())
    asyncio.run(runner.aclose())
    assert runner._owns_steamdt_http is True


async def _raise_async(exc):
    raise exc


def test_runner_blocks_when_buff_schema_mismatches() -> None:
    """Frozen-case guard: the runner refuses an R1 / R2 v1 case payload.

    The case DTO enforces `buff_case.case_schema_version == LIVE_CASE_SCHEMA_VERSION`
    at construction time, so the runner's runtime check is a belt-and-braces
    safety net for cases loaded from disk that bypass the constructor.
    """

    case = _phase16g_case()
    object.__setattr__(
        case.buff_case,
        "case_schema_version",
        999,
    )
    runner = RecipeFirstSteamDTLiveRunner(
        case=case,
        buff_identity_resolver=_FakeBuffResolver(),
        metadata_resolver=_FakeMetaResolver(),
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key="k"),
    )
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_BLOCKED