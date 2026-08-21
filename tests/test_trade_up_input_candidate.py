from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from decimal import Decimal
from pathlib import Path

import pytest

import app.services.trade_up_input_candidate as candidate_module
from app.services.trade_up_input_candidate import (
    TradeUpInputCandidate,
    TradeUpInputCandidateValidationError,
)


def _valid(**overrides: object) -> TradeUpInputCandidate:
    values: dict[str, object] = {
        "listing_id": "listing-private-1",
        "goods_id": "goods-synthetic-9",
        "market_hash_name": None,
        "price_cny": Decimal("12.3400"),
        "paintwear": Decimal("0.123000"),
        "asset_id": "asset-private-1",
        "source": "buff",
    }
    values.update(overrides)
    return TradeUpInputCandidate(**values)  # type: ignore[arg-type]


def test_public_api_is_exact() -> None:
    assert candidate_module.__all__ == (
        "TradeUpInputCandidateValidationError",
        "TradeUpInputCandidate",
    )
    assert [field.name for field in fields(TradeUpInputCandidate)] == [
        "listing_id",
        "goods_id",
        "market_hash_name",
        "price_cny",
        "paintwear",
        "asset_id",
        "source",
    ]


def test_unresolved_identity_path_is_default() -> None:
    candidate = _valid()
    assert candidate.market_hash_name is None
    assert candidate.source == "buff"


def test_explicit_market_hash_name_is_preserved_without_modification() -> None:
    name = "Synthetic | Rifle (Factory New)"
    candidate = _valid(market_hash_name=name)
    assert candidate.market_hash_name == name


def test_frozen_and_repr_suppressed() -> None:
    candidate = _valid()
    with pytest.raises(FrozenInstanceError):
        candidate.price_cny = Decimal("1")  # type: ignore[misc]
    rendered = repr(candidate)
    for forbidden in (
        "listing-private-1",
        "goods-synthetic-9",
        "12.3400",
        "0.123000",
        "asset-private-1",
    ):
        assert forbidden not in rendered


def test_decimal_precision_is_preserved() -> None:
    candidate = _valid(
        price_cny=Decimal("123.450000"),
        paintwear=Decimal("0.001200"),
    )
    assert candidate.price_cny == Decimal("123.450000")
    assert candidate.paintwear == Decimal("0.001200")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("listing_id", "  padded"),
        ("listing_id", "padded  "),
        ("listing_id", ""),
        ("listing_id", "   "),
        ("listing_id", None),
        ("listing_id", 1),
        ("listing_id", True),
        ("goods_id", " padded"),
        ("goods_id", "padded "),
        ("goods_id", ""),
        ("goods_id", None),
        ("goods_id", 1),
        ("asset_id", " "),
        ("asset_id", "padded "),
        ("asset_id", None),
        ("asset_id", True),
        ("market_hash_name", " padded"),
        ("market_hash_name", "padded "),
        ("market_hash_name", ""),
        ("market_hash_name", 1),
        ("source", ""),
        ("source", "  "),
        ("source", None),
    ],
)
def test_invalid_string_fields_fail_with_fixed_redacted_field(
    field: str,
    value: object,
) -> None:
    if field == "market_hash_name" and value is None:
        candidate = _valid(market_hash_name=None)
        assert candidate.market_hash_name is None
        return
    with pytest.raises(TradeUpInputCandidateValidationError) as captured:
        _valid(**{field: value})
    assert captured.value.field == field


@pytest.mark.parametrize(
    ("price", "wear"),
    [
        (Decimal("0"), Decimal("0.1")),
        (Decimal("-1"), Decimal("0.1")),
        (Decimal("NaN"), Decimal("0.1")),
        (Decimal("Infinity"), Decimal("0.1")),
        (Decimal("1"), Decimal("-0.01")),
        (Decimal("1"), Decimal("1.01")),
        (Decimal("1"), Decimal("NaN")),
        (Decimal("1"), Decimal("Infinity")),
        ("not-a-decimal", Decimal("0.1")),
        (Decimal("1"), "not-a-decimal"),
    ],
)
def test_invalid_price_or_paintwear_fails(
    price: object,
    wear: object,
) -> None:
    with pytest.raises(TradeUpInputCandidateValidationError) as captured:
        _valid(price_cny=price, paintwear=wear)  # type: ignore[arg-type]
    assert captured.value.field in {"price_cny", "paintwear"}


def test_error_does_not_expose_rejected_value() -> None:
    secret = "personal-secret-marker-9981"
    with pytest.raises(TradeUpInputCandidateValidationError) as captured:
        _valid(price_cny=secret)  # type: ignore[arg-type]
    assert secret not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_paintwear_boundary_values_are_accepted() -> None:
    assert _valid(paintwear=Decimal("0")).paintwear == Decimal("0")
    assert _valid(paintwear=Decimal("1")).paintwear == Decimal("1")


def test_unresolved_identity_is_observable_without_guess() -> None:
    candidate = _valid()
    assert candidate.market_hash_name is None
    candidate_named = _valid(market_hash_name="Unknown AK Variant")
    assert candidate_named.market_hash_name == "Unknown AK Variant"
    for forbidden in (
        "synthetic",
        "fixture",
        "guess",
        "inferred",
        "derived",
        "wear",
        "stattrak",
        "souvenir",
    ):
        assert forbidden not in (
            candidate.market_hash_name or ""
        ).casefold()


def test_module_has_no_external_or_engine_dependencies() -> None:
    source = (
        Path(candidate_module.__file__).read_text(encoding="utf-8")
    ).casefold()
    for forbidden in (
        "buff_listing",
        "buff_listing_provider",
        "buff_item_identity",
        "recipe_solver",
        "tradeup_engine",
        "ev_service",
        "risk_filter",
        "valuation_service",
        "live_recipe_valuation",
        "steamdt",
        "steamapis",
        "resolver",
        "metadata",
        "scanner",
        "purchase",
        "json",
        "os.environ",
        "open(",
    ):
        assert forbidden not in source
