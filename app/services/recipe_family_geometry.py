"""Phase 16B — RecipeFamily finish-level structural geometry.

This module computes the immutable finish-level structural geometry
for a `RecipeFamily`:

  RecipeFamily
    + StructuralOutputFinishIndex
    -> RecipeFamilyGeometry

Probability rule (frozen by Phase 16A / 16A-R1 / 16A-R2 and
`D-RECIPE-FIRST-PROBABILITY-001`):

  For collection c appearing `n_c` times in the family input
  distribution and having `N_c` unique eligible structural output
  finishes at the next rarity and matching StatTrak mode:

    P(one unique structural output finish j in collection c)
      = (n_c / 10) / N_c

  Implemented with exact rational arithmetic via
  `fractions.Fraction`.

  The probability sum over all outcomes in the geometry MUST equal
  exactly 1.

  Probability MUST NOT depend on:
    - number of wear rows for a finish
    - number of market_hash_names representing wear bands
    - SteamDT availability
    - BUFF identity availability for outputs

This module performs zero network I/O. It is OFFLINE ONLY. It does
NOT touch the production scanner, orchestrator, or CLI. It does NOT
touch the production `tradeup_engine.calculate_tradeup_results`.
"""

from __future__ import annotations

from collections.abc import Iterable as IterableABC
from dataclasses import dataclass
from fractions import Fraction

from app.services.recipe_family import (
    INPUT_COUNT,
    RecipeFamily,
    StatTrakMode,
    get_next_rarity,
)
from app.services.structural_output_finish import (
    StructuralOutputFinishIndex,
)

__all__ = (
    "RecipeFamilyGeometry",
    "RecipeFamilyGeometryError",
    "StructuralFinishProbability",
    "compute_recipe_family_geometry",
)

_ONE = Fraction(1, 1)
_ZERO = Fraction(0, 1)


@dataclass(frozen=True, kw_only=True, repr=False)
class StructuralFinishProbability:
    """One unique finish outcome and its exact rational probability."""

    finish_key: str
    probability: Fraction

    def __post_init__(self) -> None:
        if not isinstance(self.finish_key, str) or not self.finish_key:
            raise RecipeFamilyGeometryError(
                "finish_key must be a non-empty string"
            )
        if not isinstance(self.probability, Fraction):
            raise RecipeFamilyGeometryError(
                "probability must be a fractions.Fraction"
            )
        if self.probability <= _ZERO or self.probability > _ONE:
            raise RecipeFamilyGeometryError(
                f"probability must be in (0, 1]; got {self.probability}"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class RecipeFamilyGeometry:
    """Immutable finish-level structural geometry for one RecipeFamily."""

    family_hash: str
    output_rarity: str
    output_stattrak: bool
    outcomes: tuple[StructuralFinishProbability, ...]

    def __post_init__(self) -> None:
        if (
            type(self.family_hash) is not str
            or len(self.family_hash) != 64
            or any(ch not in "0123456789abcdef" for ch in self.family_hash)
        ):
            raise RecipeFamilyGeometryError(
                "family_hash must be full lowercase SHA-256 hex"
            )
        if not isinstance(self.output_rarity, str) or not self.output_rarity:
            raise RecipeFamilyGeometryError(
                "output_rarity must be a non-empty string"
            )
        if not isinstance(self.output_stattrak, bool):
            raise RecipeFamilyGeometryError(
                "output_stattrak must be a boolean"
            )
        if not isinstance(self.outcomes, tuple) or not all(
            isinstance(o, StructuralFinishProbability) for o in self.outcomes
        ):
            raise RecipeFamilyGeometryError(
                "outcomes must be a tuple of StructuralFinishProbability"
            )
        total = sum((o.probability for o in self.outcomes), start=_ZERO)
        if total != _ONE:
            raise RecipeFamilyGeometryError(
                f"probability sum must equal exactly 1; got {total}"
            )

    @property
    def finish_keys(self) -> tuple[str, ...]:
        return tuple(o.finish_key for o in self.outcomes)


class RecipeFamilyGeometryError(ValueError):
    """A recipe family geometry input or output violated the contract."""


def compute_recipe_family_geometry(
    family: RecipeFamily,
    *,
    finish_index: StructuralOutputFinishIndex,
) -> RecipeFamilyGeometry:
    """Compute the immutable finish-level structural geometry.

    For each input collection c appearing `n_c` times in the family:

      - look up unique eligible output finishes for c at the next
        rarity and matching StatTrak mode via the finish index;
      - if `N_c == 0`, raise (the family is structurally invalid for
        this catalog state);
      - emit `N_c` outcomes, each with `probability = (n_c / 10) / N_c`.

    Outcomes are emitted in deterministic order:
      `(collection_name ascending, finish_key ascending)`.

    Duplicate `finish_key` across multiple collections is impossible
    in the current snapshot (cross-collection collision count = 0 in
    the Phase 16A-R2 audit) and would otherwise fail closed.
    """

    if type(family) is not RecipeFamily:
        raise RecipeFamilyGeometryError("family must be a RecipeFamily")
    if type(finish_index) is not StructuralOutputFinishIndex:
        raise RecipeFamilyGeometryError(
            "finish_index must be StructuralOutputFinishIndex"
        )
    output_rarity = get_next_rarity(family.input_rarity)
    if output_rarity is None:
        raise RecipeFamilyGeometryError(
            f"no next rarity for input rarity {family.input_rarity!r}"
        )
    output_stattrak = bool(family.stattrak_mode is StatTrakMode.STATTRAK)

    seen_finish_keys: set[str] = set()
    outcomes: list[StructuralFinishProbability] = []
    for collection_name, count in family.collection_counts:
        if type(count) is not int or count <= 0 or count > INPUT_COUNT:
            raise RecipeFamilyGeometryError(
                f"invalid collection count: {collection_name!r} -> {count}"
            )
        finish_keys = finish_index.finish_keys_for_collection(
            collection_name=collection_name,
            rarity=output_rarity,
            stattrak=output_stattrak,
        )
        if not finish_keys:
            raise RecipeFamilyGeometryError(
                f"no eligible output finishes for collection "
                f"{collection_name!r} at rarity {output_rarity!r} "
                f"and stattrak={output_stattrak}"
            )
        n_c = Fraction(int(count), INPUT_COUNT)
        n_finishes = Fraction(len(finish_keys), 1)
        per_finish = n_c / n_finishes
        if per_finish <= _ZERO or per_finish > _ONE:
            raise RecipeFamilyGeometryError(
                f"per-finish probability out of (0, 1]: {per_finish}"
            )
        for finish_key in finish_keys:
            if finish_key in seen_finish_keys:
                raise RecipeFamilyGeometryError(
                    f"finish_key collision across collections: {finish_key!r}"
                )
            seen_finish_keys.add(finish_key)
            outcomes.append(
                StructuralFinishProbability(
                    finish_key=finish_key,
                    probability=per_finish,
                )
            )

    # Deterministic outcome ordering: finish_key ascending.
    outcomes.sort(key=lambda o: o.finish_key)

    return RecipeFamilyGeometry(
        family_hash=family.family_hash,
        output_rarity=output_rarity,
        output_stattrak=output_stattrak,
        outcomes=tuple(outcomes),
    )


def sum_probabilities(
    outcomes: IterableABC[StructuralFinishProbability],
) -> Fraction:
    """Exact-rational probability sum helper for tests."""

    return sum((o.probability for o in outcomes), start=_ZERO)