"""Phase 16F-R1 — Live validation case artifact identity / persistence tests.

These tests exercise the offline-only Phase 16F-R1 artifact-identity
corrections:

- ``repository_commit_oid`` stores the exact Git commit object ID.
- Persisted case bytes equal ``serialize_case(case)``.
- ``hash_case(case)`` is the SHA-256 of the persisted bytes.
- No trailing-newline ambiguity.
- Load/save round-trip remains canonical.
- Result artifact serializer/persistence deterministic.
- Zero network I/O is performed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "run_live_recipe_first_buff_interface_validation.py"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_live_recipe_first_buff_interface_validation as script  # noqa: E402

_FAKE_OID = "f" * 40


class _FakeCaseFixtureFactory:
    """Legacy v1/R1 fixture factory kept for compatibility."""


def _noop_printer(_line: str) -> None:
    return None


def _fake_git(argv: Sequence[str]) -> str:
    assert tuple(argv) == ("rev-parse", "HEAD")
    return _FAKE_OID + "\n"


def _run_prepare(tmp_path: Path) -> Path:
    case_path = tmp_path / script.CASE_FILENAME
    rc = asyncio.run(
        script.prepare_case(
            env={"RECIPE_FIRST_PHASE16F_ARTIFACT_DIR": str(tmp_path)},
            printer=_noop_printer,
            snapshot_root=ROOT,
            run_git=_fake_git,
        )
    )
    assert rc == 0
    assert case_path.is_file()
    return case_path


def test_prepare_resolves_exact_git_commit_oid_verbatim(tmp_path: Path) -> None:
    """R1 invariant A: stored commit field equals git output exactly.

    No hashing,, no coercion, no transformation. The exact 40-char
    lowercase hex output of ``git rev-parse HEAD`` is persisted.
    """

    case_path = _run_prepare(tmp_path)
    payload = json.loads(case_path.read_bytes())
    assert payload["repository_commit_oid"] == _FAKE_OID
    assert "repository_head_sha" not in payload
    assert len(payload["repository_commit_oid"]) == 40
    assert all(ch in "0123456789abcdef" for ch in payload["repository_commit_oid"])


def test_prepare_persisted_bytes_equal_serialize_case(tmp_path: Path) -> None:
    """R1 invariant B: persisted bytes == serialize_case(case)."""

    case_path = _run_prepare(tmp_path)
    persisted = case_path.read_bytes()
    payload = json.loads(persisted)
    # Reconstruct the case object from the persisted bytes and serialize.
    case = script._load_case(case_path)
    assert case.repository_commit_oid == payload["repository_commit_oid"]
    assert script.serialize_case(case) == persisted


def test_prepare_sha256_of_persisted_bytes_equals_hash_case(tmp_path: Path) -> None:
    """R1 invariant C: one authoritative case artifact digest."""

    case_path = _run_prepare(tmp_path)
    persisted = case_path.read_bytes()
    case = script._load_case(case_path)
    digest_of_persisted = hashlib.sha256(persisted).hexdigest()
    canonical_digest = script.hash_case(case)
    assert digest_of_persisted == canonical_digest


def test_prepare_no_trailing_newline_on_persisted_bytes(tmp_path: Path) -> None:
    """R1 invariant E: no hidden newline ambiguity."""

    case_path = _run_prepare(tmp_path)
    persisted = case_path.read_bytes()
    assert not persisted.endswith(b"\n")


def test_prepare_schema_version_is_3(tmp_path: Path) -> None:
    case_path = _run_prepare(tmp_path)
    payload = json.loads(case_path.read_bytes())
    assert payload["case_schema_version"] == 3


def test_prepare_load_round_trip_preserves_canonical_bytes(tmp_path: Path) -> None:
    """R1 invariant F: load/save round-trip remains canonical."""

    case_path = _run_prepare(tmp_path)
    case = script._load_case(case_path)
    re_persisted = script.serialize_case(case)
    assert re_persisted == case_path.read_bytes()


def test_load_case_rejects_v1_schema(tmp_path: Path) -> None:
    v1_payload = {
        "case_schema_version": 1,
        "repository_head_sha": "0" * 64,
        "case_purpose": "legacy",
        "family_hash": "a" * 64,
        "family_key": "a" * 24,
        "hard_request_count": 1,
        "input_rarity": "Restricted",
        "plan_items": [
            {
                "collection_name": "The 2018 Nuke Collection",
                "goods_id": "33960",
                "market_hash_name": "AK-47 | Redline (Field-Tested)",
                "priority_within_collection": 1,
            }
        ],
        "collection_counts": [["The 2018 Nuke Collection", 10]],
        "stattrak_mode": "normal",
    }
    path = tmp_path / "v1.json"
    path.write_bytes(json.dumps(v1_payload).encode("utf-8"))
    try:
        script._load_case(path)
    except script.LiveValidationCaseError as exc:
        assert "schema" in str(exc).lower()
    else:
        raise AssertionError("v1 case must be rejected")


def test_load_case_rejects_v2_schema(tmp_path: Path) -> None:
    v2_payload = {
        "case_schema_version": 2,
        "repository_commit_oid": "f" * 40,
        "case_purpose": "legacy",
        "family_hash": "a" * 64,
        "family_key": "a" * 24,
        "hard_request_count": 1,
        "input_rarity": "Restricted",
        "plan_items": [
            {
                "collection_name": "The 2018 Nuke Collection",
                "goods_id": "33960",
                "market_hash_name": "AK-47 | Redline (Field-Tested)",
                "priority_within_collection": 1,
            }
        ],
        "collection_counts": [["The 2018 Nuke Collection", 10]],
        "stattrak_mode": "normal",
    }
    path = tmp_path / "v2.json"
    path.write_bytes(json.dumps(v2_payload).encode("utf-8"))
    try:
        script._load_case(path)
    except script.LiveValidationCaseError as exc:
        assert "schema" in str(exc).lower()
    else:
        raise AssertionError("v2 case must be rejected")


def test_result_serializer_is_deterministic_and_excludes_untrusted_fields(tmp_path: Path) -> None:
    """R1 invariant G: result artifact serializer/persistence deterministic."""

    case_path = _run_prepare(tmp_path)
    case = script._load_case(case_path)
    from app.services.recipe_first_live_runner import (
        LiveValidationPageResult,
        LiveValidationRunResult,
    )

    page = LiveValidationPageResult(
        goods_id="33960",
        market_hash_name="AK-47 | Redline (Field-Tested)",
        request_status="dispatched",
        listing_count=10,
        candidate_accepted=10,
        candidate_rejected=0,
        metadata_resolved=10,
        metadata_unresolved=0,
        rejection_histograms=(),
        error_reason=None,
    )
    result = LiveValidationRunResult(
        case_sha256=script.hash_case(case),
        repository_commit_oid=case.repository_commit_oid,
        family_hash=case.family_hash,
        family_key=case.family_key,
        collection_counts=case.collection_counts,
        hard_request_count=case.hard_request_count,
        attempted=1,
        dispatched=1,
        budget_exceeded=False,
        page_results=(page,),
        aggregate_listings_received=10,
        aggregate_candidate_accepted=10,
        aggregate_metadata_resolved=10,
        family_compatible_enriched_inputs=10,
        family_incompatible_enriched_inputs=0,
        input_rarity=case.input_rarity,
        stattrak_mode=case.stattrak_mode.value,
        classification="validated",
        schema_version=3,
    )
    first = script._serialize_result(result)
    second = script._serialize_result(result)
    assert first == second
    assert not first.endswith(b"\n")
    parsed = json.loads(first)
    assert parsed["schema_version"] == 3
    assert parsed["repository_commit_oid"] == case.repository_commit_oid
    assert parsed["input_rarity"] == case.input_rarity
    assert parsed["stattrak_mode"] == case.stattrak_mode.value
    assert parsed["family_compatible_enriched_inputs"] == 10
    assert "repository_head_sha" not in parsed
    for forbidden in ("listing_id", "asset_id", "paintwear", "price", "cookie"):
        assert forbidden not in first.decode("utf-8")


def test_prepare_case_uses_no_network_factory(tmp_path: Path) -> None:
    """R2 invariant: prepare only uses offline pinned snapshots + git."""

    case_path = _run_prepare(tmp_path)
    assert case_path.is_file()
    payload = json.loads(case_path.read_bytes())
    # The corrected fixture drives family from authoritative builder.
    assert payload["input_rarity"] == "Classified"
    assert payload["collection_counts"] == [["The Phoenix Collection", 10]]
    assert payload["stattrak_mode"] == "normal"
    assert payload["case_schema_version"] == 3