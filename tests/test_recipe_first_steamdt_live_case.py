"""Phase 16G — Frozen Recipe-First + SteamDT live validation case tests.

These tests exercise the offline-only Phase 16G case module.
No network I/O is performed.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from app.services.market_universe_builder import StatTrakMode
from app.services.recipe_first_live_case import (
    LiveValidationPlanItem,
    freeze_case,
)
from app.services.recipe_first_steamdt_live_case import (
    LIVE_STEAMDT_CASE_SCHEMA_VERSION,
    RecipeFirstSteamDTCaseError,
    freeze_recipe_first_steamdt_case,
    hash_recipe_first_steamdt_case,
    serialize_recipe_first_steamdt_case,
)


def _buff_case() -> object:
    return freeze_case(
        repository_commit_oid="f" * 40,
        case_purpose="Phase 16G test",
        family_hash="a" * 64,
        family_key="a" * 24,
        input_rarity="Classified",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The Phoenix Collection", 10),),
        plan_items=(
            LiveValidationPlanItem(
                market_hash_name="AK-47 | Redline (Field-Tested)",
                goods_id="33960",
                collection_name="The Phoenix Collection",
                priority_within_collection=1,
            ),
        ),
    )


def test_freeze_case_accepts_valid_fixture() -> None:
    case = freeze_recipe_first_steamdt_case(
        repository_commit_oid="f" * 40,
        buff_case=_buff_case(),
        prescreen_market_hash_names=(
            "AK-47 | Redline (Field-Tested)",
            "AK-47 | Redline (Minimal Wear)",
        ),
    )
    assert case.case_schema_version == LIVE_STEAMDT_CASE_SCHEMA_VERSION
    assert len(case.prescreen_market_hash_names) == 2
    assert case.buff_http_cap == 1
    assert case.steamdt_batch_http_cap == 1
    assert case.steamdt_final_single_http_cap == 2
    assert case.steamdt_total_http_cap == 3


def test_freeze_case_rejects_too_many_prescreen_names() -> None:
    names = tuple(f"Item {i}" for i in range(11))
    with pytest.raises(RecipeFirstSteamDTCaseError, match="10"):
        freeze_recipe_first_steamdt_case(
            repository_commit_oid="f" * 40,
            buff_case=_buff_case(),
            prescreen_market_hash_names=names,
        )


def test_freeze_case_rejects_empty_prescreen_names() -> None:
    with pytest.raises(RecipeFirstSteamDTCaseError, match="between 1 and 10"):
        freeze_recipe_first_steamdt_case(
            repository_commit_oid="f" * 40,
            buff_case=_buff_case(),
            prescreen_market_hash_names=(),
        )


def test_freeze_case_rejects_duplicate_prescreen_names() -> None:
    with pytest.raises(RecipeFirstSteamDTCaseError, match="duplicates"):
        freeze_recipe_first_steamdt_case(
            repository_commit_oid="f" * 40,
            buff_case=_buff_case(),
            prescreen_market_hash_names=(
                "AK-47 | Redline (Field-Tested)",
                "AK-47 | Redline (Field-Tested)",
            ),
        )


def test_freeze_case_rejects_non_whitespace_oid() -> None:
    with pytest.raises(RecipeFirstSteamDTCaseError):
        freeze_recipe_first_steamdt_case(
            repository_commit_oid="  f",
            buff_case=_buff_case(),
            prescreen_market_hash_names=("AK-47 | Redline (Field-Tested)",),
        )


def test_serialize_case_is_deterministic() -> None:
    case = freeze_recipe_first_steamdt_case(
        repository_commit_oid="f" * 40,
        buff_case=_buff_case(),
        prescreen_market_hash_names=("AK-47 | Redline (Field-Tested)",),
    )
    first = serialize_recipe_first_steamdt_case(case)
    second = serialize_recipe_first_steamdt_case(case)
    assert first == second
    assert not first.endswith(b"\n")


def test_hash_case_equals_sha256_of_serialize_case() -> None:
    case = freeze_recipe_first_steamdt_case(
        repository_commit_oid="f" * 40,
        buff_case=_buff_case(),
        prescreen_market_hash_names=("AK-47 | Redline (Field-Tested)",),
    )
    serialized = serialize_recipe_first_steamdt_case(case)
    assert hashlib.sha256(serialized).hexdigest() == hash_recipe_first_steamdt_case(case)


def test_serialize_case_excludes_untrusted_fields() -> None:
    case = freeze_recipe_first_steamdt_case(
        repository_commit_oid="f" * 40,
        buff_case=_buff_case(),
        prescreen_market_hash_names=("AK-47 | Redline (Field-Tested)",),
    )
    raw = serialize_recipe_first_steamdt_case(case).decode("utf-8")
    for forbidden in (
        "listing_id",
        "asset_id",
        "paintwear",
        "price_cny",
        "api_key",
        "cookie",
        "secret",
    ):
        assert forbidden not in raw, f"forbidden field {forbidden!r} leaked"


def test_case_construction_is_reproducible() -> None:
    args = {
        "repository_commit_oid": "f" * 40,
        "buff_case": _buff_case(),
        "prescreen_market_hash_names": ("AK-47 | Redline (Field-Tested)",),
    }
    a = freeze_recipe_first_steamdt_case(**args)
    b = freeze_recipe_first_steamdt_case(**args)
    assert hash_recipe_first_steamdt_case(a) == hash_recipe_first_steamdt_case(b)


def test_prescreen_names_cannot_be_string() -> None:
    with pytest.raises(RecipeFirstSteamDTCaseError):
        freeze_recipe_first_steamdt_case(
            repository_commit_oid="f" * 40,
            buff_case=_buff_case(),
            prescreen_market_hash_names="AK-47 | Redline (Field-Tested)",
        )


def test_case_rejects_non_buff_case_type() -> None:
    with pytest.raises(RecipeFirstSteamDTCaseError, match="buff_case"):
        freeze_recipe_first_steamdt_case(
            repository_commit_oid="f" * 40,
            buff_case="not-a-case",
            prescreen_market_hash_names=("AK-47 | Redline (Field-Tested)",),
        )


def test_cap_constants_match_project_bounds() -> None:
    case = freeze_recipe_first_steamdt_case(
        repository_commit_oid="f" * 40,
        buff_case=_buff_case(),
        prescreen_market_hash_names=("AK-47 | Redline (Field-Tested)",),
    )
    assert case.buff_http_cap == 1
    assert case.steamdt_batch_http_cap == 1
    assert case.steamdt_final_single_http_cap == 2
    assert case.steamdt_total_http_cap == 3


def test_persisted_case_round_trip_loads_cleanly() -> None:
    case = freeze_recipe_first_steamdt_case(
        repository_commit_oid="f" * 40,
        buff_case=_buff_case(),
        prescreen_market_hash_names=(
            "AK-47 | Redline (Field-Tested)",
            "AK-47 | Redline (Minimal Wear)",
        ),
    )
    serialized = serialize_recipe_first_steamdt_case(case)
    payload = json.loads(serialized)
    assert payload["case_schema_version"] == LIVE_STEAMDT_CASE_SCHEMA_VERSION
    assert payload["repository_commit_oid"] == "f" * 40
    assert payload["steamdt_total_http_cap"] == 3