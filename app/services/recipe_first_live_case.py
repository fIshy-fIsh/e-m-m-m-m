"""Phase 16F / 16F-R1 / 16F-R2 — Frozen live-validation case DTO + serialization.

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
Family metadata is bound through the pinned metadata snapshot,
canonical intrinsic classifier, and authoritative
:func:`app.services.recipe_family.build_recipe_family` via
:func:`verify_case_metadata_contract`. The case is serialized outside
Git by the live runner; the SHA-256 of its canonical bytes is the
immutable case artifact identity.

R1 contract corrections (schema version 2):

- The ``repository_commit_oid`` field stores the actual Git commit
  object ID exactly as returned by ``git rev-parse HEAD``. It is no
  longer hashed or coerced to a 64-character value. Validation
  accepts either 40-character (Git SHA-1) or 64-character (Git
  SHA-256) lowercase hex so future hash transitions remain valid.
- The persisted case artifact bytes are byte-equal to
  :func:`serialize_case`. There is no longer a trailing newline on
  disk, and :func:`hash_case` returns SHA-256 of those exact bytes.
- Schema version is bumped from 1 to 2 explicitly. Phase 16F v1
  artifacts are no longer reinterpreted by v2 code paths.

R2 contract corrections (schema version 3):

- Every plan item MUST be proven against pinned metadata BEFORE
  HTTP dispatch and again against enriched evidence after HTTP
  acquisition. Identity-only proof is no longer sufficient.
- The frozen family fields (``family_hash`` / ``family_key`` /
  ``input_rarity`` / ``stattrak_mode`` / ``collection_counts``) MUST
  be reproducible from authoritative
  :func:`build_recipe_family`. Manual hash duplication is
  forbidden.
- Phase 16F v1 and v2 artifacts are no longer reinterpreted by v3
  code paths; the loader rejects them explicitly.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.buff_intrinsic_flag_resolver import (
    BuffListingIntrinsicFlagResolver,
)
from app.services.market_universe_builder import StatTrakMode
from app.services.metadata_models import SkinMetadata
from app.services.recipe_family import (
    RecipeFamilyIdentityError,
    build_recipe_family,
)
from app.services.recipe_family_geometry import (
    RecipeFamilyGeometryError,
    compute_recipe_family_geometry,
)
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.trade_up_input_enrichment import TradeUpInputMetadataResolver

__all__ = (
    "LIVE_CASE_SCHEMA_VERSION",
    "LiveValidationCase",
    "LiveValidationCaseError",
    "LiveValidationPlanItem",
    "freeze_case",
    "hash_case",
    "serialize_case",
    "verify_case_identity",
    "verify_case_metadata_contract",
)

LIVE_CASE_SCHEMA_VERSION: Final[int] = 3
_PLAN_ITEMS_HARD_CAP: Final[int] = 10
_INPUT_COUNT: Final[int] = 10
_VALID_COMMIT_OID_LENGTHS: Final[tuple[int, ...]] = (40, 64)


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


def _exact_commit_oid(value: object, *, field: str) -> str:
    """Accept 40-char (Git SHA-1) or 64-char (Git SHA-256) lowercase hex.

    No hashing, no coercion, no expansion. The exact Git commit object
    ID is preserved verbatim.
    """

    exact = _exact(value, field=field)
    if (
        len(exact) not in _VALID_COMMIT_OID_LENGTHS
        or any(ch not in "0123456789abcdef" for ch in exact)
    ):
        raise LiveValidationCaseError(
            f"{field} must be 40- or 64-character lowercase hex"
        )
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

    - the actual Git commit object ID at preparation time
      (no hashing, no coercion; verbatim ``git rev-parse HEAD``)
    - one immutable :class:`app.services.recipe_family.RecipeFamily`
      structural composition (hash / key / rarity / StatTrak mode /
      collection counts), produced by the authoritative
      :func:`build_recipe_family` after metadata contract proof
    - one deterministic active plan with at most ten distinct
      goods_ids and exact market names
    """

    case_schema_version: int
    repository_commit_oid: str
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
        _exact_commit_oid(self.repository_commit_oid, field="repository_commit_oid")
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
    repository_commit_oid: str,
    case_purpose: str,
    family_hash: str,
    family_key: str,
    input_rarity: str,
    stattrak_mode: StatTrakMode,
    collection_counts: Sequence[tuple[str, int]],
    plan_items: Sequence[LiveValidationPlanItem],
) -> LiveValidationCase:
    """Build a frozen validation case from validated offline inputs.

    The caller MUST have already proven the inputs (e.g. by
    :func:`verify_case_identity` and :func:`verify_case_metadata_contract`).
    The freeze operation is pure construction.
    """

    return LiveValidationCase(
        case_schema_version=LIVE_CASE_SCHEMA_VERSION,
        repository_commit_oid=repository_commit_oid,
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
        "repository_commit_oid": case.repository_commit_oid,
        "stattrak_mode": case.stattrak_mode.value,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def hash_case(case: LiveValidationCase) -> str:
    """Return SHA-256 hex hash of canonical case bytes.

    The returned digest is the authoritative case artifact identity.
    Persisted case bytes MUST equal :func:`serialize_case` exactly,
    so ``sha256(persisted_bytes) == hash_case(case)``.
    """

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


def verify_case_metadata_contract(
    case: LiveValidationCase,
    *,
    metadata_resolver: TradeUpInputMetadataResolver,
    intrinsic_resolver: BuffListingIntrinsicFlagResolver,
    skins: Sequence[SkinMetadata],
    finish_index: StructuralOutputFinishIndex,
) -> None:
    """Verify every plan item against pinned metadata + family contract.

    Required checks (always):

    1. exact market_hash_name resolves through pinned metadata;
    2. exact metadata collection_name equals plan item collection_name;
    3. exact metadata collection_name is represented by
       ``case.collection_counts``;
    4. exact metadata rarity equals ``case.input_rarity``;
    5. canonical intrinsic StatTrak mode equals ``case.stattrak_mode``;
    6. :func:`build_recipe_family` reproduces
       ``family_hash`` / ``family_key`` / ``input_rarity`` /
       ``stattrak_mode`` / ``collection_counts`` exactly.

    Geometry check (when ``finish_index`` is provided):

    7. :func:`compute_recipe_family_geometry` yields at least one
       structural outcome with exact Fraction probability sum equal
       to one.

    No fuzzy matching. No name synthesis. Souvenir is treated as
    concrete-input provenance and is not part of the structural
    family identity.
    """

    if type(case) is not LiveValidationCase:
        raise LiveValidationCaseError("case must be LiveValidationCase")
    if not hasattr(metadata_resolver, "resolve"):
        raise LiveValidationCaseError(
            "metadata_resolver must expose resolve"
        )
    if not hasattr(intrinsic_resolver, "resolve"):
        raise LiveValidationCaseError(
            "intrinsic_resolver must expose resolve"
        )
    if type(finish_index) is not StructuralOutputFinishIndex:
        raise LiveValidationCaseError(
            "finish_index must be StructuralOutputFinishIndex"
        )
    if not isinstance(skins, Sequence) or any(
        type(skin) is not SkinMetadata for skin in skins
    ):
        raise LiveValidationCaseError(
            "skins must contain exact SkinMetadata values"
        )
    expected_stattrak = case.stattrak_mode is StatTrakMode.STATTRAK
    represented_collections = {name for name, _ in case.collection_counts}

    for item in case.plan_items:
        metadata = metadata_resolver.resolve(item.market_hash_name)
        if metadata is None:
            raise LiveValidationCaseError(
                f"market_hash_name {item.market_hash_name!r} is not in pinned metadata"
            )
        pinned_collection_name = getattr(metadata, "collection_name", None)
        if pinned_collection_name != item.collection_name:
            raise LiveValidationCaseError(
                "pinned metadata collection_name "
                f"{pinned_collection_name!r} does not match "
                f"plan collection_name {item.collection_name!r}"
            )
        if pinned_collection_name not in represented_collections:
            raise LiveValidationCaseError(
                "pinned metadata collection_name "
                f"{pinned_collection_name!r} is not represented "
                "by case.collection_counts"
            )
        pinned_rarity = getattr(metadata, "rarity", None)
        if pinned_rarity != case.input_rarity:
            raise LiveValidationCaseError(
                "pinned metadata rarity "
                f"{pinned_rarity!r} does not match "
                f"case.input_rarity {case.input_rarity!r}"
            )
        metadata_skin = _resolve_exact_skin_metadata(
            skins=skins,
            market_hash_name=item.market_hash_name,
        )
        if metadata_skin is None:
            raise LiveValidationCaseError(
                "exact market_hash_name is not represented by the pinned "
                "metadata catalog"
            )
        if metadata_skin.collection_name != pinned_collection_name:
            raise LiveValidationCaseError(
                "pinned metadata resolver and catalog collection disagree"
            )
        if metadata_skin.rarity != pinned_rarity:
            raise LiveValidationCaseError(
                "pinned metadata resolver and catalog rarity disagree"
            )
        if metadata_skin.stattrak is not expected_stattrak:
            raise LiveValidationCaseError(
                "pinned metadata StatTrak mode does not match case.stattrak_mode"
            )
        intrinsic = intrinsic_resolver.resolve(item.market_hash_name)
        if intrinsic is None:
            raise LiveValidationCaseError(
                "canonical intrinsic flags could not be resolved for "
                f"market_hash_name {item.market_hash_name!r}"
            )
        intrinsic_stattrak = getattr(intrinsic, "stattrak", None)
        if intrinsic_stattrak is not expected_stattrak:
            raise LiveValidationCaseError(
                "canonical intrinsic StatTrak mode "
                f"{intrinsic_stattrak!r} does not match "
                f"case.stattrak_mode {case.stattrak_mode.value!r}"
            )
        intrinsic_souvenir = getattr(intrinsic, "souvenir", None)
        if metadata_skin.souvenir is not intrinsic_souvenir:
            raise LiveValidationCaseError(
                "pinned metadata Souvenir provenance does not match "
                "canonical intrinsic classification"
            )

    try:
        reconstructed = build_recipe_family(
            input_rarity=case.input_rarity,
            stattrak_mode=case.stattrak_mode,
            collection_counts=case.collection_counts,
        )
    except MemoryError:
        raise
    except RecipeFamilyIdentityError as exc:
        raise LiveValidationCaseError(
            "frozen family fields cannot construct a valid RecipeFamily"
        ) from exc
    if reconstructed.family_hash != case.family_hash:
        raise LiveValidationCaseError(
            "frozen family_hash does not match authoritative "
            "build_recipe_family output"
        )
    if reconstructed.family_key != case.family_key:
        raise LiveValidationCaseError(
            "frozen family_key does not match authoritative "
            "build_recipe_family output"
        )
    if reconstructed.input_rarity != case.input_rarity:
        raise LiveValidationCaseError(
            "frozen input_rarity does not match authoritative "
            "build_recipe_family output"
        )
    if reconstructed.stattrak_mode != case.stattrak_mode:
        raise LiveValidationCaseError(
            "frozen stattrak_mode does not match authoritative "
            "build_recipe_family output"
        )
    if reconstructed.collection_counts != case.collection_counts:
        raise LiveValidationCaseError(
            "frozen collection_counts does not match authoritative "
            "build_recipe_family output"
        )

    try:
        geometry = compute_recipe_family_geometry(
            reconstructed, finish_index=finish_index
        )
    except MemoryError:
        raise
    except RecipeFamilyGeometryError as exc:
        raise LiveValidationCaseError(
            "family geometry is invalid or has no next-rarity "
            "structural outputs"
        ) from exc
    if not geometry.outcomes:
        raise LiveValidationCaseError(
            "family geometry has no structural outcomes"
        )
    total = sum(
        (outcome.probability for outcome in geometry.outcomes),
        start=Fraction(0, 1),
    )
    if total != Fraction(1, 1):
        raise LiveValidationCaseError(
            "family geometry probability sum does not equal exactly 1"
        )
    if geometry.family_hash != case.family_hash:
        raise LiveValidationCaseError(
            "geometry family_hash does not match frozen case"
        )


def _resolve_exact_skin_metadata(
    *,
    skins: Sequence[SkinMetadata],
    market_hash_name: str,
) -> SkinMetadata | None:
    """Resolve one exact pinned ``SkinMetadata`` row without fuzzy matching."""

    matches = tuple(
        skin for skin in skins if skin.market_hash_name == market_hash_name
    )
    if len(matches) > 1:
        raise LiveValidationCaseError(
            "duplicate exact market_hash_name in pinned metadata catalog"
        )
    return matches[0] if matches else None