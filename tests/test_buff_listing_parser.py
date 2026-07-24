import ast
import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import get_type_hints

import pytest

from app.services.buff_listing import normalize_buff_listing
from app.services.buff_listing_parser import (
    BUFF_LISTING_FIXTURE_SCHEMA_VERSION,
    BUFF_LISTING_FIXTURE_SOURCE,
    BuffListingParseCause,
    BuffListingParseError,
    load_buff_listing_fixture,
    parse_buff_listing_fixture,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "buff" / "listings_v1.json"
)
OBSERVED_AT = datetime(2026, 7, 23, 12, tzinfo=UTC)


def _listing(**changes: object) -> dict[str, object]:
    listing: dict[str, object] = {
        "listing_id": " listing-001 ",
        "market_hash_name": " AK-47 | Redline (Field-Tested) ",
        "price_cny": "123.4500",
        "quantity": 1,
        "float_value": "0.234500",
        "wear_name": " Field-Tested ",
        "paint_seed": 321,
        "sticker_metadata": [
            {"key": " slot_0 ", "value": " Example Sticker "},
        ],
    }
    listing.update(changes)
    return listing


def _payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "source": "buff",
        "observed_at": "2026-07-23T12:00:00Z",
        "listings": [_listing()],
    }
    payload.update(changes)
    return payload


def _assert_parse_error(
    exc_info: pytest.ExceptionInfo[BuffListingParseError],
    *,
    field: str,
    cause: BuffListingParseCause = BuffListingParseCause.FIXTURE_SCHEMA,
    record_index: int | None = None,
) -> None:
    error = exc_info.value
    assert str(error) == "invalid BUFF listing fixture"
    assert error.field == field
    assert error.cause is cause
    assert error.record_index == record_index


def test_loads_project_owned_v1_fixture() -> None:
    observations = load_buff_listing_fixture(FIXTURE_PATH)

    assert len(observations) == 2
    assert observations[0].listing_id == "listing-001"
    assert observations[0].observed_at == OBSERVED_AT


def test_mapping_parser_and_file_loader_are_equivalent() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert parse_buff_listing_fixture(payload) == load_buff_listing_fixture(
        FIXTURE_PATH
    )


def test_listing_order_and_duplicates_are_preserved() -> None:
    payload = _payload(
        listings=[
            _listing(listing_id="duplicate", price_cny="1"),
            _listing(listing_id="middle", price_cny="2"),
            _listing(listing_id="duplicate", price_cny="3"),
        ]
    )

    observations = parse_buff_listing_fixture(payload)

    assert [item.listing_id for item in observations] == [
        "duplicate",
        "middle",
        "duplicate",
    ]
    assert [item.price_cny for item in observations] == [
        Decimal("1"),
        Decimal("2"),
        Decimal("3"),
    ]


def test_decimal_precision_and_trailing_zeroes_are_preserved() -> None:
    price = "123.4500000000000000000000001"
    float_value = "0.1234567890123456789012345678"

    observation = parse_buff_listing_fixture(
        _payload(listings=[_listing(price_cny=price, float_value=float_value)])
    )[0]

    assert str(observation.price_cny) == price
    assert str(observation.float_value) == float_value


def test_quantity_zero_and_blank_wear_are_preserved_by_contract() -> None:
    observation = parse_buff_listing_fixture(
        _payload(listings=[_listing(quantity=0, wear_name="   ")])
    )[0]

    assert observation.quantity == 0
    assert observation.wear_name is None


def test_offset_timestamp_is_normalized_to_utc() -> None:
    observation = parse_buff_listing_fixture(
        _payload(observed_at="2026-07-23T20:00:00+08:00")
    )[0]

    assert observation.observed_at == OBSERVED_AT
    assert observation.observed_at.tzinfo is UTC


def test_sticker_order_and_duplicates_are_preserved_as_pairs() -> None:
    stickers = [
        {"key": "slot_0", "value": "Example A"},
        {"key": "slot_1", "value": "Example B"},
        {"key": "slot_0", "value": "Example A"},
    ]

    observation = parse_buff_listing_fixture(
        _payload(listings=[_listing(sticker_metadata=stickers)])
    )[0]

    assert observation.sticker_metadata == (
        ("slot_0", "Example A"),
        ("slot_1", "Example B"),
        ("slot_0", "Example A"),
    )


def test_parsed_observation_normalizes_to_candidate() -> None:
    observation = parse_buff_listing_fixture(_payload())[0]

    candidate = normalize_buff_listing(observation)

    assert candidate.listing_id == "listing-001"
    assert candidate.buy_price_cny == Decimal("123.4500")
    assert candidate.available_quantity == 1


def test_empty_listing_array_returns_empty_tuple() -> None:
    assert parse_buff_listing_fixture(_payload(listings=[])) == ()


@pytest.mark.parametrize("value", [2, 0, -1, True, False, "1", None])
def test_schema_version_requires_exact_integer_one(value: object) -> None:
    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(_payload(schema_version=value))

    _assert_parse_error(exc_info, field="schema_version")


@pytest.mark.parametrize("value", ["BUFF", " buff", "buff ", "", None, 1])
def test_source_requires_exact_canonical_buff(value: object) -> None:
    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(_payload(source=value))

    _assert_parse_error(exc_info, field="source")


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        (lambda payload: payload.pop("source"), "payload"),
        (lambda payload: payload.__setitem__("extra", True), "payload"),
    ],
)
def test_top_level_missing_and_unknown_fields_fail_closed(
    mutation: object,
    field: str,
) -> None:
    payload = _payload()
    mutation(payload)  # type: ignore[operator]

    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(payload)

    _assert_parse_error(exc_info, field=field)


@pytest.mark.parametrize("value", [None, {}, "records", b"records", 1, True])
def test_listings_requires_a_non_text_sequence(value: object) -> None:
    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(_payload(listings=value))

    _assert_parse_error(exc_info, field="listings")


def test_record_requires_a_mapping() -> None:
    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(_payload(listings=[_listing(), "secret-record"]))

    _assert_parse_error(exc_info, field="listings", record_index=1)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda listing: listing.pop("listing_id"),
        lambda listing: listing.__setitem__("unknown", "value"),
    ],
)
def test_record_missing_and_unknown_fields_fail_closed(mutation: object) -> None:
    listing = _listing()
    mutation(listing)  # type: ignore[operator]

    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(_payload(listings=[listing]))

    _assert_parse_error(exc_info, field="listings", record_index=0)


@pytest.mark.parametrize("value", [123.45, 123, True, None, "", " 1.0 "])
def test_price_requires_a_nonblank_decimal_string(value: object) -> None:
    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(_payload(listings=[_listing(price_cny=value)]))

    _assert_parse_error(exc_info, field="price_cny", record_index=0)


@pytest.mark.parametrize("value", ["not-decimal", "NaN", "Infinity", "-0.01"])
def test_invalid_price_decimal_fails_closed(value: str) -> None:
    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(_payload(listings=[_listing(price_cny=value)]))

    assert exc_info.value.field == "price_cny"
    assert exc_info.value.record_index == 0
    assert exc_info.value.cause in {
        BuffListingParseCause.FIXTURE_SCHEMA,
        BuffListingParseCause.DOMAIN_VALIDATION,
    }


@pytest.mark.parametrize("value", [0.5, 1, True, {}, [], " 0.5 "])
def test_float_value_requires_null_or_decimal_string(value: object) -> None:
    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(_payload(listings=[_listing(float_value=value)]))

    _assert_parse_error(exc_info, field="float_value", record_index=0)


@pytest.mark.parametrize("value", [True, False, -1, 1.0, "1", None])
def test_quantity_requires_an_exact_nonnegative_integer(value: object) -> None:
    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(_payload(listings=[_listing(quantity=value)]))

    _assert_parse_error(exc_info, field="quantity", record_index=0)


@pytest.mark.parametrize("value", [True, False, -1, 1.0, "1", {}])
def test_paint_seed_requires_null_or_exact_nonnegative_integer(value: object) -> None:
    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(_payload(listings=[_listing(paint_seed=value)]))

    _assert_parse_error(exc_info, field="paint_seed", record_index=0)


@pytest.mark.parametrize(
    "value",
    [
        "2026-07-23T12:00:00",
        "not-a-time",
        "",
        " 2026-07-23T12:00:00Z ",
        None,
        1,
    ],
)
def test_timestamp_requires_nonblank_aware_iso8601_string(value: object) -> None:
    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(_payload(observed_at=value))

    _assert_parse_error(exc_info, field="observed_at")


@pytest.mark.parametrize("value", ["stickers", {}, (), ["entry"]])
def test_sticker_metadata_requires_null_or_json_array_of_mappings(
    value: object,
) -> None:
    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(
            _payload(listings=[_listing(sticker_metadata=value)])
        )

    _assert_parse_error(exc_info, field="sticker_metadata", record_index=0)


@pytest.mark.parametrize(
    "entry",
    [
        {"key": "slot"},
        {"key": "slot", "value": "name", "extra": "secret"},
        {"key": 1, "value": "name"},
        {"key": "slot", "value": 1},
    ],
)
def test_sticker_entry_requires_exact_string_key_and_value(
    entry: dict[str, object],
) -> None:
    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(
            _payload(listings=[_listing(sticker_metadata=[entry])])
        )

    _assert_parse_error(exc_info, field="sticker_metadata", record_index=0)


def test_malformed_later_record_returns_no_partial_tuple() -> None:
    payload = _payload(
        listings=[
            _listing(listing_id="valid-first"),
            _listing(listing_id="invalid-second", price_cny=1.0),
        ]
    )

    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(payload)

    _assert_parse_error(exc_info, field="price_cny", record_index=1)


def test_file_loader_classifies_malformed_json_without_leaking_text(
    tmp_path: Path,
) -> None:
    path = tmp_path / "Cookie=dummy-secret.json"
    path.write_text('{"Authorization":"Bearer dummy-secret"', encoding="utf-8")

    with pytest.raises(BuffListingParseError) as exc_info:
        load_buff_listing_fixture(path)

    _assert_parse_error(
        exc_info,
        field="json",
        cause=BuffListingParseCause.JSON_DECODE,
    )
    assert "dummy-secret" not in str(exc_info.value)
    assert "dummy-secret" not in repr(exc_info.value)


def test_file_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(
        '{"schema_version":1,"schema_version":1,"source":"buff",'
        '"observed_at":"2026-07-23T12:00:00Z","listings":[]}',
        encoding="utf-8",
    )

    with pytest.raises(BuffListingParseError) as exc_info:
        load_buff_listing_fixture(path)

    _assert_parse_error(
        exc_info,
        field="json",
        cause=BuffListingParseCause.JSON_DECODE,
    )


def test_file_read_error_is_safe_and_distinct(tmp_path: Path) -> None:
    path = tmp_path / "password=dummy-secret.json"

    with pytest.raises(BuffListingParseError) as exc_info:
        load_buff_listing_fixture(path)

    _assert_parse_error(
        exc_info,
        field="path",
        cause=BuffListingParseCause.FILE_READ,
    )
    assert "dummy-secret" not in repr(exc_info.value)


def test_domain_validation_error_is_classified_and_redacted() -> None:
    with pytest.raises(BuffListingParseError) as exc_info:
        parse_buff_listing_fixture(
            _payload(
                listings=[
                    _listing(
                        listing_id="Cookie=dummy-secret",
                        price_cny="NaN",
                    )
                ]
            )
        )

    _assert_parse_error(
        exc_info,
        field="price_cny",
        cause=BuffListingParseCause.DOMAIN_VALIDATION,
        record_index=0,
    )
    rendered = str(exc_info.value) + repr(exc_info.value)
    assert "dummy-secret" not in rendered
    assert "Cookie" not in rendered
    assert "NaN" not in rendered


def test_input_mutation_does_not_change_parsed_observation() -> None:
    sticker = {"key": "slot_0", "value": "Example"}
    listing = _listing(sticker_metadata=[sticker])
    listings = [listing]
    payload = _payload(listings=listings)

    observations = parse_buff_listing_fixture(payload)
    sticker["value"] = "changed"
    listing["listing_id"] = "changed"
    listings.clear()
    payload.clear()

    assert observations[0].listing_id == "listing-001"
    assert observations[0].sticker_metadata == (("slot_0", "Example"),)


def test_raw_payload_is_not_retained_on_observation() -> None:
    observation = parse_buff_listing_fixture(_payload())[0]

    assert not hasattr(observation, "raw")
    assert not hasattr(observation, "raw_payload")
    assert not hasattr(observation, "payload")


def test_memory_error_from_mapping_is_not_wrapped() -> None:
    class ExhaustedMapping(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            raise MemoryError("password=dummy-secret")

        def __iter__(self) -> Iterator[str]:
            raise MemoryError("password=dummy-secret")

        def __len__(self) -> int:
            raise MemoryError("password=dummy-secret")

    with pytest.raises(MemoryError, match="dummy-secret"):
        parse_buff_listing_fixture(ExhaustedMapping())


def test_parser_api_annotations_are_mapping_and_immutable_tuple() -> None:
    annotations = get_type_hints(parse_buff_listing_fixture)

    assert str(annotations["payload"]) == "collections.abc.Mapping[str, object]"
    assert str(annotations["return"]) == (
        "tuple[app.services.buff_listing.BuffListingObservation, ...]"
    )


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module.casefold())
    return modules


def test_parser_has_no_external_or_runtime_wiring_imports() -> None:
    project_root = Path(__file__).resolve().parents[1]
    imports = _imported_modules(
        project_root / "app" / "services" / "buff_listing_parser.py"
    )
    forbidden = {
        "app.clients",
        "app.config",
        "asyncio",
        "fastapi",
        "httpx",
        "os",
        "provider",
        "redis",
        "scheduler",
        "steamdt",
        "threading",
        "valuation",
    }

    assert not any(
        fragment in imported
        for imported in imports
        for fragment in forbidden
    )


def test_parser_source_has_no_env_task_thread_network_or_file_write_calls() -> None:
    project_root = Path(__file__).resolve().parents[1]
    source = (
        project_root / "app" / "services" / "buff_listing_parser.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert called_attributes.isdisjoint(
        {
            "create_task",
            "getenv",
            "request",
            "start",
            "write_bytes",
            "write_text",
        }
    )


def test_runtime_modules_do_not_reverse_import_buff_listing_parser() -> None:
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
        assert "app.services.buff_listing_parser" not in _imported_modules(path)


def test_fixture_is_project_owned_shape_without_private_or_transport_fields() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    serialized = json.dumps(payload).casefold()

    assert payload["schema_version"] == BUFF_LISTING_FIXTURE_SCHEMA_VERSION
    assert payload["source"] == BUFF_LISTING_FIXTURE_SOURCE
    assert not {
        "authorization",
        "cookie",
        "seller_id",
        "token",
        "url",
    }.intersection(serialized)
