from __future__ import annotations

import asyncio
import json
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.buff_listing_provider import (
    BuffListing,
    BuffListingProvider,
    BuffListingProviderError,
    parse_buff_listing_response,
)

GOODS_ID = "synthetic-goods-context"
FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "buff"
    / "anonymous_sell_orders_provider_v1.json"
)


def _assert_context_free(error: BaseException) -> None:
    assert error.__cause__ is None
    assert error.__context__ is None


class Client:
    def __init__(self, payload: bytes, error: BaseException | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[str] = []

    async def fetch_sell_order_payload(self, goods_id: str) -> bytes:
        self.calls.append(goods_id)
        if self.error is not None:
            raise self.error
        return self.payload


def _payload() -> bytes:
    return FIXTURE.read_bytes()


def _base_item() -> dict[str, object]:
    return {
        "id": "listing-1",
        "price": "12.3400",
        "asset_info": {
            "assetid": "asset-1",
            "paintwear": "0.03100",
            "paintseed": 55,
        },
    }


def _bytes(items: list[object]) -> bytes:
    return json.dumps({"code": "OK", "data": {"items": items}}).encode()


def test_fixture_maps_all_items_in_order_and_missing_seed_is_valid() -> None:
    listings = parse_buff_listing_response(_payload(), goods_id=GOODS_ID)

    assert [item.listing_id for item in listings] == [
        "synthetic-sell-order-001",
        "synthetic-sell-order-002",
    ]
    assert [item.goods_id for item in listings] == [GOODS_ID, GOODS_ID]
    assert [item.market_hash_name for item in listings] == [None, None]
    assert [item.price_cny for item in listings] == [
        Decimal("123.4500"),
        Decimal("45.6700"),
    ]
    assert [item.paintwear for item in listings] == [
        Decimal("0.031250"),
        Decimal("0.456700"),
    ]
    assert [item.asset_id for item in listings] == [
        "synthetic-asset-001",
        "synthetic-asset-002",
    ]
    assert [item.paintseed for item in listings] == [321, None]
    assert all(item.source == "buff" for item in listings)
    assert "Unverified Synthetic Name" not in repr(listings)


def test_listing_is_frozen_repr_suppressed_and_source_fixed() -> None:
    listing = parse_buff_listing_response(_payload(), goods_id=GOODS_ID)[0]
    assert "synthetic-sell-order" not in repr(listing)
    with pytest.raises(FrozenInstanceError):
        listing.price_cny = Decimal("1")  # type: ignore[misc]
    with pytest.raises(BuffListingProviderError):
        BuffListing(
            listing_id="a",
            goods_id="b",
            market_hash_name=None,
            price_cny=Decimal("1"),
            paintwear=Decimal("0.1"),
            asset_id="c",
            paintseed=None,
            source="other",
        )


def test_empty_items_returns_empty_list() -> None:
    assert parse_buff_listing_response(_bytes([]), goods_id=GOODS_ID) == []


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda item: item.pop("id"), "listing_id_invalid"),
        (lambda item: item.__setitem__("id", ""), "listing_id_invalid"),
        (lambda item: item.pop("price"), "price_invalid"),
        (lambda item: item.__setitem__("price", "bad"), "price_invalid"),
        (lambda item: item.__setitem__("price", "0"), "price_invalid"),
        (lambda item: item["asset_info"].pop("paintwear"), "paintwear_invalid"),
        (
            lambda item: item["asset_info"].__setitem__("paintwear", "1.1"),
            "paintwear_invalid",
        ),
        (lambda item: item["asset_info"].pop("assetid"), "asset_id_invalid"),
        (
            lambda item: item["asset_info"].__setitem__("assetid", ""),
            "asset_id_invalid",
        ),
        (
            lambda item: item["asset_info"].__setitem__("paintseed", True),
            "paintseed_invalid",
        ),
    ],
)
def test_invalid_item_is_rejected(
    mutation,
    reason: str,
) -> None:
    item = _base_item()
    mutation(item)
    with pytest.raises(BuffListingProviderError) as captured:
        parse_buff_listing_response(_bytes([item]), goods_id=GOODS_ID)
    assert captured.value.reason == reason
    assert captured.value.item_index == 0
    assert captured.value.__cause__ is None
    _assert_context_free(captured.value)


def test_whitespace_padded_response_identity_is_rejected() -> None:
    item = _base_item()
    item["id"] = " listing-1 "
    with pytest.raises(BuffListingProviderError) as captured:
        parse_buff_listing_response(_bytes([item]), goods_id=GOODS_ID)
    assert captured.value.reason == "listing_id_invalid"

    item = _base_item()
    item["asset_info"]["assetid"] = " asset-1 "  # type: ignore[index]
    with pytest.raises(BuffListingProviderError) as captured:
        parse_buff_listing_response(_bytes([item]), goods_id=GOODS_ID)
    assert captured.value.reason == "asset_id_invalid"


    with pytest.raises(BuffListingProviderError) as captured:
        parse_buff_listing_response(b'{"secret_marker":', goods_id=GOODS_ID)
    assert captured.value.reason == "response_not_json"
    assert "secret_marker" not in str(captured.value)
    _assert_context_free(captured.value)


def test_direct_dto_and_parser_reject_padded_goods_id() -> None:
    with pytest.raises(BuffListingProviderError) as captured:
        BuffListing(
            listing_id="listing",
            goods_id=" padded ",
            market_hash_name=None,
            price_cny=Decimal("1"),
            paintwear=Decimal("0.1"),
            asset_id="asset",
            paintseed=None,
        )
    _assert_context_free(captured.value)

    with pytest.raises(BuffListingProviderError) as captured:
        parse_buff_listing_response(_payload(), goods_id=" padded ")
    assert captured.value.reason == "invalid_goods_id"
    _assert_context_free(captured.value)


def test_invalid_second_item_rejects_whole_page() -> None:
    valid = _base_item()
    invalid = _base_item()
    invalid["id"] = None
    with pytest.raises(BuffListingProviderError) as captured:
        parse_buff_listing_response(_bytes([valid, invalid]), goods_id=GOODS_ID)
    assert captured.value.reason == "listing_id_invalid"
    assert captured.value.item_index == 1


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (b"not json", "response_not_json"),
        (b"[]", "response_schema_invalid"),
        (b'{"code":"ERROR","msg":"private"}', "anonymous_access_unavailable"),
        (b'{"code":"OK","data":{}}', "items_missing"),
        (b'{"code":"OK","code":"OK"}', "response_not_json"),
        (b'{"code":NaN}', "response_not_json"),
    ],
)
def test_envelope_failures_are_fixed(payload: bytes, reason: str) -> None:
    with pytest.raises(BuffListingProviderError) as captured:
        parse_buff_listing_response(payload, goods_id=GOODS_ID)
    assert captured.value.reason == reason
    rendered = f"{captured.value!s} {captured.value!r}"
    assert "private" not in rendered
    assert payload.decode(errors="ignore") not in rendered


def test_provider_calls_borrowed_client_once() -> None:
    client = Client(_payload())
    provider = BuffListingProvider(client)
    result = asyncio.run(provider.get_listings(f"  {GOODS_ID}  "))
    assert len(result) == 2
    assert client.calls == [GOODS_ID]
    assert not hasattr(provider, "close")
    assert not hasattr(provider, "aclose")


@pytest.mark.parametrize("goods_id", ["", "   ", None, 1, True])
def test_provider_rejects_goods_id_before_client(goods_id: object) -> None:
    client = Client(_payload())
    with pytest.raises(BuffListingProviderError) as captured:
        asyncio.run(BuffListingProvider(client).get_listings(goods_id))  # type: ignore[arg-type]
    assert captured.value.reason == "invalid_goods_id"
    assert client.calls == []


def test_provider_source_has_no_downstream_or_external_dependencies() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "buff_listing_provider.py"
    ).read_text(encoding="utf-8").casefold()
    for marker in (
        "candidatelisting",
        "recipe_solver",
        "tradeup_engine",
        "valuation",
        "ev_service",
        "risk_filter",
        "steamapis",
        "steamdt",
        "redis",
        "purchase",
        "login",
    ):
        assert marker not in source
