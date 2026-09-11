"""Phase 17D-A-R1 actual recipe-first CLI pre-live case proof.

Pure/offline only. No market provider method may execute.
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.market_universe_builder import StatTrakMode
from app.services.price_provider import PriceLookupResult, PriceQuote
from app.services.recipe_first_runtime_contract import (
    RecipeFirstDiscoveryBudget,
    RecipeFirstOutputFormat,
    RecipeFirstRuntimeConfig,
)
from app.services.recipe_first_runtime_coordinator import (
    RecipeFirstRuntimeCoordinator,
)
from app.services.recipe_solver import RecipeEnumerationConfig
from app.services.risk_filter import RiskFilterConfig
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.valuation_service import ValuationConfig, ValuationService
from scripts import run_recipe_first_scan_once as cli

ROOT = Path(__file__).resolve().parent.parent
IDENTITY_PATH = ROOT / "data" / "identity" / "buff_identity_v1.json"
METADATA_PATH = ROOT / "data" / "metadata" / "skin_metadata_v1.json"
COLLECTION = "The Phoenix Collection"
FAMILY_KEY = "45bfd0f0d3e7405588acdcf7"
FAMILY_HASH = (
    "45bfd0f0d3e7405588acdcf742d980577eed4963382c2fde31632fc43db52516"
)
METADATA_SHA = "55e4d446a5343e1932f24b9069090431f87b0c750d2cb4c091947ec2411dc421"
IDENTITY_SHA = "e3aab46d570869e0b6866eac44b26bca7492ea7c2c54669e74b2b4feeec506ac"
EXPECTED_NAMES = (
    "AK-47 | Redline (Battle-Scarred)",
    "AK-47 | Redline (Field-Tested)",
    "AK-47 | Redline (Minimal Wear)",
    "AK-47 | Redline (Well-Worn)",
    "Nova | Antique (Factory New)",
    "Nova | Antique (Field-Tested)",
    "Nova | Antique (Minimal Wear)",
    "P90 | Trigon (Battle-Scarred)",
    "P90 | Trigon (Field-Tested)",
    "P90 | Trigon (Minimal Wear)",
    "P90 | Trigon (Well-Worn)",
    "AUG | Chameleon (Factory New)",
    "AUG | Chameleon (Minimal Wear)",
    "AUG | Chameleon (Field-Tested)",
    "AUG | Chameleon (Well-Worn)",
    "AUG | Chameleon (Battle-Scarred)",
    "AWP | Asiimov (Field-Tested)",
    "AWP | Asiimov (Well-Worn)",
    "AWP | Asiimov (Battle-Scarred)",
)
ARTIFACT_DIR = Path(tempfile.gettempdir()) / "cs2-phase17d"
FROZEN_ARGS = (
    "--enable-recipe-first",
    "--input-rarity",
    "Classified",
    "--stattrak-mode",
    "normal",
    "--collection",
    COLLECTION,
    "--max-family-states-considered",
    "1",
    "--max-prescreen-names",
    "20",
    "--max-prescreen-batch-dispatches",
    "2",
    "--max-targeted-buff-goods-ids",
    "10",
    "--max-final-valuation-requests",
    "2",
    "--max-recipe-candidates-returned",
    "1",
    "--max-candidate-states-explored",
    "256",
    "--cache-backend",
    "inmemory",
    "--output-format",
    "json",
    "--artifact-dir",
    str(ARTIFACT_DIR),
)


class _NoBatch:
    async def get_price_batch_with_selection(self, *args, **kwargs):
        raise AssertionError("SteamDT dispatch forbidden")


class _NoBuff:
    async def get_listings(self, *args, **kwargs):
        raise AssertionError("BUFF dispatch forbidden")


class _NoFinal:
    async def get_price(self, *args, **kwargs) -> PriceQuote:
        raise AssertionError("final price dispatch forbidden")

    async def get_prices(self, *args, **kwargs) -> PriceLookupResult:
        raise AssertionError("final price dispatch forbidden")


def _coordinator() -> RecipeFirstRuntimeCoordinator:
    identity = BuffCommunityIdentityResolver.from_snapshot_path(IDENTITY_PATH)
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(METADATA_PATH)
    finish = StructuralOutputFinishIndex.from_skins(metadata.skins)
    return RecipeFirstRuntimeCoordinator(
        config=RecipeFirstRuntimeConfig(
            enabled=True,
            preview=False,
            input_rarities=("Classified",),
            stattrak_modes=(StatTrakMode.NORMAL,),
            collection_allowlist=(COLLECTION,),
            max_targeted_buff_goods_ids=10,
            max_final_valuation_requests=2,
            sell_fee_rate=Decimal("0.025"),
            enumeration_config=RecipeEnumerationConfig(
                max_recipe_candidates_returned=1,
                max_candidate_states_explored=256,
            ),
            cache_backend="inmemory",
            output_format=RecipeFirstOutputFormat.JSON,
        ),
        discovery_budget=RecipeFirstDiscoveryBudget(
            max_family_states_considered=1,
            max_prescreen_names=20,
            max_prescreen_batch_dispatches=2,
        ),
        identity_resolver=identity,
        metadata_resolver=metadata,
        finish_index=finish,
        prescreen_transport=_NoBatch(),
        listing_provider=_NoBuff(),
        valuation_service=ValuationService(
            _NoFinal(),
            ValuationConfig(require_all_prices=True),
        ),
        risk_config=RiskFilterConfig(
            min_roi=Decimal("0"),
            min_expected_profit_cny=Decimal("0"),
            max_worst_case_loss_pct=Decimal("1"),
            min_profit_probability=0.0,
            max_input_total_cost_cny=Decimal("1"),
        ),
    )


def test_actual_parser_accepts_frozen_args() -> None:
    args = cli._build_parser().parse_args(FROZEN_ARGS)
    assert args.enable_recipe_first is True
    assert args.input_rarity == "Classified"
    assert args.stattrak_mode == "normal"
    assert args.collection == [COLLECTION]
    assert args.max_family_states_considered == 1
    assert args.max_prescreen_names == 20
    assert args.max_prescreen_batch_dispatches == 2
    assert args.max_targeted_buff_goods_ids == 10
    assert args.max_final_valuation_requests == 2
    assert args.max_recipe_candidates_returned == 1
    assert args.max_candidate_states_explored == 256
    assert args.cache_backend == "inmemory"
    assert args.output_format == "json"
    assert args.artifact_dir == ARTIFACT_DIR


def test_enable_gate_refuses_before_any_client_construction(monkeypatch) -> None:
    calls = 0

    async def forbidden(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("client construction forbidden")

    monkeypatch.setattr(cli, "_build_live_runtime_seams", forbidden)
    assert cli.main(()) == 3
    assert calls == 0


def test_one_state_repaired_runtime_selects_exact_phoenix_family() -> None:
    coordinator = _coordinator()
    candidates, summary = coordinator._discover(phases=[])
    assert summary.visited == 1
    assert summary.infeasible == 0
    assert summary.contract_failed == 0
    assert len(candidates) == 1
    family = candidates[0].family
    assert family.collection_counts == ((COLLECTION, 10),)
    assert family.family_key == FAMILY_KEY
    assert family.family_hash == FAMILY_HASH


def test_recomputed_prescreen_shape_fits_frozen_caps() -> None:
    coordinator = _coordinator()
    candidates, summary = coordinator._discover(phases=[])
    logical = sum(len(item.prescreen_names) for item in candidates)
    unique = coordinator._dedupe_names(candidates)
    chunks = (len(unique) + 9) // 10
    assert summary.visited == 1
    assert logical == 19
    assert unique == EXPECTED_NAMES
    assert len(unique) == 19 <= 20
    assert chunks == 2 <= 2
    admitted, admission = coordinator._admit_prescreen(
        names=unique,
        logical=logical,
    )
    assert admitted is True
    assert admission.atomically_blocked == 0


def test_all_frozen_bounds_are_inside_runtime_hard_limits() -> None:
    args = cli._build_parser().parse_args(FROZEN_ARGS)
    config = cli._build_runtime_config(
        args=args,
        preview=False,
        sell_fee_rate=Decimal("0.025"),
    )
    budget = cli._build_discovery_budget(args)
    cli._validate_runtime_config(config)
    cli._validate_discovery_budget(budget)
    assert config.max_targeted_buff_goods_ids == 10
    assert config.max_final_valuation_requests == 2 <= 60
    assert budget.max_family_states_considered == 1
    assert budget.max_prescreen_names == 20
    assert budget.max_prescreen_batch_dispatches == 2
    assert config.enumeration_config == RecipeEnumerationConfig(
        max_recipe_candidates_returned=1,
        max_candidate_states_explored=256,
    )
    assert 2 + 10 + 2 == 14


def test_snapshot_paths_and_digests_are_exact() -> None:
    assert METADATA_PATH.relative_to(ROOT).as_posix() == (
        "data/metadata/skin_metadata_v1.json"
    )
    assert IDENTITY_PATH.relative_to(ROOT).as_posix() == (
        "data/identity/buff_identity_v1.json"
    )
    assert hashlib.sha256(METADATA_PATH.read_bytes()).hexdigest() == METADATA_SHA
    assert hashlib.sha256(IDENTITY_PATH.read_bytes()).hexdigest() == IDENTITY_SHA


def test_artifact_directory_is_outside_repository() -> None:
    artifact = ARTIFACT_DIR.resolve()
    repo = ROOT.resolve()
    assert not artifact.is_relative_to(repo)
    assert artifact.name == "cs2-phase17d"
    assert cli.RESULT_FILENAME == "phase17b_result.json"


def test_runtime_has_no_phase16g_import_or_retry_loop() -> None:
    source = (
        ROOT / "scripts" / "run_recipe_first_scan_once.py"
    ).read_text(encoding="utf-8")
    assert "recipe_first_steamdt_live_runner" not in source
    assert "run_live_recipe_first_steamdt_validation" not in source
    assert "max_retries=0" in source.replace(" ", "")
    assert "--repeat" not in source
    assert "--interval" not in source
    assert "--paginate" not in source


def test_goods_first_authorities_unchanged() -> None:
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
