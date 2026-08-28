from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.skin_metadata_resolver import (
    PinnedSkinMetadataResolver,
    SkinMetadataSnapshotValidationError,
)


def _entry(
    name: str = "AK-47 | Redline (Field-Tested)",
    *,
    collection: str = "Test Collection",
    rarity: str = "Restricted",
    min_float: float = 0.10,
    max_float: float = 0.70,
) -> dict[str, object]:
    return {
        "market_hash_name": name,
        "collection_name": collection,
        "rarity": rarity,
        "min_float": min_float,
        "max_float": max_float,
        "name": name.split(" (")[0],
        "weapon": "AK-47",
        "category": "Rifle",
        "stattrak": name.startswith("StatTrak™ "),
        "souvenir": name.startswith("Souvenir "),
        "paint_index": 282,
    }


def test_exact_lookup_success() -> None:
    resolver = PinnedSkinMetadataResolver.from_payload([_entry()])
    metadata = resolver.resolve("AK-47 | Redline (Field-Tested)")
    assert metadata is not None
    assert metadata.collection_name == "Test Collection"
    assert metadata.rarity == "Restricted"
    assert metadata.min_float == 0.10
    assert metadata.max_float == 0.70


def test_unknown_exact_name_returns_none() -> None:
    resolver = PinnedSkinMetadataResolver.from_payload([_entry()])
    assert resolver.resolve("AK-47 | Unknown (Field-Tested)") is None


def test_case_difference_does_not_match() -> None:
    resolver = PinnedSkinMetadataResolver.from_payload([_entry()])
    assert resolver.resolve("ak-47 | redline (field-tested)") is None


def test_whitespace_difference_does_not_match() -> None:
    resolver = PinnedSkinMetadataResolver.from_payload([_entry()])
    assert resolver.resolve(" AK-47 | Redline (Field-Tested)") is None
    assert resolver.resolve("AK-47 | Redline (Field-Tested) ") is None


def test_special_unicode_preserved() -> None:
    name = "StatTrak™ ★ Karambit | Doppler (Factory New)"
    resolver = PinnedSkinMetadataResolver.from_payload([_entry(name)])
    metadata = resolver.resolve(name)
    assert metadata is not None
    assert metadata.market_hash_name == name


def test_malformed_catalog_fails_closed() -> None:
    with pytest.raises(SkinMetadataSnapshotValidationError):
        PinnedSkinMetadataResolver.from_payload({"items": [{"bad": "row"}]})


def test_duplicate_exact_key_fails_closed() -> None:
    row = _entry()
    with pytest.raises(SkinMetadataSnapshotValidationError):
        PinnedSkinMetadataResolver.from_payload([row, dict(row)])


def test_metadata_validation_rejects_invalid_float_range() -> None:
    with pytest.raises(SkinMetadataSnapshotValidationError):
        PinnedSkinMetadataResolver.from_payload(
            [_entry(min_float=0.8, max_float=0.7)]
        )


def test_index_is_loaded_once_and_lookup_is_o1() -> None:
    resolver = PinnedSkinMetadataResolver.from_payload(
        [_entry(f"Test Skin {index} (Factory New)") for index in range(100)]
    )
    assert len(resolver._index) == 100  # type: ignore[attr-defined]
    assert resolver.resolve("Test Skin 99 (Factory New)") is not None


def test_static_snapshot_runtime_has_no_network(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"items": [_entry()]}), encoding="utf-8")
    resolver = PinnedSkinMetadataResolver.from_snapshot_path(path)
    assert resolver.resolve("AK-47 | Redline (Field-Tested)") is not None


def test_memory_error_propagates() -> None:
    class MappingRaisesMemory(dict):
        def get(self, key, default=None):  # type: ignore[no-untyped-def]
            raise MemoryError("sentinel")

    resolver = PinnedSkinMetadataResolver(
        _index=MappingRaisesMemory(),
        _skins=(),
    )
    with pytest.raises(MemoryError, match="sentinel"):
        resolver.resolve("AK-47 | Redline (Field-Tested)")


def test_pinned_catalog_loads() -> None:
    path = Path("data/metadata/skin_metadata_v1.json")
    if not path.exists():
        pytest.skip("pinned metadata snapshot not present")
    resolver = PinnedSkinMetadataResolver.from_snapshot_path(path)
    assert len(resolver._index) == 16868  # type: ignore[attr-defined]
    assert len(resolver.skins) == 16868
    metadata = resolver.resolve("AK-47 | Redline (Field-Tested)")
    assert metadata is not None
    assert metadata.collection_name == "The Phoenix Collection"
