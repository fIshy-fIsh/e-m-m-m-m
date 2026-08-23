"""Pure intrinsic-flag resolver based on canonical Steam `market_hash_name`.

This module provides a deterministic, exact-canonical-string-prefix
classifier for the two intrinsic item-instance flags (`stattrak`,
`souvenir`). The classifier uses the canonical Steam community market
naming convention:

  * `stattrak=True`  iff the exact `market_hash_name` starts with the
    canonical string `"StatTrak™ "` (the trademark sign U+2122
    followed by a single ASCII space; 10 Unicode codepoints; 12
    UTF-8 bytes).
  * `souvenir=True`  iff the exact `market_hash_name` starts with the
    canonical string `"Souvenir "` (a single ASCII space; 9 Unicode
    codepoints; 9 UTF-8 bytes).
  * Otherwise the respective flag is `False`.

The two prefixes are mutually exclusive: a `market_hash_name` cannot
start with both prefixes simultaneously. This invariant holds for the
entire pinned identity catalog (see `D-INTRINSIC-002`).

The classifier is pure:

  * no HTTP;
  * no filesystem mutation;
  * no BUFF / SteamDT / SteamApis / Redis / DB / Discord;
  * no fuzzy matching;
  * no casefold;
  * no whitespace normalization;
  * no `None -> False` coercion at the seam;
  * no caller-provided override of the rule.

Malformed input (non-string, empty string, or whitespace-padded
strings) is rejected with `IntrinsicFlagInputError`. The classifier
never silently fixes bad input.

The classifier is suitable as a production-side canonical-name
classifier for the `market_hash_name` keys supplied by the BUFF
community catalog snapshot (`D-IDENTITY-006`) and confirmed by the
13N-3A spot-check across twelve canonical-name categories.

It does NOT establish the BUFF transport-level fact of which listings
exist on the live anonymous BUFF endpoint. The classifier's output is
a `catalog-derived intrinsic classification`, not a `BUFF-supplied
intrinsic flag`. The classification is independent of any live
transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

from app.services.buff_listing_intrinsic_flags import IntrinsicFlagValidationError

__all__ = (
    "BuffListingIntrinsicFlagsValue",
    "BuffListingIntrinsicFlagResolver",
    "CanonicalNameIntrinsicFlagResolver",
    "IntrinsicFlagInputError",
    "STATTRAK_PREFIX",
    "SOUVENIR_PREFIX",
)


_FIXED_INPUT_ERROR = "invalid BUFF listing intrinsic-flag input"
_ALLOWED_INPUT_FIELDS = frozenset({"market_hash_name"})


class IntrinsicFlagInputError(ValueError):
    """The input to an intrinsic-flag resolver violated the strict contract.

    This error covers malformed input names (non-string, empty, padded)
    and is distinct from `IntrinsicFlagValidationError`, which covers
    malformed intrinsic-flag values themselves.
    """

    def __init__(self, *, field: str) -> None:
        if field not in _ALLOWED_INPUT_FIELDS:
            raise ValueError("unsupported intrinsic-flag input field")
        super().__init__(_FIXED_INPUT_ERROR)
        self.field = field


# Canonical Steam market_hash_name prefixes (exact canonical strings).
# Python `str.startswith` compares by Unicode code point, not by byte.
STATTRAK_PREFIX: Final[str] = "StatTrak™ "  # 10 codepoints; 12 UTF-8 bytes
SOUVENIR_PREFIX: Final[str] = "Souvenir "    # 9 codepoints; 9 UTF-8 bytes


@dataclass(frozen=True, kw_only=True)
class BuffListingIntrinsicFlagsValue:
    """One classification result: independent `True`/`False`/`None` per flag.

    Three states per flag:

      * `True` — established true by the classifier;
      * `False` — established false by the classifier;
      * `None` — the source could not establish the value.

    The classifier emits only `True` or `False`; the canonical
    classifier never produces `None` for a well-formed input. `None`
    is reserved for callers that wrap a different resolver whose
    source does not establish the value, or for inputs that fail
    validation upstream.
    """

    stattrak: bool | None
    souvenir: bool | None

    def __post_init__(self) -> None:
        _validate_value(self.stattrak, field="stattrak")
        _validate_value(self.souvenir, field="souvenir")


def _validate_value(value: object, *, field: str) -> None:
    if value is True or value is False or value is None:
        return
    raise IntrinsicFlagValidationError(field=field)


class BuffListingIntrinsicFlagResolver(Protocol):
    """Resolve one canonical `market_hash_name` to its intrinsic flags.

    Implementations must be pure: no HTTP, no filesystem mutation,
    no BUFF / SteamDT / SteamApis / Redis / DB / Discord.
    """

    def resolve(
        self,
        market_hash_name: str,
    ) -> BuffListingIntrinsicFlagsValue:
        """Return one classification result; `None` is reserved for unknown."""


class CanonicalNameIntrinsicFlagResolver:
    """Exact-canonical-string-prefix classifier.

    The classifier follows the canonical Steam community market naming
    convention. It is intentionally trivial; the empirical validation
    in `D-INTRINSIC-002` shows it covers the full pinned identity
    catalog (34,402 accepted entries) with zero contradictions and
    no required normalization.
    """

    def resolve(
        self,
        market_hash_name: str,
    ) -> BuffListingIntrinsicFlagsValue:
        """Return one classification result for an exact `market_hash_name`.

        The classifier:

          * rejects non-string, empty, or whitespace-padded inputs with
            `IntrinsicFlagInputError`;
          * accepts only exact strings that already passed validation
            upstream (no trimming, no casefold);
          * returns `True` for the matching prefix and `False` for the
            other prefix, deterministically.
        """
        if type(market_hash_name) is not str:
            raise IntrinsicFlagInputError(field="market_hash_name")
        if not market_hash_name:
            raise IntrinsicFlagInputError(field="market_hash_name")
        if market_hash_name != market_hash_name.strip():
            raise IntrinsicFlagInputError(field="market_hash_name")
        return BuffListingIntrinsicFlagsValue(
            stattrak=market_hash_name.startswith(STATTRAK_PREFIX),
            souvenir=market_hash_name.startswith(SOUVENIR_PREFIX),
        )


# Final re-export to placate linters.
_ = (IntrinsicFlagValidationError,)