"""Concrete `TradeUpInputMetadataResolver` backed by a pinned static catalog.

The MVP live scanner uses a pinned synthetic metadata snapshot
(`data/metadata/skin_metadata_v1.json`) rather than a live external
metadata source. This is the conservative approach documented by
`D-FIXTURE-001`: a project-defined synthetic catalog is acceptable
for offline and bounded MVP evaluation; production metadata wiring is
a separate later phase.

The resolver is pure:

  * no HTTP;
  * no filesystem mutation after load;
  * no environment / secrets;
  * no fuzzy / casefold / trim;
  * exact-string lookup only;
  * strict validation rejects malformed entries.

The lookup contract is:

  market_hash_name -> TradeUpInputMetadata | None

Unknown exact names return `None`. The downstream
`TradeUpInputEnrichment` already rejects unresolved metadata with the
existing `METADATA_NOT_FOUND` rejection code; the orchestrator does
not need to invent new rejection vocabulary.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from app.services.metadata_models import SkinMetadata
from app.services.trade_up_input_enrichment import TradeUpInputMetadata

__all__ = (
    "PinnedSkinMetadataResolver",
    "SkinMetadataSnapshotValidationError",
)


class SkinMetadataSnapshotValidationError(ValueError):
    """The pinned metadata snapshot violated the strict contract."""

    _FIXED_ERROR = "invalid pinned skin metadata snapshot"

    def __init__(self, *, reason: str) -> None:
        if not reason:
            raise ValueError("reason must be a non-empty string")
        super().__init__(self._FIXED_ERROR)
        self.reason = reason


@dataclass(frozen=True, kw_only=True)
class PinnedSkinMetadataResolver:
    """Exact-byte `market_hash_name -> TradeUpInputMetadata` resolver.

    Loads a pinned JSON snapshot once at construction. Subsequent
    lookups are pure dict reads; no I/O. Malformed snapshot entries are
    rejected at construction; the resolver never silently fixes bad
    input.

    The snapshot must contain a list of objects, each with exactly the
    canonical keys required to build a `TradeUpInputMetadata` and the
    existing `SkinMetadata` needed by the recipe/output-candidate
    builder.
    """

    _index: Mapping[str, TradeUpInputMetadata]
    _skins: tuple[SkinMetadata, ...]

    @property
    def skins(self) -> tuple[SkinMetadata, ...]:
        """Return the immutable normalized skin catalog."""
        return self._skins

    @classmethod
    def from_snapshot_path(cls, path: Path | str) -> PinnedSkinMetadataResolver:
        """Load and validate a pinned metadata snapshot from a file path."""
        path = Path(path)
        raw = path.read_bytes()
        try:
            payload: object = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SkinMetadataSnapshotValidationError(
                reason=f"snapshot JSON is malformed: {exc}"
            ) from exc
        return cls.from_payload(payload)

    @classmethod
    def from_payload(cls, payload: object) -> PinnedSkinMetadataResolver:
        """Validate and load a pinned metadata snapshot from a parsed payload.

        Accepts either:

          * a JSON array of skin objects directly, or
          * a top-level object whose ``items`` key holds the array.
        """
        if isinstance(payload, dict):
            candidate = payload.get("items")
        else:
            candidate = payload
        if not isinstance(candidate, list):
            raise SkinMetadataSnapshotValidationError(
                reason="snapshot must be a JSON array of skin objects"
                " or an object with an 'items' array"
            )
        index: dict[str, TradeUpInputMetadata] = {}
        skins: list[SkinMetadata] = []
        for index_position, raw in enumerate(candidate):
            metadata, skin = _parse_entry(raw, index_position=index_position)
            if metadata.market_hash_name in index:
                raise SkinMetadataSnapshotValidationError(
                    reason=(
                        f"duplicate market_hash_name at index "
                        f"{index_position}: {metadata.market_hash_name!r}"
                    )
                )
            index[metadata.market_hash_name] = metadata
            skins.append(skin)
        return cls(
            _index=MappingProxyType(index),
            _skins=tuple(skins),
        )

    def resolve(self, market_hash_name: str) -> TradeUpInputMetadata | None:
        """Return one metadata entry or `None` when unknown.

        Rejects non-string, empty, or whitespace-padded inputs with
        the existing enrichment input contract.
        """
        if type(market_hash_name) is not str:
            return None
        if not market_hash_name or market_hash_name != market_hash_name.strip():
            return None
        return self._index.get(market_hash_name)


def _parse_entry(
    raw: object,
    *,
    index_position: int,
) -> tuple[TradeUpInputMetadata, SkinMetadata]:
    """Validate and project one snapshot entry into canonical DTOs."""
    if not isinstance(raw, dict):
        raise SkinMetadataSnapshotValidationError(
            reason=(
                f"snapshot entry at index {index_position} must be a JSON object"
            )
        )
    market_hash_name_obj = raw.get("market_hash_name")
    if not _is_exact_nonempty_string(market_hash_name_obj):
        raise SkinMetadataSnapshotValidationError(
            reason=(
                f"snapshot entry at index {index_position} has invalid "
                f"market_hash_name: {market_hash_name_obj!r}"
            )
        )
    market_hash_name = str(market_hash_name_obj)
    collection_name_obj = raw.get("collection_name")
    if not _is_exact_nonempty_string(collection_name_obj):
        raise SkinMetadataSnapshotValidationError(
            reason=(
                f"snapshot entry at index {index_position} has invalid "
                f"collection_name: {collection_name_obj!r}"
            )
        )
    collection_name = str(collection_name_obj)
    rarity_obj = raw.get("rarity")
    if not _is_exact_nonempty_string(rarity_obj):
        raise SkinMetadataSnapshotValidationError(
            reason=(
                f"snapshot entry at index {index_position} has invalid "
                f"rarity: {rarity_obj!r}"
            )
        )
    rarity = str(rarity_obj)
    min_float = raw.get("min_float")
    max_float = raw.get("max_float")
    if (
        type(min_float) is not float
        or type(max_float) is not float
        or not _is_finite(min_float)
        or not _is_finite(max_float)
        or min_float < 0.0
        or max_float > 1.0
        or min_float >= max_float
    ):
        raise SkinMetadataSnapshotValidationError(
            reason=(
                f"snapshot entry at index {index_position} has invalid "
                f"float range: min={min_float!r} max={max_float!r}"
            )
        )
    metadata = TradeUpInputMetadata(
        market_hash_name=market_hash_name,
        collection_name=collection_name,
        rarity=rarity,
        min_float=min_float,
        max_float=max_float,
    )
    stattrak = raw.get("stattrak", False)
    souvenir = raw.get("souvenir", False)
    if type(stattrak) is not bool or type(souvenir) is not bool:
        raise SkinMetadataSnapshotValidationError(
            reason=(
                f"snapshot entry at index {index_position} has invalid "
                "stattrak/souvenir flags"
            )
        )
    skin = SkinMetadata(
        market_hash_name=market_hash_name,
        name=raw.get("name") if isinstance(raw.get("name"), str) else None,
        weapon=raw.get("weapon") if isinstance(raw.get("weapon"), str) else None,
        rarity=rarity,
        category=raw.get("category") if isinstance(raw.get("category"), str) else None,
        collection_name=collection_name,
        min_float=min_float,
        max_float=max_float,
        stattrak=stattrak,
        souvenir=souvenir,
        paint_index=raw.get("paint_index") if isinstance(raw.get("paint_index"), int) else None,
        raw=None,
    )
    return metadata, skin


def _is_exact_nonempty_string(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
    )


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))