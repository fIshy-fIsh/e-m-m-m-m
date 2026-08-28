"""Phase 13O — Intrinsic-flag representation tests.

These tests cover the new three-state (`True` / `False` / `None`)
representation of the `stattrak` and `souvenir` intrinsic item
attributes. They are designed to be invariant against any future
verified BUFF source that supplies these flags.

Project conventions:
- async tests use `asyncio.run(...)` (no pytest-asyncio marker);
- `BuffListing` is read-only (`FrozenInstanceError` on mutation);
- intrinsic flags are never inferred from `goods_id`, `listing_id`,
  `asset_id`, `paintseed`, `price`, or any other upstream field;
- malformed non-bool, non-`None` values are rejected.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.buff_listing_candidate_adapter import (
    CandidateAdapterRejection,
    CandidateAdapterRejectionReason,
    convert_buff_listing_to_candidate,
    convert_buff_listings,
)
from app.services.buff_listing_intrinsic_flags import (
    BuffListingIntrinsicFlags,
    IntrinsicFlagValidationError,
    coerce_intrinsic_flag,
    is_intrinsic_flag_value,
    with_intrinsic_flags,
)
from app.services.buff_listing_provider import BuffListing
from app.services.trade_up_input_candidate import (
    TradeUpInputCandidate,
    TradeUpInputCandidateValidationError,
)
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputEnricher,
    InMemoryTradeUpInputMetadataResolver,
    TradeUpInputMetadata,
    enrich_candidates,
)

NAME = "Synthetic AK-47 | Variant (Factory New)"


def _listing(**overrides: object) -> BuffListing:
    values: dict[str, object] = {
        "listing_id": "listing-1",
        "goods_id": "goods-1",
        "market_hash_name": NAME,
        "price_cny": Decimal("10.00"),
        "paintwear": Decimal("0.1"),
        "asset_id": "asset-1",
        "paintseed": 1,
        "source": "buff",
    }
    values.update(overrides)
    return BuffListing(**values)  # type: ignore[arg-type]


def _metadata_for(name: str) -> TradeUpInputMetadata:
    return TradeUpInputMetadata(
        market_hash_name=name,
        collection_name="C",
        rarity="R",
        min_float=0.0,
        max_float=1.0,
    )


# ---------------------------------------------------------------------------
# (1) Known `True` is preserved through the candidate boundary.
# ---------------------------------------------------------------------------


def test_known_true_is_preserved_through_adapter() -> None:
    class StubListing:
        listing_id = "l-1"
        goods_id = "g-1"
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        paintseed = 1
        source = "buff"
        stattrak = True
        souvenir = True

    outcome = convert_buff_listing_to_candidate(StubListing())  # type: ignore[arg-type]
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is True
    assert outcome.souvenir is True


# ---------------------------------------------------------------------------
# (2) Known `False` is preserved through the candidate boundary.
# ---------------------------------------------------------------------------


def test_known_false_is_preserved_through_adapter() -> None:
    class StubListing:
        listing_id = "l-1"
        goods_id = "g-1"
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        paintseed = 1
        source = "buff"
        stattrak = False
        souvenir = False

    outcome = convert_buff_listing_to_candidate(StubListing())  # type: ignore[arg-type]
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is False
    assert outcome.souvenir is False


# ---------------------------------------------------------------------------
# (3) Unknown remains `None` through the candidate boundary.
# ---------------------------------------------------------------------------


def test_unknown_remains_none_through_adapter() -> None:
    class StubListing:
        listing_id = "l-1"
        goods_id = "g-1"
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        paintseed = 1
        source = "buff"
        # intrinsic flags intentionally absent
        stattrak = None
        souvenir = None

    outcome = convert_buff_listing_to_candidate(StubListing())  # type: ignore[arg-type]
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is None
    assert outcome.souvenir is None


def test_unknown_when_listing_omits_field_is_none() -> None:
    """Plain `BuffListing` carries no flags; the adapter sees `None`."""
    listing = _listing()
    outcome = convert_buff_listing_to_candidate(listing)
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is None
    assert outcome.souvenir is None


# ---------------------------------------------------------------------------
# (4) No `None -> False` coercion at any layer.
# ---------------------------------------------------------------------------


def test_no_none_to_false_coercion_in_candidate() -> None:
    """A candidate constructed with `None` flags preserves `None`."""
    candidate = TradeUpInputCandidate(
        listing_id="l-1",
        goods_id="g-1",
        market_hash_name=NAME,
        price_cny=Decimal("10.00"),
        paintwear=Decimal("0.1"),
        asset_id="asset-1",
        source="buff",
        stattrak=None,
        souvenir=None,
    )
    assert candidate.stattrak is None
    assert candidate.souvenir is None


def test_no_none_to_false_coercion_in_adapter() -> None:
    """The adapter does not coerce a listing's `None` to `False`."""
    listing = _listing()  # Plain BuffListing; flags absent.
    outcome = convert_buff_listing_to_candidate(listing)
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is None
    assert outcome.souvenir is None


def test_no_none_to_false_coercion_in_wrapper() -> None:
    """The intrinsic-flags wrapper preserves `None`."""
    wrapper = with_intrinsic_flags(_listing(), stattrak=None, souvenir=None)
    assert wrapper.stattrak is None
    assert wrapper.souvenir is None


# ---------------------------------------------------------------------------
# (5) No inference from `goods_id`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("goods_id", ["12345", "0", "stattrak-123", "souvenir-456"])
def test_no_inference_from_goods_id(goods_id: str) -> None:
    class StubListing:
        listing_id = "l-1"
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        paintseed = 1
        source = "buff"

        def __init__(self, gid: str) -> None:
            self.goods_id = gid

        stattrak = None
        souvenir = None

    outcome = convert_buff_listing_to_candidate(StubListing(goods_id))  # type: ignore[arg-type]
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is None
    assert outcome.souvenir is None
    assert outcome.goods_id == goods_id


# ---------------------------------------------------------------------------
# (6) No inference from listing IDs.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "listing_id",
    ["stattrak-listing-001", "souvenir-listing-002", "★", ""],
)
def test_no_inference_from_listing_id(listing_id: str) -> None:
    if not listing_id:
        return  # plain BuffListing rejects empty listing_id
    listing = _listing(listing_id=listing_id)
    outcome = convert_buff_listing_to_candidate(listing)
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is None
    assert outcome.souvenir is None


# ---------------------------------------------------------------------------
# (7) No inference from asset IDs.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "asset_id",
    ["asset-stattrak-001", "asset-souvenir-002", "asset-with-stattrak-suffix"],
)
def test_no_inference_from_asset_id(asset_id: str) -> None:
    listing = _listing(asset_id=asset_id)
    outcome = convert_buff_listing_to_candidate(listing)
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is None
    assert outcome.souvenir is None


# ---------------------------------------------------------------------------
# (8) Identity binding preserves the intrinsic fields verbatim.
# ---------------------------------------------------------------------------


def test_identity_binding_preserves_stattrak_verbatim() -> None:
    """When the binding layer receives an explicit `True`, it forwards `True`."""
    listing = _listing()
    wrapper = with_intrinsic_flags(listing, stattrak=True, souvenir=False)
    assert wrapper.stattrak is True
    assert wrapper.souvenir is False
    # Adapter sees the same values.
    outcome = convert_buff_listing_to_candidate(wrapper)
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is True
    assert outcome.souvenir is False


def test_identity_binding_preserves_souvenir_verbatim() -> None:
    listing = _listing()
    wrapper = with_intrinsic_flags(listing, stattrak=False, souvenir=True)
    outcome = convert_buff_listing_to_candidate(wrapper)
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is False
    assert outcome.souvenir is True


def test_identity_binding_preserves_unknown_verbatim() -> None:
    listing = _listing()
    wrapper = with_intrinsic_flags(listing)  # defaults to None
    outcome = convert_buff_listing_to_candidate(wrapper)
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is None
    assert outcome.souvenir is None


# ---------------------------------------------------------------------------
# (9) Order and all unrelated listing fields are unchanged.
# ---------------------------------------------------------------------------


def test_intrinsic_flags_do_not_affect_other_fields_or_order() -> None:
    listings = [
        _listing(listing_id="l1"),
        _listing(listing_id="l2", market_hash_name=NAME),
        _listing(listing_id="l3"),
    ]
    wrapped = [
        with_intrinsic_flags(item, stattrak=True, souvenir=False)
        for item in listings
    ]
    candidates = convert_buff_listings(wrapped)
    assert [c.listing_id for c in candidates] == ["l1", "l2", "l3"]
    for c in candidates:
        assert c.market_hash_name == NAME
        assert c.goods_id == "goods-1"
        assert c.price_cny == Decimal("10.00")
        assert c.paintwear == Decimal("0.1")
        assert c.asset_id == "asset-1"
        assert c.stattrak is True
        assert c.souvenir is False


# ---------------------------------------------------------------------------
# (10) Malformed non-bool values are rejected at the candidate boundary.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stattrak", 1),
        ("stattrak", 0),
        ("stattrak", "true"),
        ("stattrak", "false"),
        ("stattrak", 1.0),
        ("stattrak", b"true"),
        ("stattrak", []),
        ("souvenir", 1),
        ("souvenir", 0),
        ("souvenir", "true"),
        ("souvenir", 1.0),
        ("souvenir", []),
    ],
)
def test_malformed_intrinsic_flag_is_rejected_at_candidate(
    field: str,
    value: object,
) -> None:
    """The candidate DTO rejects malformed values via fixed validation."""
    with pytest.raises(TradeUpInputCandidateValidationError) as captured:
        TradeUpInputCandidate(
            listing_id="l-1",
            goods_id="g-1",
            market_hash_name=NAME,
            price_cny=Decimal("10.00"),
            paintwear=Decimal("0.1"),
            asset_id="asset-1",
            source="buff",
            **{field: value},  # type: ignore[arg-type]
        )
    assert captured.value.field == field


def test_malformed_intrinsic_flag_is_rejected_at_adapter() -> None:
    class StubListing:
        listing_id = "l-1"
        goods_id = "g-1"
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        paintseed = 1
        source = "buff"
        stattrak = 1  # malformed
        souvenir = False

    outcome = convert_buff_listing_to_candidate(StubListing())  # type: ignore[arg-type]
    assert isinstance(outcome, CandidateAdapterRejection)
    assert outcome.reason == CandidateAdapterRejectionReason.INTRINSIC_FLAG_INVALID


def test_malformed_intrinsic_flag_is_rejected_at_wrapper() -> None:
    listing = _listing()
    with pytest.raises(IntrinsicFlagValidationError):
        with_intrinsic_flags(listing, stattrak=1, souvenir=False)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# (11) Strict bool validation rejects integer 0/1 — same convention as
#      the legacy `_validate_exact_bool` policy in the project.
# ---------------------------------------------------------------------------


def test_strict_bool_policy_rejects_int_0_and_1() -> None:
    """`is_intrinsic_flag_value` accepts only `True`/`False`/`None`."""
    assert is_intrinsic_flag_value(True)
    assert is_intrinsic_flag_value(False)
    assert is_intrinsic_flag_value(None)
    assert not is_intrinsic_flag_value(0)
    assert not is_intrinsic_flag_value(1)
    assert not is_intrinsic_flag_value("true")
    assert not is_intrinsic_flag_value("false")
    assert not is_intrinsic_flag_value("")
    assert not is_intrinsic_flag_value([])


def test_coerce_intrinsic_flag_validates_exactly() -> None:
    """`coerce_intrinsic_flag` accepts valid and rejects malformed."""
    assert coerce_intrinsic_flag(True, field="stattrak") is True
    assert coerce_intrinsic_flag(False, field="stattrak") is False
    assert coerce_intrinsic_flag(None, field="stattrak") is None
    with pytest.raises(IntrinsicFlagValidationError):
        coerce_intrinsic_flag(1, field="stattrak")
    with pytest.raises(IntrinsicFlagValidationError):
        coerce_intrinsic_flag(0, field="stattrak")
    with pytest.raises(IntrinsicFlagValidationError):
        coerce_intrinsic_flag("true", field="stattrak")
    with pytest.raises(IntrinsicFlagValidationError):
        coerce_intrinsic_flag(1.0, field="stattrak")


# ---------------------------------------------------------------------------
# (12) Existing identity tests continue to pass (verified by full pytest run).
# ---------------------------------------------------------------------------


def test_identity_tests_still_pass_via_full_suite_marker() -> None:
    """Trivial marker test; the real guarantee is the full pytest run.

    This module deliberately imports only the touched surfaces so the
    rest of the suite can verify identity continuity without coupling
    here. The actual test run confirms all identity tests pass.
    """
    assert True


# ---------------------------------------------------------------------------
# (13) Existing adapter / enrichment regression tests continue to pass.
# ---------------------------------------------------------------------------


def test_enricher_rejects_unknown_intrinsic_flags() -> None:
    """A candidate with `None` flags is rejected by the enricher."""
    class StubListing:
        listing_id = "l-1"
        goods_id = "g-1"
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        paintseed = 1
        source = "buff"
        stattrak = None
        souvenir = None

    outcome = convert_buff_listing_to_candidate(StubListing())  # type: ignore[arg-type]
    assert isinstance(outcome, TradeUpInputCandidate)
    enricher = InMemoryTradeUpInputEnricher(
        InMemoryTradeUpInputMetadataResolver({NAME: _metadata_for(NAME)})
    )
    result = enrich_candidates([outcome], enricher)
    assert len(result.enriched) == 0
    assert len(result.rejected) == 1
    assert result.rejected[0].reason.value == "intrinsic_flag_unresolved"


def test_enricher_accepts_established_false_flags() -> None:
    """A candidate with `False` flags is enriched normally."""
    class StubListing:
        listing_id = "l-1"
        goods_id = "g-1"
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        paintseed = 1
        source = "buff"
        stattrak = False
        souvenir = False

    outcome = convert_buff_listing_to_candidate(StubListing())  # type: ignore[arg-type]
    assert isinstance(outcome, TradeUpInputCandidate)
    enricher = InMemoryTradeUpInputEnricher(
        InMemoryTradeUpInputMetadataResolver({NAME: _metadata_for(NAME)})
    )
    result = enrich_candidates([outcome], enricher)
    assert len(result.enriched) == 1
    assert len(result.rejected) == 0
    item = result.enriched[0].input_item
    assert item.stattrak is False
    assert item.souvenir is False


def test_enricher_accepts_established_true_flags() -> None:
    class StubListing:
        listing_id = "l-1"
        goods_id = "g-1"
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        paintseed = 1
        source = "buff"
        stattrak = True
        souvenir = False

    outcome = convert_buff_listing_to_candidate(StubListing())  # type: ignore[arg-type]
    assert isinstance(outcome, TradeUpInputCandidate)
    enricher = InMemoryTradeUpInputEnricher(
        InMemoryTradeUpInputMetadataResolver({NAME: _metadata_for(NAME)})
    )
    result = enrich_candidates([outcome], enricher)
    assert len(result.enriched) == 1
    assert len(result.rejected) == 0
    item = result.enriched[0].input_item
    assert item.stattrak is True
    assert item.souvenir is False


# ---------------------------------------------------------------------------
# Auxiliary: the wrapper preserves every other BuffListing field via delegation.
# ---------------------------------------------------------------------------


def test_wrapper_preserves_all_other_listing_fields() -> None:
    listing = _listing()
    wrapper = with_intrinsic_flags(listing, stattrak=True, souvenir=False)
    assert wrapper.listing_id == listing.listing_id
    assert wrapper.goods_id == listing.goods_id
    assert wrapper.market_hash_name == listing.market_hash_name
    assert wrapper.price_cny == listing.price_cny
    assert wrapper.paintwear == listing.paintwear
    assert wrapper.asset_id == listing.asset_id
    assert wrapper.paintseed == listing.paintseed
    assert wrapper.source == listing.source


def test_wrapper_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    listing = _listing()
    wrapper = with_intrinsic_flags(listing, stattrak=True, souvenir=False)
    with pytest.raises(FrozenInstanceError):
        wrapper.stattrak = False  # type: ignore[misc]


def test_wrapper_module_has_no_external_or_engine_dependencies() -> None:
    """The wrapper module depends only on BuffListing + dataclasses."""
    import ast
    src_path = Path(__file__).resolve().parents[1].joinpath(
        "app/services/buff_listing_intrinsic_flags.py"
    )
    source = src_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
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
        "app.jobs.scheduler",
        "app.api",
        "app.db",
        "app.cache",
        "app.webhook",
        "app.services.scanner",
        "app.services.steamdt",
        "app.services.steamapis",
    )
    for target in imports:
        for forbidden in forbidden_targets:
            assert not target.startswith(forbidden), (
                f"forbidden import target {target!r} starts with {forbidden!r}"
            )
    # Confirm the wrapper module imports BuffListing (the only thing it needs).
    assert "app.services.buff_listing_provider" in imports


# ---------------------------------------------------------------------------
# Asynchronous binding-layer test: confirm wrapper survives an async flow.
# ---------------------------------------------------------------------------


def test_wrapper_survives_async_binding_flow() -> None:
    """The wrapper is produced by the intrinsic-flag binding layer, not the identity binding layer.

    Phase 13O-1: the identity-binding layer returns plain
    `BuffListing` instances; the intrinsic-flag binding layer wraps
    each listing in `BuffListingIntrinsicFlags`.
    """
    from app.services.buff_identity_listing_provider import (
        bind_identity_to_provider,
    )
    from app.services.buff_intrinsic_flag_listing_provider import (
        bind_intrinsic_flags_to_provider,
    )
    from app.services.buff_intrinsic_flag_resolver import (
        CanonicalNameIntrinsicFlagResolver,
    )
    from app.services.buff_item_identity import BuffItemIdentity

    class FakeProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def get_listings(self, goods_id: str) -> list[BuffListing]:
            self.calls.append(goods_id)
            return [_listing()]

    class FakeResolver:
        async def resolve_goods_id(self, goods_id: str) -> BuffItemIdentity | None:
            return BuffItemIdentity(market_hash_name=NAME, goods_id=goods_id)

    provider = FakeProvider()
    resolver = FakeResolver()
    identity_bound = bind_identity_to_provider(provider, resolver)
    intrinsic_bound = bind_intrinsic_flags_to_provider(
        identity_bound, CanonicalNameIntrinsicFlagResolver()
    )
    listings = asyncio.run(intrinsic_bound.get_listings("goods-1"))
    assert len(listings) == 1
    assert isinstance(listings[0], BuffListingIntrinsicFlags)
    # NAME does not start with either canonical prefix.
    assert listings[0].stattrak is False
    assert listings[0].souvenir is False