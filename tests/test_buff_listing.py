import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import get_type_hints

import pytest

from app.services.buff_listing import (
    BuffListingObservation,
    BuffListingSource,
    BuffListingValidationError,
    BuffTradableCandidate,
    normalize_buff_listing,
)

OBSERVED_AT = datetime(2026, 7, 23, 12, 30, tzinfo=UTC)


def _observation(**changes: object) -> BuffListingObservation:
    values: dict[str, object] = {
        "listing_id": " listing-1 ",
        "goods_id": " goods-1 ",
        "market_hash_name": " AK-47 | Redline (Field-Tested) ",
        "price_cny": Decimal("123.4500"),
        "quantity": 2,
        "float_value": Decimal("0.173400"),
        "wear_name": " Field-Tested ",
        "paint_seed": 42,
        "sticker_metadata": [("slot", "0"), ("name", "Sticker | Test")],
        "observed_at": OBSERVED_AT,
    }
    values.update(changes)
    return BuffListingObservation(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["listing_id", "market_hash_name"])
@pytest.mark.parametrize("value", ["", "   ", None, 7])
def test_required_listing_identity_rejects_invalid_values(
    field: str,
    value: object,
) -> None:
    with pytest.raises(BuffListingValidationError) as exc_info:
        _observation(**{field: value})

    assert exc_info.value.field == field
    assert str(exc_info.value) == f"invalid BUFF listing field: {field}"


@pytest.mark.parametrize(
    "value",
    [Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity"), 1.25, "1.25"],
)
def test_price_rejects_negative_nonfinite_and_non_decimal_values(value: object) -> None:
    with pytest.raises(BuffListingValidationError) as exc_info:
        _observation(price_cny=value)

    assert exc_info.value.field == "price_cny"


@pytest.mark.parametrize("value", [True, False, -1, 1.0, "1", None])
def test_quantity_requires_an_exact_nonnegative_int(value: object) -> None:
    with pytest.raises(BuffListingValidationError) as exc_info:
        _observation(quantity=value)

    assert exc_info.value.field == "quantity"


def test_zero_price_and_quantity_are_valid_contract_values() -> None:
    observation = _observation(price_cny=Decimal(0), quantity=0)

    candidate = normalize_buff_listing(observation)

    assert candidate.buy_price_cny == Decimal(0)
    assert candidate.available_quantity == 0


@pytest.mark.parametrize(
    "value",
    [
        Decimal("-0.0001"),
        Decimal("1.0001"),
        Decimal("NaN"),
        Decimal("-Infinity"),
        0.5,
        "0.5",
    ],
)
def test_float_value_rejects_out_of_range_nonfinite_and_non_decimal_values(
    value: object,
) -> None:
    with pytest.raises(BuffListingValidationError) as exc_info:
        _observation(float_value=value)

    assert exc_info.value.field == "float_value"


@pytest.mark.parametrize("value", [None, Decimal(0), Decimal(1)])
def test_optional_float_accepts_none_and_closed_interval_boundaries(
    value: Decimal | None,
) -> None:
    assert _observation(float_value=value).float_value == value


@pytest.mark.parametrize("value", [True, False, -1, 1.0, "1"])
def test_paint_seed_requires_an_optional_exact_nonnegative_int(value: object) -> None:
    with pytest.raises(BuffListingValidationError) as exc_info:
        _observation(paint_seed=value)

    assert exc_info.value.field == "paint_seed"


def test_goods_id_defaults_to_none_for_legacy_domain_values() -> None:
    observation = _observation(goods_id=None)
    candidate = normalize_buff_listing(observation)

    assert observation.goods_id is None
    assert candidate.goods_id is None


@pytest.mark.parametrize("model", [BuffListingObservation, BuffTradableCandidate])
@pytest.mark.parametrize("value", ["", "   ", 7, True, b"goods-1"])
def test_goods_id_rejects_blank_and_non_string_values(
    model: type[BuffListingObservation] | type[BuffTradableCandidate],
    value: object,
) -> None:
    values = {
        "goods_id": value,
        "listing_id": "listing-1",
        "market_hash_name": "Example Item",
        "float_value": Decimal("0.1"),
        "wear_name": None,
        "paint_seed": None,
        "observed_at": OBSERVED_AT,
    }
    if model is BuffListingObservation:
        values.update(price_cny=Decimal("1"), quantity=1)
    else:
        values.update(buy_price_cny=Decimal("1"), available_quantity=1)

    with pytest.raises(BuffListingValidationError) as exc_info:
        model(**values)  # type: ignore[arg-type]

    assert exc_info.value.field == "goods_id"
    assert str(exc_info.value) == "invalid BUFF listing field: goods_id"


def test_goods_id_is_detached_from_hostile_string_subclass() -> None:
    class HostileGoodsId(str):
        def strip(self) -> object:
            return 7

    observation = _observation(goods_id=HostileGoodsId(" goods-1 "))
    candidate = normalize_buff_listing(observation)

    assert observation.goods_id == "goods-1"
    assert type(observation.goods_id) is str
    assert candidate.goods_id == "goods-1"
    assert type(candidate.goods_id) is str


def test_strings_and_goods_id_are_stripped_and_blank_wear_becomes_none() -> None:
    observation = _observation(wear_name="   ")

    assert observation.listing_id == "listing-1"
    assert observation.goods_id == "goods-1"
    assert observation.market_hash_name == "AK-47 | Redline (Field-Tested)"
    assert observation.wear_name is None


def test_observed_at_requires_an_aware_datetime() -> None:
    with pytest.raises(BuffListingValidationError) as exc_info:
        _observation(observed_at=datetime(2026, 7, 23, 12, 30))

    assert exc_info.value.field == "observed_at"


def test_observed_at_normalizes_to_utc() -> None:
    source_time = datetime(
        2026,
        7,
        23,
        20,
        30,
        tzinfo=timezone(timedelta(hours=8)),
    )

    observation = _observation(observed_at=source_time)

    assert observation.observed_at == OBSERVED_AT
    assert observation.observed_at.tzinfo is UTC


def test_sticker_metadata_is_normalized_and_detached_from_mutable_input() -> None:
    metadata = [[" slot ", " 0 "], [" name ", " Sticker | Test "]]

    observation = _observation(sticker_metadata=metadata)
    metadata[0][1] = "changed"
    metadata.clear()

    assert observation.sticker_metadata == (
        ("slot", "0"),
        ("name", "Sticker | Test"),
    )


@pytest.mark.parametrize(
    "value",
    ["secret", b"secret", [("only-one",)], [("", "value")], [("key", 7)]],
)
def test_invalid_sticker_metadata_fails_with_a_safe_field_error(value: object) -> None:
    with pytest.raises(BuffListingValidationError) as exc_info:
        _observation(sticker_metadata=value)

    assert exc_info.value.field == "sticker_metadata"
    assert repr(value) not in str(exc_info.value)


def test_normalizer_produces_the_solver_candidate_contract() -> None:
    observation = _observation()

    candidate = normalize_buff_listing(observation)

    assert candidate == BuffTradableCandidate(
        listing_id="listing-1",
        goods_id="goods-1",
        market_hash_name="AK-47 | Redline (Field-Tested)",
        buy_price_cny=Decimal("123.4500"),
        available_quantity=2,
        float_value=Decimal("0.173400"),
        wear_name="Field-Tested",
        paint_seed=42,
        observed_at=OBSERVED_AT,
    )


def test_decimal_precision_is_preserved_without_float_conversion() -> None:
    price = Decimal("123.4500000000000000000000001")
    float_value = Decimal("0.1234567890123456789012345678")

    candidate = normalize_buff_listing(
        _observation(price_cny=price, float_value=float_value)
    )

    assert candidate.buy_price_cny is price
    assert candidate.float_value is float_value
    assert str(candidate.buy_price_cny) == "123.4500000000000000000000001"
    assert str(candidate.float_value) == "0.1234567890123456789012345678"


def test_candidate_is_detached_and_carries_no_sticker_or_raw_payload() -> None:
    metadata = [("secret-shaped", "not-carried")]
    observation = _observation(sticker_metadata=metadata)

    candidate = normalize_buff_listing(observation)
    metadata.clear()

    candidate_fields = {field.name for field in fields(candidate)}
    assert candidate_fields == {
        "listing_id",
        "goods_id",
        "market_hash_name",
        "buy_price_cny",
        "available_quantity",
        "float_value",
        "wear_name",
        "paint_seed",
        "observed_at",
    }
    assert not hasattr(candidate, "sticker_metadata")
    assert not hasattr(candidate, "raw")
    assert not hasattr(candidate, "raw_payload")


def test_observation_and_candidate_are_immutable() -> None:
    observation = _observation()
    candidate = normalize_buff_listing(observation)

    with pytest.raises(FrozenInstanceError):
        observation.quantity = 4  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        candidate.available_quantity = 4  # type: ignore[misc]


def test_normalizer_revalidates_a_tampered_public_observation() -> None:
    observation = _observation()
    object.__setattr__(observation, "quantity", True)

    with pytest.raises(BuffListingValidationError) as exc_info:
        normalize_buff_listing(observation)

    assert exc_info.value.field == "quantity"


def test_normalizer_revalidates_a_tampered_goods_id() -> None:
    observation = _observation()
    object.__setattr__(observation, "goods_id", "   ")

    with pytest.raises(BuffListingValidationError) as exc_info:
        normalize_buff_listing(observation)

    assert exc_info.value.field == "goods_id"


def test_normalizer_rejects_non_observation_without_exposing_repr() -> None:
    class SecretObject:
        def __repr__(self) -> str:
            return "Authorization: Bearer dummy-secret"

    with pytest.raises(BuffListingValidationError) as exc_info:
        normalize_buff_listing(SecretObject())  # type: ignore[arg-type]

    assert exc_info.value.field == "observation"
    assert "dummy-secret" not in str(exc_info.value)


def test_models_disable_repr_to_avoid_listing_data_disclosure() -> None:
    observation = _observation(
        listing_id="cookie=dummy-secret",
        goods_id="credential-dummy-secret",
        market_hash_name="token=dummy-secret",
    )
    candidate = normalize_buff_listing(observation)

    assert "dummy-secret" not in repr(observation)
    assert "dummy-secret" not in repr(candidate)
    assert repr(observation).startswith("<app.services.buff_listing.")
    assert repr(candidate).startswith("<app.services.buff_listing.")


def test_validation_never_includes_hostile_string_or_exception_text() -> None:
    class HostileString(str):
        def strip(self) -> str:
            raise RuntimeError("password=dummy-secret")

    with pytest.raises(BuffListingValidationError) as exc_info:
        _observation(listing_id=HostileString("token=dummy-secret"))

    assert str(exc_info.value) == "invalid BUFF listing field: listing_id"
    assert "dummy-secret" not in str(exc_info.value)


def test_source_protocol_exposes_only_the_observation_fetch_contract() -> None:
    annotations = get_type_hints(BuffListingSource.fetch_listings)

    assert set(annotations) == {"market_hash_name", "return"}
    assert annotations["market_hash_name"] is str
    assert annotations["return"] == list[BuffListingObservation] or str(
        annotations["return"]
    ) == "collections.abc.Sequence[app.services.buff_listing.BuffListingObservation]"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module.casefold())
    return modules


def test_buff_listing_module_has_no_external_or_runtime_wiring_imports() -> None:
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / "app" / "services" / "buff_listing.py"
    imports = _imported_modules(module_path)
    forbidden = {
        "app.clients",
        "app.config",
        "fastapi",
        "httpx",
        "redis",
        "steamdt",
        "pipeline",
        "scheduler",
        "provider",
        "valuation",
    }

    assert not any(
        fragment in imported
        for imported in imports
        for fragment in forbidden
    )


def test_runtime_modules_do_not_reverse_import_buff_listing() -> None:
    project_root = Path(__file__).resolve().parents[1]
    runtime_paths = [
        project_root / "app" / "main.py",
        project_root / "app" / "config.py",
        project_root / "app" / "services" / "price_provider.py",
        project_root / "app" / "services" / "valuation_service.py",
        project_root / "app" / "services" / "pipeline_service.py",
        project_root / "app" / "jobs" / "scheduler.py",
    ]

    for path in runtime_paths:
        assert "app.services.buff_listing" not in _imported_modules(path)
