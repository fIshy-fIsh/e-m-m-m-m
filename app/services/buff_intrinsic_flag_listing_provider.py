"""Composition layer that attaches resolved intrinsic flags to listings.

The phase 13O-1 architecture separates three responsibilities:

    1. `IdentityResolvingBuffListingProvider`  (identity-only)
    2. `IntrinsicFlagResolvingBuffListingProvider`  (intrinsic-flag-only; this module)
    3. `BuffListingCandidateAdapter`  (DTO -> candidate)

This module owns (2). It wraps an upstream provider (typically the
identity-resolving provider) and a `BuffListingIntrinsicFlagResolver`.
For each returned page, it:

  1. verifies that every non-`None` `market_hash_name` in the page
     carries the same exact canonical value (a single identity-resolved
     `goods_id` MUST correspond to a single canonical name across the
     whole page);
  2. invokes the intrinsic-flag resolver at most ONCE per page, using
     that canonical name;
  3. applies the resulting flags to every listing in the page via
     `BuffListingIntrinsicFlags`.

When the page is empty, the resolver is not invoked and no flags are
produced. When every listing in the page has `market_hash_name=None`
(identity fully unresolved), the resolver is not invoked and every
listing's flags remain `None`.

Invariants enforced by this layer:

  * the underlying provider contract is preserved verbatim;
  * the canonical `market_hash_name` is identical across all
    non-`None` listings in the same page (or the binding layer fails
    closed with `IntrinsicFlagInputError`);
  * the intrinsic-flag resolver is invoked at most once per page;
  * no `None -> False` coercion occurs at any seam;
  * every other listing field is preserved exactly;
  * the resolver never falls back to a different source when one
    fails (the failure propagates verbatim);
  * no network I/O is initiated by the binding layer itself.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.services.buff_intrinsic_flag_resolver import (
    BuffListingIntrinsicFlagResolver,
    IntrinsicFlagInputError,
)
from app.services.buff_listing_intrinsic_flags import BuffListingIntrinsicFlags
from app.services.buff_listing_provider import BuffListing

__all__ = (
    "BuffListingProviderLike",
    "IntrinsicFlagResolvingBuffListingProvider",
    "bind_intrinsic_flags_to_provider",
)


class BuffListingProviderLike(Protocol):
    """Structural surface for the upstream provider."""

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        """Return one parsed page of listings for one caller-provided goods_id."""


class IntrinsicFlagResolvingBuffListingProvider:
    """Attach intrinsic flags to every listing returned by an upstream provider.

    Construction:
        ``IntrinsicFlagResolvingBuffListingProvider(provider, resolver)``

    Public API:
        ``async get_listings(goods_id) -> list[BuffListing]``

    Per call:
        1. invoke ``provider.get_listings(goods_id)`` once;
        2. determine the single canonical ``market_hash_name`` for the
           page (or detect that all are ``None``, or fail closed if the
           page contains conflicting non-``None`` names);
        3. invoke the intrinsic-flag resolver at most once per page
           using the canonical name;
        4. wrap each listing in ``BuffListingIntrinsicFlags`` with the
           classification result.

    The composed provider exposes ONLY the ``get_listings`` surface; the
    binding layer does not leak the resolver or the upstream provider
    to the outside world.
    """

    _provider: BuffListingProviderLike
    _resolver: BuffListingIntrinsicFlagResolver

    def __init__(
        self,
        provider: BuffListingProviderLike,
        resolver: BuffListingIntrinsicFlagResolver,
    ) -> None:
        if not hasattr(provider, "get_listings"):
            raise TypeError("provider must expose get_listings")
        if resolver is None or not hasattr(resolver, "resolve"):
            raise TypeError("resolver must expose resolve")
        self._provider = provider
        self._resolver = resolver

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        """Return one flagged page of listings.

        The intrinsic-flag resolver is invoked at most once per page.
        When the page is empty or fully unresolved, no resolver call is
        made. When the page contains conflicting non-``None`` canonical
        names, the binding layer fails closed with
        ``IntrinsicFlagInputError``.
        """
        raw_listings = await self._provider.get_listings(goods_id)
        raw_sequence: Sequence[BuffListing] = tuple(raw_listings)

        if not raw_sequence:
            return []

        canonical_name = _extract_canonical_name(raw_sequence)

        if canonical_name is None:
            # Identity is fully unresolved across the page. We
            # cannot classify. Every listing's flags remain `None`.
            return [
                BuffListingIntrinsicFlags(  # type: ignore[misc]
                    listing=listing,
                    stattrak=None,
                    souvenir=None,
                )
                for listing in raw_sequence
            ]

        # Resolver invoked at most once per page.
        value = self._resolver.resolve(canonical_name)
        return [
            BuffListingIntrinsicFlags(  # type: ignore[misc]
                listing=listing,
                stattrak=value.stattrak,
                souvenir=value.souvenir,
            )
            for listing in raw_sequence
        ]


def _extract_canonical_name(
    raw_sequence: Sequence[BuffListing],
) -> str | None:
    """Determine the single canonical ``market_hash_name`` for a page.

    Returns the common non-``None`` value when at least one listing
    carries it; returns ``None`` when every listing has ``market_hash_name``
    set to ``None``; raises ``IntrinsicFlagInputError`` when the page
    contains conflicting non-``None`` values (an integrity violation
    that the upstream identity-binding stage is supposed to prevent).
    """
    canonical_name: str | None = None
    has_any = False
    for listing in raw_sequence:
        current = listing.market_hash_name
        if current is None:
            continue
        has_any = True
        if canonical_name is None:
            canonical_name = current
        elif canonical_name != current:
            raise IntrinsicFlagInputError(field="market_hash_name")
    if not has_any:
        return None
    return canonical_name


@runtime_checkable
class _ResolverLike(Protocol):
    def resolve(self, market_hash_name: str) -> object: ...


def bind_intrinsic_flags_to_provider(
    provider: BuffListingProviderLike,
    resolver: BuffListingIntrinsicFlagResolver,
) -> IntrinsicFlagResolvingBuffListingProvider:
    """Construct one ``IntrinsicFlagResolvingBuffListingProvider``."""
    if not isinstance(resolver, _ResolverLike):
        raise TypeError("resolver must expose resolve")
    return IntrinsicFlagResolvingBuffListingProvider(
        provider=provider,
        resolver=resolver,
    )