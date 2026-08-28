from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

import app.services.buff_listing_candidate_adapter as adapter_module
from app.services.buff_listing_candidate_adapter import (
    CandidateAdapterRejection,
    CandidateAdapterRejectionReason,
    convert_buff_listing_to_candidate,
    convert_buff_listings,
)
from app.services.buff_listing_provider import BuffListing
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputEnricher,
    InMemoryTradeUpInputMetadataResolver,
    TradeUpInputMetadata,
    enrich_candidates,
)

NAME = "Synthetic AK-47 | Redline (Field-Tested)"
COLLECTION = "Synthetic Collection"
RARITY = "Restricted"


def _listing(
    *,
    listing_id: str = "listing-synthetic-1",
    goods_id: str = "goods-synthetic-1",
    market_hash_name: str | None = NAME,
    price_cny: Decimal = Decimal("12.34"),
    paintwear: Decimal = Decimal("0.1234"),
    asset_id: str = "asset-synthetic-1",
    paintseed: int | None = 123,
    source: str = "buff",
) -> BuffListing:
    return BuffListing(
        listing_id=listing_id,
        goods_id=goods_id,
        market_hash_name=market_hash_name,
        price_cny=price_cny,
        paintwear=paintwear,
        asset_id=asset_id,
        paintseed=paintseed,
        source=source,
    )


def _metadata(*, name: str = NAME) -> TradeUpInputMetadata:
    return TradeUpInputMetadata(
        market_hash_name=name,
        collection_name=COLLECTION,
        rarity=RARITY,
        min_float=0.0,
        max_float=1.0,
    )


def test_public_api_is_exact() -> None:
    assert adapter_module.__all__ == (
        "CandidateAdapterRejectionReason",
        "CandidateAdapterRejection",
        "BuffListingCandidateAdapter",
        "convert_buff_listing_to_candidate",
        "convert_buff_listings",
    )


def test_rejection_reason_vocabulary_is_closed() -> None:
    members = tuple(CandidateAdapterRejectionReason)
    assert members == (
        CandidateAdapterRejectionReason.MISSING_IDENTITY,
        CandidateAdapterRejectionReason.MISSING_PRICE,
        CandidateAdapterRejectionReason.INVALID_FLOAT,
        CandidateAdapterRejectionReason.MISSING_ASSET_ID,
        CandidateAdapterRejectionReason.UNSUPPORTED_SOURCE,
        CandidateAdapterRejectionReason.INTRINSIC_FLAG_INVALID,
    )


def test_valid_listing_creates_candidate() -> None:
    listing = _listing()
    outcome = convert_buff_listing_to_candidate(listing)
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.listing_id == "listing-synthetic-1"
    assert outcome.goods_id == "goods-synthetic-1"
    assert outcome.market_hash_name == NAME
    assert outcome.price_cny == Decimal("12.34")
    assert outcome.paintwear == Decimal("0.1234")
    assert outcome.asset_id == "asset-synthetic-1"
    assert outcome.source == "buff"


def test_missing_market_hash_name_flows_through_as_unresolved() -> None:
    listing = _listing(market_hash_name=None)
    outcome = convert_buff_listing_to_candidate(listing)
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.market_hash_name is None


def test_missing_price_returns_missin_price_rejection() -> None:
    class Stub:
        market_hash_name = NAME
        price_cny = Decimal("-1")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        source = "buff"
        goods_id = "g-1"
        listing_id = "l-1"

    outcome = convert_buff_listing_to_candidate(Stub())  # type: ignore[arg-type]
    assert isinstance(outcome, CandidateAdapterRejection)
    assert outcome.reason == CandidateAdapterRejectionReason.MISSING_PRICE


def test_invalid_float_returns_invalid_float_rejection() -> None:
    class Stub:
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("2.0")
        asset_id = "asset-1"
        source = "buff"
        goods_id = "g-1"
        listing_id = "l-1"

    outcome = convert_buff_listing_to_candidate(Stub())  # type: ignore[arg-type]
    assert isinstance(outcome, CandidateAdapterRejection)
    assert outcome.reason == CandidateAdapterRejectionReason.INVALID_FLOAT


def test_missing_asset_id_returns_missing_asset_id_rejection() -> None:
    class Stub:
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = ""
        source = "buff"
        goods_id = "g-1"
        listing_id = "l-1"

    outcome = convert_buff_listing_to_candidate(Stub())  # type: ignore[arg-type]
    assert isinstance(outcome, CandidateAdapterRejection)
    assert outcome.reason == CandidateAdapterRejectionReason.MISSING_ASSET_ID


def test_unsupported_source_returns_unsupported_source_rejection() -> None:
    class Stub:
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        source = "unknown"
        goods_id = "g-1"
        listing_id = "l-1"

    outcome = convert_buff_listing_to_candidate(Stub())  # type: ignore[arg-type]
    assert isinstance(outcome, CandidateAdapterRejection)
    assert outcome.reason == CandidateAdapterRejectionReason.UNSUPPORTED_SOURCE


def test_stattrak_default_is_none_when_listing_does_not_expose_it() -> None:
    """Phase 13O: when the listing does not expose `stattrak`, the adapter
    forwards `None` (not `False`). The legacy `False` default silently
    fabricated certainty; the new `None` default explicitly represents
    the unknown-upstream state.
    """
    listing = _listing()
    outcome = convert_buff_listing_to_candidate(listing)
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is None


def test_souvenir_default_is_none_when_listing_does_not_expose_it() -> None:
    listing = _listing()
    outcome = convert_buff_listing_to_candidate(listing)
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.souvenir is None


def test_stattrak_true_is_forwarded_verbatim() -> None:
    class Stub:
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        source = "buff"
        goods_id = "g-1"
        listing_id = "l-1"
        stattrak = True
        souvenir = False

    outcome = convert_buff_listing_to_candidate(Stub())  # type: ignore[arg-type]
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is True
    assert outcome.souvenir is False


def test_souvenir_true_is_forwarded_verbatim() -> None:
    class Stub:
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        source = "buff"
        goods_id = "g-1"
        listing_id = "l-1"
        stattrak = False
        souvenir = True

    outcome = convert_buff_listing_to_candidate(Stub())  # type: ignore[arg-type]
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is False
    assert outcome.souvenir is True


def test_intrinsic_flag_none_is_forwarded_verbatim() -> None:
    class Stub:
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        source = "buff"
        goods_id = "g-1"
        listing_id = "l-1"
        stattrak = None
        souvenir = None

    outcome = convert_buff_listing_to_candidate(Stub())  # type: ignore[arg-type]
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is None
    assert outcome.souvenir is None


def test_intrinsic_flag_malformed_value_returns_rejection() -> None:
    """Non-bool, non-None intrinsic-flag values trigger INTRINSIC_FLAG_INVALID."""

    class StubInteger:
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        source = "buff"
        goods_id = "g-1"
        listing_id = "l-1"
        stattrak = 1
        souvenir = False

    outcome = convert_buff_listing_to_candidate(StubInteger())  # type: ignore[arg-type]
    assert isinstance(outcome, CandidateAdapterRejection)
    assert outcome.reason == CandidateAdapterRejectionReason.INTRINSIC_FLAG_INVALID

    class StubString:
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        source = "buff"
        goods_id = "g-1"
        listing_id = "l-1"
        stattrak = "true"
        souvenir = False

    outcome = convert_buff_listing_to_candidate(StubString())  # type: ignore[arg-type]
    assert isinstance(outcome, CandidateAdapterRejection)
    assert outcome.reason == CandidateAdapterRejectionReason.INTRINSIC_FLAG_INVALID


def test_no_metadata_fields_created_on_candidate() -> None:
    listing = _listing()
    outcome = convert_buff_listing_to_candidate(listing)
    assert isinstance(outcome, TradeUpInputCandidate)
    forbidden = ("collection_name", "rarity", "min_float", "max_float")
    for attr in forbidden:
        assert not hasattr(outcome, attr), (
            f"adapter leaked metadata field {attr!r} onto the candidate"
        )


def test_deterministic_output_for_same_listing() -> None:
    listing = _listing()
    first = convert_buff_listing_to_candidate(listing)
    second = convert_buff_listing_to_candidate(listing)
    assert isinstance(first, TradeUpInputCandidate)
    assert isinstance(second, TradeUpInputCandidate)
    assert first == second


def test_repr_does_not_leak_listing_values() -> None:
    secret_listing_id = "personal-secret-listing-2251"
    secret_goods_id = "personal-secret-goods-2251"
    secret_asset_id = "personal-secret-asset-2251"
    class Stub:
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = secret_asset_id
        source = "unknown"
        goods_id = secret_goods_id
        listing_id = secret_listing_id

    outcome = convert_buff_listing_to_candidate(Stub())  # type: ignore[arg-type]
    assert isinstance(outcome, CandidateAdapterRejection)
    rendered = repr(outcome) + " | " + str(outcome)
    for forbidden in (
        secret_listing_id,
        secret_goods_id,
        secret_asset_id,
        "10.00",
        "Redline",
    ):
        assert forbidden not in rendered


def test_convert_buff_listings_partitions_correctly() -> None:
    class HappyListing:
        listing_id = "l-1"
        goods_id = "g-1"
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.1")
        asset_id = "asset-1"
        paintseed = 1
        source = "buff"

    class UnresolvedListing:
        listing_id = "l-2"
        goods_id = "g-2"
        market_hash_name = None
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.5")
        asset_id = "asset-2"
        paintseed = 2
        source = "buff"

    class InvalidFloatListing:
        listing_id = "l-3"
        goods_id = "g-3"
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("2.0")
        asset_id = "asset-3"
        paintseed = 3
        source = "buff"

    class UnsupportedSourceListing:
        listing_id = "l-4"
        goods_id = "g-4"
        market_hash_name = NAME
        price_cny = Decimal("10.00")
        paintwear = Decimal("0.5")
        asset_id = "asset-4"
        paintseed = 4
        source = "unknown"

    kept = convert_buff_listings(
        [
            HappyListing(),
            UnresolvedListing(),
            InvalidFloatListing(),
            UnsupportedSourceListing(),
        ]
    )
    assert len(kept) == 2
    assert [c.listing_id for c in kept] == ["l-1", "l-2"]


def test_adapters_output_flows_into_enrichment_seam() -> None:
    """Listing exposes established `stattrak=False, souvenir=False`.

    Phase 13O migration: the listing must explicitly carry the
    intrinsic flags for the seam to succeed. A plain `BuffListing`
    (with no flags exposed) propagates `None` through the adapter and
    the enricher rejects it as `INTRINSIC_FLAG_UNRESOLVED`. This
    test exercises the established-false branch.
    """
    class StubListing:
        listing_id = "listing-synthetic-1"
        goods_id = "goods-synthetic-1"
        market_hash_name = NAME
        price_cny = Decimal("12.34")
        paintwear = Decimal("0.1234")
        asset_id = "asset-synthetic-1"
        paintseed = 123
        source = "buff"
        stattrak = False
        souvenir = False

    outcome = convert_buff_listing_to_candidate(StubListing())  # type: ignore[arg-type]
    assert isinstance(outcome, TradeUpInputCandidate)
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    enricher = InMemoryTradeUpInputEnricher(resolver)
    result = enrich_candidates([outcome], enricher)
    assert len(result.enriched) == 1
    assert len(result.rejected) == 0
    item = result.enriched[0].input_item
    assert item.market_hash_name == NAME
    assert item.price_cny == Decimal("12.34")
    assert item.collection_name == COLLECTION
    assert item.rarity == RARITY


def test_unresolved_identity_is_rejected_by_enrichment() -> None:
    listing = _listing(market_hash_name=None)
    outcome = convert_buff_listing_to_candidate(listing)
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is None
    assert outcome.souvenir is None
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    enricher = InMemoryTradeUpInputEnricher(resolver)
    result = enrich_candidates([outcome], enricher)
    assert len(result.enriched) == 0
    assert len(result.rejected) == 1
    # When `market_hash_name` is `None`, the enricher surfaces
    # `MARKET_HASH_NAME_UNRESOLVED` first (the intrinsic-flag check
    # runs only after the market-hash-name check passes). The
    # `INTRINSIC_FLAG_UNRESOLVED` branch is exercised in the next
    # test.
    assert result.rejected[0].reason.value == "market_hash_name_unresolved"


def test_unresolved_intrinsic_flags_are_rejected_by_enrichment() -> None:
    """Even with a known market_hash_name, `None` flags fail closed."""
    class StubListing:
        listing_id = "listing-synthetic-2"
        goods_id = "goods-synthetic-2"
        market_hash_name = NAME
        price_cny = Decimal("12.34")
        paintwear = Decimal("0.1234")
        asset_id = "asset-synthetic-2"
        paintseed = 123
        source = "buff"
        stattrak = None
        souvenir = None

    outcome = convert_buff_listing_to_candidate(StubListing())  # type: ignore[arg-type]
    assert isinstance(outcome, TradeUpInputCandidate)
    assert outcome.stattrak is None
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    enricher = InMemoryTradeUpInputEnricher(resolver)
    result = enrich_candidates([outcome], enricher)
    assert len(result.enriched) == 0
    assert len(result.rejected) == 1
    assert result.rejected[0].reason.value == "intrinsic_flag_unresolved"


def test_non_buff_listing_argument_raises_type_error() -> None:
    with pytest.raises(TypeError):
        convert_buff_listing_to_candidate(object())  # type: ignore[arg-type]


def test_module_has_no_protected_core_or_live_dependencies() -> None:
    source = (
        Path(adapter_module.__file__).read_text(encoding="utf-8").casefold()
    )
    forbidden = (
        "tradeup_engine",
        "recipe_solver",
        "ev_service",
        "risk_filter",
        "valuation_service",
        "live_recipe_valuation",
        "metadata_models",
        "metadata_provider",
        "metadata_service",
        "live_metadata_catalog",
        "trade_up_input_enrichment",
        "scheduler",
        "webhook",
        "purchase",
        "httpx",
        "asyncio",
        "requests",
        "aiohttp",
        "websockets",
        "os.environ",
        "open(",
        "json",
        "buff_readonly_smoke_goods_id",
        "steamapis",
        "steamdt",
        "scanner",
    )
    for token in forbidden:
        assert token not in source, (
            f"forbidden token {token!r} found in adapter module"
        )


def test_test_module_does_not_import_protected_core() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    top_level_imports: list[tuple[str, list[str]]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.append(
                (
                    node.names[0].name if node.names else "",
                    [alias.asname or alias.name for alias in node.names],
                )
            )
        elif isinstance(node, ast.ImportFrom):
            top_level_imports.append(
                (
                    node.module or "",
                    [alias.asname or alias.name for alias in node.names],
                )
            )
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
        "app.services.trade_up_pipeline",
        "app.services.buff_listing.",
        "app.services.buff_item_identity",
        "app.services.buff_client",
        "app.jobs.scheduler",
        "app.api",
        "app.db",
        "app.cache",
        "app.webhook",
        "app.services.scanner",
        "app.services.steamdt",
        "app.services.steamapis",
    )
    for target, _ in top_level_imports:
        for forbidden in forbidden_targets:
            assert not target.startswith(forbidden), (
                f"forbidden import target {target!r} starts with {forbidden!r}"
            )


def test_adapter_does_not_populate_metadata_fields() -> None:
    listing = _listing()
    outcome = convert_buff_listing_to_candidate(listing)
    assert isinstance(outcome, TradeUpInputCandidate)
    for attr in (
        "collection_name",
        "rarity",
        "min_float",
        "max_float",
    ):
        assert attr not in outcome.__dict__, (
            f"adapter populated metadata field {attr!r}"
        )