"""Intrinsic item-attribute representation for BUFF listing flow.

The BUFF sell-order payload currently does **not** expose authoritative
intrinsic item-instance flags (`stattrak`, `souvenir`). The previous
representation in the candidate layer hard-coded both to `False`, which
silently fabricated certainty. That is not acceptable as production
data representation.

This module defines the **correct** representation, which distinguishes:

  True  = established true by the verified source
  False = established false by the verified source
  None  = not established by this source (capability unknown / unverified)

The semantics are:

  * **No fabrication.** The default is `None`, never `False`.
  * **No inference.** Values are not derived from `goods_id`,
    `listing_id`, `asset_id`, `paintseed`, `price`, `URL`, or any
    other BUFF response field. Inference from any of those would
    silently invent data.
  * **Strict validation.** Non-bool, non-`None` values are rejected.
    `int 0` / `int 1` / string `"true"` / etc. are never accepted.
  * **Verbatim preservation.** The wrapping dataclass preserves every
    `BuffListing` field via `dataclasses.replace`; it does not mutate
    or reinterpret the underlying DTO.

The current source capability is **UNKNOWN** (the authorized anonymous
BUFF sell-order endpoint does not currently expose these fields). Any
field that is `None` is documented to flow into the candidate as
`None`, and the downstream enrichment boundary fails closed.

This module does NOT:

  * contact BUFF, SteamDT, SteamApis, or any other network source;
  * depend on the trade-up engine, valuation service, recipe solver,
    or any Protected Core module;
  * mutate any frozen DTO, including `BuffListing` itself.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from app.services.buff_listing_provider import BuffListing

__all__ = (
    "BuffListingIntrinsicFlags",
    "IntrinsicFlagValidationError",
    "coerce_intrinsic_flag",
    "is_intrinsic_flag_value",
)


_FIXED_ERROR = "invalid BUFF listing intrinsic flag value"
_ALLOWED_FIELDS = frozenset({"stattrak", "souvenir"})


class IntrinsicFlagValidationError(ValueError):
    """An intrinsic flag value violated the strict bool-or-None contract."""

    def __init__(self, *, field: str) -> None:
        if field not in _ALLOWED_FIELDS:
            raise ValueError("unsupported intrinsic flag field")
        super().__init__(_FIXED_ERROR)
        self.field = field


def is_intrinsic_flag_value(value: object) -> bool:
    """Return True iff `value` is `True`, `False`, or `None`."""

    return value is True or value is False or value is None


def coerce_intrinsic_flag(value: object, *, field: str) -> bool | None:
    """Validate one intrinsic flag value.

    Accepted:
      * `True` (the value `True`, not any truthy object);
      * `False` (the value `False`, not any falsy object);
      * `None` (not established by the source).

    Rejected (with `IntrinsicFlagValidationError`):
      * integers (`0`, `1`);
      * strings (`"true"`, `"false"`, `""`);
      * subclasses of `bool`;
      * `Decimal`, `float`, `list`, etc.

    The error is fixed-message; no rejected value is exposed.
    """

    if value is True or value is False or value is None:
        return value
    raise IntrinsicFlagValidationError(field=field)


@dataclass(frozen=True, kw_only=True, repr=False)
class BuffListingIntrinsicFlags:
    """One augmented listing carrying intrinsic item-instance flags.

    Wraps a `BuffListing` (which the project does NOT modify — see
    `ARCHITECTURE_STATE.md` Protected Core) and adds `stattrak` and
    `souvenir` in their correct three-state representation:

      * `True`  — established true;
      * `False` — established false;
      * `None`  — not established by this source.

    Every other field of the wrapped `BuffListing` is preserved
    verbatim via `dataclasses.replace`. The wrapper does NOT mutate
    the underlying DTO. The wrapper does NOT fabricate `False` from
    `None`; that translation is forbidden by project decision and is
    rejected at construction.

    The wrapper's repr is suppressed because the wrapped listing's
    value fields may include secret markers in test fixtures.
    """

    listing: BuffListing
    stattrak: bool | None = None
    souvenir: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.listing, BuffListing):
            raise TypeError("listing must be a BuffListing")
        coerce_intrinsic_flag(self.stattrak, field="stattrak")
        coerce_intrinsic_flag(self.souvenir, field="souvenir")

    def __getattr__(self, name: str) -> Any:
        # Delegate every other attribute to the wrapped BuffListing.
        # This lets the candidate adapter read `market_hash_name`,
        # `price_cny`, `paintwear`, `asset_id`, etc. via normal
        # attribute access, exactly as it does for a plain
        # BuffListing.
        return getattr(self.listing, name)


def with_intrinsic_flags(
    listing: BuffListing,
    *,
    stattrak: bool | None = None,
    souvenir: bool | None = None,
) -> BuffListingIntrinsicFlags:
    """Construct one wrapper around `listing` with the given flags.

    Convenience factory that performs the strict validation. Default
    values are `None` (not established) for both fields.
    """
    return BuffListingIntrinsicFlags(
        listing=listing,
        stattrak=stattrak,
        souvenir=souvenir,
    )


def replace_intrinsic_flags(
    wrapper: BuffListingIntrinsicFlags,
    *,
    stattrak: bool | None | object = ...,
    souvenir: bool | None | object = ...,
) -> BuffListingIntrinsicFlags:
    """Return a new wrapper with selected intrinsic flags replaced.

    Use the sentinel `...` to leave a field unchanged.
    """
    new_kwargs: dict[str, Any] = {}
    if stattrak is not ...:
        new_kwargs["stattrak"] = stattrak
    if souvenir is not ...:
        new_kwargs["souvenir"] = souvenir
    return replace(wrapper, **new_kwargs)


# Re-export Decimal for callers that need to type-hint alongside this
# module. The import is preserved intentionally to keep the surface
# stable for tests that exercise the wrapper with custom Decimal values.
_ = (Decimal,)