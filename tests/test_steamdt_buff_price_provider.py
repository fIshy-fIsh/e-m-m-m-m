from __future__ import annotations

import ast
import asyncio
import inspect
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

import app.services.steamdt_buff_price_provider as provider_module
from app.clients.steamdt_client import SteamDTPlatformPrice
from app.services.price_provider import (
    PriceLookupResult,
    PriceProvider,
    PriceQuote,
)
from app.services.steamdt_buff_price_policy import (
    SteamDTBuffOutputPrice,
    SteamDTBuffPriceSelectionError,
    SteamDTBuffPriceSelectionReason,
)
from app.services.steamdt_buff_price_provider import SteamDTBuffPriceProvider
from app.services.steamdt_market_data import SteamDTMarketDataResult

ITEM_A = "AK-47 | Redline (Field-Tested)"
ITEM_B = "M4A1-S | Decimator (Field-Tested)"
ITEM_C = "AWP | Asiimov (Battle-Scarred)"
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "steamdt_buff_price_provider.py"
)


def _quote(
    platform: str = "BUFF",
    *,
    sell_price: str | None = "12.3400",
    bidding_price: str | None = "11.00",
    sell_count: int | None = 2,
) -> SteamDTPlatformPrice:
    return SteamDTPlatformPrice(
        platform=platform,
        platform_item_id="opaque-provider-id",
        sell_price_cny=None if sell_price is None else Decimal(sell_price),
        sell_count=sell_count,
        bidding_price_cny=(
            None if bidding_price is None else Decimal(bidding_price)
        ),
        bidding_count=999,
        update_time="opaque-time",
        raw={"secret": "not retained"},
    )


class RecordingClient:
    def __init__(
        self,
        responses: dict[str, list[SteamDTPlatformPrice] | BaseException],
    ) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def get_price_single_candidates(
        self,
        market_hash_name: str,
    ) -> list[SteamDTPlatformPrice]:
        self.calls.append(market_hash_name)
        response = self.responses[market_hash_name]
        if isinstance(response, BaseException):
            raise response
        return response


def _provider(
    responses: dict[str, list[SteamDTPlatformPrice] | BaseException],
) -> tuple[SteamDTBuffPriceProvider, RecordingClient]:
    client = RecordingClient(responses)
    return SteamDTBuffPriceProvider(client), client


def test_public_api_and_price_provider_signatures_are_exact() -> None:
    assert provider_module.__all__ == ("SteamDTBuffPriceProvider",)
    assert inspect.iscoroutinefunction(SteamDTBuffPriceProvider.get_price)
    assert inspect.iscoroutinefunction(SteamDTBuffPriceProvider.get_prices)
    assert list(inspect.signature(SteamDTBuffPriceProvider).parameters) == ["client"]
    assert list(inspect.signature(SteamDTBuffPriceProvider.get_price).parameters) == [
        "self",
        "market_hash_name",
    ]
    assert list(inspect.signature(SteamDTBuffPriceProvider.get_prices).parameters) == [
        "self",
        "market_hash_names",
    ]
    assert (
        inspect.signature(SteamDTBuffPriceProvider.get_price).return_annotation
        == "PriceQuote"
    )
    assert (
        inspect.signature(SteamDTBuffPriceProvider.get_prices).return_annotation
        == "PriceLookupResult"
    )


def test_provider_structurally_satisfies_price_provider_for_type_checking() -> None:
    provider, _client = _provider({})

    typed_provider: PriceProvider = provider

    assert typed_provider is provider


def test_single_exact_buff_sell_price_returns_generic_quote() -> None:
    provider, client = _provider(
        {
            ITEM_A: [
                _quote("STEAM", sell_price="1.00"),
                _quote("BUFF", sell_price="101.2300", bidding_price="999.99"),
                _quote("YOUPIN", sell_price="9999", bidding_price="99999"),
            ]
        }
    )

    result = asyncio.run(provider.get_price(ITEM_A))

    assert type(result) is PriceQuote
    assert result.market_hash_name == ITEM_A
    assert result.price_cny == Decimal("101.2300")
    assert result.price_cny.as_tuple() == Decimal("101.2300").as_tuple()
    assert result.source == "steamdt:buff"
    assert result.raw is None
    assert client.calls == [ITEM_A]


def test_single_composes_aggregate_then_policy_as_authoritative_functions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingClient({})
    provider = SteamDTBuffPriceProvider(client)
    market_data = SteamDTMarketDataResult(market_hash_name=ITEM_A, quotes=())
    selected = SteamDTBuffOutputPrice(
        market_hash_name=ITEM_A,
        platform="BUFF",
        sell_price_cny=Decimal("77.7700"),
        sell_count=4,
        platform_item_id="opaque",
        update_time="opaque",
    )
    aggregate = AsyncMock(return_value=market_data)
    policy = Mock(return_value=selected)
    monkeypatch.setattr(provider_module, "get_steamdt_market_data", aggregate)
    monkeypatch.setattr(provider_module, "select_buff_output_price", policy)

    result = asyncio.run(provider.get_price(ITEM_A))

    aggregate.assert_awaited_once_with(client=client, market_hash_name=ITEM_A)
    policy.assert_called_once_with(market_data=market_data)
    assert result == PriceQuote(
        market_hash_name=ITEM_A,
        price_cny=Decimal("77.7700"),
        source="steamdt:buff",
        raw=None,
    )


@pytest.mark.parametrize(
    ("quotes", "reason"),
    [
        ([_quote("STEAM")], SteamDTBuffPriceSelectionReason.BUFF_RECORD_MISSING),
        (
            [_quote("BUFF"), _quote("BUFF")],
            SteamDTBuffPriceSelectionReason.DUPLICATE_BUFF_RECORDS,
        ),
        (
            [_quote("BUFF", sell_price=None, bidding_price="99999")],
            SteamDTBuffPriceSelectionReason.BUFF_SELL_PRICE_MISSING,
        ),
        (
            [_quote("BUFF", sell_price="0", bidding_price="99999")],
            SteamDTBuffPriceSelectionReason.BUFF_SELL_PRICE_NON_POSITIVE,
        ),
    ],
)
def test_single_policy_failures_propagate_without_quote(
    quotes: list[SteamDTPlatformPrice],
    reason: SteamDTBuffPriceSelectionReason,
) -> None:
    provider, client = _provider({ITEM_A: quotes})

    with pytest.raises(SteamDTBuffPriceSelectionError) as caught:
        asyncio.run(provider.get_price(ITEM_A))

    assert caught.value.reason is reason
    assert str(caught.value) == "SteamDT BUFF output price selection failed"
    assert client.calls == [ITEM_A]


def test_single_other_platform_prices_and_bids_never_fallback() -> None:
    provider, _client = _provider(
        {
            ITEM_A: [
                _quote("STEAM", sell_price="5000", bidding_price="6000"),
                _quote("YOUPIN", sell_price="7000", bidding_price="999999"),
                _quote("C5", sell_price="8000", bidding_price="9000"),
            ]
        }
    )

    with pytest.raises(SteamDTBuffPriceSelectionError) as caught:
        asyncio.run(provider.get_price(ITEM_A))

    assert caught.value.reason is SteamDTBuffPriceSelectionReason.BUFF_RECORD_MISSING


@pytest.mark.parametrize("market_hash_name", ["", " ", f" {ITEM_A}", f"{ITEM_A} "])
def test_single_noncanonical_name_fails_before_client_call(
    market_hash_name: str,
) -> None:
    provider, client = _provider({})

    with pytest.raises(ValueError, match="market_hash_name"):
        asyncio.run(provider.get_price(market_hash_name))

    assert client.calls == []


def test_single_ordinary_client_exception_propagates_by_identity() -> None:
    failure = RuntimeError("Authorization: Bearer secret-do-not-copy")
    provider, client = _provider({ITEM_A: failure})

    with pytest.raises(RuntimeError) as caught:
        asyncio.run(provider.get_price(ITEM_A))

    assert caught.value is failure
    assert client.calls == [ITEM_A]


@pytest.mark.parametrize(
    "failure",
    [
        MemoryError("memory"),
        asyncio.CancelledError("cancelled"),
        KeyboardInterrupt("keyboard"),
        SystemExit(9),
    ],
)
def test_single_process_control_failure_propagates_by_identity(
    failure: BaseException,
) -> None:
    provider, client = _provider({ITEM_A: failure})

    with pytest.raises(type(failure)) as caught:
        asyncio.run(provider.get_price(ITEM_A))

    assert caught.value is failure
    assert client.calls == [ITEM_A]


@pytest.mark.parametrize("raw_names", [[], [""], [" ", "  "]])
def test_batch_empty_canonical_input_returns_exact_empty_result(
    raw_names: list[str],
) -> None:
    provider, client = _provider({})

    result = asyncio.run(provider.get_prices(raw_names))

    assert type(result) is PriceLookupResult
    assert type(result.quotes) is dict
    assert type(result.missing) is list
    assert type(result.errors) is list
    assert result == PriceLookupResult(quotes={}, missing=[], errors=[])
    assert client.calls == []


def test_batch_strips_drops_and_stably_deduplicates_before_sequential_calls() -> None:
    provider, client = _provider(
        {
            ITEM_A: [_quote(sell_price="10.100")],
            ITEM_B: [_quote(sell_price="20.200")],
            ITEM_C: [_quote(sell_price="30.300")],
        }
    )

    result = asyncio.run(
        provider.get_prices(
            [
                f" {ITEM_A} ",
                " ",
                ITEM_B,
                ITEM_A,
                f"{ITEM_C} ",
                f" {ITEM_B}",
            ]
        )
    )

    assert client.calls == [ITEM_A, ITEM_B, ITEM_C]
    assert list(result.quotes) == [ITEM_A, ITEM_B, ITEM_C]
    assert [quote.market_hash_name for quote in result.quotes.values()] == [
        ITEM_A,
        ITEM_B,
        ITEM_C,
    ]
    assert [quote.price_cny for quote in result.quotes.values()] == [
        Decimal("10.100"),
        Decimal("20.200"),
        Decimal("30.300"),
    ]
    assert all(quote.source == "steamdt:buff" for quote in result.quotes.values())
    assert all(quote.raw is None for quote in result.quotes.values())
    assert result.missing == []
    assert result.errors == []


@pytest.mark.parametrize("invalid_names", [None, (), "name", {ITEM_A}, object()])
def test_batch_requires_exact_list_before_client_call(invalid_names: object) -> None:
    provider, client = _provider({})

    with pytest.raises(TypeError, match="market_hash_names"):
        asyncio.run(provider.get_prices(invalid_names))  # type: ignore[arg-type]

    assert client.calls == []


@pytest.mark.parametrize("invalid_value", [None, 1, True, Decimal("1"), object()])
def test_batch_requires_every_input_to_be_exact_string_before_client_call(
    invalid_value: object,
) -> None:
    provider, client = _provider({})

    with pytest.raises(TypeError, match="only strings"):
        asyncio.run(provider.get_prices([ITEM_A, invalid_value]))  # type: ignore[list-item]

    assert client.calls == []


def test_batch_middle_policy_failure_does_not_shift_later_quote() -> None:
    provider, client = _provider(
        {
            ITEM_A: [_quote(sell_price="10")],
            ITEM_B: [_quote("STEAM", sell_price="999")],
            ITEM_C: [_quote(sell_price="30")],
        }
    )

    result = asyncio.run(provider.get_prices([ITEM_A, ITEM_B, ITEM_C]))

    assert client.calls == [ITEM_A, ITEM_B, ITEM_C]
    assert list(result.quotes) == [ITEM_A, ITEM_C]
    assert result.quotes[ITEM_A].market_hash_name == ITEM_A
    assert result.quotes[ITEM_C].market_hash_name == ITEM_C
    assert result.quotes[ITEM_C].price_cny == Decimal("30")
    assert result.missing == [ITEM_B]
    assert result.errors == [
        "STEAMDT_BUFF_PRICE_SELECTION_FAILED: "
        "item_index=1, reason=buff_record_missing"
    ]


@pytest.mark.parametrize(
    ("quotes", "reason_value"),
    [
        ([_quote("BUFF"), _quote("BUFF")], "duplicate_buff_records"),
        ([_quote("BUFF", sell_price=None)], "buff_sell_price_missing"),
        ([_quote("BUFF", sell_price="0")], "buff_sell_price_non_positive"),
    ],
)
def test_batch_policy_failures_have_allowlisted_reason_only(
    quotes: list[SteamDTPlatformPrice],
    reason_value: str,
) -> None:
    provider, _client = _provider({ITEM_A: quotes})

    result = asyncio.run(provider.get_prices([ITEM_A]))

    assert result.quotes == {}
    assert result.missing == [ITEM_A]
    assert result.errors == [
        "STEAMDT_BUFF_PRICE_SELECTION_FAILED: "
        f"item_index=0, reason={reason_value}"
    ]
    assert ITEM_A not in result.errors[0]


def test_batch_ordinary_failure_is_fixed_redacted_and_later_items_continue() -> None:
    secret = "Bearer secret-token-value"
    failure = RuntimeError(f"Authorization: {secret}; raw response private")
    provider, client = _provider(
        {
            ITEM_A: failure,
            ITEM_B: [_quote(sell_price="22")],
        }
    )

    result = asyncio.run(provider.get_prices([ITEM_A, ITEM_B]))

    assert client.calls == [ITEM_A, ITEM_B]
    assert list(result.quotes) == [ITEM_B]
    assert result.missing == [ITEM_A]
    assert result.errors == ["STEAMDT_BUFF_PRICE_LOOKUP_FAILED: item_index=0"]
    rendered = "\n".join(result.errors)
    assert secret not in rendered
    assert "Authorization" not in rendered
    assert "RuntimeError" not in rendered
    assert "raw response" not in rendered
    assert ITEM_A not in rendered


def test_batch_multiple_failures_preserve_failed_item_order_and_unique_indices() -> None:
    provider, client = _provider(
        {
            ITEM_A: [_quote("STEAM")],
            ITEM_B: RuntimeError("hidden"),
            ITEM_C: [_quote("BUFF"), _quote("BUFF")],
        }
    )

    result = asyncio.run(
        provider.get_prices([ITEM_A, ITEM_B, ITEM_A, ITEM_C, ITEM_B])
    )

    assert client.calls == [ITEM_A, ITEM_B, ITEM_C]
    assert result.quotes == {}
    assert result.missing == [ITEM_A, ITEM_B, ITEM_C]
    assert result.errors == [
        "STEAMDT_BUFF_PRICE_SELECTION_FAILED: "
        "item_index=0, reason=buff_record_missing",
        "STEAMDT_BUFF_PRICE_LOOKUP_FAILED: item_index=1",
        "STEAMDT_BUFF_PRICE_SELECTION_FAILED: "
        "item_index=2, reason=duplicate_buff_records",
    ]


def test_batch_misaligned_single_quote_fails_closed_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _client = _provider({})
    get_price = AsyncMock(
        side_effect=[
            PriceQuote(ITEM_C, Decimal("1"), "steamdt:buff", None),
            PriceQuote(ITEM_B, Decimal("2"), "steamdt:buff", None),
        ]
    )
    monkeypatch.setattr(provider, "get_price", get_price)

    result = asyncio.run(provider.get_prices([ITEM_A, ITEM_B]))

    assert result.quotes == {ITEM_B: PriceQuote(ITEM_B, Decimal("2"), "steamdt:buff")}
    assert result.missing == [ITEM_A]
    assert result.errors == ["STEAMDT_BUFF_PRICE_LOOKUP_FAILED: item_index=0"]
    assert get_price.await_args_list[0].args == (ITEM_A,)
    assert get_price.await_args_list[1].args == (ITEM_B,)


@pytest.mark.parametrize(
    "failure",
    [
        MemoryError("memory"),
        asyncio.CancelledError("cancelled"),
        KeyboardInterrupt("keyboard"),
        SystemExit(7),
    ],
)
def test_batch_process_control_stops_before_later_item_and_returns_no_result(
    failure: BaseException,
) -> None:
    provider, client = _provider(
        {
            ITEM_A: [_quote(sell_price="1")],
            ITEM_B: failure,
            ITEM_C: [_quote(sell_price="3")],
        }
    )

    with pytest.raises(type(failure)) as caught:
        asyncio.run(provider.get_prices([ITEM_A, ITEM_B, ITEM_C]))

    assert caught.value is failure
    assert client.calls == [ITEM_A, ITEM_B]


def test_policy_module_has_no_selection_duplication_or_prohibited_boundaries() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    constants = {
        node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
    }
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)

    assert imports == {
        "__future__",
        "app.services.price_provider",
        "app.services.steamdt_buff_price_policy",
        "app.services.steamdt_market_data",
    }
    assert "BUFF" not in constants
    assert "bidding_price_cny" not in attributes
    assert "bidding_count" not in attributes
    assert "quotes" not in attributes
    assert "get_price_single_candidates" not in attributes
    assert "get_price_batch" not in attributes
    assert "get_price_single" not in attributes
    prohibited = {
        "httpx",
        "requests",
        "steamdt_client",
        "steamapis",
        "redis",
        "cache",
        "limiter",
        "valuation",
        "ev_service",
        "roi",
        "risk",
        "recipe",
        "scheduler",
        "fastapi",
        "discord",
        "environment",
        "config",
        "fee",
        "purchase",
        "listing",
    }
    folded_imports = "\n".join(imports).casefold()
    assert not any(fragment in folded_imports for fragment in prohibited)
    prohibited_calls = {
        "create_task",
        "gather",
        "TaskGroup",
        "sleep",
        "to_thread",
        "run_in_executor",
    }
    assert not any(
        isinstance(call.func, ast.Name) and call.func.id in prohibited_calls
        or isinstance(call.func, ast.Attribute) and call.func.attr in prohibited_calls
        for call in calls
    )


def test_protected_runtime_and_contracts_do_not_reverse_import_provider() -> None:
    root = Path(__file__).resolve().parents[1]
    protected_paths = [
        root / "app" / "clients" / "steamdt_client.py",
        root / "app" / "services" / "price_provider.py",
        root / "app" / "services" / "valuation_service.py",
        root / "app" / "services" / "live_recipe_valuation.py",
        root / "app" / "services" / "steamdt_market_data.py",
        root / "app" / "services" / "steamdt_buff_price_policy.py",
    ]

    for path in protected_paths:
        assert "steamdt_buff_price_provider" not in path.read_text(encoding="utf-8")


def test_no_concrete_runtime_methods_are_required_from_fake_client() -> None:
    provider, client = _provider({ITEM_A: [_quote()]})

    result = asyncio.run(provider.get_price(ITEM_A))

    assert result.price_cny == Decimal("12.3400")
    assert set(vars(client)) == {"responses", "calls"}
    assert not hasattr(client, "get_price_batch")
    assert not hasattr(client, "aclose")
    assert not hasattr(client, "api_key")


def test_price_provider_type_annotation_remains_existing_contract() -> None:
    provider, _client = _provider({})

    accepted = cast(PriceProvider, provider)

    assert accepted is provider
