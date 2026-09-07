"""Phase 16G-R6 — Offline regression coverage for the repaired live harness.

All external market seams are in-memory. The tests exercise the real pinned
family/geometry authorities, normalized acquisition pipeline, Phase16E
``search_family_constrained_recipes``, ``RunScopedValuationSession``, and
``ValuationService`` path without any network request.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.buff_intrinsic_flag_resolver import (
    CanonicalNameIntrinsicFlagResolver,
)
from app.services.buff_item_identity import BuffItemIdentity
from app.services.buff_listing_provider import BuffListing
from app.services.market_universe_builder import StatTrakMode
from app.services.price_provider import PriceQuote
from app.services.recipe_family import RecipeFamily, build_recipe_family
from app.services.recipe_family_geometry import (
    RecipeFamilyGeometry,
    compute_recipe_family_geometry,
)
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
    LIVE_STEAMDT_RESULT_SCHEMA_VERSION,
    RecipeFirstSteamDTLiveRunner,
    RecipeFirstSteamDTLiveRunnerConfig,
    _LiveSinglePriceProvider,
)
from app.services.recipe_solver import RecipeEnumerationConfig, RecipeSolverConfig
from app.services.static_float_feasibility import (
    StaticFloatFeasibilityStatus,
    compute_static_float_feasibility,
)
from app.services.steamdt_batch_prescreen import (
    SteamDTBatchPreScreenDiagnostics,
    SteamDTBatchPreScreenResult,
    SteamDTBuffPreScreenQuote,
)
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.trade_up_input_enrichment import TradeUpInputMetadata

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_FAMILY_HASH = (
    "45bfd0f0d3e7405588acdcf742d980577eed4963382c2fde31632fc43db52516"
)
EXPECTED_FAMILY_KEY = "45bfd0f0d3e7405588acdcf7"
TARGET_NAME = "AK-47 | Redline (Field-Tested)"
TARGET_GOODS_ID = "33960"
COLLECTION = "The Phoenix Collection"
INPUT_RARITY = "Classified"
PRESCREEN_NAMES = (
    TARGET_NAME,
    "AUG | Chameleon (Factory New)",
    "AUG | Chameleon (Minimal Wear)",
    "AUG | Chameleon (Field-Tested)",
    "AUG | Chameleon (Well-Worn)",
    "AUG | Chameleon (Battle-Scarred)",
    "AWP | Asiimov (Field-Tested)",
    "AWP | Asiimov (Well-Worn)",
    "AWP | Asiimov (Battle-Scarred)",
)


def _load_skins() -> tuple:
    from app.services.metadata_models import SkinMetadata

    payload = json.loads(
        (ROOT / "data" / "metadata" / "skin_metadata_v1.json").read_bytes()
    )
    return tuple(
        SkinMetadata(
            market_hash_name=item["market_hash_name"],
            name=item.get("name"),
            weapon=item.get("weapon"),
            rarity=item["rarity"],
            category=item.get("category"),
            collection_name=item.get("collection_name"),
            min_float=item["min_float"],
            max_float=item["max_float"],
            stattrak=bool(item.get("stattrak", False)),
            souvenir=bool(item.get("souvenir", False)),
            paint_index=item.get("paint_index"),
            raw=None,
        )
        for item in payload["items"]
    )


@dataclass(frozen=True, kw_only=True)
class _Authorities:
    family: RecipeFamily
    geometry: RecipeFamilyGeometry
    finish_index: StructuralOutputFinishIndex
    solver_config: RecipeSolverConfig
    enumeration_config: RecipeEnumerationConfig


def _authorities() -> _Authorities:
    family = build_recipe_family(
        input_rarity=INPUT_RARITY,
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=((COLLECTION, 10),),
    )
    finish_index = StructuralOutputFinishIndex.from_skins(_load_skins())
    geometry = compute_recipe_family_geometry(family, finish_index=finish_index)
    assert family.family_hash == EXPECTED_FAMILY_HASH
    assert family.family_key == EXPECTED_FAMILY_KEY
    assert geometry.family_hash == EXPECTED_FAMILY_HASH
    return _Authorities(
        family=family,
        geometry=geometry,
        finish_index=finish_index,
        solver_config=RecipeSolverConfig(
            input_rarity=INPUT_RARITY,
            sell_fee_rate=Decimal("0"),
            target_stattrak=False,
        ),
        enumeration_config=RecipeEnumerationConfig(
            max_recipe_candidates_returned=1,
            max_candidate_states_explored=256,
        ),
    )


def _case(*, prescreen_names: tuple[str, ...] = PRESCREEN_NAMES) -> RecipeFirstSteamDTCase:
    buff_case = freeze_case(
        repository_commit_oid="f" * 40,
        case_purpose="Phase16G-R6 offline test",
        family_hash=EXPECTED_FAMILY_HASH,
        family_key=EXPECTED_FAMILY_KEY,
        input_rarity=INPUT_RARITY,
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=((COLLECTION, 10),),
        plan_items=(
            LiveValidationPlanItem(
                market_hash_name=TARGET_NAME,
                goods_id=TARGET_GOODS_ID,
                collection_name=COLLECTION,
                priority_within_collection=1,
            ),
        ),
    )
    return freeze_recipe_first_steamdt_case(
        repository_commit_oid="f" * 40,
        buff_case=buff_case,
        prescreen_market_hash_names=prescreen_names,
    )


class _IdentityResolver:
    async def resolve_goods_id(self, goods_id: str):
        if goods_id != TARGET_GOODS_ID:
            return None
        return BuffItemIdentity(
            market_hash_name=TARGET_NAME,
            goods_id=TARGET_GOODS_ID,
        )


class _MetadataResolver:
    def resolve(self, market_hash_name: str):
        if market_hash_name != TARGET_NAME:
            return None
        return TradeUpInputMetadata(
            market_hash_name=TARGET_NAME,
            collection_name=COLLECTION,
            rarity=INPUT_RARITY,
            min_float=0.1,
            max_float=0.7,
        )


@dataclass
class _ListingProvider:
    listing_count: int = 10
    calls: int = 0

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        self.calls += 1
        assert goods_id == TARGET_GOODS_ID
        return [
            BuffListing(
                listing_id=f"listing-{index:02d}",
                goods_id=TARGET_GOODS_ID,
                market_hash_name=None,
                price_cny=Decimal("186"),
                paintwear=Decimal("0.10") + Decimal(index) * Decimal("0.06"),
                asset_id=f"asset-{index:02d}",
                paintseed=index,
            )
            for index in range(self.listing_count)
        ]


async def _full_prescreen(names: tuple[str, ...]) -> SteamDTBatchPreScreenResult:
    return _prescreen_result(requested=names, selected=names)


def _prescreen_result(
    *,
    requested: tuple[str, ...],
    selected: tuple[str, ...],
) -> SteamDTBatchPreScreenResult:
    selected_set = set(selected)
    missing = tuple(name for name in requested if name not in selected_set)
    return SteamDTBatchPreScreenResult(
        requested_market_hash_names=requested,
        quotes=tuple(
            SteamDTBuffPreScreenQuote(
                market_hash_name=name,
                sell_price_cny=Decimal("100"),
                sell_count=1,
                update_time="opaque",
            )
            for name in selected
        ),
        missing_market_hash_names=missing,
        terminal_selection_failures=(),
        diagnostics=SteamDTBatchPreScreenDiagnostics(
            logical_requested_names=len(requested),
            unique_names=len(requested),
            duplicates_suppressed=0,
            chunk_count=1,
            transport_attempted_names=len(requested),
            selected_names=len(selected),
            missing_names=len(missing),
            terminal_selection_failures=0,
            transport_errors=(),
        ),
    )


def _runner(
    *,
    case: RecipeFirstSteamDTCase | None = None,
    listing_count: int = 10,
    batch_provider=_full_prescreen,
    single_fetcher=None,
) -> tuple[RecipeFirstSteamDTLiveRunner, _ListingProvider, list[str]]:
    auth = _authorities()
    listing_provider = _ListingProvider(listing_count=listing_count)
    single_calls: list[str] = []

    async def default_single(name: str) -> PriceQuote:
        single_calls.append(name)
        return PriceQuote(
            market_hash_name=name,
            price_cny=Decimal("700"),
            source="steamdt:buff",
            raw=None,
        )

    runner = RecipeFirstSteamDTLiveRunner(
        case=case or _case(),
        buff_identity_resolver=_IdentityResolver(),
        metadata_resolver=_MetadataResolver(),
        intrinsic_resolver=CanonicalNameIntrinsicFlagResolver(),
        family=auth.family,
        geometry=auth.geometry,
        finish_index=auth.finish_index,
        solver_config=auth.solver_config,
        enumeration_config=auth.enumeration_config,
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key="offline-test-key"),
        batch_result_provider=batch_provider,
        buff_listing_provider=listing_provider,
        single_price_fetcher=single_fetcher or default_single,
    )
    return runner, listing_provider, single_calls


def test_constructor_rejects_invalid_case_and_exact_enumeration_bounds() -> None:
    auth = _authorities()
    common = {
        "buff_identity_resolver": _IdentityResolver(),
        "metadata_resolver": _MetadataResolver(),
        "family": auth.family,
        "geometry": auth.geometry,
        "finish_index": auth.finish_index,
        "solver_config": auth.solver_config,
        "config": RecipeFirstSteamDTLiveRunnerConfig(api_key="offline-test-key"),
    }
    with pytest.raises(RecipeFirstSteamDTCaseError, match="case"):
        RecipeFirstSteamDTLiveRunner(
            case="bad",  # type: ignore[arg-type]
            enumeration_config=auth.enumeration_config,
            **common,  # type: ignore[arg-type]
        )
    with pytest.raises(RecipeFirstSteamDTCaseError, match="bound"):
        RecipeFirstSteamDTLiveRunner(
            case=_case(),
            enumeration_config=RecipeEnumerationConfig(
                max_recipe_candidates_returned=2,
                max_candidate_states_explored=256,
            ),
            **common,  # type: ignore[arg-type]
        )
    with pytest.raises(RecipeFirstSteamDTCaseError, match="bound"):
        RecipeFirstSteamDTLiveRunner(
            case=_case(),
            enumeration_config=RecipeEnumerationConfig(
                max_recipe_candidates_returned=1,
                max_candidate_states_explored=255,
            ),
            **common,  # type: ignore[arg-type]
        )


def test_constructor_rejects_family_identity_and_solver_mode_mismatch() -> None:
    auth = _authorities()
    wrong_family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=((COLLECTION, 10),),
    )
    with pytest.raises(RecipeFirstSteamDTCaseError, match="family identity"):
        RecipeFirstSteamDTLiveRunner(
            case=_case(),
            buff_identity_resolver=_IdentityResolver(),
            metadata_resolver=_MetadataResolver(),
            family=wrong_family,
            geometry=auth.geometry,
            finish_index=auth.finish_index,
            solver_config=auth.solver_config,
            enumeration_config=auth.enumeration_config,
        )
    with pytest.raises(RecipeFirstSteamDTCaseError, match="StatTrak"):
        RecipeFirstSteamDTLiveRunner(
            case=_case(),
            buff_identity_resolver=_IdentityResolver(),
            metadata_resolver=_MetadataResolver(),
            family=auth.family,
            geometry=auth.geometry,
            finish_index=auth.finish_index,
            solver_config=RecipeSolverConfig(
                input_rarity=INPUT_RARITY,
                target_stattrak=True,
            ),
            enumeration_config=auth.enumeration_config,
        )


def test_runner_blocks_without_key_or_authorization_with_zero_dispatch() -> None:
    auth = _authorities()
    no_key = RecipeFirstSteamDTLiveRunner(
        case=_case(),
        buff_identity_resolver=_IdentityResolver(),
        metadata_resolver=_MetadataResolver(),
        family=auth.family,
        geometry=auth.geometry,
        finish_index=auth.finish_index,
        solver_config=auth.solver_config,
        enumeration_config=auth.enumeration_config,
        config=RecipeFirstSteamDTLiveRunnerConfig(api_key=None),
    )
    result = asyncio.run(no_key.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_BLOCKED
    assert result.request_state.steamdt_batch_dispatched == 0
    assert result.request_state.buff_dispatched == 0
    assert result.request_state.steamdt_single_dispatched == 0

    unauthorized, _, _ = _runner()
    result = asyncio.run(
        unauthorized.run(live_validation_authorized=False)
    )
    assert result.classification == CLASSIFICATION_BLOCKED
    assert result.request_state.steamdt_batch_dispatched == 0


def test_validated_runs_real_concrete_search_and_session_valuation() -> None:
    runner, listing_provider, single_calls = _runner()
    result = asyncio.run(runner.run(live_validation_authorized=True))

    assert result.classification == CLASSIFICATION_VALIDATED
    assert listing_provider.calls == 1
    assert result.family_compatible_enriched_inputs == 10
    assert result.family_incompatible_enriched_inputs == 0
    assert result.concrete_selection_count == 1
    assert result.concrete_search_diagnostics is not None
    assert result.concrete_search_diagnostics.family_hash == EXPECTED_FAMILY_HASH
    assert result.concrete_search_diagnostics.states_explored == 1
    assert result.concrete_search_diagnostics.unique_candidates_returned == 1
    assert 1 <= len(result.concrete_output_market_hash_names) <= 2
    assert result.final_new_live_names == result.concrete_output_market_hash_names
    assert tuple(single_calls) == result.concrete_output_market_hash_names
    assert tuple(q.market_hash_name for q in result.final_quotes) == (
        result.concrete_output_market_hash_names
    )
    assert all(q.source == "steamdt:buff" for q in result.final_quotes)
    assert result.structural_fields_preserved is True
    assert result.structural_mismatch_reason is None
    assert len(result.concrete_tradeup_results) == len(
        result.valued_tradeup_results
    )
    for before, after in zip(
        result.concrete_tradeup_results,
        result.valued_tradeup_results,
        strict=True,
    ):
        assert before.output_market_hash_name == after.output_market_hash_name
        assert before.probability == after.probability
        assert before.output_float == after.output_float
        assert before.output_wear == after.output_wear
        assert before.estimated_price_cny == Decimal("0")
        assert after.estimated_price_cny == Decimal("700")
        assert after.expected_value_contribution > 0
    assert result.request_state.steamdt_batch_dispatched == 1
    assert result.request_state.buff_dispatched == 1
    assert result.request_state.steamdt_single_dispatched == len(single_calls)
    assert result.schema_version == LIVE_STEAMDT_RESULT_SCHEMA_VERSION
    assert (
        result.buff_http_cap,
        result.steamdt_batch_http_cap,
        result.steamdt_final_single_http_cap,
        result.steamdt_total_http_cap,
    ) == (1, 1, 2, 3)


def test_concrete_output_missing_from_successful_prescreen_is_inconclusive() -> None:
    omitted = "AWP | Asiimov (Battle-Scarred)"

    async def malformed_success(
        names: tuple[str, ...],
    ) -> SteamDTBatchPreScreenResult:
        selected = tuple(name for name in names if name != omitted)
        result = _prescreen_result(requested=names, selected=selected)
        return SteamDTBatchPreScreenResult(
            requested_market_hash_names=result.requested_market_hash_names,
            quotes=result.quotes,
            missing_market_hash_names=result.missing_market_hash_names,
            terminal_selection_failures=result.terminal_selection_failures,
            diagnostics=result.diagnostics,
        )

    runner, _, single_calls = _runner(batch_provider=malformed_success)
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_INCONCLUSIVE
    assert omitted in result.prescreen_missing_names
    assert single_calls == []
    assert result.request_state.steamdt_single_attempted == 0


def test_legitimate_insufficient_inputs_yield_no_selection_and_zero_singles() -> None:
    runner, _, single_calls = _runner(listing_count=9)
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_INCONCLUSIVE
    assert result.family_compatible_enriched_inputs == 9
    assert result.concrete_selection_count == 0
    assert single_calls == []
    assert result.request_state.steamdt_single_attempted == 0


def test_single_failure_shape_is_normalized_and_run_is_inconclusive() -> None:
    calls: list[str] = []

    async def one_failure(name: str) -> PriceQuote:
        calls.append(name)
        if len(calls) == 1:
            raise RuntimeError("untrusted provider detail")
        return PriceQuote(
            market_hash_name=name,
            price_cny=Decimal("700"),
            source="steamdt:buff",
            raw=None,
        )

    runner, _, _ = _runner(single_fetcher=one_failure)
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_INCONCLUSIVE
    assert len(result.final_missing_names) == 1
    assert result.final_missing_names[0] == result.concrete_output_market_hash_names[0]
    assert result.final_errors == (
        "LIVE_LOOKUP_TERMINAL_FAILURE: item_index=0",
    )
    assert result.request_state.steamdt_single_attempted == 2
    assert result.request_state.steamdt_single_dispatched == 2
    assert runner._steamdt_single_successes == 1
    assert "untrusted provider detail" not in repr(result)


def test_batch_failure_consumes_dispatch_started_counter() -> None:
    async def fail(_names: tuple[str, ...]) -> SteamDTBatchPreScreenResult:
        raise RuntimeError("offline fake failure")

    runner, _, _ = _runner(batch_provider=fail)
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_CONTRACT_FAILURE
    assert result.request_state.steamdt_batch_attempted == 1
    assert result.request_state.steamdt_batch_dispatched == 1
    assert result.request_state.steamdt_single_dispatched == 0
    assert result.request_state.buff_dispatched == 0
    assert runner._steamdt_batch_successes == 0


def test_single_first_call_failure_consumes_dispatch_started_counter() -> None:
    calls: list[str] = []

    async def one_failure(name: str) -> PriceQuote:
        calls.append(name)
        if len(calls) == 1:
            raise RuntimeError("untrusted provider detail")
        return PriceQuote(
            market_hash_name=name,
            price_cny=Decimal("700"),
            source="steamdt:buff",
            raw=None,
        )

    runner, _, _ = _runner(single_fetcher=one_failure)
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_INCONCLUSIVE
    assert result.request_state.steamdt_single_attempted == 2
    assert result.request_state.steamdt_single_dispatched == 2
    assert runner._steamdt_single_successes == 1
    assert len(result.final_missing_names) == 1
    assert result.final_missing_names[0] == result.concrete_output_market_hash_names[0]


def test_single_identity_mismatch_consumes_dispatch_started_counter() -> None:
    async def mismatch(name: str) -> PriceQuote:
        return PriceQuote(
            market_hash_name=f"WRONG::{name}",
            price_cny=Decimal("700"),
            source="steamdt:buff",
            raw=None,
        )

    runner, _, _ = _runner(single_fetcher=mismatch)
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_INCONCLUSIVE
    assert result.request_state.steamdt_single_dispatched == len(
        result.concrete_output_market_hash_names
    )
    assert runner._steamdt_single_successes == 0
    assert result.final_quotes == ()


def test_prescreen_silent_omission_blocks_buff_with_zero_dispatch() -> None:
    omitted = "AWP | Asiimov (Battle-Scarred)"

    async def silent_omission(
        names: tuple[str, ...],
    ) -> SteamDTBatchPreScreenResult:
        selected = tuple(name for name in names if name != omitted)
        return SteamDTBatchPreScreenResult(
            requested_market_hash_names=names,
            quotes=tuple(
                SteamDTBuffPreScreenQuote(
                    market_hash_name=name,
                    sell_price_cny=Decimal("100"),
                    sell_count=1,
                    update_time="opaque",
                )
                for name in selected
            ),
            missing_market_hash_names=(),
            terminal_selection_failures=(),
            diagnostics=SteamDTBatchPreScreenDiagnostics(
                logical_requested_names=len(names),
                unique_names=len(names),
                duplicates_suppressed=0,
                chunk_count=1,
                transport_attempted_names=len(names),
                selected_names=len(selected),
                missing_names=0,
                terminal_selection_failures=0,
                transport_errors=(),
            ),
        )

    runner, listing_provider, _ = _runner(batch_provider=silent_omission)
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_CONTRACT_FAILURE
    assert result.request_state.buff_dispatched == 0
    assert result.request_state.steamdt_single_dispatched == 0
    assert listing_provider.calls == 0


def test_prescreen_duplicate_overlap_blocks_buff_with_zero_dispatch() -> None:
    async def overlap(
        names: tuple[str, ...],
    ) -> SteamDTBatchPreScreenResult:
        first = names[0]
        return SteamDTBatchPreScreenResult(
            requested_market_hash_names=names,
            quotes=(
                SteamDTBuffPreScreenQuote(
                    market_hash_name=first,
                    sell_price_cny=Decimal("100"),
                    sell_count=1,
                    update_time="opaque",
                ),
            ),
            missing_market_hash_names=names,
            terminal_selection_failures=(),
            diagnostics=SteamDTBatchPreScreenDiagnostics(
                logical_requested_names=len(names),
                unique_names=len(names),
                duplicates_suppressed=0,
                chunk_count=1,
                transport_attempted_names=len(names),
                selected_names=1,
                missing_names=len(names),
                terminal_selection_failures=0,
                transport_errors=(),
            ),
        )

    runner, listing_provider, _ = _runner(batch_provider=overlap)
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_CONTRACT_FAILURE
    assert result.request_state.buff_dispatched == 0
    assert listing_provider.calls == 0


def test_prescreen_complete_missing_partition_is_inconclusive_with_zero_buff() -> None:
    async def missing_partition(
        names: tuple[str, ...],
    ) -> SteamDTBatchPreScreenResult:
        first = names[0]
        return SteamDTBatchPreScreenResult(
            requested_market_hash_names=names,
            quotes=(
                SteamDTBuffPreScreenQuote(
                    market_hash_name=first,
                    sell_price_cny=Decimal("100"),
                    sell_count=1,
                    update_time="opaque",
                ),
            ),
            missing_market_hash_names=tuple(names[1:]),
            terminal_selection_failures=(),
            diagnostics=SteamDTBatchPreScreenDiagnostics(
                logical_requested_names=len(names),
                unique_names=len(names),
                duplicates_suppressed=0,
                chunk_count=1,
                transport_attempted_names=len(names),
                selected_names=1,
                missing_names=len(names) - 1,
                terminal_selection_failures=0,
                transport_errors=(),
            ),
        )

    runner, listing_provider, _ = _runner(batch_provider=missing_partition)
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_INCONCLUSIVE
    assert result.request_state.buff_dispatched == 0
    assert listing_provider.calls == 0


def test_prescreen_quotes_must_be_in_exact_frozen_order() -> None:
    async def wrong_order(
        names: tuple[str, ...],
    ) -> SteamDTBatchPreScreenResult:
        reversed_names = tuple(reversed(names))
        return SteamDTBatchPreScreenResult(
            requested_market_hash_names=names,
            quotes=tuple(
                SteamDTBuffPreScreenQuote(
                    market_hash_name=name,
                    sell_price_cny=Decimal("100"),
                    sell_count=1,
                    update_time="opaque",
                )
                for name in reversed_names
            ),
            missing_market_hash_names=(),
            terminal_selection_failures=(),
            diagnostics=SteamDTBatchPreScreenDiagnostics(
                logical_requested_names=len(names),
                unique_names=len(names),
                duplicates_suppressed=0,
                chunk_count=1,
                transport_attempted_names=len(names),
                selected_names=len(names),
                missing_names=0,
                terminal_selection_failures=0,
                transport_errors=(),
            ),
        )

    runner, listing_provider, _ = _runner(batch_provider=wrong_order)
    result = asyncio.run(runner.run(live_validation_authorized=True))
    assert result.classification == CLASSIFICATION_CONTRACT_FAILURE
    assert result.request_state.buff_dispatched == 0
    assert listing_provider.calls == 0


def test_live_single_provider_failure_includes_matching_missing_name() -> None:
    runner, _, _ = _runner()
    requested = "AUG | Chameleon (Field-Tested)"

    async def fail(_name: str) -> PriceQuote:
        raise RuntimeError("must not leak")

    provider = _LiveSinglePriceProvider(single=fail, tracker=runner, cap=2)
    lookup = asyncio.run(provider.get_prices([requested]))
    assert lookup.quotes == {}
    assert lookup.missing == [requested]
    assert lookup.errors == ["STEAMDT_SINGLE_FAILED:0"]
    assert "must not leak" not in repr(lookup)


def test_serialized_result_v2_has_concrete_rows_numeric_caps_and_no_raw() -> None:
    from scripts.run_live_recipe_first_steamdt_validation import _serialize_result

    runner, _, _ = _runner()
    result = asyncio.run(runner.run(live_validation_authorized=True))
    payload_bytes = _serialize_result(result)
    payload = json.loads(payload_bytes)

    assert payload["schema_version"] == 2
    assert payload["buff_http_cap"] == 1
    assert payload["steamdt_batch_http_cap"] == 1
    assert payload["steamdt_final_single_http_cap"] == 2
    assert payload["steamdt_total_http_cap"] == 3
    assert payload["concrete_selection_count"] == 1
    assert payload["concrete_output_market_hash_names"] == list(
        result.concrete_output_market_hash_names
    )
    assert payload["concrete_tradeup_results"]
    assert payload["valued_tradeup_results"]
    assert payload["structural_fields_preserved"] is True
    for row in payload["valued_tradeup_results"]:
        assert set(row) == {
            "estimated_price_cny",
            "expected_value_contribution",
            "market_hash_name",
            "output_float",
            "output_wear",
            "probability",
        }
    forbidden_keys = {
        "listing_id",
        "asset_id",
        "paintwear",
        "seller",
        "api_key",
        "cookie",
        "authorization",
        "raw",
    }

    def assert_no_forbidden_keys(value) -> None:
        if isinstance(value, dict):
            assert forbidden_keys.isdisjoint(value)
            for child in value.values():
                assert_no_forbidden_keys(child)
        elif isinstance(value, list):
            for child in value:
                assert_no_forbidden_keys(child)

    assert_no_forbidden_keys(payload)


def test_pinned_family_static_authorities_remain_feasible_and_two_finishes() -> None:
    auth = _authorities()
    from app.services.buff_community_identity_resolver import (
        BuffCommunityIdentityResolver,
    )

    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        ROOT / "data" / "identity" / "buff_identity_v1.json"
    )
    feasibility = compute_static_float_feasibility(
        auth.family,
        skins=_load_skins(),
        identity_resolver=identity,
        finish_index=auth.finish_index,
    )
    assert feasibility.status is StaticFloatFeasibilityStatus.FEASIBLE
    assert len(auth.geometry.outcomes) == 2
    assert sum(
        outcome.probability for outcome in auth.geometry.outcomes
    ) == 1
