"""Identity binding layer between BuffListingProvider and BuffListingCandidateAdapter.

This module composes a raw `BuffListingProvider` with a goods-id identity
resolver. It performs exactly **one** `resolve_goods_id` call per provider
fetch (a BUFF sell-order page is already scoped to one caller-provided
goods_id), and rebinds that identity onto every returned listing as the
exact `market_hash_name` value.

The result is a new provider whose `get_listings(goods_id)` returns a
list of `BuffListing` instances whose `market_hash_name` is either the
resolved exact name (resolved identity) or stays `None` (unresolved).
The downstream `BuffListingCandidateAdapter` then continues to operate
without any knowledge of identity resolution — it reads the name off
the DTO exactly as it did before.

Strict invariants enforced by this layer:

* the underlying provider contract (borrowed `fetch_sell_order_payload`)
  is preserved verbatim;
* identity lookup count per provider fetch is exactly one;
* the resolved identity's `goods_id` MUST equal the requested `goods_id`
  — otherwise fail closed with a deterministic integrity error;
* every returned listing's `goods_id` MUST equal the requested `goods_id`
  — otherwise fail closed;
* pre-existing `market_hash_name` on a returned listing:
    - if it equals the resolved exact name → preserved;
    - if it conflicts with the resolved exact name → fail closed;
    - if no resolution → preserved (typically `None`);
* identity resolver failures (network, MemoryError, validation) do not
  trigger fallback I/O; they propagate verbatim.
* no HTTP / no scheduling framework / no scanner / no metadata / no enrichment /
  no trade-up engine / no SteamDT / no SteamApis / no Redis / no DB /
  no Discord. This module performs only in-process composition.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from app.services.buff_community_identity_resolver import BuffGoodsIdIdentityResolver
from app.services.buff_listing_provider import BuffListing

__all__ = (
    "BuffIdentityBindingError",
    "BuffIdentityBindingListingGoodsIdMismatchError",
    "BuffIdentityBindingMarketHashNameConflictError",
    "BuffIdentityBindingResolverMismatchError",
    "IdentityResolvingBuffListingProvider",
    "bind_identity_to_provider",
    "resolve_listings_identity",
)


_FIXED_ERROR = "invalid BUFF listing identity binding contract"
_ALLOWED_ERROR_KINDS = frozenset(
    {
        "resolver_goods_id_mismatch",
        "listing_goods_id_mismatch",
        "market_hash_name_conflict",
    }
)


class BuffIdentityBindingError(ValueError):
    """A BUFF listing identity binding invariant failed.

    The binding layer is fail-closed. Any integrity violation produces
    a deterministic error with one of three closed reasons:

      * ``resolver_goods_id_mismatch`` — the resolver returned an
        identity whose `goods_id` did not equal the requested
        `goods_id`. This should never happen with the pinned snapshot,
        but the seam defends itself against it.
      * ``listing_goods_id_mismatch`` — the underlying provider
        returned a listing whose `goods_id` did not equal the requested
        `goods_id`. The provider is supposed to scope one page to one
        goods_id; this defends against silent contract drift.
      * ``market_hash_name_conflict`` — the underlying provider
        returned a listing whose existing `market_hash_name` did not
        equal the resolved exact name. The binding layer does not
        silently overwrite conflicting identity; it fails closed.

    Errors expose only the allowlisted reason code. The rejected
    listing, the requested goods_id, and any other value are NOT
    attached to the exception (see `__repr__` / `__str__`).
    """

    def __init__(self, *, reason: str) -> None:
        if reason not in _ALLOWED_ERROR_KINDS:
            raise ValueError("unsupported BUFF identity binding reason")
        super().__init__(_FIXED_ERROR)
        self.reason = reason


class BuffIdentityBindingResolverMismatchError(BuffIdentityBindingError):
    """Convenience subclass: resolver returned identity for a different goods_id."""


class BuffIdentityBindingListingGoodsIdMismatchError(BuffIdentityBindingError):
    """Convenience subclass: provider returned a listing for a different goods_id."""


class BuffIdentityBindingMarketHashNameConflictError(BuffIdentityBindingError):
    """Convenience subclass: existing market_hash_name conflicts with the resolved name."""


class BuffListingProviderLike(Protocol):
    """Structural surface for the underlying provider.

    Only the `get_listings` coroutine is needed. The binding layer does
    not import the provider class into a nominal check; it duck-types.
    """

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        """Return one parsed page of listings for one caller-provided goods_id."""


@dataclass(frozen=True, kw_only=True)
class _ResolvedPage:
    """One resolved provider page with the resolved identity and rebound listings.

    `rebound_listings` may contain plain `BuffListing` instances (when
    no intrinsic flags were supplied for the fetch) or
    `BuffListingIntrinsicFlags` wrappers (when flags were supplied).
    The wrappers expose every original field via attribute delegation
    so downstream code can read `listing.market_hash_name`,
    `listing.price_cny`, etc. uniformly.
    """

    resolved_market_hash_name: str | None
    resolved_goods_id: str
    rebound_listings: tuple[BuffListing, ...]


class IdentityResolvingBuffListingProvider:
    """Compose a raw `BuffListingProvider` with an identity resolver.

    Construction:
        ``IdentityResolvingBuffListingProvider(provider, resolver)``

    Public API:
        ``async get_listings(goods_id) -> list[BuffListing]``

    Per call:
        1. invoke `provider.get_listings(goods_id)` once;
        2. invoke `resolver.resolve_goods_id(goods_id)` once;
        3. validate the resolver identity's `goods_id` equals the
           requested `goods_id`; fail closed otherwise;
        4. validate every listing's `goods_id` equals the requested
           `goods_id`; fail closed otherwise;
        5. for each listing:
             * if listing already carries an exact `market_hash_name`
               that equals the resolved name → preserve;
             * if listing already carries a different `market_hash_name`
               → fail closed (`market_hash_name_conflict`);
             * otherwise replace with the resolved exact name, or keep
               `None` if identity is unresolved.

    The composed provider exposes ONLY the `get_listings` surface; the
    binding layer does not leak the resolver or the underlying provider
    to the outside world.
    """

    _provider: BuffListingProviderLike
    _resolver: BuffGoodsIdIdentityResolver

    def __init__(
        self,
        provider: BuffListingProviderLike,
        resolver: BuffGoodsIdIdentityResolver,
    ) -> None:
        if not hasattr(provider, "get_listings"):
            raise BuffIdentityBindingError(reason="listing_goods_id_mismatch")
        if not hasattr(resolver, "resolve_goods_id"):
            raise BuffIdentityBindingError(reason="resolver_goods_id_mismatch")
        self._provider = provider
        self._resolver = resolver

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        """Return one rebound page of listings; exactly one identity lookup.

        The identity-binding layer is identity-only (Phase 13O-1). It
        does NOT carry intrinsic-flag state. Intrinsic flags are the
        responsibility of a separate composition layer
        (``IntrinsicFlagResolvingBuffListingProvider``); that layer
        runs after this one and reads the resolved names off the
        returned listings.
        """
        resolved = await resolve_listings_identity(
            provider=self._provider,
            resolver=self._resolver,
            goods_id=goods_id,
        )
        return list(resolved.rebound_listings)


async def resolve_listings_identity(
    *,
    provider: BuffListingProviderLike,
    resolver: BuffGoodsIdIdentityResolver,
    goods_id: str,
) -> _ResolvedPage:
    """Resolve one provider page using the supplied resolver.

    The caller may be a composed provider or a one-shot test harness.
    The function is exported to make the integration testable in
    isolation (no composed wrapper required).

    `goods_id` MUST be an exact non-empty stripped string. The
    underlying provider's own contract enforces this; the binding
    layer's validation here is a defensive pass-through. A non-string
    input raises `TypeError` immediately (not fail-closed; the caller
    has violated the type contract).

    Phase 13O-1: the identity-binding layer does NOT carry intrinsic
    flags. Each returned listing is a plain ``BuffListing`` with the
    resolved ``market_hash_name``. A separate composition layer
    attaches intrinsic flags after this step.
    """
    if type(goods_id) is not str or not goods_id or goods_id != goods_id.strip():
        raise TypeError("goods_id must be a non-empty stripped string")

    raw_listings = await provider.get_listings(goods_id)
    raw_sequence: Sequence[BuffListing] = tuple(raw_listings)

    identity = await resolver.resolve_goods_id(goods_id)

    if identity is None:
        resolved_name: str | None = None
    else:
        if identity.goods_id != goods_id:
            raise BuffIdentityBindingError(reason="resolver_goods_id_mismatch")
        resolved_name = identity.market_hash_name

    rebound: list[BuffListing] = []
    # Track the canonical non-None market_hash_name across the page.
    # All listings in one page MUST share the same canonical name
    # (the BUFF sell-order endpoint scopes one page to one
    # caller-provided goods_id; the identity resolver either supplies
    # the same name or leaves all names None). Conflicting non-None
    # values are an integrity violation and fail closed.
    page_canonical_name: str | None = None
    page_has_any_name = False
    for listing in raw_sequence:
        if listing.goods_id != goods_id:
            raise BuffIdentityBindingError(reason="listing_goods_id_mismatch")
        existing = listing.market_hash_name
        if existing is None:
            rebound_listing: BuffListing = (
                listing if resolved_name is None
                else replace(listing, market_hash_name=resolved_name)
            )
        else:
            if resolved_name is None:
                rebound_listing = listing
            elif existing == resolved_name:
                rebound_listing = listing
            else:
                raise BuffIdentityBindingError(reason="market_hash_name_conflict")
        rebound.append(rebound_listing)
        # Track page-level canonical-name consistency.
        rebound_name = rebound_listing.market_hash_name
        if rebound_name is None:
            continue
        page_has_any_name = True
        if page_canonical_name is None:
            page_canonical_name = rebound_name
        elif page_canonical_name != rebound_name:
            raise BuffIdentityBindingError(reason="market_hash_name_conflict")
    # Defensive check: the page should never contain both None and
    # non-None names (every listing either has the resolved name or
    # None). If it does, fail closed.
    if page_has_any_name and page_canonical_name is None:
        raise BuffIdentityBindingError(reason="market_hash_name_conflict")

    return _ResolvedPage(
        resolved_market_hash_name=resolved_name,
        resolved_goods_id=goods_id,
        rebound_listings=tuple(rebound),
    )


def bind_identity_to_provider(
    provider: BuffListingProviderLike,
    resolver: BuffGoodsIdIdentityResolver,
) -> IdentityResolvingBuffListingProvider:
    """Construct an `IdentityResolvingBuffListingProvider`.

    This is the explicit composition seam. Callers that want identity
    binding call this once at composition time and receive a provider
    whose only API is `get_listings(goods_id)`.
    """
    return IdentityResolvingBuffListingProvider(provider=provider, resolver=resolver)


# Convenience subclass aliases (preserved for diagnostic clarity but
# not part of `__all__`). They share the same closed vocabulary so they
# never add new failure modes.
_ = (
    BuffIdentityBindingResolverMismatchError,
    BuffIdentityBindingListingGoodsIdMismatchError,
    BuffIdentityBindingMarketHashNameConflictError,
)