"""Phase 16B — Structural output finish index tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.metadata_models import SkinMetadata
from app.services.structural_output_finish import (
    StructuralOutputFinishIndex,
    StructuralOutputFinishIndexError,
    WearMarketMapping,
    compute_finish_key,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "metadata"


def _skin(**kwargs: object) -> SkinMetadata:
    defaults: dict[str, object] = {
        "market_hash_name": "AWP | PAW (Factory New)",
        "name": "AWP | PAW",
        "weapon": "AWP",
        "rarity": "Restricted",
        "category": "Rifles",
        "collection_name": "The Horizon Collection",
        "min_float": 0.0,
        "max_float": 0.5,
        "stattrak": False,
        "souvenir": False,
        "paint_index": None,
        "raw": None,
    }
    defaults.update(kwargs)
    return SkinMetadata(**defaults)  # type: ignore[arg-type]


def test_canonical_wear_order_deterministic() -> None:
    finish = StructuralOutputFinishIndex.from_skins(
        [
            _skin(market_hash_name="AWP | PAW (Battle-Scarred)"),
            _skin(market_hash_name="AWP | PAW (Factory New)"),
            _skin(market_hash_name="AWP | PAW (Well-Worn)"),
            _skin(market_hash_name="AWP | PAW (Field-Tested)"),
            _skin(market_hash_name="AWP | PAW (Minimal Wear)"),
        ]
    )
    [finish_dto] = finish.finishes
    wear_names = [wm.wear_name for wm in finish_dto.wear_market_names]
    assert wear_names == [
        "Factory New",
        "Minimal Wear",
        "Field-Tested",
        "Well-Worn",
        "Battle-Scarred",
    ]


def test_finish_key_collision_free_under_six_tuple() -> None:
    # Two distinct finishes (AWP | PAW vs MP9 | Goo) in the same collection.
    rows = [
        _skin(
            market_hash_name="AWP | PAW (Factory New)",
            name="AWP | PAW",
            weapon="AWP",
            min_float=0.0,
            max_float=0.5,
        ),
        _skin(
            market_hash_name="MP9 | Goo (Factory New)",
            name="MP9 | Goo",
            weapon="MP9",
            min_float=0.0,
            max_float=0.6,
        ),
    ]
    index = StructuralOutputFinishIndex.from_skins(rows)
    assert len(index.finishes) == 2
    keys = {f.finish_key for f in index.finishes}
    assert len(keys) == 2


def test_min_max_mismatch_within_one_finish_fails_closed() -> None:
    rows = [
        _skin(
            market_hash_name="AWP | PAW (Factory New)",
            min_float=0.0,
            max_float=0.5,
        ),
        _skin(
            market_hash_name="AWP | PAW (Minimal Wear)",
            min_float=0.0,
            max_float=0.4,
        ),
    ]
    with pytest.raises(StructuralOutputFinishIndexError):
        StructuralOutputFinishIndex.from_skins(rows)


def test_souvenir_rows_excluded_from_output_wear_map() -> None:
    rows = [
        _skin(
            market_hash_name="AWP | PAW (Factory New)",
            min_float=0.0,
            max_float=0.5,
        ),
        _skin(
            market_hash_name="Souvenir AWP | PAW (Factory New)",
            souvenir=True,
            min_float=0.0,
            max_float=0.5,
        ),
    ]
    finish_index = StructuralOutputFinishIndex.from_skins(rows)
    [finish_dto] = finish_index.finishes
    assert len(finish_dto.wear_market_names) == 1
    assert finish_dto.wear_market_names[0].market_hash_name == (
        "AWP | PAW (Factory New)"
    )


def test_duplicate_exact_row_fails_closed() -> None:
    rows = [
        _skin(market_hash_name="AWP | PAW (Factory New)"),
        _skin(market_hash_name="AWP | PAW (Factory New)"),
    ]
    with pytest.raises(StructuralOutputFinishIndexError):
        StructuralOutputFinishIndex.from_skins(rows)


def test_unparsable_wear_suffix_fails_closed() -> None:
    rows = [_skin(market_hash_name="AWP | PAW")]
    with pytest.raises(StructuralOutputFinishIndexError):
        StructuralOutputFinishIndex.from_skins(rows)


def test_by_finish_key_lookup() -> None:
    finish_index = StructuralOutputFinishIndex.from_skins([_skin()])
    [finish_dto] = finish_index.finishes
    looked_up = finish_index.by_finish_key(finish_dto.finish_key)
    assert looked_up is finish_dto
    assert finish_index.by_finish_key("not-a-real-key") is None


def test_resolve_wear_market_hash_name() -> None:
    finish_index = StructuralOutputFinishIndex.from_skins(
        [
            _skin(market_hash_name="AWP | PAW (Factory New)"),
            _skin(market_hash_name="AWP | PAW (Minimal Wear)"),
        ]
    )
    [finish_dto] = finish_index.finishes
    assert (
        finish_index.resolve_wear_market_hash_name(
            finish_key=finish_dto.finish_key, wear_name="Factory New"
        )
        == "AWP | PAW (Factory New)"
    )
    assert (
        finish_index.resolve_wear_market_hash_name(
            finish_key=finish_dto.finish_key, wear_name="Minimal Wear"
        )
        == "AWP | PAW (Minimal Wear)"
    )
    # Missing wear -> None (fail closed).
    assert (
        finish_index.resolve_wear_market_hash_name(
            finish_key=finish_dto.finish_key, wear_name="Battle-Scarred"
        )
        is None
    )


def test_source_row_order_permutation_is_stable() -> None:
    rows_a = [
        _skin(market_hash_name="AWP | PAW (Factory New)"),
        _skin(market_hash_name="AWP | PAW (Minimal Wear)"),
    ]
    rows_b = list(reversed(rows_a))
    index_a = StructuralOutputFinishIndex.from_skins(rows_a)
    index_b = StructuralOutputFinishIndex.from_skins(rows_b)
    assert [f.finish_key for f in index_a.finishes] == [
        f.finish_key for f in index_b.finishes
    ]
    [fa] = index_a.finishes
    [fb] = index_b.finishes
    assert fa.wear_market_names == fb.wear_market_names


def test_finish_key_hash_matches_expected_canonical_bytes() -> None:
    canonical_payload = {
        "finish_spec_version": 1,
        "collection_name": "The Horizon Collection",
        "rarity": "Restricted",
        "stattrak": False,
        "base_name": "AWP | PAW",
        "weapon": "AWP",
        "paint_index": None,
    }
    expected = hashlib.sha256(
        json.dumps(
            canonical_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    actual = compute_finish_key(
        collection_name="The Horizon Collection",
        rarity="Restricted",
        stattrak=False,
        base_name="AWP | PAW",
        weapon="AWP",
        paint_index=None,
    )
    assert actual == expected


def test_finish_index_offline_against_pinned_snapshot() -> None:
    snapshot_path = DATA_DIR / "skin_metadata_v1.json"
    if not snapshot_path.exists():
        pytest.skip("pinned snapshot not present")
    payload = json.loads(snapshot_path.read_bytes())
    items = payload["items"]
    skins: list[SkinMetadata] = []
    for it in items:
        skins.append(
            SkinMetadata(
                market_hash_name=it["market_hash_name"],
                name=it.get("name"),
                weapon=it.get("weapon"),
                rarity=it["rarity"],
                category=it.get("category"),
                collection_name=it.get("collection_name"),
                min_float=it["min_float"],
                max_float=it["max_float"],
                stattrak=bool(it.get("stattrak", False)),
                souvenir=bool(it.get("souvenir", False)),
                paint_index=it.get("paint_index"),
                raw=None,
            )
        )

    finish_index = StructuralOutputFinishIndex.from_skins(skins)
    # Frozen Phase 16A-R2 audit numbers:
    assert len(skins) == 16868
    assert len(finish_index.finishes) == 2148
    # No finish_key collision.
    keys = [f.finish_key for f in finish_index.finishes]
    assert len(set(keys)) == 2148


def test_wear_market_mapping_dataclass_rejects_bad_inputs() -> None:
    with pytest.raises(StructuralOutputFinishIndexError):
        WearMarketMapping(wear_name="", market_hash_name="X")
    with pytest.raises(StructuralOutputFinishIndexError):
        WearMarketMapping(wear_name="Factory New", market_hash_name="")
    with pytest.raises(StructuralOutputFinishIndexError):
        WearMarketMapping(
            wear_name="NotARealWear",
            market_hash_name="AWP | PAW (NotARealWear)",
        )