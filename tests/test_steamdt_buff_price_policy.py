from __future__ import annotations

import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from decimal import Decimal
from pathlib import Path

import pytest

from app.clients.steamdt_client import SteamDTPlatformPrice
from app.services.steamdt_buff_price_policy import (
    SteamDTBuffOutputPrice,
    SteamDTBuffPriceSelectionError,
    SteamDTBuffPriceSelectionReason,
    select_buff_output_price,
)
from app.services.steamdt_market_data import SteamDTMarketDataResult

ITEM = "AK-47 | Redline (Field-Tested)"
FIXED_ERROR = "SteamDT BUFF output price selection failed"
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "steamdt_buff_price_policy.py"
)


def _quote(
    platform: str = "BUFF",
    *,
    sell_price: Decimal | None = Decimal("12.3400"),
    sell_count: int | None = 3,
    platform_item_id: str | None = "opaque-item",
    update_time: int | str | None = 123456,
    bidding_price: object = Decimal("11.25"),
    bidding_count: object = 2,
) -> SteamDTPlatformPrice:
    return SteamDTPlatformPrice(
        platform=platform,
        platform_item_id=platform_item_id,
        sell_price_cny=sell_price,
        sell_count=sell_count,
        bidding_price_cny=bidding_price,  # type: ignore[arg-type]
        bidding_count=bidding_count,  # type: ignore[arg-type]
        update_time=update_time,
        raw={"private": "not retained"},
    )


def _market_data(*quotes: SteamDTPlatformPrice) -> SteamDTMarketDataResult:
    return SteamDTMarketDataResult(market_hash_name=ITEM, quotes=quotes)


def _assert_reason(
    expected: SteamDTBuffPriceSelectionReason,
    *,
    market_data: object,
) -> SteamDTBuffPriceSelectionError:
    with pytest.raises(SteamDTBuffPriceSelectionError) as caught:
        select_buff_output_price(market_data=market_data)  # type: ignore[arg-type]

    assert str(caught.value) == FIXED_ERROR
    assert caught.value.args == (FIXED_ERROR,)
    assert caught.value.reason is expected
    assert caught.value.__cause__ is None
    assert ITEM not in str(caught.value)
    return caught.value


def test_public_api_is_narrow_and_stable() -> None:
    import app.services.steamdt_buff_price_policy as policy

    assert policy.__all__ == (
        "SteamDTBuffPriceSelectionReason",
        "SteamDTBuffPriceSelectionError",
        "SteamDTBuffOutputPrice",
        "select_buff_output_price",
    )
    assert list(SteamDTBuffPriceSelectionReason) == [
        SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA,
        SteamDTBuffPriceSelectionReason.BUFF_RECORD_MISSING,
        SteamDTBuffPriceSelectionReason.DUPLICATE_BUFF_RECORDS,
        SteamDTBuffPriceSelectionReason.BUFF_SELL_PRICE_MISSING,
        SteamDTBuffPriceSelectionReason.BUFF_SELL_PRICE_NON_FINITE,
        SteamDTBuffPriceSelectionReason.BUFF_SELL_PRICE_NON_POSITIVE,
    ]
    assert [reason.value for reason in SteamDTBuffPriceSelectionReason] == [
        "invalid_market_data",
        "buff_record_missing",
        "duplicate_buff_records",
        "buff_sell_price_missing",
        "buff_sell_price_non_finite",
        "buff_sell_price_non_positive",
    ]
    signature = inspect.signature(select_buff_output_price)
    assert list(signature.parameters) == ["market_data"]
    assert signature.parameters["market_data"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.return_annotation == "SteamDTBuffOutputPrice"
    assert issubclass(SteamDTBuffPriceSelectionError, RuntimeError)


def test_output_contract_is_frozen_keyword_only_and_repr_suppressed() -> None:
    assert [field.name for field in fields(SteamDTBuffOutputPrice)] == [
        "market_hash_name",
        "platform",
        "sell_price_cny",
        "sell_count",
        "platform_item_id",
        "update_time",
    ]
    with pytest.raises(TypeError):
        SteamDTBuffOutputPrice(  # type: ignore[misc]
            ITEM,
            "BUFF",
            Decimal("1"),
            1,
            None,
            None,
        )

    result = select_buff_output_price(market_data=_market_data(_quote()))

    with pytest.raises(FrozenInstanceError):
        result.sell_count = 4  # type: ignore[misc]
    assert repr(result).startswith("<")
    assert ITEM not in repr(result)
    assert "12.3400" not in repr(result)
    assert not hasattr(result, "raw")
    assert not hasattr(result, "quote")
    assert not hasattr(result, "bidding_price_cny")


def test_one_exact_buff_record_returns_detached_gross_price() -> None:
    source = _quote(
        sell_price=Decimal("101.2300"),
        sell_count=7,
        platform_item_id="provider-local-1",
        update_time="opaque-time",
        bidding_price=Decimal("999.99"),
        bidding_count=999,
    )
    market_data = _market_data(source)
    selected_quote = market_data.quotes[0]

    result = select_buff_output_price(market_data=market_data)

    assert result == SteamDTBuffOutputPrice(
        market_hash_name=ITEM,
        platform="BUFF",
        sell_price_cny=Decimal("101.2300"),
        sell_count=7,
        platform_item_id="provider-local-1",
        update_time="opaque-time",
    )
    assert result.sell_price_cny.as_tuple() == Decimal("101.2300").as_tuple()
    assert market_data.quotes == (selected_quote,)
    assert market_data.quotes[0].bidding_price_cny == Decimal("999.99")
    assert market_data.quotes[0].raw is None


def test_mixed_platforms_select_only_exact_buff_without_price_ranking() -> None:
    market_data = _market_data(
        _quote("STEAM", sell_price=Decimal("0.01")),
        _quote("YOUPIN", sell_price=Decimal("900")),
        _quote("BUFF", sell_price=Decimal("42.500")),
        _quote("C5", sell_price=Decimal("1.00")),
    )

    result = select_buff_output_price(market_data=market_data)

    assert result.platform == "BUFF"
    assert result.sell_price_cny == Decimal("42.500")


@pytest.mark.parametrize(
    "platform",
    ["buff", "Buff", "BUFF163", "网易BUFF", " BUFF ", "BUFF ", " BUFF"],
)
def test_near_match_platform_alone_fails_closed(platform: str) -> None:
    _assert_reason(
        SteamDTBuffPriceSelectionReason.BUFF_RECORD_MISSING,
        market_data=_market_data(_quote(platform)),
    )


def test_near_matches_are_ignored_when_one_exact_buff_exists() -> None:
    market_data = _market_data(
        _quote("buff", sell_price=Decimal("1")),
        _quote("BUFF163", sell_price=Decimal("2")),
        _quote(" BUFF ", sell_price=Decimal("3")),
        _quote("BUFF", sell_price=Decimal("4.500")),
    )

    result = select_buff_output_price(market_data=market_data)

    assert result.sell_price_cny == Decimal("4.500")


@pytest.mark.parametrize(
    "quotes",
    [
        (),
        (_quote("STEAM"),),
        (_quote("STEAM"), _quote("YOUPIN"), _quote("C5")),
    ],
)
def test_no_exact_buff_has_no_cross_platform_fallback(
    quotes: tuple[SteamDTPlatformPrice, ...],
) -> None:
    _assert_reason(
        SteamDTBuffPriceSelectionReason.BUFF_RECORD_MISSING,
        market_data=_market_data(*quotes),
    )


def test_duplicate_exact_buff_records_fail_without_picking_one() -> None:
    market_data = _market_data(
        _quote("BUFF", sell_price=Decimal("1")),
        _quote("BUFF", sell_price=Decimal("999")),
    )

    _assert_reason(
        SteamDTBuffPriceSelectionReason.DUPLICATE_BUFF_RECORDS,
        market_data=market_data,
    )


def test_duplicate_reason_precedes_duplicate_price_validation() -> None:
    market_data = _market_data(
        _quote("BUFF", sell_price=None),
        _quote("BUFF", sell_price=Decimal("2")),
    )
    object.__setattr__(market_data.quotes[1], "sell_price_cny", Decimal("NaN"))

    _assert_reason(
        SteamDTBuffPriceSelectionReason.DUPLICATE_BUFF_RECORDS,
        market_data=market_data,
    )


def test_missing_sell_price_is_not_replaced_by_higher_bid() -> None:
    market_data = _market_data(
        _quote(
            sell_price=None,
            bidding_price=Decimal("1000000"),
            bidding_count=500,
        )
    )

    _assert_reason(
        SteamDTBuffPriceSelectionReason.BUFF_SELL_PRICE_MISSING,
        market_data=market_data,
    )


@pytest.mark.parametrize("sell_price", [Decimal("0"), Decimal("-0")])
def test_zero_sell_price_fails_even_with_positive_bid(sell_price: Decimal) -> None:
    market_data = _market_data(
        _quote(sell_price=sell_price, bidding_price=Decimal("100"))
    )

    _assert_reason(
        SteamDTBuffPriceSelectionReason.BUFF_SELL_PRICE_NON_POSITIVE,
        market_data=market_data,
    )


def test_tampered_negative_sell_price_fails_closed() -> None:
    market_data = _market_data(_quote())
    object.__setattr__(market_data.quotes[0], "sell_price_cny", Decimal("-1"))

    _assert_reason(
        SteamDTBuffPriceSelectionReason.BUFF_SELL_PRICE_NON_POSITIVE,
        market_data=market_data,
    )


@pytest.mark.parametrize(
    "sell_price",
    [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_nonfinite_sell_price_fails_closed(sell_price: Decimal) -> None:
    market_data = _market_data(_quote())
    object.__setattr__(market_data.quotes[0], "sell_price_cny", sell_price)

    _assert_reason(
        SteamDTBuffPriceSelectionReason.BUFF_SELL_PRICE_NON_FINITE,
        market_data=market_data,
    )


@pytest.mark.parametrize("sell_price", [1, 1.5, "1", True, object()])
def test_non_decimal_sell_price_is_invalid_market_data(sell_price: object) -> None:
    market_data = _market_data(_quote())
    object.__setattr__(market_data.quotes[0], "sell_price_cny", sell_price)

    _assert_reason(
        SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA,
        market_data=market_data,
    )


@pytest.mark.parametrize(
    ("bidding_price", "bidding_count"),
    [
        (None, None),
        (Decimal("0"), 0),
        (Decimal("1"), 1),
        (Decimal("12.3400"), 2),
        (Decimal("999999"), 999),
        (Decimal("NaN"), -1),
        (Decimal("Infinity"), True),
        (object(), object()),
    ],
)
def test_all_bid_values_are_ignored(
    bidding_price: object,
    bidding_count: object,
) -> None:
    market_data = _market_data(_quote())
    object.__setattr__(market_data.quotes[0], "bidding_price_cny", bidding_price)
    object.__setattr__(market_data.quotes[0], "bidding_count", bidding_count)

    result = select_buff_output_price(market_data=market_data)

    assert result.sell_price_cny == Decimal("12.3400")


@pytest.mark.parametrize("sell_count", [None, 0, 1, 123])
def test_sell_count_is_preserved_without_liquidity_gate(
    sell_count: int | None,
) -> None:
    result = select_buff_output_price(
        market_data=_market_data(_quote(sell_count=sell_count))
    )

    assert result.sell_count == sell_count


@pytest.mark.parametrize("sell_count", [True, -1, 1.5, "1", object()])
def test_invalid_sell_count_fails_closed(sell_count: object) -> None:
    market_data = _market_data(_quote())
    object.__setattr__(market_data.quotes[0], "sell_count", sell_count)

    _assert_reason(
        SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA,
        market_data=market_data,
    )


@pytest.mark.parametrize("platform_item_id", [None, "", "opaque", " listing-like "])
def test_platform_item_id_is_preserved_as_opaque_text(
    platform_item_id: str | None,
) -> None:
    result = select_buff_output_price(
        market_data=_market_data(_quote(platform_item_id=platform_item_id))
    )

    assert result.platform_item_id == platform_item_id


@pytest.mark.parametrize("update_time", [None, 0, -1, 1720000000, "", "opaque"])
def test_update_time_is_preserved_without_interpretation(
    update_time: int | str | None,
) -> None:
    result = select_buff_output_price(
        market_data=_market_data(_quote(update_time=update_time))
    )

    assert result.update_time == update_time


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("platform_item_id", 123),
        ("platform_item_id", True),
        ("update_time", True),
        ("update_time", Decimal("1")),
        ("update_time", object()),
    ],
)
def test_invalid_selected_opaque_field_types_fail_closed(
    field: str,
    value: object,
) -> None:
    market_data = _market_data(_quote())
    object.__setattr__(market_data.quotes[0], field, value)

    _assert_reason(
        SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA,
        market_data=market_data,
    )


def test_repeated_selection_is_deterministic_detached_and_nonmutating() -> None:
    market_data = _market_data(_quote())
    original_quote = market_data.quotes[0]
    original_fields = (
        original_quote.platform,
        original_quote.sell_price_cny,
        original_quote.sell_count,
        original_quote.platform_item_id,
        original_quote.update_time,
        original_quote.raw,
    )

    first = select_buff_output_price(market_data=market_data)
    second = select_buff_output_price(market_data=market_data)
    object.__setattr__(original_quote, "sell_price_cny", Decimal("777"))

    assert first == second
    assert first is not second
    assert first.sell_price_cny == Decimal("12.3400")
    assert original_fields == (
        "BUFF",
        Decimal("12.3400"),
        3,
        "opaque-item",
        123456,
        None,
    )


@pytest.mark.parametrize("market_data", [None, object(), "market-data", 1])
def test_invalid_outer_input_type_fails_closed(market_data: object) -> None:
    _assert_reason(
        SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA,
        market_data=market_data,
    )


def test_subclassed_outer_result_fails_closed() -> None:
    class DerivedMarketData(SteamDTMarketDataResult):
        pass

    market_data = DerivedMarketData(market_hash_name=ITEM, quotes=(_quote(),))

    _assert_reason(
        SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA,
        market_data=market_data,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("market_hash_name", ""),
        ("market_hash_name", f" {ITEM}"),
        ("market_hash_name", 123),
        ("quotes", []),
        ("quotes", "quotes"),
        ("quotes", (object(),)),
    ],
)
def test_tampered_outer_contract_fails_closed(field: str, value: object) -> None:
    market_data = _market_data(_quote())
    object.__setattr__(market_data, field, value)

    _assert_reason(
        SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA,
        market_data=market_data,
    )


def test_tampered_platform_type_fails_closed() -> None:
    market_data = _market_data(_quote())
    object.__setattr__(market_data.quotes[0], "platform", 123)

    _assert_reason(
        SteamDTBuffPriceSelectionReason.INVALID_MARKET_DATA,
        market_data=market_data,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"market_hash_name": ""},
        {"platform": "buff"},
        {"sell_price_cny": Decimal("0")},
        {"sell_price_cny": Decimal("Infinity")},
        {"sell_price_cny": 1},
        {"sell_count": True},
        {"platform_item_id": 1},
        {"update_time": True},
    ],
)
def test_direct_output_construction_revalidates_contract(
    kwargs: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "market_hash_name": ITEM,
        "platform": "BUFF",
        "sell_price_cny": Decimal("1"),
        "sell_count": 1,
        "platform_item_id": None,
        "update_time": None,
    }
    values.update(kwargs)

    with pytest.raises(SteamDTBuffPriceSelectionError) as caught:
        SteamDTBuffOutputPrice(**values)  # type: ignore[arg-type]

    assert str(caught.value) == FIXED_ERROR


def test_exception_rejects_invalid_reason_type() -> None:
    with pytest.raises(TypeError, match="reason"):
        SteamDTBuffPriceSelectionError(reason="invalid_market_data")  # type: ignore[arg-type]


def test_policy_has_no_bid_access_or_runtime_dependencies() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    accessed_attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)

    assert imports == {
        "__future__",
        "dataclasses",
        "decimal",
        "enum",
        "typing",
        "app.clients.steamdt_client",
        "app.services.steamdt_market_data",
    }
    assert "bidding_price_cny" not in accessed_attributes
    assert "bidding_count" not in accessed_attributes
    forbidden_fragments = {
        "pricequote",
        "price_provider",
        "valuation",
        "ev_service",
        "roi",
        "risk",
        "recipe",
        "steamapis",
        "redis",
        "cache",
        "limiter",
        "scheduler",
        "fastapi",
        "discord",
        "httpx",
        "requests",
        "asyncio",
        "thread",
        "environment",
        "os.environ",
        "fee",
        "purchase",
        "listing",
    }
    folded_imports = "\n".join(sorted(imports)).casefold()
    assert not any(fragment in folded_imports for fragment in forbidden_fragments)
    assert not any(isinstance(node, (ast.AsyncFunctionDef, ast.Await)) for node in ast.walk(tree))


def test_protected_services_do_not_reverse_import_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    protected_paths = [
        root / "app" / "clients" / "steamdt_client.py",
        root / "app" / "services" / "steamdt_market_data.py",
        root / "app" / "services" / "price_provider.py",
        root / "app" / "services" / "valuation_service.py",
        root / "app" / "services" / "live_recipe_valuation.py",
    ]

    for path in protected_paths:
        assert "steamdt_buff_price_policy" not in path.read_text(encoding="utf-8")
