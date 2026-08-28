from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

import app.services.trade_up_input_enrichment as enrichment_module
from app.services.trade_up_input_candidate import TradeUpInputCandidate
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputEnricher,
    InMemoryTradeUpInputMetadataResolver,
    TradeUpEnrichedInput,
    TradeUpEnrichmentRejection,
    TradeUpEnrichmentRejectionReason,
    TradeUpInputEnrichmentResult,
    TradeUpInputMetadata,
    enrich_candidates,
)
from app.services.tradeup_engine import InputItem

NAME = "Synthetic AK-47 | Redline (Field-Tested)"
COLLECTION = "Synthetic Collection"
RARITY = "Restricted"
MIN = 0.0
MAX = 1.0


def _metadata(
    *,
    min_float: float = MIN,
    max_float: float = MAX,
    collection_name: str = COLLECTION,
    rarity: str = RARITY,
    market_hash_name: str = NAME,
) -> TradeUpInputMetadata:
    return TradeUpInputMetadata(
        market_hash_name=market_hash_name,
        collection_name=collection_name,
        rarity=rarity,
        min_float=min_float,
        max_float=max_float,
    )


def _candidate(
    *,
    listing_id: str = "listing-1",
    goods_id: str = "goods-1",
    market_hash_name: str | None = NAME,
    price_cny: Decimal = Decimal("12.34"),
    paintwear: Decimal = Decimal("0.1234"),
    asset_id: str = "asset-1",
    source: str = "buff",
    stattrak: bool = False,
    souvenir: bool = False,
) -> TradeUpInputCandidate:
    return TradeUpInputCandidate(
        listing_id=listing_id,
        goods_id=goods_id,
        market_hash_name=market_hash_name,
        price_cny=price_cny,
        paintwear=paintwear,
        asset_id=asset_id,
        source=source,
        stattrak=stattrak,
        souvenir=souvenir,
    )


def test_public_api_is_exact() -> None:
    assert enrichment_module.__all__ == (
        "TradeUpInputMetadata",
        "TradeUpInputMetadataResolver",
        "InMemoryTradeUpInputMetadataResolver",
        "TradeUpEnrichmentRejectionReason",
        "TradeUpEnrichmentRejection",
        "TradeUpEnrichedInput",
        "TradeUpInputEnrichmentResult",
        "TradeUpInputEnricher",
        "InMemoryTradeUpInputEnricher",
        "enrich_candidates",
    )


def test_metadata_rejects_empty_or_out_of_range_float_band() -> None:
    with pytest.raises(ValueError):
        TradeUpInputMetadata(
            market_hash_name=NAME,
            collection_name=COLLECTION,
            rarity=RARITY,
            min_float=1.0,
            max_float=1.0,
        )
    with pytest.raises(ValueError):
        TradeUpInputMetadata(
            market_hash_name=NAME,
            collection_name=COLLECTION,
            rarity=RARITY,
            min_float=-0.1,
            max_float=0.5,
        )


def test_in_memory_resolver_returns_record_or_none() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    assert resolver.resolve(NAME) is not None
    assert resolver.resolve("Unknown") is None


def test_successful_enrichment_returns_input_item() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    enricher = InMemoryTradeUpInputEnricher(resolver)
    candidate = _candidate(
        price_cny=Decimal("99.50"),
        paintwear=Decimal("0.225000"),
        stattrak=True,
        souvenir=False,
    )
    outcome = enricher.enrich(candidate)
    assert isinstance(outcome, TradeUpEnrichedInput)
    assert outcome.candidate is candidate
    assert isinstance(outcome.input_item, InputItem)
    assert outcome.input_item.market_hash_name == NAME
    assert outcome.input_item.collection_name == COLLECTION
    assert outcome.input_item.rarity == RARITY
    assert outcome.input_item.min_float == pytest.approx(MIN)
    assert outcome.input_item.max_float == pytest.approx(MAX)
    assert outcome.input_item.actual_float == pytest.approx(0.225)
    assert outcome.input_item.price_cny == Decimal("99.50")
    assert outcome.input_item.stattrak is True
    assert outcome.input_item.souvenir is False


def test_unresolved_market_hash_name_returns_rejection() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    enricher = InMemoryTradeUpInputEnricher(resolver)
    outcome = enricher.enrich(_candidate(market_hash_name=None))
    assert isinstance(outcome, TradeUpEnrichmentRejection)
    assert outcome.reason == (
        TradeUpEnrichmentRejectionReason.MARKET_HASH_NAME_UNRESOLVED
    )


def test_missing_metadata_returns_rejection() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({})
    enricher = InMemoryTradeUpInputEnricher(resolver)
    outcome = enricher.enrich(_candidate(market_hash_name="Unknown"))
    assert isinstance(outcome, TradeUpEnrichmentRejection)
    assert outcome.reason == (
        TradeUpEnrichmentRejectionReason.METADATA_NOT_FOUND
    )


def test_candidate_stattrak_and_souvenir_pass_through_unchanged() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    enricher = InMemoryTradeUpInputEnricher(resolver)
    enriched = enricher.enrich(
        _candidate(stattrak=True, souvenir=True)
    )
    rejected = enricher.enrich(
        _candidate(stattrak=False, souvenir=False)
    )
    assert isinstance(enriched, TradeUpEnrichedInput)
    assert enriched.input_item.stattrak is True
    assert enriched.input_item.souvenir is True
    assert isinstance(rejected, TradeUpEnrichedInput)
    assert rejected.input_item.stattrak is False
    assert rejected.input_item.souvenir is False


def test_metadata_catalog_fields_pass_through_unchanged() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver(
        {
            NAME: _metadata(
                min_float=0.07,
                max_float=0.80,
                collection_name="The Collection 2026",
                rarity="Classified",
            )
        }
    )
    enricher = InMemoryTradeUpInputEnricher(resolver)
    outcome = enricher.enrich(_candidate())
    assert isinstance(outcome, TradeUpEnrichedInput)
    assert outcome.input_item.collection_name == "The Collection 2026"
    assert outcome.input_item.rarity == "Classified"
    assert outcome.input_item.min_float == pytest.approx(0.07)
    assert outcome.input_item.max_float == pytest.approx(0.80)


def test_paintwear_decimal_is_converted_to_float_exactly_once() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    enricher = InMemoryTradeUpInputEnricher(resolver)
    outcome = enricher.enrich(_candidate(paintwear=Decimal("0.125000")))
    assert isinstance(outcome, TradeUpEnrichedInput)
    assert outcome.input_item.actual_float == pytest.approx(0.125)
    assert type(outcome.input_item.actual_float) is float


def test_enrich_candidates_preserves_input_order_and_partitions() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    enricher = InMemoryTradeUpInputEnricher(resolver)
    candidates = [
        _candidate(goods_id="g-1", price_cny=Decimal("10.00")),
        _candidate(goods_id="g-2", market_hash_name=None),
        _candidate(goods_id="g-3", price_cny=Decimal("12.00")),
        _candidate(goods_id="g-4", market_hash_name="Unknown"),
    ]
    result = enrich_candidates(candidates, enricher)
    assert isinstance(result, TradeUpInputEnrichmentResult)
    assert [item.candidate.goods_id for item in result.enriched] == ["g-1", "g-3"]
    assert [item.candidate.goods_id for item in result.rejected] == ["g-2", "g-4"]
    assert [item.candidate.price_cny for item in result.enriched] == [
        Decimal("10.00"),
        Decimal("12.00"),
    ]


def test_enrich_candidates_with_empty_input_returns_empty_result() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    enricher = InMemoryTradeUpInputEnricher(resolver)
    result = enrich_candidates([], enricher)
    assert result.enriched == ()
    assert result.rejected == ()


def test_enrichment_does_not_infer_or_guess_unresolved_identity() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    enricher = InMemoryTradeUpInputEnricher(resolver)
    candidate = _candidate(market_hash_name=None)
    outcome = enricher.enrich(candidate)
    assert isinstance(outcome, TradeUpEnrichmentRejection)
    for forbidden in ("guess", "infer", "derive", "default", "synthetic"):
        assert forbidden not in (candidate.market_hash_name or "").casefold()


def test_enrichment_rejection_does_not_expose_redacted_value_in_str() -> None:
    resolver = InMemoryTradeUpInputMetadataResolver({NAME: _metadata()})
    enricher = InMemoryTradeUpInputEnricher(resolver)
    secret = "personal-secret-marker-2251"
    candidate = _candidate(
        listing_id=secret,
        market_hash_name=None,
    )
    outcome = enricher.enrich(candidate)
    assert isinstance(outcome, TradeUpEnrichmentRejection)
    assert secret not in str(outcome)


def test_enrichment_module_has_no_live_or_external_dependencies() -> None:
    source = (
        Path(enrichment_module.__file__).read_text(encoding="utf-8")
    ).casefold()
    for forbidden in (
        "buff_listing",
        "buff_listing_provider",
        "buff_item_identity",
        "recipe_solver",
        "live_metadata_catalog",
        "live_recipe",
        "ev_service",
        "risk_filter",
        "valuation_service",
        "steamdt",
        "steamapis",
        "metadata_service",
        "metadata_provider",
        "metadata_models",
        "scanner",
        "purchase",
        "json",
        "os.environ",
        "open(",
    ):
        assert forbidden not in source