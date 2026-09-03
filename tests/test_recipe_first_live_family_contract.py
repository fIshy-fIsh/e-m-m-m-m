"""Phase 16F-R2 — Family metadata contract and corrected fixture tests.

All tests are offline. They prove metadata/family gates before any HTTP,
authoritative family construction, post-acquisition family/provenance checks,
v3 schema rejection of v1/v2 artifacts, and R1 digest invariants.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.buff_intrinsic_flag_resolver import (
    BuffListingIntrinsicFlagsValue,
    CanonicalNameIntrinsicFlagResolver,
)
from app.services.buff_item_identity import BuffItemIdentity
from app.services.market_universe_builder import StatTrakMode
from app.services.metadata_models import SkinMetadata
from app.services.recipe_family import build_recipe_family
from app.services.recipe_family_geometry import compute_recipe_family_geometry
from app.services.recipe_first_acquisition import (
    RecipeFirstAcquisitionPage,
    RecipeFirstAcquisitionStageCounts,
    RecipeFirstListingProvenance,
)
from app.services.recipe_first_live_case import (
    LIVE_CASE_SCHEMA_VERSION,
    LiveValidationCase,
    LiveValidationCaseError,
    LiveValidationPlanItem,
    freeze_case,
    hash_case,
    serialize_case,
    verify_case_metadata_contract,
)
from app.services.recipe_first_live_runner import (
    RUN_STATUS_DISPATCHED,
    LiveValidationPageResult,
    LiveValidationRunner,
    LiveValidationRunnerConfig,
    _PageAcquisitionOutcome,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import TradeUpEnrichedInput
from app.services.tradeup_engine import InputItem

ROOT = Path(__file__).resolve().parent.parent
TARGET_NAME = "AK-47 | Redline (Field-Tested)"
TARGET_GOODS_ID = "33960"
CORRECT_COLLECTION = "The Phoenix Collection"
CORRECT_RARITY = "Classified"


def _pinned_metadata() -> PinnedSkinMetadataResolver:
    return PinnedSkinMetadataResolver.from_snapshot_path(
        ROOT / "data" / "metadata" / "skin_metadata_v1.json"
    )


def _pinned_identity() -> BuffCommunityIdentityResolver:
    return BuffCommunityIdentityResolver.from_snapshot_path(
        ROOT / "data" / "identity" / "buff_identity_v1.json"
    )


def _finish_index(skins: Sequence[SkinMetadata] | None = None) -> StructuralOutputFinishIndex:
    values = tuple(skins) if skins is not None else _pinned_metadata().skins
    return StructuralOutputFinishIndex.from_skins(values)


def _plan_item(collection: str = CORRECT_COLLECTION) -> LiveValidationPlanItem:
    return LiveValidationPlanItem(
        market_hash_name=TARGET_NAME,
        goods_id=TARGET_GOODS_ID,
        collection_name=collection,
        priority_within_collection=1,
    )


def _correct_case() -> LiveValidationCase:
    family = build_recipe_family(
        input_rarity=CORRECT_RARITY,
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=((CORRECT_COLLECTION, 10),),
    )
    return freeze_case(
        repository_commit_oid="f" * 40,
        case_purpose="R2 fixture",
        family_hash=family.family_hash,
        family_key=family.family_key,
        input_rarity=family.input_rarity,
        stattrak_mode=family.stattrak_mode,
        collection_counts=family.collection_counts,
        plan_items=(_plan_item(),),
    )


def _verify(case: LiveValidationCase) -> None:
    metadata = _pinned_metadata()
    verify_case_metadata_contract(
        case,
        metadata_resolver=metadata,
        intrinsic_resolver=CanonicalNameIntrinsicFlagResolver(),
        skins=metadata.skins,
        finish_index=_finish_index(metadata.skins),
    )


def test_pinned_audit_proves_correct_redline_metadata() -> None:
    metadata = _pinned_metadata()
    row = metadata.resolve(TARGET_NAME)
    assert row is not None
    assert row.market_hash_name == TARGET_NAME
    assert row.collection_name == CORRECT_COLLECTION
    assert row.rarity == CORRECT_RARITY
    skin_rows = tuple(
        skin for skin in metadata.skins if skin.market_hash_name == TARGET_NAME
    )
    assert len(skin_rows) == 1
    skin = skin_rows[0]
    assert skin.stattrak is False
    assert skin.souvenir is False
    assert skin.min_float == 0.1
    assert skin.max_float == 0.7


def test_pinned_identity_proves_exact_goods_name_pair() -> None:
    identity = _pinned_identity()
    resolved = asyncio.run(identity.resolve_goods_id(TARGET_GOODS_ID))
    assert resolved == BuffItemIdentity(
        market_hash_name=TARGET_NAME,
        goods_id=TARGET_GOODS_ID,
    )


def test_corrected_family_uses_authoritative_builder_and_geometry() -> None:
    case = _correct_case()
    family = build_recipe_family(
        input_rarity=CORRECT_RARITY,
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=((CORRECT_COLLECTION, 10),),
    )
    assert case.family_hash == family.family_hash
    assert case.family_key == family.family_key
    assert case.collection_counts == family.collection_counts
    assert case.input_rarity == family.input_rarity
    assert case.stattrak_mode == family.stattrak_mode
    assert family.family_hash == (
        "45bfd0f0d3e7405588acdcf742d980577eed4963382c2fde31632fc43db52516"
    )
    geometry = compute_recipe_family_geometry(
        family,
        finish_index=_finish_index(),
    )
    assert geometry.family_hash == family.family_hash
    assert geometry.output_rarity == "Covert"
    assert geometry.output_stattrak is False
    assert len(geometry.outcomes) == 2
    assert sum(outcome.probability for outcome in geometry.outcomes) == 1


def test_old_wrong_collection_and_rarity_rejected_before_http() -> None:
    case = freeze_case(
        repository_commit_oid="f" * 40,
        case_purpose="superseded fixture",
        family_hash="a" * 64,
        family_key="a" * 24,
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The 2018 Nuke Collection", 10),),
        plan_items=(_plan_item("The 2018 Nuke Collection"),),
    )
    with pytest.raises(LiveValidationCaseError, match="collection_name"):
        _verify(case)


def test_collection_mismatch_rejected_before_http() -> None:
    family = build_recipe_family(
        input_rarity=CORRECT_RARITY,
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The 2018 Nuke Collection", 10),),
    )
    case = freeze_case(
        repository_commit_oid="f" * 40,
        case_purpose="wrong collection",
        family_hash=family.family_hash,
        family_key=family.family_key,
        input_rarity=family.input_rarity,
        stattrak_mode=family.stattrak_mode,
        collection_counts=family.collection_counts,
        plan_items=(_plan_item("The 2018 Nuke Collection"),),
    )
    with pytest.raises(LiveValidationCaseError, match="collection_name"):
        _verify(case)


def test_rarity_mismatch_rejected_before_http() -> None:
    family = build_recipe_family(
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=((CORRECT_COLLECTION, 10),),
    )
    case = freeze_case(
        repository_commit_oid="f" * 40,
        case_purpose="wrong rarity",
        family_hash=family.family_hash,
        family_key=family.family_key,
        input_rarity=family.input_rarity,
        stattrak_mode=family.stattrak_mode,
        collection_counts=family.collection_counts,
        plan_items=(_plan_item(),),
    )
    with pytest.raises(LiveValidationCaseError, match="rarity"):
        _verify(case)


def test_stattrak_mismatch_rejected_before_http() -> None:
    family = build_recipe_family(
        input_rarity=CORRECT_RARITY,
        stattrak_mode=StatTrakMode.STATTRAK,
        collection_counts=((CORRECT_COLLECTION, 10),),
    )
    case = freeze_case(
        repository_commit_oid="f" * 40,
        case_purpose="wrong mode",
        family_hash=family.family_hash,
        family_key=family.family_key,
        input_rarity=family.input_rarity,
        stattrak_mode=family.stattrak_mode,
        collection_counts=family.collection_counts,
        plan_items=(_plan_item(),),
    )
    with pytest.raises(LiveValidationCaseError, match="StatTrak"):
        _verify(case)


def test_family_hash_mismatch_rejected_before_http() -> None:
    case = _correct_case()
    object.__setattr__(case, "family_hash", "0" * 64)
    with pytest.raises(LiveValidationCaseError, match="family_hash"):
        _verify(case)


def test_family_key_mismatch_rejected_before_http() -> None:
    case = _correct_case()
    object.__setattr__(case, "family_key", "0" * 24)
    with pytest.raises(LiveValidationCaseError, match="family_key"):
        _verify(case)


def test_no_next_rarity_geometry_rejected_before_http() -> None:
    metadata = _pinned_metadata()
    case = _correct_case()
    finish_index = _finish_index(metadata.skins)
    object.__setattr__(finish_index, "_by_collection", {})
    with pytest.raises(LiveValidationCaseError, match="geometry"):
        verify_case_metadata_contract(
            case,
            metadata_resolver=metadata,
            intrinsic_resolver=CanonicalNameIntrinsicFlagResolver(),
            skins=metadata.skins,
            finish_index=finish_index,
        )


def test_valid_corrected_case_passes_metadata_contract() -> None:
    _verify(_correct_case())


@pytest.mark.parametrize("version", [1, 2])
def test_v1_v2_artifacts_rejected_by_v3_loader(
    tmp_path: Path,
    version: int,
) -> None:
    from scripts import run_live_recipe_first_buff_interface_validation as script

    payload = json.loads(serialize_case(_correct_case()))
    payload["case_schema_version"] = version
    path = tmp_path / f"v{version}.json"
    path.write_bytes(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    with pytest.raises(LiveValidationCaseError, match="schema"):
        script._load_case(path)


def test_r1_case_digest_invariants_remain_intact() -> None:
    case = _correct_case()
    persisted = serialize_case(case)
    assert not persisted.endswith(b"\n")
    assert hashlib.sha256(persisted).hexdigest() == hash_case(case)
    assert LIVE_CASE_SCHEMA_VERSION == 3


def test_enriched_family_mismatch_is_contract_failure() -> None:
    fake_page = _page(collection_name="WRONG COLLECTION")
    runner = _runner(_correct_case())
    runner._tracker.attempted = 1
    runner._tracker.dispatched = 1

    class _Stub:
        async def acquire(self, *, pipeline, plan_item):
            return _PageAcquisitionOutcome(
                page_result=_page_result(metadata_resolved=1),
                family_compatible=0,
                family_incompatible=1,
                provenance_keys=(
                    ("buff", TARGET_GOODS_ID, "listing-1"),
                ),
                contract_failed=False,
            )

    runner._acquire_one = _Stub().acquire  # type: ignore[assignment]
    result = asyncio.run(runner.run())
    assert fake_page.enriched_inputs[0].input_item.collection_name == "WRONG COLLECTION"
    assert result.classification == "contract_failure"
    assert result.family_compatible_enriched_inputs == 0
    assert result.family_incompatible_enriched_inputs == 1


def test_page_validator_checks_candidate_input_and_provenance_alignment() -> None:
    from app.services.recipe_first_live_runner import _validate_family_compatible_page

    page = _page()
    compatible, incompatible, provenance_keys, contract_failed = (
        _validate_family_compatible_page(
            page,
            plan_item=_plan_item(),
            case=_correct_case(),
        )
    )
    assert compatible == 1
    assert incompatible == 0
    assert provenance_keys == (("buff", TARGET_GOODS_ID, "listing-1"),)
    assert contract_failed is False


def test_page_validator_rejects_provenance_mismatch() -> None:
    from app.services.recipe_first_live_runner import _validate_family_compatible_page

    page = _page(provenance_goods_id="999")
    compatible, incompatible, _keys, contract_failed = (
        _validate_family_compatible_page(
            page,
            plan_item=_plan_item(),
            case=_correct_case(),
        )
    )
    assert compatible == 0
    assert incompatible == 1
    assert contract_failed is False


def test_memory_error_from_metadata_resolver_propagates() -> None:
    class _MemoryMetadata:
        def resolve(self, market_hash_name: str):
            raise MemoryError("simulated")

    metadata = _pinned_metadata()
    with pytest.raises(MemoryError, match="simulated"):
        verify_case_metadata_contract(
            _correct_case(),
            metadata_resolver=_MemoryMetadata(),  # type: ignore[arg-type]
            intrinsic_resolver=CanonicalNameIntrinsicFlagResolver(),
            skins=metadata.skins,
            finish_index=_finish_index(metadata.skins),
        )


def test_no_forbidden_transport_imports_in_r2_surface() -> None:
    forbidden_imports = (
        "from app.services.steamdt",
        "from app.services.steamapis",
        "import steamdt",
        "import steamapis",
    )
    paths = (
        ROOT / "app" / "services" / "recipe_first_live_case.py",
        ROOT / "app" / "services" / "recipe_first_live_runner.py",
        ROOT / "scripts" / "run_live_recipe_first_buff_interface_validation.py",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8").lower()
        for forbidden in forbidden_imports:
            assert forbidden not in source, f"{forbidden!r} leaked into {path.name}"


# Helpers


@dataclass
class _StubIntrinsicResolver:
    stattrak: bool = False
    souvenir: bool = False

    def resolve(self, market_hash_name: str) -> BuffListingIntrinsicFlagsValue:
        return BuffListingIntrinsicFlagsValue(
            stattrak=self.stattrak,
            souvenir=self.souvenir,
        )


def _enriched(
    *,
    collection_name: str = CORRECT_COLLECTION,
    rarity: str = CORRECT_RARITY,
    candidate_goods_id: str = TARGET_GOODS_ID,
    candidate_market_name: str = TARGET_NAME,
    stattrak: bool = False,
    souvenir: bool = False,
) -> TradeUpEnrichedInput:
    candidate = TradeUpInputCandidate(
        listing_id="listing-1",
        goods_id=candidate_goods_id,
        market_hash_name=candidate_market_name,
        price_cny=Decimal("1"),
        paintwear=Decimal("0.2"),
        asset_id="asset-1",
        source="buff",
        stattrak=stattrak,
        souvenir=souvenir,
    )
    return TradeUpEnrichedInput(
        candidate=candidate,
        input_item=InputItem(
            market_hash_name=candidate_market_name,
            collection_name=collection_name,
            rarity=rarity,
            actual_float=0.2,
            min_float=0.1,
            max_float=0.7,
            price_cny=Decimal("1"),
            stattrak=stattrak,
            souvenir=souvenir,
        ),
    )


def _page(
    *,
    collection_name: str = CORRECT_COLLECTION,
    provenance_goods_id: str = TARGET_GOODS_ID,
) -> RecipeFirstAcquisitionPage:
    enriched = _enriched(collection_name=collection_name)
    provenance = RecipeFirstListingProvenance(
        listing_id="listing-1",
        goods_id=provenance_goods_id,
        asset_id="asset-1",
        market_hash_name=TARGET_NAME,
        price_cny=Decimal("1"),
        paintwear=Decimal("0.2"),
        paintseed=None,
        stattrak=False,
        souvenir=False,
        source="buff",
    )
    return RecipeFirstAcquisitionPage(
        goods_id=TARGET_GOODS_ID,
        market_hash_name=TARGET_NAME,
        enriched_inputs=(enriched,),
        provenance=(provenance,),
        counts=RecipeFirstAcquisitionStageCounts(
            listings_received=1,
            identity_resolved=1,
            identity_unresolved=0,
            intrinsic_resolved=1,
            intrinsic_unresolved=0,
            candidate_accepted=1,
            candidate_rejected=0,
            metadata_resolved=1,
            metadata_unresolved=0,
        ),
        candidate_rejection_histogram=(),
        metadata_rejection_histogram=(),
    )


def _page_result(*, metadata_resolved: int) -> LiveValidationPageResult:
    return LiveValidationPageResult(
        goods_id=TARGET_GOODS_ID,
        market_hash_name=TARGET_NAME,
        request_status=RUN_STATUS_DISPATCHED,
        listing_count=metadata_resolved,
        candidate_accepted=metadata_resolved,
        candidate_rejected=0,
        metadata_resolved=metadata_resolved,
        metadata_unresolved=0,
        rejection_histograms=(),
        error_reason=None,
    )


def _runner(case: LiveValidationCase) -> LiveValidationRunner:
    return LiveValidationRunner(
        case=case,
        identity_resolver=_pinned_identity(),
        metadata_resolver=_pinned_metadata(),
        intrinsic_resolver=CanonicalNameIntrinsicFlagResolver(),
        config=LiveValidationRunnerConfig(pacing_seconds=0.0),
    )
