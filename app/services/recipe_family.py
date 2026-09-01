"""Phase 16B — RecipeFamily structural domain.

This module defines the immutable `RecipeFamily` structural DTO and
the `StatTrakMode` enum used by the recipe-first architecture.

RecipeFamily structural identity consists ONLY of:

  - family_spec_version (exactly 1)
  - input rarity
  - StatTrak mode
  - deterministic collection/count composition

It does NOT contain:

  - Souvenir policy
  - goods_id
  - exact input market_hash_name
  - listing_id
  - asset_id
  - input price
  - input actual float
  - SteamDT price
  - ranking score
  - output rarity / output finish identities

Derived output geometry (output rarity, finish identities, structural
probabilities) lives in a separate service: `recipe_family_geometry`.

This module performs zero network I/O and has zero production runtime
callers in Phase 16B. It is OFFLINE ONLY.

Frozen by Phase 16A / 16A-R1 / 16A-R2:

  - `MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3` (PROJECT bound).
  - `sum(collection_counts) == 10`.
  - collection counts are positive integers.
  - collection names are canonical, non-empty, exact, no
    casefold / trim / alias.
  - collection/count pairs are sorted ascending by exact
    collection name.
  - duplicate collection names are forbidden.
  - 1 <= number of collections <= 3.
  - Souvenir is NOT a RecipeFamily structural identity axis.
  - StatTrak mode IS a structural family dimension.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Final

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.market_universe_builder import StatTrakMode
from app.services.metadata_models import SkinMetadata
from app.services.metadata_service import get_next_rarity
from app.services.structural_output_finish import StructuralOutputFinishIndex

__all__ = (
    "MAX_DISTINCT_COLLECTIONS_PER_FAMILY",
    "ProductiveInputRarities",
    "RecipeFamily",
    "RecipeFamilyGenerator",
    "RecipeFamilyIdentityError",
    "RecipeFamilyStratum",
    "StatTrakMode",
    "build_recipe_family",
    "compute_recipe_family_hash",
    "count_recipe_families",
    "get_next_rarity",
)

MAX_DISTINCT_COLLECTIONS_PER_FAMILY: Final[int] = 3
RECIPE_FAMILY_SPEC_VERSION: Final[int] = 1
INPUT_COUNT: Final[int] = 10

ProductiveInputRarities: Final[tuple[str, ...]] = (
    "Consumer Grade",
    "Industrial Grade",
    "Mil-Spec Grade",
    "Restricted",
    "Classified",
)


class RecipeFamilyIdentityError(ValueError):
    """A RecipeFamily input or constructed object violated the contract."""


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFamily:
    """Immutable RecipeFamily structural identity.

    Memory rule: this DTO intentionally carries NO output geometry,
    NO finish identities, and NO prices. Derived geometry lives in a
    separate service. This keeps each family DTO small and makes
    per-family construction independent of catalog iteration order.
    """

    family_spec_version: int
    input_rarity: str
    stattrak_mode: StatTrakMode
    collection_counts: tuple[tuple[str, int], ...]
    family_hash: str
    family_key: str

    def __post_init__(self) -> None:
        if (
            type(self.family_spec_version) is not int
            or self.family_spec_version != RECIPE_FAMILY_SPEC_VERSION
        ):
            raise RecipeFamilyIdentityError(
                f"family_spec_version must be exactly {RECIPE_FAMILY_SPEC_VERSION}"
            )
        if type(self.input_rarity) is not str or not self.input_rarity.strip():
            raise RecipeFamilyIdentityError("input_rarity must be non-empty")
        if self.input_rarity not in ProductiveInputRarities:
            raise RecipeFamilyIdentityError(
                f"input_rarity must be one of {ProductiveInputRarities}"
            )
        if not isinstance(self.stattrak_mode, StatTrakMode):
            raise RecipeFamilyIdentityError(
                "stattrak_mode must be a StatTrakMode enum value"
            )
        if not isinstance(self.collection_counts, tuple) or not self.collection_counts:
            raise RecipeFamilyIdentityError(
                "collection_counts must be a non-empty tuple"
            )
        if len(self.collection_counts) > MAX_DISTINCT_COLLECTIONS_PER_FAMILY:
            raise RecipeFamilyIdentityError(
                "distinct collections exceed MAX_DISTINCT_COLLECTIONS_PER_FAMILY"
            )
        if len(self.collection_counts) < 1:
            raise RecipeFamilyIdentityError(
                "distinct collections must be at least 1"
            )
        previous_name: str | None = None
        total = 0
        for entry in self.collection_counts:
            if (
                type(entry) is not tuple
                or len(entry) != 2
            ):
                raise RecipeFamilyIdentityError(
                    "collection_counts entries must be (collection_name, count)"
                )
            name, count = entry
            if type(name) is not str or not name or name != name.strip():
                raise RecipeFamilyIdentityError(
                    "collection_name must be non-empty exact string"
                )
            if previous_name is not None and name <= previous_name:
                raise RecipeFamilyIdentityError(
                    "collection_counts must be sorted ascending by exact name"
                )
            if type(count) is not int or isinstance(count, bool):
                raise RecipeFamilyIdentityError("count must be int")
            if count <= 0:
                raise RecipeFamilyIdentityError("count must be > 0")
            total += count
            previous_name = name
        if total != INPUT_COUNT:
            raise RecipeFamilyIdentityError(
                f"sum(collection_counts) must equal {INPUT_COUNT}"
            )
        if (
            type(self.family_hash) is not str
            or len(self.family_hash) != 64
            or any(ch not in "0123456789abcdef" for ch in self.family_hash)
        ):
            raise RecipeFamilyIdentityError(
                "family_hash must be full lowercase SHA-256 hex"
            )
        if (
            type(self.family_key) is not str
            or len(self.family_key) != 24
            or self.family_key != self.family_hash[:24]
        ):
            raise RecipeFamilyIdentityError(
                "family_key must equal first 24 hex characters of family_hash"
            )
        expected_hash = compute_recipe_family_hash(
            input_rarity=self.input_rarity,
            stattrak_mode=self.stattrak_mode,
            collection_counts=self.collection_counts,
        )
        if self.family_hash != expected_hash:
            raise RecipeFamilyIdentityError(
                "family_hash does not match canonical family identity"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFamilyStratum:
    """One productive input-rarity / StatTrak structural stratum."""

    input_rarity: str
    stattrak_mode: StatTrakMode
    eligible_collections: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.input_rarity not in ProductiveInputRarities:
            raise RecipeFamilyIdentityError("unsupported stratum input rarity")
        if type(self.stattrak_mode) is not StatTrakMode:
            raise RecipeFamilyIdentityError("invalid stratum StatTrak mode")
        if type(self.eligible_collections) is not tuple:
            raise RecipeFamilyIdentityError(
                "eligible_collections must be an exact tuple"
            )
        if any(
            type(name) is not str or not name or name != name.strip()
            for name in self.eligible_collections
        ):
            raise RecipeFamilyIdentityError(
                "eligible collection names must be exact non-empty strings"
            )
        if tuple(sorted(set(self.eligible_collections))) != self.eligible_collections:
            raise RecipeFamilyIdentityError(
                "eligible_collections must be unique and sorted by exact name"
            )

    @property
    def family_count(self) -> int:
        return count_recipe_families(len(self.eligible_collections))


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFamilyGenerator:
    """Pure lazy RecipeFamily generator over pinned offline catalogs.

    Construction computes only the bounded eligible collection tuple for
    one stratum. `iter_families` is a true generator: it yields one family
    at a time and never materializes the full state space.
    """

    stratum: RecipeFamilyStratum

    @classmethod
    def from_catalogs(
        cls,
        *,
        skins: Sequence[SkinMetadata],
        identity_resolver: BuffCommunityIdentityResolver,
        finish_index: StructuralOutputFinishIndex,
        input_rarity: str,
        stattrak_mode: StatTrakMode,
    ) -> RecipeFamilyGenerator:
        if input_rarity not in ProductiveInputRarities:
            raise RecipeFamilyIdentityError("unsupported productive input rarity")
        if type(identity_resolver) is not BuffCommunityIdentityResolver:
            raise RecipeFamilyIdentityError(
                "identity_resolver must be BuffCommunityIdentityResolver"
            )
        if type(finish_index) is not StructuralOutputFinishIndex:
            raise RecipeFamilyIdentityError(
                "finish_index must be StructuralOutputFinishIndex"
            )
        if not isinstance(skins, Sequence):
            raise RecipeFamilyIdentityError("skins must be a sequence")
        if not isinstance(stattrak_mode, StatTrakMode):
            raise RecipeFamilyIdentityError("invalid StatTrak mode")
        output_rarity = get_next_rarity(input_rarity)
        if output_rarity is None:
            raise RecipeFamilyIdentityError("input rarity has no output rarity")
        exact_identity_names = frozenset(
            name for name, _goods_id in identity_resolver.identities
        )
        expected_stattrak = stattrak_mode is StatTrakMode.STATTRAK
        candidate_collections: set[str] = set()
        for skin in skins:
            if skin.collection_name is None:
                continue
            if skin.rarity != input_rarity:
                continue
            if bool(skin.stattrak) is not expected_stattrak:
                continue
            # Normal-mode structural acquisition eligibility permits
            # both normal and Souvenir input rows. StatTrak mode remains
            # homogeneous and uses only StatTrak rows.
            if skin.market_hash_name not in exact_identity_names:
                continue
            output_keys = finish_index.finish_keys_for_collection(
                collection_name=skin.collection_name,
                rarity=output_rarity,
                stattrak=expected_stattrak,
            )
            if output_keys:
                candidate_collections.add(skin.collection_name)
        ordered = tuple(sorted(candidate_collections))
        return cls(
            stratum=RecipeFamilyStratum(
                input_rarity=input_rarity,
                stattrak_mode=stattrak_mode,
                eligible_collections=ordered,
            )
        )

    def count(self) -> int:
        """Return analytic family count without materializing families."""

        return count_recipe_families(len(self.stratum.eligible_collections))

    def iter_families(self) -> Iterator[RecipeFamily]:
        """Yield RecipeFamily values in deterministic lazy order.

        Order:
          1. k distinct collections ascending: 1, 2, 3
          2. exact collection-name combinations lexicographically
          3. positive count compositions lexicographically
        """

        collections = self.stratum.eligible_collections
        upper = min(MAX_DISTINCT_COLLECTIONS_PER_FAMILY, len(collections))
        for k in range(1, upper + 1):
            for selected in combinations(collections, k):
                for counts in _positive_compositions(INPUT_COUNT, k):
                    yield build_recipe_family(
                        input_rarity=self.stratum.input_rarity,
                        stattrak_mode=self.stratum.stattrak_mode,
                        collection_counts=tuple(zip(selected, counts, strict=True)),
                    )


def _positive_compositions(total: int, parts: int) -> Iterator[tuple[int, ...]]:
    """Yield lexicographically ordered positive compositions."""

    if parts == 1:
        yield (total,)
        return
    # First component ascending, then recurse, producing lexicographic order.
    for first in range(1, total - parts + 2):
        for rest in _positive_compositions(total - first, parts - 1):
            yield (first, *rest)


def build_recipe_family(
    *,
    input_rarity: str,
    stattrak_mode: StatTrakMode,
    collection_counts: tuple[tuple[str, int], ...],
) -> RecipeFamily:
    """Build an immutable RecipeFamily from validated structural inputs.

    Sorts the collection_counts ascending by exact collection name and
    rejects duplicate collections, non-positive counts, and a sum
    different from `INPUT_COUNT = 10`. Souvenir policy is NOT part of
    structural identity.
    """

    if not isinstance(stattrak_mode, StatTrakMode):
        raise RecipeFamilyIdentityError(
            "stattrak_mode must be a StatTrakMode enum value"
        )
    if not isinstance(collection_counts, tuple) or not collection_counts:
        raise RecipeFamilyIdentityError(
            "collection_counts must be a non-empty tuple"
        )
    if len(collection_counts) > MAX_DISTINCT_COLLECTIONS_PER_FAMILY:
        raise RecipeFamilyIdentityError(
            "distinct collections exceed MAX_DISTINCT_COLLECTIONS_PER_FAMILY"
        )

    normalised: list[tuple[str, int]] = []
    seen: set[str] = set()
    total = 0
    for entry in collection_counts:
        if type(entry) is not tuple or len(entry) != 2:
            raise RecipeFamilyIdentityError(
                "collection_counts entries must be (collection_name, count)"
            )
        name, count = entry
        if type(name) is not str or not name or name != name.strip():
            raise RecipeFamilyIdentityError(
                "collection_name must be non-empty exact string"
            )
        if name in seen:
            raise RecipeFamilyIdentityError(
                f"duplicate collection in counts: {name!r}"
            )
        if type(count) is not int or isinstance(count, bool):
            raise RecipeFamilyIdentityError("count must be int")
        if count <= 0:
            raise RecipeFamilyIdentityError("count must be > 0")
        seen.add(name)
        normalised.append((name, count))
        total += count
    if total != INPUT_COUNT:
        raise RecipeFamilyIdentityError(
            f"sum(collection_counts) must equal {INPUT_COUNT}"
        )
    normalised.sort(key=lambda pair: pair[0])
    sorted_counts = tuple(normalised)

    family_hash = compute_recipe_family_hash(
        input_rarity=input_rarity,
        stattrak_mode=stattrak_mode,
        collection_counts=sorted_counts,
    )
    family_key = family_hash[:24]
    return RecipeFamily(
        family_spec_version=RECIPE_FAMILY_SPEC_VERSION,
        input_rarity=input_rarity,
        stattrak_mode=stattrak_mode,
        collection_counts=sorted_counts,
        family_hash=family_hash,
        family_key=family_key,
    )


def compute_recipe_family_hash(
    *,
    input_rarity: str,
    stattrak_mode: StatTrakMode,
    collection_counts: tuple[tuple[str, int], ...],
) -> str:
    """Compute the canonical SHA-256 hex `family_hash` for a RecipeFamily.

    Identity bytes include ONLY:
      - family_spec_version
      - input_rarity
      - stattrak_mode (canonical token)
      - collection_counts (sorted ascending by exact collection name)

    They never include:
      - derived output rarity
      - finish keys
      - catalog version/hash
      - prices
      - Souvenir
      - ranking
    """

    sorted_counts = tuple(sorted(collection_counts, key=lambda pair: pair[0]))
    payload: dict[str, object] = {
        "family_spec_version": RECIPE_FAMILY_SPEC_VERSION,
        "input_rarity": input_rarity,
        "stattrak_mode": stattrak_mode.value,
        "collection_counts": [
            [name, int(count)] for name, count in sorted_counts
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def count_recipe_families(
    collection_count: int,
    *,
    max_distinct: int = MAX_DISTINCT_COLLECTIONS_PER_FAMILY,
) -> int:
    """Analytic count of RecipeFamily states for one stratum.

    For each subset of `k` distinct collections, the count of positive
    integer count-compositions of 10 into those `k` named buckets is
    `choose(9, k-1)`. The number of ordered-by-name subsets of size `k`
    chosen from `collection_count` collections is `choose(C, k)`.

    `count_families(C, K) = Σ_{k=1..min(K, C)} choose(C, k) * choose(9, k-1)`.
    """

    from math import comb

    if type(collection_count) is not int or isinstance(collection_count, bool):
        raise RecipeFamilyIdentityError("collection_count must be an integer")
    if type(max_distinct) is not int or isinstance(max_distinct, bool):
        raise RecipeFamilyIdentityError("max_distinct must be an integer")
    if max_distinct < 1 or max_distinct > MAX_DISTINCT_COLLECTIONS_PER_FAMILY:
        raise RecipeFamilyIdentityError(
            "max_distinct must be in [1, MAX_DISTINCT_COLLECTIONS_PER_FAMILY]"
        )
    if collection_count < 0:
        raise RecipeFamilyIdentityError("collection_count cannot be negative")
    if collection_count == 0:
        return 0
    upper = min(max_distinct, collection_count)
    total = 0
    for k in range(1, upper + 1):
        total += comb(collection_count, k) * comb(9, k - 1)
    return total