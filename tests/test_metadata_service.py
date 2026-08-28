import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.metadata_service import (
    build_output_candidates_by_collection,
    get_next_rarity,
    normalize_skin,
    normalize_skins,
)

FIXTURE_PATH = Path("tests/fixtures/metadata/sample_skins.json")



def _load_fixture() -> list[dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))



def test_normalize_skin_normal_case() -> None:
    raw = {
        "market_hash_name": "AK-47 | Redline (Field-Tested)",
        "name": "AK-47 | Redline (Field-Tested)",
        "weapon": "AK-47",
        "rarity": "Classified",
        "collection_name": "Collection Alpha",
        "min_float": 0.10,
        "max_float": 0.70,
    }

    skin = normalize_skin(raw)

    assert skin.market_hash_name == "AK-47 | Redline (Field-Tested)"
    assert skin.collection_name == "Collection Alpha"
    assert skin.raw == raw



def test_normalize_skin_uses_name_fallback_for_market_hash_name() -> None:
    raw = {
        "name": "Fallback Skin Name",
        "rarity": "Restricted",
        "min_float": 0.10,
        "max_float": 0.60,
    }

    skin = normalize_skin(raw)

    assert skin.market_hash_name == "Fallback Skin Name"
    assert skin.name == "Fallback Skin Name"
    assert skin.raw == raw



def test_normalize_skin_raises_when_market_hash_name_and_name_missing() -> None:
    raw = {
        "rarity": "Restricted",
        "min_float": 0.10,
        "max_float": 0.60,
    }

    with pytest.raises(ValueError, match="market_hash_name"):
        normalize_skin(raw)



def test_normalize_skin_raises_when_rarity_missing() -> None:
    raw = {
        "market_hash_name": "Valid Name",
        "min_float": 0.10,
        "max_float": 0.60,
    }

    with pytest.raises(ValueError, match="rarity"):
        normalize_skin(raw)



def test_normalize_skin_raises_when_min_float_missing() -> None:
    raw = {
        "market_hash_name": "Valid Name",
        "rarity": "Restricted",
        "max_float": 0.60,
    }

    with pytest.raises(ValueError, match="min_float"):
        normalize_skin(raw)



def test_normalize_skin_raises_when_max_float_missing() -> None:
    raw = {
        "market_hash_name": "Valid Name",
        "rarity": "Restricted",
        "min_float": 0.10,
    }

    with pytest.raises(ValueError, match="max_float"):
        normalize_skin(raw)



def test_get_next_rarity_returns_expected_values() -> None:
    assert get_next_rarity("Restricted") == "Classified"
    assert get_next_rarity("Classified") == "Covert"
    assert get_next_rarity("Covert") is None



def test_build_output_candidates_by_collection_constructs_candidates() -> None:
    skins = normalize_skins(_load_fixture())

    candidates = build_output_candidates_by_collection(skins, "Restricted")

    assert "Collection Alpha" in candidates
    assert "Collection Beta" in candidates
    assert len(candidates["Collection Alpha"]) == 2
    assert len(candidates["Collection Beta"]) == 1



def test_build_output_candidates_skips_none_collection_names() -> None:
    skins = normalize_skins(_load_fixture())

    candidates = build_output_candidates_by_collection(skins, "Classified")

    assert "Collection Gamma" not in candidates
    assert "Collection Alpha" not in candidates



def test_build_output_candidates_returns_empty_when_no_next_rarity_exists() -> None:
    skins = normalize_skins(_load_fixture())

    candidates = build_output_candidates_by_collection(skins, "Covert")

    assert candidates == {}



def test_output_candidates_use_zero_estimated_price_placeholder() -> None:
    skins = normalize_skins(_load_fixture())

    candidates = build_output_candidates_by_collection(skins, "Restricted")

    assert candidates["Collection Alpha"][0].estimated_price_cny == Decimal("0")
