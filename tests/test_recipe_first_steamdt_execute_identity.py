"""Phase 16G-R6.1 — Pre-live fail-closed identity binding regression tests.

These tests prove that ``scripts.run_live_recipe_first_steamdt_validation.execute_case``
refuses pre-network when:

* current Git HEAD resolution fails
* the tracked worktree is dirty (untracked files ignored)
* the loaded case's ``repository_commit_oid`` does not match the current HEAD

All tests are zero-network. External market seams are not exercised.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from app.services.market_universe_builder import StatTrakMode
from app.services.recipe_first_live_case import (
    LiveValidationPlanItem,
    freeze_case,
)
from app.services.recipe_first_steamdt_live_case import (
    freeze_recipe_first_steamdt_case,
)
from scripts import run_live_recipe_first_steamdt_validation as script

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


def _buff_case(repository_commit_oid: str) -> object:
    return freeze_case(
        repository_commit_oid=repository_commit_oid,
        case_purpose="Phase16G-R6.1 execute identity binding test",
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


def _phase16g_case(repository_commit_oid: str) -> object:
    return freeze_recipe_first_steamdt_case(
        repository_commit_oid=repository_commit_oid,
        buff_case=_buff_case(repository_commit_oid),
        prescreen_market_hash_names=PRESCREEN_NAMES,
    )


def _serialize_case(case) -> bytes:
    return script.serialize_recipe_first_steamdt_case(case)


def _make_env(artifact_dir: Path) -> dict:
    return {
        script.RUN_GATE_ENV: "true",
        script.ARTIFACT_DIR_ENV: str(artifact_dir),
    }


def _capture_printer() -> tuple[list[str], callable]:
    captured: list[str] = []

    def _printer(*lines: str) -> None:
        for line in lines:
            captured.append(line)

    return captured, _printer


def _matching_head() -> str:
    return script._resolve_current_head_safe()[0]


def test_execute_refuses_when_current_head_resolution_fails(tmp_path) -> None:
    case = _phase16g_case(_matching_head())
    case_path = tmp_path / script.CASE_FILENAME
    case_path.write_bytes(_serialize_case(case))

    captured, printer = _capture_printer()

    def _failing_git(argv: Sequence[str]) -> str:
        raise RuntimeError("simulated git unavailable")

    def _always_dirty() -> bool:
        return False

    rc = asyncio.run(
        script.execute_case(
            env=_make_env(tmp_path),
            printer=printer,
            snapshot_root=ROOT,
            api_key="dummy",
            current_head_resolver=_failing_git,
            tracked_tree_clean_checker=_always_dirty,
        )
    )
    assert rc == 1
    assert any("current_head_unavailable" in line for line in captured)
    assert "live_validation_executed: no" in captured
    assert any(line.startswith("reason: current_head_unavailable") for line in captured)


def test_execute_refuses_on_repository_commit_mismatch(tmp_path) -> None:
    case = _phase16g_case("0" * 40)
    case_path = tmp_path / script.CASE_FILENAME
    case_path.write_bytes(_serialize_case(case))

    captured, printer = _capture_printer()
    real_head = _matching_head()
    assert real_head is not None
    assert real_head != "0" * 40

    def _matching_git(argv: Sequence[str]) -> str:
        return real_head + "\n"

    def _always_clean() -> bool:
        return True

    rc = asyncio.run(
        script.execute_case(
            env=_make_env(tmp_path),
            printer=printer,
            snapshot_root=ROOT,
            api_key="dummy",
            current_head_resolver=_matching_git,
            tracked_tree_clean_checker=_always_clean,
        )
    )
    assert rc == 1
    assert any("repository_commit_mismatch" in line for line in captured)
    assert "live_validation_executed: no" in captured


def test_execute_refuses_when_tracked_tree_dirty(tmp_path) -> None:
    case = _phase16g_case(_matching_head())
    case_path = tmp_path / script.CASE_FILENAME
    case_path.write_bytes(_serialize_case(case))

    captured, printer = _capture_printer()
    real_head = _matching_head()

    def _matching_git(argv: Sequence[str]) -> str:
        return real_head + "\n"

    def _always_dirty() -> bool:
        return False

    rc = asyncio.run(
        script.execute_case(
            env=_make_env(tmp_path),
            printer=printer,
            snapshot_root=ROOT,
            api_key="dummy",
            current_head_resolver=_matching_git,
            tracked_tree_clean_checker=_always_dirty,
        )
    )
    assert rc == 1
    assert any("tracked_tree_dirty" in line for line in captured)
    assert "live_validation_executed: no" in captured


def test_execute_progression_with_matching_head_and_clean_tree(
    tmp_path, monkeypatch
) -> None:
    case = _phase16g_case(_matching_head())
    case_path = tmp_path / script.CASE_FILENAME
    case_path.write_bytes(_serialize_case(case))

    captured, printer = _capture_printer()
    real_head = _matching_head()

    def _matching_git(argv: Sequence[str]) -> str:
        return real_head + "\n"

    def _always_clean() -> bool:
        return True

    # Force the runner to be a no-network fake so we can prove progression
    # past the identity-binding gate without ever hitting SteamDT/BUFF.
    class _FakeRunner:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, *, live_validation_authorized):
            from app.services.recipe_first_steamdt_live_runner import (
                CLASSIFICATION_BLOCKED,
                LIVE_STEAMDT_RESULT_SCHEMA_VERSION,
                LiveSteamDTRequestState,
                LiveSteamDTRunResult,
            )
            return LiveSteamDTRunResult(
                case_sha256="0" * 64,
                repository_commit_oid=real_head,
                family_hash=EXPECTED_FAMILY_HASH,
                family_key=EXPECTED_FAMILY_KEY,
                input_rarity=INPUT_RARITY,
                stattrak_mode="normal",
                hard_request_count=1,
                static_feasibility_status="feasible",
                prescreen_names=PRESCREEN_NAMES,
                phases=(),
                page_results=(),
                prescreen_quotes=(),
                prescreen_missing_names=(),
                prescreen_failure_names=(),
                family_compatible_enriched_inputs=0,
                family_incompatible_enriched_inputs=0,
                concrete_selection_count=0,
                concrete_output_market_hash_names=(),
                concrete_search_diagnostics=None,
                concrete_tradeup_results=(),
                valued_tradeup_results=(),
                structural_fields_preserved=None,
                structural_mismatch_reason=None,
                final_quotes=(),
                final_missing_names=(),
                final_errors=(),
                final_new_live_names=(),
                request_state=LiveSteamDTRequestState(
                    steamdt_batch_attempted=0,
                    steamdt_batch_dispatched=0,
                    steamdt_single_attempted=0,
                    steamdt_single_dispatched=0,
                    buff_attempted=0,
                    buff_dispatched=0,
                ),
                classification=CLASSIFICATION_BLOCKED,
                schema_version=LIVE_STEAMDT_RESULT_SCHEMA_VERSION,
                buff_http_cap=1,
                steamdt_batch_http_cap=1,
                steamdt_final_single_http_cap=2,
                steamdt_total_http_cap=3,
            )

        async def aclose(self):
            return None

    monkeypatch.setattr(
        script, "RecipeFirstSteamDTLiveRunner", _FakeRunner
    )

    rc = asyncio.run(
        script.execute_case(
            env=_make_env(tmp_path),
            printer=printer,
            snapshot_root=ROOT,
            api_key="dummy",
            current_head_resolver=_matching_git,
            tracked_tree_clean_checker=_always_clean,
        )
    )
    # The progression ran the offline fake runner. Identity-binding gate
    # did not refuse.
    assert not any("current_head_unavailable" in line for line in captured)
    assert not any("repository_commit_mismatch" in line for line in captured)
    assert not any("tracked_tree_dirty" in line for line in captured)
    assert rc == 0
    assert (tmp_path / script.RESULT_FILENAME).is_file()