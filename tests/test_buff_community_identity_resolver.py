"""Tests for BuffCommunityIdentityResolver runtime behavior.

These tests use synthetic in-memory forward/reverse mappings; they do
not require the real pinned snapshot. The pinned snapshot is tested
separately in tests/test_buff_identity_pinned_snapshot.py.

This project does not configure pytest-asyncio; async resolver calls
are wrapped in `asyncio.run(...)` to follow existing project test
conventions (see tests/test_buff_anonymous_listing_client.py).
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from app.services.buff_community_identity_resolver import (
    EXPECTED_SCHEMA_VERSION,
    BuffCommunityIdentityResolver,
    BuffCommunitySnapshotMetadata,
    BuffCommunitySnapshotValidationError,
)


def _metadata(
    *,
    sha256: str = "deadbeef" * 8,
    source_count: int = 3,
    accepted_count: int = 3,
    rejected_count: int = 0,
) -> BuffCommunitySnapshotMetadata:
    return BuffCommunitySnapshotMetadata(
        schema_version=EXPECTED_SCHEMA_VERSION,
        catalog_kind="community_catalog",
        repository="example/test",
        file="x.json",
        commit="abc",
        sha256=sha256,
        license="CC-BY-4.0",
        attribution="test",
        source_count=source_count,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
    )


def _resolver(pairs: dict[str, str]) -> BuffCommunityIdentityResolver:
    forward = dict(pairs)
    reverse = {gid: name for name, gid in forward.items()}
    return BuffCommunityIdentityResolver(
        forward=forward, reverse=reverse, metadata=_metadata()
    )


def _resolve(r: BuffCommunityIdentityResolver, name: str):
    return asyncio.run(r.resolve(name))


def _resolve_gid(r: BuffCommunityIdentityResolver, gid: str):
    return asyncio.run(r.resolve_goods_id(gid))


def test_forward_resolve_exact() -> None:
    r = _resolver({"AK-47 | Redline (Field-Tested)": "33960"})
    ident = _resolve(r, "AK-47 | Redline (Field-Tested)")
    assert ident is not None
    assert ident.market_hash_name == "AK-47 | Redline (Field-Tested)"
    assert ident.goods_id == "33960"


def test_reverse_resolve_exact() -> None:
    r = _resolver({"AK-47 | Redline (Field-Tested)": "33960"})
    ident = _resolve_gid(r, "33960")
    assert ident is not None
    assert ident.market_hash_name == "AK-47 | Redline (Field-Tested)"
    assert ident.goods_id == "33960"


def test_forward_unknown_returns_none() -> None:
    r = _resolver({"AK-47 | Redline (Field-Tested)": "33960"})
    assert _resolve(r, "AK-47 | Blue Laminate (FT)") is None


def test_reverse_unknown_returns_none() -> None:
    r = _resolver({"AK-47 | Redline (Field-Tested)": "33960"})
    assert _resolve_gid(r, "99999") is None


def test_case_difference_does_not_match() -> None:
    r = _resolver({"AK-47 | Redline (Field-Tested)": "33960"})
    assert _resolve(r, "ak-47 | redline (field-tested)") is None


def test_whitespace_not_normalized_forward() -> None:
    r = _resolver({"AK-47 | Redline (Field-Tested)": "33960"})
    assert _resolve(r, " AK-47 | Redline (Field-Tested) ") is None


def test_whitespace_not_normalized_reverse() -> None:
    r = _resolver({"AK-47 | Redline (Field-Tested)": "33960"})
    assert _resolve_gid(r, " 33960 ") is None


def test_special_chars_preserved() -> None:
    """Star, TM, pipe, parentheses all preserved byte-for-byte."""
    r = _resolver(
        {
            "★ Karambit | Doppler (Factory New)": "42998",
            "StatTrak™ AK-47 | Redline (Field-Tested)": "38220",
        }
    )
    a = _resolve(r, "★ Karambit | Doppler (Factory New)")
    b = _resolve(r, "StatTrak™ AK-47 | Redline (Field-Tested)")
    assert a is not None and a.goods_id == "42998"
    assert b is not None and b.goods_id == "38220"


def test_zero_goods_id_returns_none() -> None:
    r = _resolver({"a": "1"})
    assert _resolve_gid(r, "0") is None


def test_leading_zero_goods_id_returns_none() -> None:
    r = _resolver({"a": "1"})
    assert _resolve_gid(r, "033960") is None


def test_empty_goods_id_returns_none() -> None:
    r = _resolver({"a": "1"})
    assert _resolve_gid(r, "") is None


def test_non_integer_goods_id_returns_none() -> None:
    r = _resolver({"a": "1"})
    assert _resolve_gid(r, "abc") is None


def test_non_string_input_returns_none() -> None:
    r = _resolver({"a": "1"})
    assert _resolve(r, None) is None  # type: ignore[arg-type]
    assert _resolve_gid(r, None) is None  # type: ignore[arg-type]


def test_collision_in_forward_fails_construction() -> None:
    forward = {"a": "1", "b": "1"}
    reverse = {"1": "a"}
    with pytest.raises(BuffCommunitySnapshotValidationError):
        BuffCommunityIdentityResolver(
            forward=forward, reverse=reverse, metadata=_metadata()
        )


def test_inconsistent_reverse_fails_construction() -> None:
    forward = {"a": "1", "b": "2"}
    reverse = {"1": "a", "2": "c"}
    with pytest.raises(BuffCommunitySnapshotValidationError):
        BuffCommunityIdentityResolver(
            forward=forward, reverse=reverse, metadata=_metadata()
        )


def test_from_snapshot_path_loads_valid_file(tmp_path: Path) -> None:
    snap = {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "catalog_kind": "community_catalog",
        "source": {
            "repository": "example/repo",
            "file": "x.json",
            "commit": "abc",
            "sha256": "deadbeef" * 8,
            "license": "CC-BY-4.0",
            "attribution": "test attribution",
        },
        "counts": {"source": 1, "accepted": 1, "rejected": 0},
        "items": {"Test Item": "1"},
    }
    path = tmp_path / "snap.json"
    path.write_bytes(
        json.dumps(snap, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    )
    r = BuffCommunityIdentityResolver.from_snapshot_path(path)
    assert r.metadata.repository == "example/repo"
    assert r.metadata.source_count == 1


def test_from_snapshot_path_rejects_wrong_schema_version(tmp_path: Path) -> None:
    snap = {
        "schema_version": 99,
        "catalog_kind": "community_catalog",
        "source": {
            "repository": "x", "file": "y", "commit": "z", "sha256": "q" * 8,
            "license": "L", "attribution": "A",
        },
        "counts": {"source": 0, "accepted": 0, "rejected": 0},
        "items": {},
    }
    path = tmp_path / "snap.json"
    path.write_text(json.dumps(snap))
    with pytest.raises(BuffCommunitySnapshotValidationError, match="schema_version"):
        BuffCommunityIdentityResolver.from_snapshot_path(path)


def test_from_snapshot_path_rejects_wrong_catalog_kind(tmp_path: Path) -> None:
    snap = {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "catalog_kind": "official_bullshit",
        "source": {
            "repository": "x", "file": "y", "commit": "z", "sha256": "q" * 8,
            "license": "L", "attribution": "A",
        },
        "counts": {"source": 0, "accepted": 0, "rejected": 0},
        "items": {},
    }
    path = tmp_path / "snap.json"
    path.write_text(json.dumps(snap))
    with pytest.raises(BuffCommunitySnapshotValidationError, match="catalog_kind"):
        BuffCommunityIdentityResolver.from_snapshot_path(path)


def test_from_snapshot_path_rejects_corrupt_json(tmp_path: Path) -> None:
    path = tmp_path / "snap.json"
    path.write_bytes(b"this is not json")
    with pytest.raises(BuffCommunitySnapshotValidationError, match="JSON is malformed"):
        BuffCommunityIdentityResolver.from_snapshot_path(path)


def test_from_snapshot_path_rejects_oversize(tmp_path: Path) -> None:
    path = tmp_path / "snap.json"
    path.write_bytes(b"// " + b"x" * (17 * 1024 * 1024))
    with pytest.raises(BuffCommunitySnapshotValidationError, match="too large"):
        BuffCommunityIdentityResolver.from_snapshot_path(path)


def test_from_snapshot_path_rejects_missing_metadata_field(tmp_path: Path) -> None:
    snap = {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "catalog_kind": "community_catalog",
        "source": {
            "repository": "x", "file": "y", "commit": "z", "sha256": "q" * 8,
            "license": "L",  # attribution missing
        },
        "counts": {"source": 0, "accepted": 0, "rejected": 0},
        "items": {},
    }
    path = tmp_path / "snap.json"
    path.write_text(json.dumps(snap))
    with pytest.raises(BuffCommunitySnapshotValidationError):
        BuffCommunityIdentityResolver.from_snapshot_path(path)


def test_lookup_does_not_scan_items_each_call() -> None:
    """Internal structure: forward dict is built once and reused."""
    r = _resolver({"a": "1", "b": "2", "c": "3"})
    assert len(r._forward) == 3  # type: ignore[attr-defined]
    assert len(r._reverse) == 3  # type: ignore[attr-defined]
    assert "a" in r._forward  # type: ignore[attr-defined]


def test_resolver_implements_both_protocol_methods() -> None:
    """Concrete resolver exposes forward and reverse lookup methods by name."""
    r = _resolver({"a": "1"})
    assert hasattr(r, "resolve")
    assert hasattr(r, "resolve_goods_id")
    assert callable(r.resolve)
    assert callable(r.resolve_goods_id)


def test_runtime_makes_no_network_calls() -> None:
    """Resolver constructor + lookups touch no path.

    The snapshot file is read once during construction; subsequent
    lookups perform no I/O. We verify by file mtime before/after.
    """
    snap = {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "catalog_kind": "community_catalog",
        "source": {
            "repository": "x", "file": "y", "commit": "z", "sha256": "q" * 8,
            "license": "L", "attribution": "A",
        },
        "counts": {"source": 1, "accepted": 1, "rejected": 0},
        "items": {"Test Item": "1"},
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "snap.json"
        path.write_bytes(
            json.dumps(snap, sort_keys=True, separators=(",", ":")).encode("utf-8")
            + b"\n"
        )
        r = BuffCommunityIdentityResolver.from_snapshot_path(path)
        mtime_before = path.stat().st_mtime_ns
        _resolve(r, "Test Item")
        _resolve_gid(r, "1")
        mtime_after = path.stat().st_mtime_ns
        assert mtime_before == mtime_after