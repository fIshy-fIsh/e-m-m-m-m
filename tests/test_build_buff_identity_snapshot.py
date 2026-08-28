"""Tests for the deterministic BUFF community identity snapshot builder."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_buff_identity_snapshot import (
    EXPECTED_RAW_SHA256,
    EXPECTED_SOURCE_COMMIT,
    SNAPSHOT_SCHEMA_VERSION,
    SOURCE_FILE,
    SOURCE_LICENSE,
    SOURCE_REPOSITORY,
    SnapshotBuilderError,
    build_snapshot_from_bytes,
    build_snapshot_from_dict,
    serialize_snapshot,
)


def _make_raw(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def _build(payload: dict[str, object]):
    return build_snapshot_from_dict(payload)


def test_valid_mapping_canonicalized_to_decimal_string() -> None:
    snap, _ = _build({"AK-47 | Redline (Field-Tested)": 33960})
    assert snap["items"] == {"AK-47 | Redline (Field-Tested)": "33960"}


def test_negative_one_sentinel_rejected_not_recorded() -> None:
    snap, _ = _build({"AK-47 | Redline (Field-Tested)": -1})
    assert snap["items"] == {}
    assert snap["counts"]["source"] == 1
    assert snap["counts"]["accepted"] == 0
    assert snap["counts"]["rejected"] == 1


def test_zero_rejected() -> None:
    snap, _ = _build({"name": 0})
    assert snap["counts"]["accepted"] == 0


def test_bool_rejected() -> None:
    snap, _ = _build({"a": True, "b": False})
    assert snap["counts"]["accepted"] == 0
    assert snap["counts"]["rejected"] == 2


def test_null_rejected() -> None:
    snap, _ = _build({"a": None})
    assert snap["counts"]["accepted"] == 0


def test_float_rejected() -> None:
    snap, _ = _build({"a": 1.5})
    assert snap["counts"]["accepted"] == 0


def test_malformed_schema_top_level_not_dict_rejected() -> None:
    with pytest.raises(SnapshotBuilderError):
        build_snapshot_from_dict(["not", "a", "dict"])


def test_empty_market_hash_name_rejected() -> None:
    snap, _ = _build({"": 1})
    assert snap["counts"]["accepted"] == 0


def test_leading_whitespace_name_rejected() -> None:
    snap, _ = _build({"  AK-47 | Redline  ": 33960})
    assert snap["counts"]["accepted"] == 0


def test_trailing_whitespace_name_rejected() -> None:
    snap, _ = _build({"AK-47 | Redline ": 33960})
    assert snap["counts"]["accepted"] == 0


def test_goods_id_collision_detected() -> None:
    with pytest.raises(SnapshotBuilderError, match="collision"):
        _build(
            {
                "AK-47 | Redline (Field-Tested)": 33960,
                "AK-47 | Redline (Minimal Wear)": 33960,
            }
        )


def test_deterministic_output_independent_of_input_order() -> None:
    raw_a = {"a": 1, "b": 2, "c": 3}
    raw_b = {"c": 3, "a": 1, "b": 2}
    _, out_a = build_snapshot_from_dict(raw_a)
    _, out_b = build_snapshot_from_dict(raw_b)
    assert out_a == out_b


def test_byte_for_byte_reproducibility() -> None:
    raw = {"a": 1, "b": 2}
    _, first = build_snapshot_from_dict(raw)
    _, second = build_snapshot_from_dict(raw)
    assert first == second


def test_wrong_raw_source_sha256_fails_closed() -> None:
    raw_bytes = b'{"a": 1}'
    with pytest.raises(SnapshotBuilderError, match="SHA-256"):
        build_snapshot_from_bytes(raw_bytes)


def test_correct_raw_source_sha256_passes() -> None:
    raw_path = Path("research/identity_revalidation/data/eric_zhu_730.json")
    if not raw_path.exists():
        pytest.skip("pinned source not present in working tree")
    raw = raw_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_RAW_SHA256
    snap, _ = build_snapshot_from_bytes(raw)
    assert snap["counts"]["accepted"] == 34402


def test_provenance_metadata_emitted_correctly() -> None:
    snap, _ = _build({"a": 1})
    assert snap["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert snap["catalog_kind"] == "community_catalog"
    assert snap["source"]["repository"] == SOURCE_REPOSITORY
    assert snap["source"]["file"] == SOURCE_FILE
    assert snap["source"]["commit"] == EXPECTED_SOURCE_COMMIT
    assert snap["source"]["license"] == SOURCE_LICENSE


def test_provenance_metadata_includes_source_sha256_via_bytes_path() -> None:
    raw_path = Path("research/identity_revalidation/data/eric_zhu_730.json")
    if not raw_path.exists():
        pytest.skip("pinned source not present in working tree")
    snap, _ = build_snapshot_from_bytes(raw_path.read_bytes())
    assert snap["source"]["sha256"] == EXPECTED_RAW_SHA256


def test_snapshot_serialized_deterministically() -> None:
    snap, _ = _build({"z": 1, "a": 2})
    serialized = serialize_snapshot(snap)
    assert serialized.endswith(b"\n")
    decoded = json.loads(serialized)
    assert decoded == snap
    assert serialize_snapshot(snap) == serialized


def test_pinned_source_metadata_matches_phase_13n3a() -> None:
    assert (
        EXPECTED_RAW_SHA256
        == "a7f370a61dd34f7d206e0372f6806cbcb936e1ba89e33f48bbb89adaa273d72f"
    )


def test_pinned_source_builds_to_expected_counts(tmp_path: Path) -> None:
    raw_path = Path("research/identity_revalidation/data/eric_zhu_730.json")
    if not raw_path.exists():
        pytest.skip("pinned source not present in working tree")
    snap, _ = build_snapshot_from_bytes(raw_path.read_bytes())
    assert snap["counts"]["source"] == 34417
    assert snap["counts"]["accepted"] == 34402
    assert snap["counts"]["rejected"] == 15


def test_leading_zeros_string_rejected() -> None:
    snap, _ = _build({"a": "033960"})
    assert snap["counts"]["accepted"] == 0


def test_string_decimal_canonicalized() -> None:
    snap, _ = _build({"a": "33960"})
    assert snap["items"] == {"a": "33960"}