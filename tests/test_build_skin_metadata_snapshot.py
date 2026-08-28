from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.build_skin_metadata_snapshot import (
    SOURCE_COMMIT,
    SOURCE_LICENSE,
    SOURCE_REPOSITORY,
    SOURCE_SHA256,
    SkinMetadataSnapshotBuilderError,
    build_snapshot_from_bytes,
    build_snapshot_from_payload,
    serialize_snapshot,
)


def _row() -> dict[str, object]:
    return {
        "name": "AK-47 | Redline",
        "rarity": {"name": "Classified"},
        "collections": [{"name": "The Phoenix Collection"}],
        "min_float": 0.10,
        "max_float": 0.70,
        "stattrak": True,
        "souvenir": False,
        "weapon": {"name": "AK-47"},
        "category": {"name": "Rifle"},
        "paint_index": 282,
        "wears": [{"name": "Field-Tested"}],
    }


def test_payload_expands_normal_and_stattrak_variants() -> None:
    snapshot = build_snapshot_from_payload([_row()])
    names = [item["market_hash_name"] for item in snapshot["items"]]
    assert names == [
        "AK-47 | Redline (Field-Tested)",
        "StatTrak™ AK-47 | Redline (Field-Tested)",
    ]


def test_payload_is_deterministic() -> None:
    first = serialize_snapshot(build_snapshot_from_payload([_row()]))
    second = serialize_snapshot(build_snapshot_from_payload([_row()]))
    assert first == second


def test_wrong_raw_hash_fails_closed() -> None:
    with pytest.raises(SkinMetadataSnapshotBuilderError, match="SHA-256"):
        build_snapshot_from_bytes(b"[]")


def test_provenance_constants_are_pinned() -> None:
    assert SOURCE_REPOSITORY == "ByMykel/CSGO-API"
    assert SOURCE_COMMIT == "8a785962b291d57a023b79408416c6792782712e"
    assert SOURCE_SHA256 == "7aeb9582c5f3308be78c78d2fd3681e3c469c67c0aeeeb7a9e54adb5c3be32d7"
    assert SOURCE_LICENSE == "MIT"


def test_canonical_snapshot_reproducible() -> None:
    raw_path = Path("research/metadata/by_mykel_skins.json")
    snapshot_path = Path("data/metadata/skin_metadata_v1.json")
    if not raw_path.exists() or not snapshot_path.exists():
        pytest.skip("pinned metadata artifacts not present")
    raw = raw_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA256
    rebuilt = serialize_snapshot(build_snapshot_from_bytes(raw))
    canonical = snapshot_path.read_bytes()
    assert hashlib.sha256(rebuilt).hexdigest() == (
        "55e4d446a5343e1932f24b9069090431f87b0c750d2cb4c091947ec2411dc421"
    )
    assert rebuilt == canonical


def test_malformed_payload_fails_closed() -> None:
    with pytest.raises(SkinMetadataSnapshotBuilderError):
        build_snapshot_from_payload({"not": "a list"})


def test_missing_collection_is_rejected() -> None:
    row = _row()
    row["collections"] = []
    snapshot = build_snapshot_from_payload([row])
    assert snapshot["counts"]["accepted"] == 0
    assert snapshot["counts"]["rejected"] == 1
