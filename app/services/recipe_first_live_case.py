"""Phase 16F — Frozen live-validation case DTO + serialization.

This module freezes the deterministic Phase 16F validation case used to
exercise the recipe-first BUFF acquisition interface against the
anonymous sell-order endpoint exactly once.

The case content is fully serializable and contains NO:

- raw BUFF payload
- seller / account / listing_id data
- cookies / authorization headers
- secret / credential / webhook data

Identity is bound through the pinned BUFF community identity snapshot
via the :func:`verify_case_identity` function before any HTTP dispatch.
The case is serialized outside Git by the live runner; the SHA-256 of
its canonical bytes is the immutable case identity.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.market_universe_builder import StatTrakMode

__all__ = (
    "LIVE_CASE_SCHEMA_VERSION",
    "LiveValidationCase",
    "LiveValidationCaseError",
    "LiveValidationPlanItem",
    "freeze_case",
    "hash_case",
    "serialize_case",
    "verify_case_identity",
)

LIVE_CASE_SCHEMA_VERSION: Final[int] = 1
_PLAN_ITEMS_HARD_CAP: Final[int] = 10
_INPUT_COUNT: Final[int] = 10


class LiveValidationCaseError(ValueError):
    """A frozen Phase 16F validation case violated its strict contract."""


def _exact(value: object, *, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise LiveValidationCaseError(f"{field} must be an exact non-empty string")
    return value


def _exact_hex64(value: object, *, field: str) -> str:
    exact = _exact(value, field=field)
    if len(exact) != 64 or any(ch not in "0123456789abcdef" for ch in exact):
        raise LiveValidationCaseError(f"{field} must be full lowercase SHA-256 hex")
    return exact


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveValidationPlanItem:
    """One deterministic planned BUFF goods-page request."""

    market_hash_name: str
    goods_id: str
    collection_name: str
    priority_within_collection: int

    def __post_init__(self) -> None:
        _exact(self.market_hash_name, field="market_hash_name")
        _exact(self.goods_id, field="goods_id")
        _exact(self.collection_name, field="collection_name")
        if (
            type(self.priority_within_collection) is not int
            or isinstance(self.priority_within_collection, bool)
            or self.priority_within_collection < 1
        ):
            raise LiveValidationCaseError(
                "priority_within_collection must be a positive integer"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class LiveValidationCase:
    """Immutable Phase 16F validation case.

    The case freezes:

    - exact repository HEAD SHA at preparation time
    - one immutable :class:`app.services.recipe_family.RecipeFamily`
      structural composition (hash / key / rarity / StatTrak mode /
      collection counts)
    - one deterministic active plan with at most ten distinct
      goods_ids and exact market names
    """

    case_schema_version: int
    repository_head_sha: str
    case_purpose: str
    family_hash: str
    family_key: str
    input_rarity: str
    stattrak_mode: StatTrakMode
    collection_counts: tuple[tuple[str, int], ...]
    plan_items: tuple[LiveValidationPlanItem, ...]
    hard_request_count: int

    def __post_init__(self) -> None:
        if (
            type(self.case_schema_version) is not int
            or self.case_schema_version != LIVE_CASE_SCHEMA_VERSION
        ):
            raise LiveValidationCaseError(
                f"case_schema_version must equal {LIVE_CASE_SCHEMA_VERSION}"
            )
        _exact_hex64(self.repository_head_sha, field="repository_head_sha")
        _exact(self.case_purpose, field="case_purpose")
        _exact_hex64(self.family_hash, field="family_hash")
        if (
            type(self.family_key) is not str
            or len(self.family_key) != 24
            or self.family_key != self.family_hash[:24]
        ):
            raise LiveValidationCaseError(
                "family_key must be first 24 hex characters of family_hash"
            )
        _exact(self.input_rarity, field="input_rarity")
        if not isinstance(self.stattrak_mode, StatTrakMode):
            raise LiveValidationCaseError("stattrak_mode must be StatTrakMode")
        if (
            not isinstance(self.collection_counts, tuple)
            or not self.collection_counts
            or any(
                type(entry) is not tuple or len(entry) != 2
                for entry in self.collection_counts
            )
        ):
            raise LiveValidationCaseError(
                "collection_counts must be a non-empty tuple of (name, count) pairs"
            )
        seen: set[str] = set()
        total = 0
        for entry in self.collection_counts:
            name = _exact(entry[0], field="collection_name")
            if name in seen:
                raise LiveValidationCaseError(
                    "collection_counts contains duplicate collection_name"
                )
            seen.add(name)
            count = entry[1]
            if (
                type(count) is not int
                or isinstance(count, bool)
                or count <= 0
            ):
                raise LiveValidationCaseError(
                    "collection count must be a positive integer"
                )
            total += count
        if total != _INPUT_COUNT:
            raise LiveValidationCaseError(
                f"sum(collection_counts) must equal {_INPUT_COUNT}"
            )
        if (
            not isinstance(self.plan_items, tuple)
            or not self.plan_items
            or any(
                type(item) is not LiveValidationPlanItem
                for item in self.plan_items
            )
        ):
            raise LiveValidationCaseError(
                "plan_items must be a non-empty tuple of LiveValidationPlanItem"
            )
        if (
            type(self.hard_request_count) is not int
            or self.hard_request_count != len(self.plan_items)
        ):
            raise LiveValidationCaseError(
                "hard_request_count must equal len(plan_items)"
            )
        if self.hard_request_count > _PLAN_ITEMS_HARD_CAP:
            raise LiveValidationCaseError(
                "hard_request_count exceeds project cap of 10"
            )
        names = tuple(item.market_hash_name for item in self.plan_items)
        goods_ids = tuple(item.goods_id for item in self.plan_items)
        if len(set(names)) != len(names):
            raise LiveValidationCaseError(
                "plan_items contain duplicate market_hash_name"
            )
        if len(set(goods_ids)) != len(goods_ids):
            raise LiveValidationCaseError(
                "plan_items contain duplicate goods_id"
            )
        plan_collections = {item.collection_name for item in self.plan_items}
        family_collections = {name for name, _ in self.collection_counts}
        if plan_collections != family_collections:
            raise LiveValidationCaseError(
                "plan_items collections must exactly cover family collections"
            )


def freeze_case(
    *,
    repository_head_sha: str,
    case_purpose: str,
    family_hash: str,
    family_key: str,
    input_rarity: str,
    stattrak_mode: StatTrakMode,
    collection_counts: Sequence[tuple[str, int]],
    plan_items: Sequence[LiveValidationPlanItem],
) -> LiveValidationCase:
    """Build a frozen validation case from validated offline inputs.

    The caller MUST have already verified the inputs (e.g. by
    reverse-resolving every goods_id through the pinned identity
    snapshot). The freeze operation is pure construction.
    """

    return LiveValidationCase(
        case_schema_version=LIVE_CASE_SCHEMA_VERSION,
        repository_head_sha=repository_head_sha,
        case_purpose=case_purpose,
        family_hash=family_hash,
        family_key=family_key,
        input_rarity=input_rarity,
        stattrak_mode=stattrak_mode,
        collection_counts=tuple(
            (str(name), int(count)) for name, count in collection_counts
        ),
        plan_items=tuple(plan_items),
        hard_request_count=len(plan_items),
    )


def serialize_case(case: LiveValidationCase) -> bytes:
    """Serialize a frozen case into deterministic canonical UTF-8 JSON bytes.

    Encoding is sorted-key, compact separators, ``ensure_ascii=False``,
    so two structurally equal cases produce byte-equal output.
    """

    if type(case) is not LiveValidationCase:
        raise LiveValidationCaseError("case must be LiveValidationCase")
    payload: dict[str, object] = {
        "case_purpose": case.case_purpose,
        "case_schema_version": case.case_schema_version,
        "collection_counts": [
            [name, int(count)] for name, count in sorted(case.collection_counts)
        ],
        "family_hash": case.family_hash,
        "family_key": case.family_key,
        "hard_request_count": case.hard_request_count,
        "input_rarity": case.input_rarity,
        "plan_items": [
            {
                "collection_name": item.collection_name,
                "goods_id": item.goods_id,
                "market_hash_name": item.market_hash_name,
                "priority_within_collection": item.priority_within_collection,
            }
            for item in sorted(
                case.plan_items,
                key=lambda entry: (
                    entry.collection_name,
                    entry.priority_within_collection,
                    entry.market_hash_name,
                    entry.goods_id,
                ),
            )
        ],
        "repository_head_sha": case.repository_head_sha,
        "stattrak_mode": case.stattrak_mode.value,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def hash_case(case: LiveValidationCase) -> str:
    """Return SHA-256 hex hash of canonical case bytes."""

    if type(case) is not LiveValidationCase:
        raise LiveValidationCaseError("case must be LiveValidationCase")
    return hashlib.sha256(serialize_case(case)).hexdigest()


async def verify_case_identity(
    case: LiveValidationCase,
    *,
    identity_resolver: BuffCommunityIdentityResolver,
) -> None:
    """Reverse-prove every plan goods_id against the pinned identity snapshot.

    Each plan item MUST:

    - be present in the pinned snapshot;
    - resolve to its exact declared ``market_hash_name``;
    - resolve to its exact declared ``goods_id``.

    Raises :class:`LiveValidationCaseError` on any mismatch.

    The resolver may be any object exposing
    ``async resolve_goods_id(goods_id) -> BuffItemIdentity | None``;
    this is satisfied by both the pinned snapshot and test stubs.
    """

    if type(case) is not LiveValidationCase:
        raise LiveValidationCaseError("case must be LiveValidationCase")
    if not hasattr(identity_resolver, "resolve_goods_id"):
        raise LiveValidationCaseError(
            "identity_resolver must expose resolve_goods_id"
        )
    for item in case.plan_items:
        resolved = await identity_resolver.resolve_goods_id(item.goods_id)
        if resolved is None:
            raise LiveValidationCaseError(
                f"goods_id {item.goods_id!r} is not in pinned identity snapshot"
            )
        resolved_name = getattr(resolved, "market_hash_name", None)
        resolved_gid = getattr(resolved, "goods_id", None)
        if resolved_name != item.market_hash_name:
            raise LiveValidationCaseError(
                "goods_id "
                f"{item.goods_id!r} resolved to {resolved_name!r}, "
                f"expected {item.market_hash_name!r}"
            )
        if resolved_gid != item.goods_id:
            raise LiveValidationCaseError(
                "goods_id "
                f"{item.goods_id!r} resolver returned goods_id {resolved_gid!r}"
            )