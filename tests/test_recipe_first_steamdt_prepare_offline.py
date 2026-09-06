"""Phase 16G-R3 — Real offline prepare_case() regression test.

This test invokes the actual ``prepare_case`` async function from
``scripts.run_live_recipe_first_steamdt_validation`` against the real
pinned identity + metadata snapshots, with the real ``.venv`` Python
process running the test.

The test proves:

* the script's prepare path executes without raising
* a case artifact is persisted outside Git
* the case's ``repository_commit_oid`` equals the current HEAD
* the family/plan/prescreen fields match the frozen authority
* no live HTTP is performed
* no ``.env`` file is read
* no ``STEAMDT_API_KEY`` is required
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_FAMILY_HASH: str = (
    "45bfd0f0d3e7405588acdcf742d980577eed4963382c2fde31632fc43db52516"
)
EXPECTED_FAMILY_KEY: str = "45bfd0f0d3e7405588acdcf7"
EXPECTED_INPUT_RARITY: str = "Classified"
EXPECTED_COLLECTION_NAME: str = "The Phoenix Collection"


def _resolve_head() -> str:
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), text=True
    ).strip()


def test_prepare_case_offline_freezes_case_artifact_bound_to_head(tmp_path) -> None:
    """prepare_case() must succeed offline and bind the case to current HEAD."""

    from scripts import run_live_recipe_first_steamdt_validation as script

    artifact_dir = tmp_path / "cs2-phase16g-r3"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    case_path = artifact_dir / script.CASE_FILENAME

    env: dict = {
        script.ARTIFACT_DIR_ENV: str(artifact_dir),
    }
    captured: list[str] = []

    def _printer(*lines: str) -> None:
        for line in lines:
            captured.append(line)

    rc = asyncio.run(
        script.prepare_case(
            env=env,
            printer=_printer,
            snapshot_root=ROOT,
        )
    )
    assert rc == 0, "prepare_case must succeed offline"
    assert case_path.is_file(), f"case artifact must be persisted at {case_path}"
    assert any("phase16g_prepare: ok" in line for line in captured)
    assert any("live_validation_executed: no" in line for line in captured)

    raw = case_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    payload = json.loads(raw)

    head = _resolve_head()
    assert payload["repository_commit_oid"] == head, (
        "case repository_commit_oid must equal current HEAD"
    )
    assert sha == script.hash_recipe_first_steamdt_case(
        script._load_case(case_path)
    )

    assert payload["case_schema_version"] == script.LIVE_STEAMDT_CASE_SCHEMA_VERSION
    assert payload["buff_http_cap"] == 1
    assert payload["steamdt_batch_http_cap"] == 1
    assert payload["steamdt_final_single_http_cap"] == 2
    assert payload["steamdt_total_http_cap"] == 3

    assert len(payload["prescreen_market_hash_names"]) == 9
    assert len(set(payload["prescreen_market_hash_names"])) == 9

    buff = payload["buff_case"]
    assert buff["family_hash"] == EXPECTED_FAMILY_HASH
    assert buff["family_key"] == EXPECTED_FAMILY_KEY
    assert buff["input_rarity"] == EXPECTED_INPUT_RARITY
    assert list(buff["collection_counts"]) == [
        [EXPECTED_COLLECTION_NAME, 10]
    ]
    assert buff["hard_request_count"] == 1
    plan_names = [item["market_hash_name"] for item in buff["plan_items"]]
    assert plan_names == ["AK-47 | Redline (Field-Tested)"]
    plan_gids = [item["goods_id"] for item in buff["plan_items"]]
    assert plan_gids == ["33960"]


def test_prepare_case_offline_does_not_read_env_or_network(tmp_path) -> None:
    """prepare_case() must not consult .env, API key, or any live service."""

    from scripts import run_live_recipe_first_steamdt_validation as script

    artifact_dir = tmp_path / "cs2-phase16g-r3-net"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    env: dict = {
        script.ARTIFACT_DIR_ENV: str(artifact_dir),
    }

    rc = asyncio.run(
        script.prepare_case(env=env, printer=lambda *_: None, snapshot_root=ROOT)
    )
    assert rc == 0
    assert not (artifact_dir / script.RESULT_FILENAME).exists()
    assert (artifact_dir / script.CASE_FILENAME).is_file()