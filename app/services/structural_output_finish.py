"""Phase 16B — Structural output finish index.

This module builds a strict immutable offline structural-output finish
index from a pinned `Sequence[SkinMetadata]`. It does NOT touch the
network, the filesystem, the BUFF HTTP API, or the SteamDT HTTP API.

It does NOT touch the production scanner, orchestrator, or CLI.

Semantics frozen by `D-RECIPE-FIRST-OUTPUT-IDENTITY-001` /
`D-RECIPE-FIRST-PROBABILITY-001` / `D-OUTPUT-WEAR-MAPPING-001` /
`D-TRADEUP-WEAR-ROW-MIGRATION-001`:

  - Structural trade-up output identity is finish-level, NOT
    wear-row-level.
  - The canonical 6-tuple finish key is
    `(collection_name, rarity, stattrak, name, weapon, paint_index)`.
  - The canonical non-Souvenir wear rows form a deterministic
    `(wear_name, exact_market_hash_name)` map per finish.
  - The exact market_hash_name used for SteamDT valuation is
    resolved fail-closed from pinned finish + wear metadata.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from app.services.metadata_models import SkinMetadata
from app.utils.wear import WEAR_RANGES

__all__ = (
    "StructuralOutputFinish",
    "StructuralOutputFinishIndex",
    "StructuralOutputFinishIndexError",
    "WearMarketMapping",
    "compute_finish_key",
    "parse_canonical_wear_name",
)

_CANONICAL_WEAR_ORDER: Final[tuple[str, ...]] = (
    "FactoryNew",
    "MinimalWear",
    "Field-Tested",
    "Well-Worn",
    "Battle-Scarred",
)

_CANONICAL_WEAR_DISPLAY: Final[tuple[str, ...]] = tuple(
    WEAR_RANGES.keys()
)


def _canonical_wear_display_to_token(display: str) -> str:
    """Map the display wear name to the canonical token used internally."""

    if display == "Factory New":
        return "FactoryNew"
    if display == "Minimal Wear":
        return "MinimalWear"
    if display == "Field-Tested":
        return "Field-Tested"
    if display == "Well-Worn":
        return "Well-Worn"
    if display == "Battle-Scarred":
        return "Battle-Scarred"
    raise ValueError(f"unsupported canonical wear name: {display!r}")


class StructuralOutputFinishIndexError(ValueError):
    """A structural finish index input violated the strict contract."""


@dataclass(frozen=True, kw_only=True)
class WearMarketMapping:
    """A canonical mapping from a structural finish to an exact market name."""

    wear_name: str          # canonical display name (e.g. "Factory New")
    market_hash_name: str   # exact original market_hash_name from the snapshot

    def __post_init__(self) -> None:
        if not isinstance(self.wear_name, str) or not self.wear_name:
            raise StructuralOutputFinishIndexError(
                "wear_name must be a non-empty string"
            )
        if not isinstance(self.market_hash_name, str) or not self.market_hash_name:
            raise StructuralOutputFinishIndexError(
                "market_hash_name must be a non-empty string"
            )
        if self.wear_name not in _CANONICAL_WEAR_DISPLAY:
            raise StructuralOutputFinishIndexError(
                f"unsupported wear_name: {self.wear_name!r}"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class StructuralOutputFinish:
    """One structural output finish identity.

    Structural trade-up probability is a probability over
    `StructuralOutputFinish`, NOT over wear-qualified
    `market_hash_name` rows.

    Souvenir rows are concrete-input provenance and MUST NOT appear
    in `wear_market_names` for the canonical non-Souvenir output pool.
    """

    finish_key: str
    collection_name: str
    rarity: str
    stattrak: bool
    base_name: str
    weapon: str | None
    paint_index: int | None
    min_float: float
    max_float: float
    wear_market_names: tuple[WearMarketMapping, ...]

    def __post_init__(self) -> None:
        if (
            type(self.finish_key) is not str
            or len(self.finish_key) != 64
            or any(ch not in "0123456789abcdef" for ch in self.finish_key)
        ):
            raise StructuralOutputFinishIndexError(
                "finish_key must be full lowercase SHA-256 hex"
            )
        if not isinstance(self.collection_name, str) or not self.collection_name:
            raise StructuralOutputFinishIndexError(
                "collection_name must be a non-empty string"
            )
        if self.collection_name != self.collection_name.strip():
            raise StructuralOutputFinishIndexError(
                "collection_name must not contain surrounding whitespace"
            )
        if not isinstance(self.rarity, str) or not self.rarity:
            raise StructuralOutputFinishIndexError(
                "rarity must be a non-empty string"
            )
        if self.rarity != self.rarity.strip():
            raise StructuralOutputFinishIndexError(
                "rarity must not contain surrounding whitespace"
            )
        if not isinstance(self.stattrak, bool):
            raise StructuralOutputFinishIndexError(
                "stattrak must be a boolean"
            )
        if not isinstance(self.base_name, str) or not self.base_name:
            raise StructuralOutputFinishIndexError(
                "base_name must be a non-empty string"
            )
        if self.base_name != self.base_name.strip():
            raise StructuralOutputFinishIndexError(
                "base_name must not contain surrounding whitespace"
            )
        if self.weapon is not None and type(self.weapon) is not str:
            raise StructuralOutputFinishIndexError(
                "weapon must be a string or None"
            )
        if self.paint_index is not None and type(self.paint_index) is not int:
            raise StructuralOutputFinishIndexError(
                "paint_index must be an integer or None"
            )
        if not isinstance(self.wear_market_names, tuple) or not all(
            isinstance(wm, WearMarketMapping) for wm in self.wear_market_names
        ):
            raise StructuralOutputFinishIndexError(
                "wear_market_names must be a tuple of WearMarketMapping"
            )
        if not self.wear_market_names:
            raise StructuralOutputFinishIndexError(
                "wear_market_names cannot be empty"
            )
        wear_names = tuple(wm.wear_name for wm in self.wear_market_names)
        expected_wear_names = tuple(
            name for name in _CANONICAL_WEAR_DISPLAY if name in wear_names
        )
        if wear_names != expected_wear_names or len(set(wear_names)) != len(wear_names):
            raise StructuralOutputFinishIndexError(
                "wear_market_names must be unique and canonically ordered"
            )
        if (
            type(self.min_float) is not float
            or type(self.max_float) is not float
            or not math.isfinite(self.min_float)
            or not math.isfinite(self.max_float)
            or self.min_float < 0.0
            or self.max_float > 1.0
            or self.min_float >= self.max_float
        ):
            raise StructuralOutputFinishIndexError(
                f"invalid float bounds: min={self.min_float} max={self.max_float}"
            )
        expected_key = compute_finish_key(
            collection_name=self.collection_name,
            rarity=self.rarity,
            stattrak=self.stattrak,
            base_name=self.base_name,
            weapon=self.weapon,
            paint_index=self.paint_index,
        )
        if self.finish_key != expected_key:
            raise StructuralOutputFinishIndexError(
                "finish_key does not match canonical finish identity"
            )

    @property
    def unique_wear_count(self) -> int:
        """Count of unique canonical wear mappings for this finish."""

        return len(self.wear_market_names)


@dataclass(frozen=True, kw_only=True, repr=False)
class StructuralOutputFinishIndex:
    """Immutable offline structural output finish index.

    The index is built from a pinned `Sequence[SkinMetadata]`. It performs
    zero network I/O. It canonicalizes wear rows into a deterministic
    `(wear_name, exact_market_hash_name)` map per finish.

    Lookup APIs:

      - by_finish_key: O(1) lookup by canonical finish_key.
      - finish_keys_for_collection: ordered unique finish_keys
        whose `(collection_name, rarity, stattrak)` matches.
      - resolve_wear_market_hash_name: fail-closed finish_key+wear
        -> exact market_hash_name lookup.
    """

    _by_key: Mapping[str, StructuralOutputFinish]
    _by_collection: Mapping[
        tuple[str, str, bool], tuple[str, ...]
    ]

    @property
    def finishes(self) -> tuple[StructuralOutputFinish, ...]:
        """Return the immutable ordered tuple of unique structural finishes."""

        return tuple(self._by_key.values())

    def by_finish_key(self, finish_key: str) -> StructuralOutputFinish | None:
        """O(1) exact-finish-key lookup. Returns None when missing."""

        if not isinstance(finish_key, str):
            return None
        return self._by_key.get(finish_key)

    def finish_keys_for_collection(
        self,
        *,
        collection_name: str,
        rarity: str,
        stattrak: bool,
    ) -> tuple[str, ...]:
        """Return ordered unique finish_keys for one collection / rarity / mode."""

        return self._by_collection.get(
            (collection_name, rarity, bool(stattrak)), ()
        )

    def resolve_wear_market_hash_name(
        self,
        *,
        finish_key: str,
        wear_name: str,
    ) -> str | None:
        """Fail-closed finish_key+wear -> exact market_hash_name lookup.

        Returns None when the finish or wear band is absent. NEVER
        synthesizes a missing market name.
        """

        finish = self.by_finish_key(finish_key)
        if finish is None:
            return None
        for mapping in finish.wear_market_names:
            if mapping.wear_name == wear_name:
                return mapping.market_hash_name
        return None

    @classmethod
    def from_skins(
        cls, skins: SequenceABC[SkinMetadata]
    ) -> StructuralOutputFinishIndex:
        """Build the index from a pinned `Sequence[SkinMetadata]`.

        All wear rows in one finish MUST share:

          - collection_name
          - rarity
          - stattrak
          - name
          - weapon
          - paint_index
          - min_float
          - max_float

        Souvenir rows are excluded from the canonical output wear map.

        Each canonical non-Souvenir finish+wear MUST map to exactly one
        exact market_hash_name. Duplicate finish+wear mappings fail closed.
        """

        groups: dict[
            tuple[str, str, bool, str, str | None, int | None],
            list[SkinMetadata],
        ] = {}
        for skin in skins:
            if skin.souvenir:
                # Souvenir rows are concrete-input provenance and MUST NOT
                # appear in the canonical non-Souvenir output wear map.
                continue
            if skin.name is None or skin.collection_name is None or skin.rarity is None:
                # Rows with missing required fields cannot form a structural
                # finish. Reject fail-closed to avoid silent drift.
                raise StructuralOutputFinishIndexError(
                    f"skin row missing required identity: {skin.market_hash_name!r}"
                )
            key = (
                skin.collection_name,
                skin.rarity,
                bool(skin.stattrak),
                skin.name,
                skin.weapon,
                skin.paint_index,
            )
            groups.setdefault(key, []).append(skin)

        finishes: list[StructuralOutputFinish] = []
        for key, group_rows in groups.items():
            collection_name, rarity, stattrak, base_name, weapon, paint_index = key
            # Group consistency: identical min/max across all rows.
            first = group_rows[0]
            for row in group_rows[1:]:
                if (
                    row.min_float != first.min_float
                    or row.max_float != first.max_float
                ):
                    raise StructuralOutputFinishIndexError(
                        "min/max float mismatch within one structural finish: "
                        f"finish={base_name!r} collection={collection_name!r}"
                    )

            wear_map: dict[str, str] = {}
            wear_order: list[str] = []
            for row in group_rows:
                wear_display = _extract_canonical_wear_name(row.market_hash_name)
                if wear_display is None:
                    # Zero matches or unsupported wear label.
                    # Reject fail-closed to avoid fuzzy construction.
                    raise StructuralOutputFinishIndexError(
                        f"could not parse wear label: {row.market_hash_name!r}"
                    )
                wear_token = _canonical_wear_display_to_token(wear_display)
                if wear_token in wear_map:
                    raise StructuralOutputFinishIndexError(
                        "duplicate finish+wear mapping: "
                        f"wear={wear_display!r} "
                        f"existing={wear_map[wear_token]!r} "
                        f"new={row.market_hash_name!r}"
                    )
                wear_map[wear_token] = row.market_hash_name
                wear_order.append(wear_token)

            ordered_mappings = tuple(
                WearMarketMapping(
                    wear_name=display_wear_name(wear_token),
                    market_hash_name=wear_map[wear_token],
                )
                for wear_token in sorted(wear_order, key=_canonical_wear_index)
            )

            finish = StructuralOutputFinish(
                finish_key=compute_finish_key(
                    collection_name=collection_name,
                    rarity=rarity,
                    stattrak=stattrak,
                    base_name=base_name,
                    weapon=weapon,
                    paint_index=paint_index,
                ),
                collection_name=collection_name,
                rarity=rarity,
                stattrak=bool(stattrak),
                base_name=base_name,
                weapon=weapon,
                paint_index=paint_index,
                min_float=first.min_float,
                max_float=first.max_float,
                wear_market_names=ordered_mappings,
            )
            finishes.append(finish)

        # Sort deterministically by canonical finish_key.
        finishes.sort(key=lambda f: f.finish_key)
        by_key: dict[str, StructuralOutputFinish] = {
            finish.finish_key: finish for finish in finishes
        }
        if len(by_key) != len(finishes):
            raise StructuralOutputFinishIndexError(
                "duplicate finish_key generated by structural finish hashing"
            )

        # Build collection -> finish_keys index.
        by_collection: dict[
            tuple[str, str, bool], list[str]
        ] = {}
        for finish in finishes:
            coll_key = (finish.collection_name, finish.rarity, finish.stattrak)
            by_collection.setdefault(coll_key, []).append(finish.finish_key)
        for _key, finish_keys in by_collection.items():
            finish_keys.sort()
        by_collection_tuple: dict[
            tuple[str, str, bool], tuple[str, ...]
        ] = {key: tuple(values) for key, values in by_collection.items()}

        return cls(
            _by_key=MappingProxyType(by_key),
            _by_collection=MappingProxyType(by_collection_tuple),
        )


def compute_finish_key(
    *,
    collection_name: str,
    rarity: str,
    stattrak: bool,
    base_name: str,
    weapon: str | None,
    paint_index: int | None,
) -> str:
    """Compute the canonical SHA-256 hex `finish_key` for one structural finish.

    Identity bytes represent ONLY the frozen 6-tuple. They never include
    derived wear rows, prices, catalogs, or floats.

    Use a deterministic compact sorted-key UTF-8 JSON encoding with an
    explicit schema-version marker.
    """

    if (
        type(collection_name) is not str
        or not collection_name
        or collection_name != collection_name.strip()
    ):
        raise StructuralOutputFinishIndexError(
            "collection_name must be an exact non-empty string"
        )
    if type(rarity) is not str or not rarity or rarity != rarity.strip():
        raise StructuralOutputFinishIndexError(
            "rarity must be an exact non-empty string"
        )
    if type(stattrak) is not bool:
        raise StructuralOutputFinishIndexError("stattrak must be a boolean")
    if type(base_name) is not str or not base_name or base_name != base_name.strip():
        raise StructuralOutputFinishIndexError(
            "base_name must be an exact non-empty string"
        )
    if weapon is not None and type(weapon) is not str:
        raise StructuralOutputFinishIndexError("weapon must be string or None")
    if paint_index is not None and type(paint_index) is not int:
        raise StructuralOutputFinishIndexError(
            "paint_index must be integer or None"
        )
    payload: dict[str, object] = {
        "finish_spec_version": 1,
        "collection_name": collection_name,
        "rarity": rarity,
        "stattrak": bool(stattrak),
        "base_name": base_name,
        "weapon": weapon,
        "paint_index": paint_index,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_canonical_wear_name(market_hash_name: str) -> str | None:
    """Extract an exact terminal canonical wear suffix.

    Returns the canonical wear display name, or `None` when zero
    canonical suffixes match. The input identity is never trimmed,
    case-folded, or reconstructed.
    """

    if type(market_hash_name) is not str or not market_hash_name:
        return None
    matches = tuple(
        display
        for display in _CANONICAL_WEAR_DISPLAY
        if market_hash_name.endswith(f" ({display})")
    )
    return matches[0] if len(matches) == 1 else None


def _extract_canonical_wear_name(market_hash_name: str) -> str | None:
    """Backward-compatible private alias for the Phase 16B builder."""

    return parse_canonical_wear_name(market_hash_name)


def display_wear_name(token: str) -> str:
    """Map the canonical token back to the canonical display name.

    The token is the underscore-free canonical form: "FactoryNew",
    "MinimalWear", "Field-Tested", "Well-Worn", "Battle-Scarred".
    """

    if token == "FactoryNew":
        return "Factory New"
    if token == "MinimalWear":
        return "Minimal Wear"
    if token == "Field-Tested":
        return "Field-Tested"
    if token == "Well-Worn":
        return "Well-Worn"
    if token == "Battle-Scarred":
        return "Battle-Scarred"
    raise ValueError(f"unsupported canonical wear token: {token!r}")


def _canonical_wear_index(token: str) -> int:
    """Return the deterministic canonical order index of a wear token."""

    for i, candidate in enumerate(_CANONICAL_WEAR_ORDER):
        if candidate == token:
            return i
    raise ValueError(f"unsupported canonical wear token: {token!r}")