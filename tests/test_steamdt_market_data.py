import ast
import asyncio
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from app.clients.steamdt_client import (
    SteamDTClientConfig,
    SteamDTHttpClient,
    SteamDTPlatformPrice,
)
from app.services.price_provider import SteamDTPriceProvider
from app.services.steamdt_market_data import (
    SteamDTMarketDataResult,
    get_steamdt_market_data,
)

ITEM = "AK-47 | Redline (Field-Tested)"


def _quote(
    platform: str = "BUFF",
    *,
    platform_item_id: str | None = "opaque-item",
    sell_price: str | None = "12.3400",
    sell_count: int | None = 3,
    bidding_price: str | None = "11.2500",
    bidding_count: int | None = 2,
    update_time: int | str | None = 123456,
    raw: dict[str, object] | None = None,
) -> SteamDTPlatformPrice:
    return SteamDTPlatformPrice(
        platform=platform,
        platform_item_id=platform_item_id,
        sell_price_cny=None if sell_price is None else Decimal(sell_price),
        sell_count=sell_count,
        bidding_price_cny=(
            None if bidding_price is None else Decimal(bidding_price)
        ),
        bidding_count=bidding_count,
        update_time=update_time,
        raw=raw,
    )


class FakeClient:
    def __init__(self, quotes: object) -> None:
        self.quotes = quotes
        self.calls: list[str] = []

    async def get_price_single_candidates(self, market_hash_name: str):
        self.calls.append(market_hash_name)
        return self.quotes


@pytest.mark.parametrize("market_hash_name", ["", " ", f" {ITEM}", f"{ITEM} "])
def test_market_data_rejects_noncanonical_market_hash_name(
    market_hash_name: str,
) -> None:
    client = FakeClient([])

    with pytest.raises(ValueError, match="market_hash_name"):
        asyncio.run(
            get_steamdt_market_data(
                client=client,  # type: ignore[arg-type]
                market_hash_name=market_hash_name,
            )
        )

    assert client.calls == []


def test_market_data_rejects_non_string_market_hash_name() -> None:
    client = FakeClient([])

    with pytest.raises(TypeError, match="market_hash_name"):
        asyncio.run(
            get_steamdt_market_data(
                client=client,  # type: ignore[arg-type]
                market_hash_name=123,  # type: ignore[arg-type]
            )
        )

    assert client.calls == []


def test_market_data_preserves_provider_order_duplicates_and_all_typed_fields() -> None:
    raw = {"Authorization": "Bearer secret", "raw_response": "not retained"}
    quotes = [
        _quote("网易BUFF", raw=raw),
        _quote(
            "buff",
            platform_item_id=None,
            sell_price=None,
            sell_count=None,
            bidding_price=None,
            bidding_count=None,
            update_time="opaque",
            raw=raw,
        ),
        _quote("网易BUFF", platform_item_id="duplicate", raw=raw),
    ]
    client = FakeClient(quotes)

    result = asyncio.run(
        get_steamdt_market_data(
            client=client,  # type: ignore[arg-type]
            market_hash_name=ITEM,
        )
    )

    assert client.calls == [ITEM]
    assert result.market_hash_name == ITEM
    assert [quote.platform for quote in result.quotes] == ["网易BUFF", "buff", "网易BUFF"]
    assert result.quotes[0].platform_item_id == "opaque-item"
    assert result.quotes[0].sell_price_cny == Decimal("12.3400")
    assert result.quotes[0].sell_count == 3
    assert result.quotes[0].bidding_price_cny == Decimal("11.2500")
    assert result.quotes[0].bidding_count == 2
    assert result.quotes[0].update_time == 123456
    assert result.quotes[1].platform_item_id is None
    assert result.quotes[1].sell_price_cny is None
    assert result.quotes[1].sell_count is None
    assert result.quotes[1].bidding_price_cny is None
    assert result.quotes[1].bidding_count is None
    assert result.quotes[1].update_time == "opaque"
    assert all(quote.raw is None for quote in result.quotes)
    assert result.quotes[0] is not quotes[0]


def test_market_data_accepts_empty_provider_collection() -> None:
    client = FakeClient([])

    result = asyncio.run(
        get_steamdt_market_data(
            client=client,  # type: ignore[arg-type]
            market_hash_name=ITEM,
        )
    )

    assert result.quotes == ()
    assert client.calls == [ITEM]


@pytest.mark.parametrize("invalid_quotes", [None, "quotes", b"quotes", {"platform": "x"}])
def test_market_data_rejects_invalid_client_sequence(invalid_quotes: object) -> None:
    client = FakeClient(invalid_quotes)

    with pytest.raises(TypeError, match="quote sequence"):
        asyncio.run(
            get_steamdt_market_data(
                client=client,  # type: ignore[arg-type]
                market_hash_name=ITEM,
            )
        )

    assert client.calls == [ITEM]


def test_market_data_rejects_non_platform_price_value_atomically() -> None:
    client = FakeClient([_quote(), object()])

    with pytest.raises(TypeError, match="SteamDTPlatformPrice"):
        asyncio.run(
            get_steamdt_market_data(
                client=client,  # type: ignore[arg-type]
                market_hash_name=ITEM,
            )
        )


def test_result_revalidates_and_defensively_strips_raw() -> None:
    original = _quote(raw={"payload": "private"})

    result = SteamDTMarketDataResult(market_hash_name=ITEM, quotes=(original,))

    assert result.quotes == (_quote(raw=None),)
    assert result.quotes[0] is not original
    assert result.quotes[0].raw is None
    assert repr(result).startswith("<")
    assert ITEM not in repr(result)


def test_real_client_parser_and_service_preserve_official_shaped_platform_data() -> None:
    payload = {
        "success": True,
        "data": [
            {
                "platform": "BUFF163",
                "platformItemId": "provider-local-1",
                "sellPrice": "101.2300",
                "sellCount": 4,
                "biddingPrice": "99.50",
                "biddingCount": 7,
                "updateTime": 1720000000,
            },
            {
                "platform": "Other Market",
                "platformItemId": None,
                "sellPrice": None,
                "sellCount": None,
                "biddingPrice": "80.00",
                "biddingCount": 1,
                "updateTime": "opaque",
            },
        ],
    }
    http_client = AsyncMock()
    http_client.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "https://example.invalid/open/cs2/v1/price/single"),
        json=payload,
    )
    client = SteamDTHttpClient(
        SteamDTClientConfig(
            base_url="https://example.invalid",
            api_key="offline-secret",
            max_retries=0,
            dry_run=False,
        ),
        http_client=http_client,
    )

    result = asyncio.run(
        get_steamdt_market_data(client=client, market_hash_name=ITEM)
    )

    assert [quote.platform for quote in result.quotes] == ["BUFF163", "Other Market"]
    assert result.quotes[0].sell_price_cny == Decimal("101.2300")
    assert result.quotes[0].bidding_price_cny == Decimal("99.50")
    assert result.quotes[1].sell_price_cny is None
    assert result.quotes[1].bidding_price_cny == Decimal("80.00")
    assert all(quote.raw is None for quote in result.quotes)
    http_client.request.assert_awaited_once()


def test_project_approved_cny_assumption_reaches_existing_price_provider() -> None:
    """This verifies the project assumption, not an official currency guarantee."""

    payload = {
        "success": True,
        "data": [
            {
                "platform": "provider-exact",
                "sellPrice": "123.4500",
                "sellCount": 2,
                "biddingPrice": "120.00",
                "biddingCount": 1,
            }
        ],
    }
    http_client = AsyncMock()
    http_client.request.return_value = httpx.Response(
        200,
        request=httpx.Request("GET", "https://example.invalid/open/cs2/v1/price/single"),
        json=payload,
    )
    client = SteamDTHttpClient(
        SteamDTClientConfig(
            base_url="https://example.invalid",
            api_key="offline-secret",
            max_retries=0,
            dry_run=False,
        ),
        http_client=http_client,
    )
    provider = SteamDTPriceProvider(client)

    quote = asyncio.run(provider.get_price(ITEM))

    assert quote.market_hash_name == ITEM
    assert quote.price_cny == Decimal("123.4500")
    assert quote.source == "steamdt"
    http_client.request.assert_awaited_once()


def test_market_data_module_has_no_listing_synthesis_or_runtime_imports() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "steamdt_market_data.py"
    )
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module.casefold())

    forbidden = {
        "steamapis",
        "buff",
        "candidate",
        "price_provider",
        "valuation",
        "ev_service",
        "risk",
        "recipe",
        "redis",
        "cache",
        "scheduler",
        "fastapi",
    }
    assert not any(fragment in imported for imported in imports for fragment in forbidden)
    assert "purchase" not in source.casefold()
    assert "listing_id" not in source
    assert source.count("get_price_single_candidates(") == 2
