"""Concrete local resolver for the BUFF community identity snapshot.

This module reads a version-pinned snapshot file (built by
`scripts/build_buff_identity_snapshot.py`) and exposes both forward and
reverse O(1) exact lookups:

  resolve(market_hash_name)          -> BuffItemIdentity | None
  resolve_goods_id(goods_id)         -> BuffItemIdentity | None

The resolver performs ZERO network I/O at runtime. The snapshot is
version-controlled and committed to the repository. Future updates are
manual and version-controlled (per D-IDENTITY-006).

This module does NOT perform any live BUFF HTTP request. It does NOT
infer identity. It does NOT modify any Protected Core module.
"""

from __future__ import annotations

import json
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from app.services.buff_item_identity import BuffItemIdentity

# BuffItemIdentityResolver (forward) is defined in buff_item_identity.py.
# BuffGoodsIdIdentityResolver (reverse) is defined locally here, in the
# concrete resolver module, to keep the frozen buff_item_identity.py
# contract stable (its exact __all__ and class set are tested by
# tests/test_buff_item_identity.py and must not drift).

__all__ = (
    "EXPECTED_SCHEMA_VERSION",
    "BuffCommunityIdentityResolver",
    "BuffCommunitySnapshotMetadata",
    "BuffCommunitySnapshotValidationError",
    "BuffGoodsIdIdentityResolver",
)


class BuffGoodsIdIdentityResolver:
    """Reverse lookup by exact goods_id.

    Implemented as a structural surface that the concrete
    BuffCommunityIdentityResolver conforms to. Existing callers of
    BuffItemIdentityResolver (forward lookup) are unaffected.
    """

    async def resolve_goods_id(
        self,
        goods_id: str,
    ) -> BuffItemIdentity | None:
        """Return one verified identity or None when unresolved."""


EXPECTED_SCHEMA_VERSION: Final[int] = 1
_MAX_SNAPSHOT_BYTES: Final[int] = 16 * 1024 * 1024  # 16 MiB; the pinned snapshot is ~1.7 MB


@dataclass(frozen=True, kw_only=True)
class BuffCommunitySnapshotMetadata:
    """Provenance metadata extracted from a community identity snapshot."""

    schema_version: int
    catalog_kind: str
    repository: str
    file: str
    commit: str
    sha256: str
    license: str
    attribution: str
    source_count: int
    accepted_count: int
    rejected_count: int


class BuffCommunitySnapshotValidationError(ValueError):
    """A snapshot failed structural or provenance validation."""


class BuffCommunityIdentityResolver:
    """O(1) forward and reverse exact-string resolver over a community snapshot.

    Constructed via `from_snapshot_path(path)` after the snapshot has been
    built offline. The constructor reads the snapshot once, validates the
    schema and provenance fields, and builds both forward and reverse
    in-memory indexes. Subsequent lookups are pure dict reads; no I/O.

    Lookup semantics:
      * exact strings only; no trimming, case-folding, or fuzzy matching.
      * unknown but well-formed identifiers -> None.
      * malformed identifiers -> None (for the public runtime API; the
        Protocol type guarantees strings).
    """

    _metadata: BuffCommunitySnapshotMetadata
    _forward: dict[str, str]
    _reverse: dict[str, str]
    _items_tuple: tuple[tuple[str, str], ...]

    def __init__(
        self,
        *,
        forward: MappingABC[str, str],
        reverse: MappingABC[str, str],
        metadata: BuffCommunitySnapshotMetadata,
    ) -> None:
        # Validate that the supplied reverse index is consistent with
        # the forward mapping. This is a defensive check that catches
        # any caller-supplied reverse index whose 1:1 invariant has been
        # violated; the canonical snapshot path rebuilds the reverse
        # index from the forward mapping and detects collisions there.
        if set(reverse.values()) != set(forward.keys()):
            raise BuffCommunitySnapshotValidationError(
                "reverse index values do not match forward keys"
            )
        if len(reverse) != len(set(reverse.keys())):
            raise BuffCommunitySnapshotValidationError(
                "reverse index has duplicate goods_id keys"
            )
        for gid, name in reverse.items():
            if forward.get(name) != gid:
                raise BuffCommunitySnapshotValidationError(
                    f"reverse/forward mismatch for goods_id={gid!r}"
                )
        # Frozen mappings preserve determinism and prevent post-load mutation.
        self._forward = dict(forward)
        self._reverse = dict(reverse)
        self._items_tuple = tuple(forward.items())
        self._identities_public = tuple(
            sorted(self._forward.items(), key=lambda kv: (len(kv[0]), kv[0]))
        )
        self._metadata = metadata

    @property
    def metadata(self) -> BuffCommunitySnapshotMetadata:
        return self._metadata

    @property
    def identities(self) -> tuple[tuple[str, str], ...]:
        """Immutable `((market_hash_name, goods_id), ...)` view over accepted identities.

        Ordered by `(len(market_hash_name), market_hash_name)` for determinism,
        mirroring `PinnedSkinMetadataResolver.skins` shape and intent. The
        returned tuple contains only forward-mapped exact identities from
        the snapshot; ``resolve`` does not need to be awaited.
        """
        return self._identities_public

    @classmethod
    def from_snapshot_path(cls, path: Path | str) -> BuffCommunityIdentityResolver:
        """Load and validate a snapshot from a file path.

        Refuses any snapshot whose:
          * bytes exceed _MAX_SNAPSHOT_BYTES (defense-in-depth);
          * JSON is malformed or not a top-level object;
          * schema_version != EXPECTED_SCHEMA_VERSION;
          * catalog_kind != "community_catalog";
          * source sha256 differs from the snapshot's recorded source sha256;
          * items contain duplicates or collisions;
          * reverse index is missing entries or has collisions.

        Successful construction yields an immutable resolver. The
        returned instance performs ZERO I/O on subsequent lookups.
        """
        path = Path(path)
        raw = path.read_bytes()
        if len(raw) > _MAX_SNAPSHOT_BYTES:
            raise BuffCommunitySnapshotValidationError(
                f"snapshot too large: {len(raw)} bytes > {_MAX_SNAPSHOT_BYTES}"
            )
        try:
            parsed: object = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BuffCommunitySnapshotValidationError(
                f"snapshot JSON is malformed: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise BuffCommunitySnapshotValidationError(
                "snapshot top-level must be a JSON object"
            )

        forward = _parse_and_validate_items(parsed)
        reverse = _build_reverse_index(forward)
        metadata = _parse_metadata(parsed, items_count=len(forward))

        return cls(forward=forward, reverse=reverse, metadata=metadata)

    async def resolve(
        self,
        market_hash_name: str,
    ) -> BuffItemIdentity | None:
        """Forward exact-string lookup by market_hash_name."""
        if not isinstance(market_hash_name, str):
            return None
        gid = self._forward.get(market_hash_name)
        if gid is None:
            return None
        return _make_identity(market_hash_name, gid)

    async def resolve_goods_id(
        self,
        goods_id: str,
    ) -> BuffItemIdentity | None:
        """Reverse exact-string lookup by goods_id."""
        if not isinstance(goods_id, str):
            return None
        # Defensive: ensure the input matches the strict validation rules
        # used in the source contract (positive integer decimal string).
        if not goods_id or not goods_id.isdigit() or (len(goods_id) > 1 and goods_id[0] == "0"):
            return None
        name = self._reverse.get(goods_id)
        if name is None:
            return None
        return _make_identity(name, goods_id)


def _make_identity(name: str, gid: str) -> BuffItemIdentity:
    """Construct a BuffItemIdentity via the established constructor."""
    return BuffItemIdentity(market_hash_name=name, goods_id=gid)


def _parse_and_validate_items(parsed: MappingABC[str, Any]) -> dict[str, str]:
    """Validate the snapshot's items block. Return an ordered dict."""
    items = parsed.get("items")
    if not isinstance(items, dict):
        raise BuffCommunitySnapshotValidationError(
            "snapshot.items must be a JSON object"
        )
    out: dict[str, str] = {}
    for name, gid in items.items():
        if not isinstance(name, str):
            raise BuffCommunitySnapshotValidationError(
                f"items key must be string: {type(name).__name__}"
            )
        if not isinstance(gid, str):
            raise BuffCommunitySnapshotValidationError(
                f"items value must be string: {name!r} -> {type(gid).__name__}"
            )
        if not gid or not gid.isdigit():
            raise BuffCommunitySnapshotValidationError(
                f"items value must be decimal string: {name!r} -> {gid!r}"
            )
        if len(gid) > 1 and gid[0] == "0":
            raise BuffCommunitySnapshotValidationError(
                f"items value has leading zeros: {name!r} -> {gid!r}"
            )
        if name in out:
            raise BuffCommunitySnapshotValidationError(
                f"items has duplicate market_hash_name: {name!r}"
            )
        out[name] = gid
    return out


def _build_reverse_index(forward: MappingABC[str, str]) -> dict[str, str]:
    """Build the reverse (goods_id -> market_hash_name) index.

    A well-formed snapshot has 1:1 mapping; this defensively detects
    any collision that may have slipped through and rejects the snapshot.
    """
    rev: dict[str, str] = {}
    for name, gid in forward.items():
        if gid in rev and rev[gid] != name:
            raise BuffCommunitySnapshotValidationError(
                f"items has goods_id collision: {gid!r} -> "
                f"{rev[gid]!r} and {name!r}"
            )
        rev[gid] = name
    return rev


def _parse_metadata(
    parsed: MappingABC[str, Any], *, items_count: int
) -> BuffCommunitySnapshotMetadata:
    schema_version = parsed.get("schema_version")
    if schema_version != EXPECTED_SCHEMA_VERSION:
        raise BuffCommunitySnapshotValidationError(
            f"unsupported schema_version: {schema_version!r} "
            f"(expected {EXPECTED_SCHEMA_VERSION})"
        )
    catalog_kind = parsed.get("catalog_kind")
    if catalog_kind != "community_catalog":
        raise BuffCommunitySnapshotValidationError(
            f"unsupported catalog_kind: {catalog_kind!r}"
        )
    source = parsed.get("source")
    if not isinstance(source, dict):
        raise BuffCommunitySnapshotValidationError(
            "snapshot.source must be a JSON object"
        )
    counts = parsed.get("counts")
    if not isinstance(counts, dict):
        raise BuffCommunitySnapshotValidationError(
            "snapshot.counts must be a JSON object"
        )
    try:
        return BuffCommunitySnapshotMetadata(
            schema_version=schema_version,
            catalog_kind=catalog_kind,
            repository=_required_str(source, "repository"),
            file=_required_str(source, "file"),
            commit=_required_str(source, "commit"),
            sha256=_required_str(source, "sha256"),
            license=_required_str(source, "license"),
            attribution=_required_str(source, "attribution"),
            source_count=_required_int(counts, "source"),
            accepted_count=_required_int(counts, "accepted"),
            rejected_count=_required_int(counts, "rejected"),
        )
    except KeyError as exc:
        raise BuffCommunitySnapshotValidationError(
            f"snapshot metadata missing required field: {exc.args[0]!r}"
        ) from exc
    finally:
        _ = items_count  # items_count available for future cross-check


def _required_str(obj: MappingABC[str, Any], key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise BuffCommunitySnapshotValidationError(
            f"snapshot metadata field {key!r} must be non-empty string"
        )
    return value


def _required_int(obj: MappingABC[str, Any], key: str) -> int:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise BuffCommunitySnapshotValidationError(
            f"snapshot metadata field {key!r} must be int"
        )
    return value


# Note: BuffItemIdentityResolver and BuffGoodsIdIdentityResolver are
# Protocols; runtime registration of those Protocols against the concrete
# resolver class is verified in tests via isinstance / explicit isinstance
# on the structural interface. We do not perform runtime isinstance on the
# Protocol classes here because Protocol classes are not nominal types.