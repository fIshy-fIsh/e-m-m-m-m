"""Phase 16G — Frozen Recipe-First + SteamDT live validation case DTO.

Phase 16G composes the corrected Phase 16F-R2 BUFF case with a
pre-screen name set, exact HTTP caps, and explicit caps for the
SteamDT strict batch pre-screen and final single valuation. The case
is serialized to canonical UTF-8 JSON outside Git; the SHA-256 of the
persisted bytes is the authoritative case artifact identity.

Schema version 1. v1 artifacts are not silently reinterpreted.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from app.services.recipe_first_live_case import LiveValidationCase

__all__ = (
    "LIVE_STEAMDT_CASE_SCHEMA_VERSION",
    "RecipeFirstSteamDTCase",
    "RecipeFirstSteamDTCaseError",
    "freeze_recipe_first_steamdt_case",
    "hash_recipe_first_steamdt_case",
    "serialize_recipe_first_steamdt_case",
)

LIVE_STEAMDT_CASE_SCHEMA_VERSION: Final[int] = 1
_MAX_PRESCREEN_NAMES: Final[int] = 10
_DEFAULT_BUFF_CAP: Final[int] = 1
_DEFAULT_STEAMDT_BATCH_CAP: Final[int] = 1
_DEFAULT_STEAMDT_FINAL_SINGLE_CAP: Final[int] = 2
_DEFAULT_STEAMDT_TOTAL_CAP: Final[int] = 3


class RecipeFirstSteamDTCaseError(ValueError):
    """A frozen Phase 16G validation case violated its strict contract."""


def _exact(value: object, *, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise RecipeFirstSteamDTCaseError(
            f"{field} must be an exact non-empty string"
        )
    return value


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFirstSteamDTCase:
    """Immutable Phase 16G validation case."""

    case_schema_version: int
    repository_commit_oid: str
    buff_case: LiveValidationCase
    prescreen_market_hash_names: tuple[str, ...]
    buff_http_cap: int
    steamdt_batch_http_cap: int
    steamdt_final_single_http_cap: int
    steamdt_total_http_cap: int

    def __post_init__(self) -> None:
        if (
            type(self.case_schema_version) is not int
            or self.case_schema_version != LIVE_STEAMDT_CASE_SCHEMA_VERSION
        ):
            raise RecipeFirstSteamDTCaseError(
                f"case_schema_version must equal {LIVE_STEAMDT_CASE_SCHEMA_VERSION}"
            )
        if not isinstance(self.buff_case, LiveValidationCase):
            raise RecipeFirstSteamDTCaseError("buff_case must be LiveValidationCase")
        if not isinstance(self.prescreen_market_hash_names, tuple) or not all(
            type(name) is str and name and name == name.strip()
            for name in self.prescreen_market_hash_names
        ):
            raise RecipeFirstSteamDTCaseError(
                "prescreen_market_hash_names must be tuple of exact strings"
            )
        if len(set(self.prescreen_market_hash_names)) != len(
            self.prescreen_market_hash_names
        ):
            raise RecipeFirstSteamDTCaseError(
                "prescreen_market_hash_names contains duplicates"
            )
        if not (1 <= len(self.prescreen_market_hash_names) <= _MAX_PRESCREEN_NAMES):
            raise RecipeFirstSteamDTCaseError(
                "prescreen_market_hash_names must be between 1 and 10 inclusive"
            )
        for cap_name, cap_value in (
            ("buff_http_cap", self.buff_http_cap),
            ("steamdt_batch_http_cap", self.steamdt_batch_http_cap),
            ("steamdt_final_single_http_cap", self.steamdt_final_single_http_cap),
            ("steamdt_total_http_cap", self.steamdt_total_http_cap),
        ):
            if type(cap_value) is not int or cap_value <= 0:
                raise RecipeFirstSteamDTCaseError(
                    f"{cap_name} must be a positive int"
                )
        if self.buff_http_cap != _DEFAULT_BUFF_CAP:
            raise RecipeFirstSteamDTCaseError(
                f"buff_http_cap must equal {_DEFAULT_BUFF_CAP}"
            )
        if self.steamdt_batch_http_cap != _DEFAULT_STEAMDT_BATCH_CAP:
            raise RecipeFirstSteamDTCaseError(
                f"steamdt_batch_http_cap must equal {_DEFAULT_STEAMDT_BATCH_CAP}"
            )
        if self.steamdt_final_single_http_cap != _DEFAULT_STEAMDT_FINAL_SINGLE_CAP:
            raise RecipeFirstSteamDTCaseError(
                f"steamdt_final_single_http_cap must equal {_DEFAULT_STEAMDT_FINAL_SINGLE_CAP}"
            )
        if self.steamdt_total_http_cap != _DEFAULT_STEAMDT_TOTAL_CAP:
            raise RecipeFirstSteamDTCaseError(
                f"steamdt_total_http_cap must equal {_DEFAULT_STEAMDT_TOTAL_CAP}"
            )


def freeze_recipe_first_steamdt_case(
    *,
    repository_commit_oid: str,
    buff_case: LiveValidationCase,
    prescreen_market_hash_names: Sequence[str],
) -> RecipeFirstSteamDTCase:
    """Build a frozen Phase 16G validation case."""

    _exact(repository_commit_oid, field="repository_commit_oid")
    return RecipeFirstSteamDTCase(
        case_schema_version=LIVE_STEAMDT_CASE_SCHEMA_VERSION,
        repository_commit_oid=repository_commit_oid,
        buff_case=buff_case,
        prescreen_market_hash_names=tuple(prescreen_market_hash_names),
        buff_http_cap=_DEFAULT_BUFF_CAP,
        steamdt_batch_http_cap=_DEFAULT_STEAMDT_BATCH_CAP,
        steamdt_final_single_http_cap=_DEFAULT_STEAMDT_FINAL_SINGLE_CAP,
        steamdt_total_http_cap=_DEFAULT_STEAMDT_TOTAL_CAP,
    )


def serialize_recipe_first_steamdt_case(
    case: RecipeFirstSteamDTCase,
) -> bytes:
    """Serialize a frozen Phase 16G case to deterministic canonical UTF-8 JSON bytes."""

    if type(case) is not RecipeFirstSteamDTCase:
        raise RecipeFirstSteamDTCaseError("case must be RecipeFirstSteamDTCase")
    buff_bytes = json.loads(
        json.dumps(
            {
                "case_purpose": case.buff_case.case_purpose,
                "case_schema_version": case.buff_case.case_schema_version,
                "collection_counts": [
                    [name, int(count)]
                    for name, count in sorted(case.buff_case.collection_counts)
                ],
                "family_hash": case.buff_case.family_hash,
                "family_key": case.buff_case.family_key,
                "hard_request_count": case.buff_case.hard_request_count,
                "input_rarity": case.buff_case.input_rarity,
                "plan_items": [
                    {
                        "collection_name": item.collection_name,
                        "goods_id": item.goods_id,
                        "market_hash_name": item.market_hash_name,
                        "priority_within_collection": item.priority_within_collection,
                    }
                    for item in sorted(
                        case.buff_case.plan_items,
                        key=lambda entry: (
                            entry.collection_name,
                            entry.priority_within_collection,
                            entry.market_hash_name,
                            entry.goods_id,
                        ),
                    )
                ],
                "repository_commit_oid": case.buff_case.repository_commit_oid,
                "stattrak_mode": case.buff_case.stattrak_mode.value,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    payload: dict[str, object] = {
        "buff_case": buff_bytes,
        "buff_http_cap": case.buff_http_cap,
        "case_purpose": (
            "Phase 16G bounded recipe-first SteamDT pre-screen + "
            "final-valuation live validation; one corrected Classified "
            "family and one anonymous BUFF page."
        ),
        "case_schema_version": case.case_schema_version,
        "prescreen_market_hash_names": list(case.prescreen_market_hash_names),
        "repository_commit_oid": case.repository_commit_oid,
        "steamdt_batch_http_cap": case.steamdt_batch_http_cap,
        "steamdt_final_single_http_cap": case.steamdt_final_single_http_cap,
        "steamdt_total_http_cap": case.steamdt_total_http_cap,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def hash_recipe_first_steamdt_case(case: RecipeFirstSteamDTCase) -> str:
    """Return SHA-256 hex of canonical Phase 16G case bytes."""

    if type(case) is not RecipeFirstSteamDTCase:
        raise RecipeFirstSteamDTCaseError("case must be RecipeFirstSteamDTCase")
    return hashlib.sha256(serialize_recipe_first_steamdt_case(case)).hexdigest()