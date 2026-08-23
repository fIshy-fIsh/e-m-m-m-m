"""Tests for the identity-binding layer between BuffListingProvider and the adapter.

Project convention: async tests are wrapped in `asyncio.run(...)` rather
than `@pytest.mark.asyncio`. The binding layer must compose, not modify,
the provider and the adapter; the adapter tests continue to operate
unchanged.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.buff_identity_listing_provider import (
    BuffIdentityBindingError,
    bind_identity_to_provider,
    resolve_listings_identity,
)
from app.services.buff_listing_candidate_adapter import convert_buff_listings
from app.services.buff_listing_provider import BuffListing
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputEnricher,
    InMemoryTradeUpInputMetadataResolver,
    TradeUpInputMetadata,
    enrich_candidates,
)

NAME = "AK-47 | Redline (Field-Tested)"
OTHER_NAME = "AK-47 | Redline (Minimal Wear)"
GOODS_ID = "33960"
OTHER_GOODS_ID = "33961"


def _listing(
    *,
    listing_id: str = "listing-1",
    goods_id: str = GOODS_ID,
    market_hash_name: str | None = None,
    price_cny: Decimal = Decimal("12.34"),
    paintwear: Decimal = Decimal("0.1234"),
    asset_id: str = "asset-1",
    paintseed: int | None = 123,
) -> BuffListing:
    return BuffListing(
        listing_id=listing_id,
        goods_id=goods_id,
        market_hash_name=market_hash_name,
        price_cny=price_cny,
        paintwear=paintwear,
        asset_id=asset_id,
        paintseed=paintseed,
        source="buff",
    )


class _FakeProvider:
    """Minimal provider surface for binding-layer tests."""

    def __init__(self, listings: list[BuffListing]) -> None:
        self._listings = listings
        self.calls: list[str] = []

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        self.calls.append(goods_id)
        return list(self._listings)


class _FakeResolver:
    """Records call count; resolves or returns None deterministically."""

    def __init__(self, mapping: dict[str, str] | None) -> None:
        self._mapping = mapping or {}
        self.calls: list[str] = []

    async def resolve_goods_id(self, goods_id: str) -> object:
        self.calls.append(goods_id)
        from app.services.buff_item_identity import BuffItemIdentity
        if goods_id in self._mapping:
            return BuffItemIdentity(
                market_hash_name=self._mapping[goods_id],
                goods_id=goods_id,
            )
        return None


def _run(coro: object) -> object:
    return asyncio.run(coro)


def test_resolved_identity_is_rebound_onto_listing() -> None:
    provider = _FakeProvider([_listing()])
    resolver = _FakeResolver({GOODS_ID: NAME})
    bound = bind_identity_to_provider(provider, resolver)
    listings = _run(bound.get_listings(GOODS_ID))
    assert len(listings) == 1
    assert listings[0].market_hash_name == NAME
    assert listings[0].goods_id == GOODS_ID


def test_one_provider_fetch_performs_exactly_one_identity_lookup() -> None:
    provider = _FakeProvider(
        [_listing(listing_id="l1"), _listing(listing_id="l2"), _listing(listing_id="l3")]
    )
    resolver = _FakeResolver({GOODS_ID: NAME})
    bound = bind_identity_to_provider(provider, resolver)
    _run(bound.get_listings(GOODS_ID))
    assert len(provider.calls) == 1
    assert provider.calls == [GOODS_ID]
    assert resolver.calls == [GOODS_ID]


def test_all_listings_for_same_goods_id_receive_same_resolved_name() -> None:
    provider = _FakeProvider(
        [
            _listing(listing_id="l1", market_hash_name=None),
            _listing(listing_id="l2", market_hash_name=None),
            _listing(listing_id="l3", market_hash_name=None),
        ]
    )
    resolver = _FakeResolver({GOODS_ID: NAME})
    bound = bind_identity_to_provider(provider, resolver)
    listings = _run(bound.get_listings(GOODS_ID))
    assert [item.market_hash_name for item in listings] == [NAME, NAME, NAME]


def test_all_non_identity_fields_are_preserved_verbatim() -> None:
    original = _listing(
        listing_id="listing-99",
        price_cny=Decimal("999.99"),
        paintwear=Decimal("0.456789"),
        asset_id="asset-99",
        paintseed=999,
    )
    provider = _FakeProvider([original])
    resolver = _FakeResolver({GOODS_ID: NAME})
    bound = bind_identity_to_provider(provider, resolver)
    listings = _run(bound.get_listings(GOODS_ID))
    assert len(listings) == 1
    out = listings[0]
    assert out.listing_id == "listing-99"
    assert out.goods_id == GOODS_ID
    assert out.price_cny == Decimal("999.99")
    assert out.paintwear == Decimal("0.456789")
    assert out.asset_id == "asset-99"
    assert out.paintseed == 999
    assert out.source == "buff"
    assert out.market_hash_name == NAME


def test_unresolved_goods_id_keeps_market_hash_name_none() -> None:
    provider = _FakeProvider(
        [_listing(listing_id="l1", market_hash_name=None)]
    )
    resolver = _FakeResolver(mapping={})
    bound = bind_identity_to_provider(provider, resolver)
    listings = _run(bound.get_listings(GOODS_ID))
    assert listings[0].market_hash_name is None


def test_unresolved_listing_flows_into_adapter_then_misses_identity() -> None:
    provider = _FakeProvider(
        [_listing(listing_id="l1", market_hash_name=None)]
    )
    resolver = _FakeResolver(mapping={})
    bound = bind_identity_to_provider(provider, resolver)
    listings = _run(bound.get_listings(GOODS_ID))
    candidates = convert_buff_listings(listings)
    assert candidates[0].market_hash_name is None

    enricher = InMemoryTradeUpInputEnricher(
        InMemoryTradeUpInputMetadataResolver(
            {NAME: TradeUpInputMetadata(
                market_hash_name=NAME,
                collection_name="C",
                rarity="R",
                min_float=0.0,
                max_float=1.0,
            )}
        )
    )
    result = enrich_candidates(candidates, enricher)
    assert len(result.enriched) == 0
    assert len(result.rejected) == 1
    assert result.rejected[0].reason.value == "market_hash_name_unresolved"


def test_resolved_listing_flows_through_full_seam() -> None:
    """End-to-end seam: provider → identity binding → intrinsic-flag binding → adapter → enricher.

    Phase 13O-1: the identity binding layer is identity-only; the
    intrinsic-flag binding layer attaches resolved flags via the
    canonical-name classifier. A `NAME` that does not start with
    either prefix is classified `stattrak=False, souvenir=False`,
    which the enricher accepts.
    """
    from app.services.buff_intrinsic_flag_listing_provider import (
        bind_intrinsic_flags_to_provider,
    )
    from app.services.buff_intrinsic_flag_resolver import (
        CanonicalNameIntrinsicFlagResolver,
    )

    provider = _FakeProvider([_listing()])
    resolver = _FakeResolver({GOODS_ID: NAME})
    intrinsic = CanonicalNameIntrinsicFlagResolver()
    identity_bound = bind_identity_to_provider(provider, resolver)
    full_bound = bind_intrinsic_flags_to_provider(identity_bound, intrinsic)
    listings = _run(full_bound.get_listings(GOODS_ID))

    candidates = convert_buff_listings(listings)
    assert len(candidates) == 1
    assert candidates[0].market_hash_name == NAME
    assert candidates[0].stattrak is False
    assert candidates[0].souvenir is False

    enricher = InMemoryTradeUpInputEnricher(
        InMemoryTradeUpInputMetadataResolver(
            {NAME: TradeUpInputMetadata(
                market_hash_name=NAME,
                collection_name="C",
                rarity="R",
                min_float=0.0,
                max_float=1.0,
            )}
        )
    )
    result = enrich_candidates(candidates, enricher)
    assert len(result.enriched) == 1
    assert len(result.rejected) == 0


class _MismatchedResolver:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def resolve_goods_id(self, goods_id: str) -> object:
        from app.services.buff_item_identity import BuffItemIdentity
        self.calls.append(goods_id)
        return BuffItemIdentity(market_hash_name=OTHER_NAME, goods_id=OTHER_GOODS_ID)


def test_resolver_identity_goods_id_mismatch_fails_closed() -> None:
    provider = _FakeProvider([_listing()])
    resolver = _MismatchedResolver()
    bound = bind_identity_to_provider(provider, resolver)
    with pytest.raises(BuffIdentityBindingError) as captured:
        _run(bound.get_listings(GOODS_ID))
    assert captured.value.reason == "resolver_goods_id_mismatch"
    assert str(captured.value) == "invalid BUFF listing identity binding contract"
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_listing_goods_id_mismatch_fails_closed() -> None:
    bad = _listing(listing_id="l-bad", goods_id=OTHER_GOODS_ID)
    provider = _FakeProvider([bad])
    resolver = _FakeResolver({GOODS_ID: NAME})
    bound = bind_identity_to_provider(provider, resolver)
    with pytest.raises(BuffIdentityBindingError) as captured:
        _run(bound.get_listings(GOODS_ID))
    assert captured.value.reason == "listing_goods_id_mismatch"


def test_existing_market_hash_name_equal_to_resolved_is_preserved() -> None:
    listing = _listing(market_hash_name=NAME)
    provider = _FakeProvider([listing])
    resolver = _FakeResolver({GOODS_ID: NAME})
    bound = bind_identity_to_provider(provider, resolver)
    listings = _run(bound.get_listings(GOODS_ID))
    assert listings[0].market_hash_name == NAME
    # Phase 13O-1: the identity-binding layer is identity-only and
    # returns plain `BuffListing` instances; intrinsic flags are
    # attached by a separate downstream layer.
    assert listings[0] is listing
    from app.services.buff_listing_intrinsic_flags import BuffListingIntrinsicFlags
    assert not isinstance(listings[0], BuffListingIntrinsicFlags)


def test_existing_market_hash_name_conflicting_fails_closed() -> None:
    listing = _listing(market_hash_name=OTHER_NAME)
    provider = _FakeProvider([listing])
    resolver = _FakeResolver({GOODS_ID: NAME})
    bound = bind_identity_to_provider(provider, resolver)
    with pytest.raises(BuffIdentityBindingError) as captured:
        _run(bound.get_listings(GOODS_ID))
    assert captured.value.reason == "market_hash_name_conflict"


def test_existing_market_hash_name_preserved_when_unresolved() -> None:
    listing = _listing(market_hash_name=NAME)
    provider = _FakeProvider([listing])
    resolver = _FakeResolver(mapping={})
    bound = bind_identity_to_provider(provider, resolver)
    listings = _run(bound.get_listings(GOODS_ID))
    assert listings[0].market_hash_name == NAME


@pytest.mark.parametrize(
    "name",
    [
        "★ Karambit | Doppler (Factory New)",
        "StatTrak™ AK-47 | Redline (Field-Tested)",
        "AK-47 | Redline (Field-Tested)",
        "Souvenir AWP | Dragon Lore (Factory New)",
        "Sticker | Howling Dawn",
    ],
)
def test_special_unicode_characters_are_preserved_exact(name: str) -> None:
    provider = _FakeProvider([_listing(market_hash_name=None)])
    resolver = _FakeResolver({GOODS_ID: name})
    bound = bind_identity_to_provider(provider, resolver)
    listings = _run(bound.get_listings(GOODS_ID))
    assert listings[0].market_hash_name == name
    assert listings[0].market_hash_name.encode("utf-8") == name.encode("utf-8")


def test_no_trimming_in_binding_layer() -> None:
    provider = _FakeProvider([_listing()])
    resolver = _FakeResolver({GOODS_ID: NAME})
    bound = bind_identity_to_provider(provider, resolver)
    with pytest.raises(TypeError):
        _run(bound.get_listings(f"  {GOODS_ID}  "))


def test_no_casefold_at_resolver_boundary() -> None:
    """The binding layer forwards the exact requested goods_id to the resolver.

    Casefolding is the resolver's contract concern; this test asserts the
    binding layer never mutates the requested goods_id before the
    resolver sees it. The `BuffCommunityIdentityResolver.resolve_goods_id`
    contract (no casefolding) is tested in
    `tests/test_buff_community_identity_resolver.py`.
    """
    provider = _FakeProvider([_listing()])
    resolver = _FakeResolver({GOODS_ID: NAME})
    bound = bind_identity_to_provider(provider, resolver)
    _run(bound.get_listings(GOODS_ID))
    assert resolver.calls == [GOODS_ID]
    assert GOODS_ID == "33960"


def test_unknown_valid_goods_id_resolves_to_none() -> None:
    provider = _FakeProvider([_listing()])
    resolver = _FakeResolver(mapping={})
    bound = bind_identity_to_provider(provider, resolver)
    listings = _run(bound.get_listings(GOODS_ID))
    assert listings[0].market_hash_name is None


class _AlwaysFailureResolver:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def resolve_goods_id(self, goods_id: str) -> object:
        self.calls.append(goods_id)
        # Defensive failure that must NOT trigger any fallback network I/O.
        # We deliberately raise a distinct exception to prove it propagates.
        raise RuntimeError("resolver-side failure; no fallback I/O allowed")


def test_resolver_failure_does_not_trigger_fallback_network_io() -> None:
    provider = _FakeProvider([_listing()])
    resolver = _AlwaysFailureResolver()
    bound = bind_identity_to_provider(provider, resolver)
    with pytest.raises(RuntimeError, match="no fallback I/O allowed"):
        _run(bound.get_listings(GOODS_ID))


class _MemoryErrorResolver:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def resolve_goods_id(self, goods_id: str) -> object:
        self.calls.append(goods_id)
        raise MemoryError("simulated resolver memory exhaustion")


def test_memory_error_propagates_verbatim() -> None:
    provider = _FakeProvider([_listing()])
    resolver = _MemoryErrorResolver()
    bound = bind_identity_to_provider(provider, resolver)
    try:
        _run(bound.get_listings(GOODS_ID))
    except MemoryError as exc:
        assert "simulated resolver memory exhaustion" in str(exc)
    else:
        pytest.fail("MemoryError did not propagate")


def test_order_of_returned_listings_is_preserved() -> None:
    provider = _FakeProvider(
        [
            _listing(listing_id="l1", price_cny=Decimal("1")),
            _listing(listing_id="l2", price_cny=Decimal("2")),
            _listing(listing_id="l3", price_cny=Decimal("3")),
        ]
    )
    resolver = _FakeResolver({GOODS_ID: NAME})
    bound = bind_identity_to_provider(provider, resolver)
    listings = _run(bound.get_listings(GOODS_ID))
    assert [item.listing_id for item in listings] == ["l1", "l2", "l3"]
    assert [item.price_cny for item in listings] == [
        Decimal("1"),
        Decimal("2"),
        Decimal("3"),
    ]


def test_empty_listing_page_remains_valid() -> None:
    provider = _FakeProvider([])
    resolver = _FakeResolver({GOODS_ID: NAME})
    bound = bind_identity_to_provider(provider, resolver)
    listings = _run(bound.get_listings(GOODS_ID))
    assert listings == []
    assert resolver.calls == [GOODS_ID]


def test_repeated_deterministic_call_with_fresh_fakes_gives_equivalent_results() -> None:
    a_provider = _FakeProvider([_listing()])
    a_resolver = _FakeResolver({GOODS_ID: NAME})
    a = _run(bind_identity_to_provider(a_provider, a_resolver).get_listings(GOODS_ID))

    b_provider = _FakeProvider([_listing()])
    b_resolver = _FakeResolver({GOODS_ID: NAME})
    b = _run(bind_identity_to_provider(b_provider, b_resolver).get_listings(GOODS_ID))

    assert len(a) == len(b) == 1
    assert a[0].market_hash_name == b[0].market_hash_name == NAME
    assert a[0].goods_id == b[0].goods_id == GOODS_ID
    assert a[0].listing_id == b[0].listing_id
    assert a[0].price_cny == b[0].price_cny
    assert a[0].paintwear == b[0].paintwear
    assert a[0].asset_id == b[0].asset_id
    assert a[0].paintseed == b[0].paintseed


def test_resolve_listings_identity_helper_equivalent_to_composed_provider() -> None:
    provider = _FakeProvider([_listing()])
    resolver = _FakeResolver({GOODS_ID: NAME})
    page = _run(
        resolve_listings_identity(
            provider=provider,
            resolver=resolver,
            goods_id=GOODS_ID,
        )
    )
    assert page.resolved_market_hash_name == NAME
    assert page.resolved_goods_id == GOODS_ID
    assert len(page.rebound_listings) == 1
    assert page.rebound_listings[0].market_hash_name == NAME


def test_frozen_listing_mutation_protected() -> None:
    listing = _listing()
    provider = _FakeProvider([listing])
    resolver = _FakeResolver({GOODS_ID: NAME})
    bound = bind_identity_to_provider(provider, resolver)
    out = _run(bound.get_listings(GOODS_ID))[0]
    with pytest.raises(FrozenInstanceError):
        out.market_hash_name = "hacked"  # type: ignore[misc]


def test_module_has_no_protected_core_or_external_dependencies() -> None:
    """The binding module depends only on provider + resolver + dataclasses."""
    import ast
    src_path = Path(__file__).resolve().parents[1].joinpath(
        "app/services/buff_identity_listing_provider.py"
    )
    source = src_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    plain_imports = {
        node.names[0].name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import) and node.names
    }
    assert "dataclasses" in imports
    assert "typing" in imports
    forbidden_targets = (
        "app.services.tradeup_engine",
        "app.services.recipe_solver",
        "app.services.ev_service",
        "app.services.risk_filter",
        "app.services.valuation_service",
        "app.services.live_recipe_valuation",
        "app.services.metadata_models",
        "app.services.metadata_provider",
        "app.services.metadata_service",
        "app.services.live_metadata_catalog",
        "app.services.trade_up_input_enrichment",
        "app.services.trade_up_input_candidate",
        "app.services.trade_up_pipeline",
        "app.services.buff_listing_candidate_adapter",
        "app.services.buff_http_client",
        "app.services.buff_goods_info",
        "app.jobs.scheduler",
        "app.api",
        "app.db",
        "app.cache",
        "app.webhook",
        "app.services.scanner",
        "app.services.steamdt",
        "app.services.steamapis",
    )
    for target in imports | plain_imports:
        for forbidden in forbidden_targets:
            assert not target.startswith(forbidden), (
                f"forbidden import target {target!r} starts with {forbidden!r}"
            )
    # Verify the binding layer never imports the adapter. The adapter
    # remains untouched by design. The binding layer wraps the
    # provider, not the adapter.
    assert "app.services.buff_listing_candidate_adapter" not in imports
    # And never opens sockets, files, environment, scheduler, etc.
    for token in (
        "open(",
        "os.environ",
        "httpx",
        "aiohttp",
        "websockets",
        "requests",
    ):
        assert token not in source, f"forbidden token {token!r} in source"


def test_composed_provider_exposes_only_get_listings() -> None:
    provider = _FakeProvider([])
    resolver = _FakeResolver({GOODS_ID: NAME})
    bound = bind_identity_to_provider(provider, resolver)
    public = {
        name
        for name, value in inspect.getmembers(bound)
        if not name.startswith("_")
        and callable(value)
    }
    assert public == {"get_listings"}


def test_error_repr_does_not_leak_value_fields() -> None:
    err = BuffIdentityBindingError(reason="market_hash_name_conflict")
    rendered = f"{err!s} {err!r}"
    assert NAME not in rendered
    assert GOODS_ID not in rendered
    assert "Redline" not in rendered
    assert "market_hash_name_conflict" not in rendered


def test_unsupported_error_reason_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="unsupported BUFF identity binding reason"):
        BuffIdentityBindingError(reason="not_a_real_reason")


def test_adapter_rejection_vocabulary_added_intrinsic_flag_invalid() -> None:
    """The adapter vocabulary is closed but may grow with documented additions.

    Phase 13O added `INTRINSIC_FLAG_INVALID` to the adapter rejection
    vocabulary. The binding layer does not own this code; it merely
    documents that the adapter has a new, closed rejection entry.
    """
    from app.services.buff_listing_candidate_adapter import CandidateAdapterRejectionReason
    members = tuple(CandidateAdapterRejectionReason)
    assert members == (
        CandidateAdapterRejectionReason.MISSING_IDENTITY,
        CandidateAdapterRejectionReason.MISSING_PRICE,
        CandidateAdapterRejectionReason.INVALID_FLOAT,
        CandidateAdapterRejectionReason.MISSING_ASSET_ID,
        CandidateAdapterRejectionReason.UNSUPPORTED_SOURCE,
        CandidateAdapterRejectionReason.INTRINSIC_FLAG_INVALID,
    )


def test_binding_layer_does_not_call_resolver_forward() -> None:
    """The binding layer uses only the reverse (goods_id) lookup; forward is unused."""
    class _ForwardSpy:
        def __init__(self) -> None:
            self.forward_calls: list[str] = []
            self.reverse_calls: list[str] = []

        async def resolve_goods_id(self, goods_id: str) -> object:
            from app.services.buff_item_identity import BuffItemIdentity
            self.reverse_calls.append(goods_id)
            return BuffItemIdentity(market_hash_name=NAME, goods_id=goods_id)

        async def resolve(self, market_hash_name: str) -> object:
            self.forward_calls.append(market_hash_name)
            return None

    provider = _FakeProvider([_listing()])
    resolver = _ForwardSpy()
    bound = bind_identity_to_provider(provider, resolver)
    _run(bound.get_listings(GOODS_ID))
    assert resolver.reverse_calls == [GOODS_ID]
    assert resolver.forward_calls == []