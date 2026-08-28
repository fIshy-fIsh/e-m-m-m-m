from __future__ import annotations

import ast
import asyncio
import inspect
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

import app.services.live_recipe_valuation as live_valuation_module
import app.services.steamdt_buff_live_recipe_valuation as composition_module
from app.clients.steamdt_client import SteamDTPlatformPrice
from app.services.live_metadata_catalog import (
    LiveCandidateBinding,
    LiveCandidateClassification,
    LiveSolverBucket,
    LiveSolverBucketKey,
)
from app.services.live_recipe_construction import (
    LiveConstructedRecipe,
    LiveRecipeConstructionResult,
)
from app.services.live_recipe_valuation import (
    LiveRecipeValuationRejectionReason,
    LiveRecipeValuationResult,
)
from app.services.market_scan_service import CandidateListing
from app.services.metadata_models import SkinMetadata
from app.services.price_provider import PriceQuote
from app.services.recipe_solver import ConstructedRecipe, RecipeSolverConfig
from app.services.risk_filter import RiskFilterConfig
from app.services.steamdt_buff_live_recipe_valuation import (
    value_live_recipes_with_steamdt_buff_prices,
)
from app.services.tradeup_engine import InputItem, TradeupResult

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "steamdt_buff_live_recipe_valuation.py"
)
_SOURCE = "steamapis:buff163"
_NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
OutputSpec = tuple[str, float, float, str]


def _source_id(index: int) -> str:
    return f"{index:064x}"


def _tradeup_result(spec: OutputSpec) -> TradeupResult:
    name, probability, output_float, output_wear = spec
    return TradeupResult(
        output_market_hash_name=name,
        probability=probability,
        output_float=output_float,
        output_wear=output_wear,
        estimated_price_cny=Decimal("0"),
        expected_value_contribution=Decimal("0"),
    )


def _construction(
    output_sets: tuple[tuple[OutputSpec, ...], ...] = (
        (
            ("Output Alpha", 0.4, 0.12, "Minimal Wear"),
            ("Output Beta", 0.6, 0.24, "Field-Tested"),
        ),
    ),
) -> LiveRecipeConstructionResult:
    bindings: list[LiveCandidateBinding] = []
    recipes: list[LiveConstructedRecipe] = []

    for recipe_index, output_specs in enumerate(output_sets):
        input_items: list[InputItem] = []
        selected_ids: list[str] = []
        paint_seeds: list[int] = []
        for item_index in range(10):
            global_index = recipe_index * 10 + item_index + 1
            source_id = _source_id(global_index)
            market_hash_name = f"Input {recipe_index}-{item_index}"
            collection_name = (
                "Collection Alpha" if item_index < 5 else "Collection Beta"
            )
            price = Decimal(10 + item_index)
            actual_float = 0.10 + item_index / 1000
            paint_seed = None if item_index == 4 else 1000 + global_index
            candidate = CandidateListing(
                goods_id=f"{_SOURCE}:{source_id}",
                listing_id=f"{_SOURCE}:{source_id}",
                market_hash_name=market_hash_name,
                price_cny=price,
                float_value=actual_float,
                paint_seed=paint_seed,
                inspect_link=None,
                source=_SOURCE,
                scanned_at=_NOW,
                raw=None,
            )
            skin = SkinMetadata(
                market_hash_name=market_hash_name,
                name=None,
                weapon=None,
                rarity="Restricted",
                category=None,
                collection_name=collection_name,
                min_float=0.0,
                max_float=1.0,
                stattrak=False,
                souvenir=False,
                paint_index=None,
                raw=None,
            )
            binding = LiveCandidateBinding(
                source_offer_id=source_id,
                candidate=candidate,
                skin_metadata=skin,
            )
            bindings.append(binding)
            selected_ids.append(source_id)
            input_items.append(
                InputItem(
                    market_hash_name=market_hash_name,
                    collection_name=collection_name,
                    rarity="Restricted",
                    actual_float=actual_float,
                    min_float=0.0,
                    max_float=1.0,
                    price_cny=price,
                    stattrak=False,
                    souvenir=False,
                )
            )
            if paint_seed is not None:
                paint_seeds.append(paint_seed)

        recipes.append(
            LiveConstructedRecipe(
                recipe=ConstructedRecipe(
                    input_items=tuple(input_items),
                    tradeup_results=tuple(
                        _tradeup_result(spec) for spec in output_specs
                    ),
                    paint_seeds=tuple(paint_seeds),
                ),
                selected_source_offer_ids=tuple(selected_ids),
            )
        )

    key = LiveSolverBucketKey(
        input_rarity="Restricted",
        stattrak=False,
        souvenir=False,
    )
    binding_tuple = tuple(bindings)
    classification = LiveCandidateClassification(
        eligible=binding_tuple,
        rejected=(),
        buckets=(
            LiveSolverBucket(
                key=key,
                bindings=binding_tuple,
                affected_collections=frozenset(
                    {"Collection Alpha", "Collection Beta"}
                ),
            ),
        ),
    )
    return LiveRecipeConstructionResult(
        classification=classification,
        recipes=tuple(recipes),
    )


def _platform_quote(
    platform: str = "BUFF",
    *,
    sell_price: str | None = "100",
    bidding_price: str | None = "999999",
) -> SteamDTPlatformPrice:
    return SteamDTPlatformPrice(
        platform=platform,
        platform_item_id="opaque-provider-id",
        sell_price_cny=None if sell_price is None else Decimal(sell_price),
        sell_count=5,
        bidding_price_cny=(
            None if bidding_price is None else Decimal(bidding_price)
        ),
        bidding_count=999,
        update_time="opaque-time",
        raw={"Authorization": "Bearer not-retained"},
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


def _solver_config() -> RecipeSolverConfig:
    return RecipeSolverConfig(
        input_rarity="Restricted",
        input_count=10,
        sell_fee_rate=Decimal("0.025"),
        target_stattrak=False,
        target_souvenir=False,
    )


def _risk_config(**overrides: object) -> RiskFilterConfig:
    values: dict[str, object] = {
        "min_roi": Decimal("-1"),
        "min_expected_profit_cny": Decimal("-1000"),
        "max_worst_case_loss_pct": Decimal("2"),
        "min_profit_probability": 0.0,
        "max_input_total_cost_cny": Decimal("10000"),
    }
    values.update(overrides)
    return RiskFilterConfig(**values)  # type: ignore[arg-type]


def _run(
    construction: LiveRecipeConstructionResult,
    client: RecordingClient,
    *,
    risk_config: RiskFilterConfig | None = None,
    liquidity_score: Decimal | None = None,
) -> LiveRecipeValuationResult:
    return asyncio.run(
        value_live_recipes_with_steamdt_buff_prices(
            construction_result=construction,
            client=client,
            solver_config=_solver_config(),
            risk_config=risk_config or _risk_config(),
            liquidity_score=liquidity_score,
        )
    )


def test_public_api_is_exact_and_closed() -> None:
    assert composition_module.__all__ == (
        "value_live_recipes_with_steamdt_buff_prices",
    )
    assert inspect.iscoroutinefunction(
        value_live_recipes_with_steamdt_buff_prices
    )
    signature = inspect.signature(value_live_recipes_with_steamdt_buff_prices)
    assert list(signature.parameters) == [
        "construction_result",
        "client",
        "solver_config",
        "risk_config",
        "liquidity_score",
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )
    assert signature.parameters["liquidity_score"].default is None
    assert signature.return_annotation == "LiveRecipeValuationResult"
    assert not {
        "price_provider",
        "valuation_service",
        "provider_factory",
        "source",
        "valuation_config",
    }.intersection(signature.parameters)


def test_composition_constructs_authorities_once_and_returns_exact_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction = _construction()
    client = RecordingClient({})
    provider = object()
    service = object()
    expected = LiveRecipeValuationResult(opportunities=(), rejected=())
    provider_constructor = Mock(return_value=provider)
    service_constructor = Mock(return_value=service)
    delegate = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        composition_module,
        "SteamDTBuffPriceProvider",
        provider_constructor,
    )
    monkeypatch.setattr(
        composition_module,
        "ValuationService",
        service_constructor,
    )
    monkeypatch.setattr(composition_module, "value_live_recipes", delegate)
    solver = _solver_config()
    risk = _risk_config()
    liquidity = Decimal("0.75")

    result = asyncio.run(
        value_live_recipes_with_steamdt_buff_prices(
            construction_result=construction,
            client=client,
            solver_config=solver,
            risk_config=risk,
            liquidity_score=liquidity,
        )
    )

    assert result is expected
    provider_constructor.assert_called_once_with(client)
    service_constructor.assert_called_once_with(provider)
    delegate.assert_awaited_once_with(
        construction_result=construction,
        valuation_service=service,
        solver_config=solver,
        risk_config=risk,
        liquidity_score=liquidity,
    )


def test_complete_real_chain_uses_only_buff_sell_and_existing_math_and_risk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction = _construction()
    client = RecordingClient(
        {
            "Output Alpha": [
                _platform_quote("STEAM", sell_price="9000"),
                _platform_quote(
                    "BUFF",
                    sell_price="300.1200",
                    bidding_price="999999.99",
                ),
                _platform_quote("YOUPIN", sell_price="8000"),
            ],
            "Output Beta": [
                _platform_quote(
                    "BUFF",
                    sell_price="100.5000",
                    bidding_price="888888.88",
                ),
                _platform_quote("C5", sell_price="7000"),
            ],
        }
    )
    seen_sources: list[str] = []
    real_validator = live_valuation_module._validate_aligned_quote

    def capture_source(
        value: object,
        expected_name: str,
        result: TradeupResult,
    ) -> None:
        if type(value) is PriceQuote:
            seen_sources.append(value.source)
        real_validator(value, expected_name, result)

    monkeypatch.setattr(
        live_valuation_module,
        "_validate_aligned_quote",
        capture_source,
    )
    excluded_seed = construction.recipes[0].recipe.paint_seeds[3]

    result = _run(
        construction,
        client,
        risk_config=_risk_config(
            exclude_special_pattern_seeds={excluded_seed},
        ),
        liquidity_score=Decimal("0.80"),
    )

    assert result.rejected == ()
    assert len(result.opportunities) == 1
    opportunity = result.opportunities[0]
    assert client.calls == ["Output Alpha", "Output Beta"]
    assert seen_sources == ["steamdt:buff", "steamdt:buff"]
    assert opportunity.recipe == construction.recipes[0].recipe
    assert opportunity.selected_source_offer_ids == (
        construction.recipes[0].selected_source_offer_ids
    )
    assert opportunity.recipe.paint_seeds == construction.recipes[0].recipe.paint_seeds
    assert len(opportunity.recipe.paint_seeds) == 9
    assert [
        valued.estimated_price_cny
        for valued in opportunity.valued_tradeup_results
    ] == [Decimal("300.1200"), Decimal("100.5000")]
    assert [
        valued.expected_value_contribution
        for valued in opportunity.valued_tradeup_results
    ] == [Decimal("120.04800"), Decimal("60.30000")]
    assert opportunity.metrics.input_total_cost_cny == Decimal("145")
    assert opportunity.metrics.expected_revenue_cny == Decimal("180.34800")
    assert opportunity.metrics.expected_profit_cny == Decimal("30.83930000")
    assert opportunity.metrics.roi == Decimal("30.83930000") / Decimal("145")
    assert opportunity.metrics.worst_case_profit_cny == Decimal("-47.0125000")
    assert opportunity.metrics.best_case_profit_cny == Decimal("147.6170000")
    assert opportunity.risk_decision.passed is False
    assert "SPECIAL_PATTERN_SEED_EXCLUDED" in (
        opportunity.risk_decision.reason_codes
    )
    assert all(
        original.estimated_price_cny == 0
        and original.expected_value_contribution == 0
        for original in opportunity.recipe.tradeup_results
    )


@pytest.mark.parametrize(
    "bad_response",
    [
        [
            _platform_quote("STEAM", sell_price="9000"),
            _platform_quote("YOUPIN", sell_price="8000"),
        ],
        [
            _platform_quote("BUFF", sell_price="200"),
            _platform_quote("BUFF", sell_price="100"),
        ],
        [_platform_quote("BUFF", sell_price=None, bidding_price="999999")],
        [_platform_quote("BUFF", sell_price="0", bidding_price="999999")],
    ],
    ids=[
        "buff-missing-other-platform-high",
        "duplicate-buff",
        "buff-sell-missing-high-bid",
        "buff-sell-zero-high-bid",
    ],
)
def test_invalid_buff_price_rejects_whole_recipe_before_math_or_risk(
    bad_response: list[SteamDTPlatformPrice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction = _construction()
    client = RecordingClient(
        {
            "Output Alpha": [_platform_quote(sell_price="300")],
            "Output Beta": bad_response,
        }
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("metrics and risk must not run")

    monkeypatch.setattr(
        live_valuation_module,
        "calculate_opportunity_metrics",
        forbidden,
    )
    monkeypatch.setattr(
        live_valuation_module,
        "evaluate_opportunity",
        forbidden,
    )

    result = _run(construction, client)

    assert result.opportunities == ()
    assert len(result.rejected) == 1
    assert result.rejected[0].reason_code is (
        LiveRecipeValuationRejectionReason.PRICE_PROVIDER_ERROR
    )
    assert result.rejected[0].selected_source_offer_ids == (
        construction.recipes[0].selected_source_offer_ids
    )
    assert client.calls == ["Output Alpha", "Output Beta"]
    assert "Authorization" not in repr(result)
    assert "999999" not in repr(result)


def test_ordinary_client_failure_is_redacted_whole_recipe_rejection() -> None:
    construction = _construction()
    secret = "Bearer secret-token purchaseLink=https://private.invalid"
    client = RecordingClient(
        {
            "Output Alpha": RuntimeError(
                f"Authorization: {secret}; raw SteamDT response"
            ),
            "Output Beta": [_platform_quote(sell_price="100")],
        }
    )

    result = _run(construction, client)

    assert result.opportunities == ()
    assert result.rejected[0].reason_code is (
        LiveRecipeValuationRejectionReason.PRICE_PROVIDER_ERROR
    )
    assert client.calls == ["Output Alpha", "Output Beta"]
    rendered = repr(result)
    assert secret not in rendered
    assert "Authorization" not in rendered
    assert "raw SteamDT response" not in rendered
    assert "RuntimeError" not in rendered


def test_shared_outputs_are_deterministic_and_failed_recipe_does_not_contaminate_later() -> None:
    construction = _construction(
        (
            (
                ("Output Alpha", 0.4, 0.12, "Minimal Wear"),
                ("Output Beta", 0.6, 0.24, "Field-Tested"),
            ),
            (
                ("Output Alpha", 0.25, 0.13, "Minimal Wear"),
                ("Output Gamma", 0.75, 0.31, "Field-Tested"),
            ),
        )
    )
    client = RecordingClient(
        {
            "Output Alpha": [_platform_quote(sell_price="300")],
            "Output Beta": [_platform_quote("STEAM", sell_price="9999")],
            "Output Gamma": [_platform_quote(sell_price="125")],
        }
    )

    result = _run(construction, client)

    assert client.calls == [
        "Output Alpha",
        "Output Beta",
        "Output Alpha",
        "Output Gamma",
    ]
    assert len(result.rejected) == 1
    assert len(result.opportunities) == 1
    assert result.rejected[0].reason_code is (
        LiveRecipeValuationRejectionReason.PRICE_PROVIDER_ERROR
    )
    assert result.rejected[0].selected_source_offer_ids == (
        construction.recipes[0].selected_source_offer_ids
    )
    opportunity = result.opportunities[0]
    assert opportunity.selected_source_offer_ids == (
        construction.recipes[1].selected_source_offer_ids
    )
    assert [
        valued.output_market_hash_name
        for valued in opportunity.valued_tradeup_results
    ] == ["Output Alpha", "Output Gamma"]
    assert [
        valued.estimated_price_cny
        for valued in opportunity.valued_tradeup_results
    ] == [Decimal("300"), Decimal("125")]
    assert set(result.rejected[0].selected_source_offer_ids).isdisjoint(
        opportunity.selected_source_offer_ids
    )


def test_provider_dedup_does_not_legitimize_duplicate_recipe_geometry() -> None:
    construction = _construction(
        (
            (
                ("Output Alpha", 0.4, 0.12, "Minimal Wear"),
                ("Output Alpha", 0.6, 0.12, "Minimal Wear"),
            ),
        )
    )
    client = RecordingClient(
        {"Output Alpha": [_platform_quote(sell_price="300")]}
    )

    result = _run(construction, client)

    assert client.calls == ["Output Alpha"]
    assert result.opportunities == ()
    assert result.rejected[0].reason_code is (
        LiveRecipeValuationRejectionReason.INVALID_VALUATION_RESULT
    )


@pytest.mark.parametrize(
    "failure",
    [
        MemoryError("memory"),
        asyncio.CancelledError("cancelled"),
        KeyboardInterrupt("keyboard"),
        SystemExit(9),
    ],
)
def test_process_control_failure_propagates_by_identity_and_stops_later_calls(
    failure: BaseException,
) -> None:
    construction = _construction(
        (
            (
                ("Output Alpha", 0.2, 0.12, "Minimal Wear"),
                ("Output Beta", 0.3, 0.24, "Field-Tested"),
                ("Output Gamma", 0.5, 0.31, "Field-Tested"),
            ),
        )
    )
    client = RecordingClient(
        {
            "Output Alpha": [_platform_quote(sell_price="300")],
            "Output Beta": failure,
            "Output Gamma": [_platform_quote(sell_price="125")],
        }
    )

    with pytest.raises(type(failure)) as caught:
        _run(construction, client)

    assert caught.value is failure
    assert client.calls == ["Output Alpha", "Output Beta"]


def test_empty_construction_makes_no_client_calls() -> None:
    populated = _construction()
    construction = LiveRecipeConstructionResult(
        classification=populated.classification,
        recipes=(),
    )
    client = RecordingClient({})

    result = _run(construction, client)

    assert result == LiveRecipeValuationResult(opportunities=(), rejected=())
    assert client.calls == []


def test_production_module_has_only_thin_offline_composition_boundaries() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)

    assert imports == {
        "__future__",
        "decimal",
        "app.services.live_recipe_construction",
        "app.services.live_recipe_valuation",
        "app.services.recipe_solver",
        "app.services.risk_filter",
        "app.services.steamdt_buff_price_provider",
        "app.services.steamdt_market_data",
        "app.services.valuation_service",
    }
    constants = {
        node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
    }
    assert "BUFF" not in constants
    assert "steamdt:buff" not in constants
    assert not any(isinstance(node, (ast.For, ast.AsyncFor, ast.While)) for node in ast.walk(tree))

    folded = source.casefold()
    prohibited_markers = {
        "steamapis",
        "steamdt_client",
        "httpx",
        "requests",
        "websocket",
        "redis",
        "cache",
        "limiter",
        "scheduler",
        "fastapi",
        "discord",
        "database",
        "create_task",
        "taskgroup",
        "gather",
        "sleep(",
        "get_price(",
        "get_prices(",
        "get_steamdt_market_data(",
        "select_buff_output_price(",
        "calculate_opportunity_metrics(",
        "evaluate_opportunity(",
        "construct_live_recipes(",
        "purchase",
        "inspect_link",
        "auto_buy",
        "aclose(",
        "os.environ",
    }
    assert not any(marker in folded for marker in prohibited_markers)


def test_protected_authorities_do_not_reverse_import_composition() -> None:
    root = Path(__file__).resolve().parents[1]
    protected_paths = [
        root / "app" / "clients" / "steamdt_client.py",
        root / "app" / "services" / "steamdt_market_data.py",
        root / "app" / "services" / "steamdt_buff_price_policy.py",
        root / "app" / "services" / "steamdt_buff_price_provider.py",
        root / "app" / "services" / "price_provider.py",
        root / "app" / "services" / "valuation_service.py",
        root / "app" / "services" / "live_recipe_valuation.py",
        root / "app" / "services" / "live_recipe_construction.py",
        root / "app" / "services" / "recipe_solver.py",
    ]

    for path in protected_paths:
        assert "steamdt_buff_live_recipe_valuation" not in path.read_text(
            encoding="utf-8"
        )


def test_fake_client_has_no_runtime_or_network_surface() -> None:
    construction = _construction()
    client = RecordingClient(
        {
            "Output Alpha": [_platform_quote(sell_price="300")],
            "Output Beta": [_platform_quote(sell_price="100")],
        }
    )

    result = _run(construction, client)

    assert len(result.opportunities) == 1
    assert set(vars(client)) == {"responses", "calls"}
    assert not hasattr(client, "api_key")
    assert not hasattr(client, "http_client")
    assert not hasattr(client, "aclose")
    assert not hasattr(client, "get_price_batch")
