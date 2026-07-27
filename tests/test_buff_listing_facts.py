from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import Iterator, Mapping
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import get_type_hints

import pytest

import app.services.buff_listing_facts as facts_module
from app.services.buff_listing import BuffTradableCandidate
from app.services.buff_listing_eligibility import (
    BuffListingEligibilityFacts,
    BuffListingEligibilityPolicy,
    BuffListingIneligibilityReason,
    evaluate_buff_listing_eligibility,
)
from app.services.buff_listing_facts import (
    BUFF_LISTING_FACTS_SCHEMA_VERSION,
    BUFF_LISTING_FACTS_SOURCE,
    BuffListingFactsCause,
    BuffListingFactsLookupResult,
    BuffListingFactsLookupStatus,
    BuffListingFactsParseError,
    BuffListingFactsProvider,
    BuffListingFactsRecord,
    BuffListingFactsValidationError,
    OfflineBuffListingFactsProvider,
    load_buff_listing_facts_fixture,
    parse_buff_listing_facts_fixture,
)

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "buff" / "listing_facts_v1.json"
)


def _record(
    *,
    listing_id: str = "listing-001",
    market_hash_name: str = "AK-47 | Redline (Field-Tested)",
    is_stattrak: bool = False,
    is_souvenir: bool = False,
    has_special_seed: bool = False,
) -> BuffListingFactsRecord:
    return BuffListingFactsRecord(
        listing_id=listing_id,
        market_hash_name=market_hash_name,
        is_stattrak=is_stattrak,
        is_souvenir=is_souvenir,
        has_special_seed=has_special_seed,
    )


def _raw_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "listing_id": "listing-001",
        "market_hash_name": "AK-47 | Redline (Field-Tested)",
        "is_stattrak": False,
        "is_souvenir": False,
        "has_special_seed": False,
    }
    record.update(overrides)
    return record


def _payload(records: list[object] | None = None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": "buff",
        "records": [_raw_record()] if records is None else records,
    }


def _candidate(
    *,
    listing_id: str = "listing-001",
    market_hash_name: str = "AK-47 | Redline (Field-Tested)",
    goods_id: str | None = "goods-001",
    paint_seed: int | None = None,
) -> BuffTradableCandidate:
    return BuffTradableCandidate(
        listing_id=listing_id,
        goods_id=goods_id,
        market_hash_name=market_hash_name,
        buy_price_cny=Decimal("12.34"),
        available_quantity=1,
        float_value=Decimal("0.20"),
        wear_name="Field-Tested",
        paint_seed=paint_seed,
        observed_at=datetime(2026, 7, 25, tzinfo=UTC),
    )


def _assert_parse_error(
    exc_info: pytest.ExceptionInfo[BuffListingFactsParseError],
    *,
    field: str,
    cause: BuffListingFactsCause,
    record_index: int | None = None,
) -> None:
    error = exc_info.value
    assert str(error) == "invalid BUFF listing facts fixture"
    assert error.field == field
    assert error.cause is cause
    assert error.record_index == record_index
    assert error.__cause__ is None


def test_record_has_exact_flat_public_fields() -> None:
    assert tuple(field.name for field in fields(BuffListingFactsRecord)) == (
        "listing_id",
        "market_hash_name",
        "is_stattrak",
        "is_souvenir",
        "has_special_seed",
    )


def test_record_is_keyword_only_frozen_and_repr_suppressed() -> None:
    record = _record(listing_id="secret-listing")

    with pytest.raises(TypeError):
        BuffListingFactsRecord(  # type: ignore[misc]
            "listing-001",
            "Item",
            False,
            False,
            False,
        )
    with pytest.raises(FrozenInstanceError):
        record.listing_id = "replacement"  # type: ignore[misc]

    assert "secret-listing" not in repr(record)


def test_record_strips_identity_without_case_folding() -> None:
    record = _record(
        listing_id="  Listing-ABC  ",
        market_hash_name="  AK-47  | Redline  ",
    )

    assert record.listing_id == "Listing-ABC"
    assert record.market_hash_name == "AK-47  | Redline"


@pytest.mark.parametrize("field", ["listing_id", "market_hash_name"])
@pytest.mark.parametrize("value", [None, 1, True, "", "   "])
def test_record_rejects_invalid_identity(field: str, value: object) -> None:
    values: dict[str, object] = {
        "listing_id": "listing-001",
        "market_hash_name": "Item",
    }
    values[field] = value

    with pytest.raises(BuffListingFactsValidationError) as exc_info:
        BuffListingFactsRecord(
            listing_id=values["listing_id"],  # type: ignore[arg-type]
            market_hash_name=values["market_hash_name"],  # type: ignore[arg-type]
            is_stattrak=False,
            is_souvenir=False,
            has_special_seed=False,
        )

    assert exc_info.value.field == field
    assert str(exc_info.value) == "invalid BUFF listing facts contract"


@pytest.mark.parametrize(
    "field",
    ["is_stattrak", "is_souvenir", "has_special_seed"],
)
@pytest.mark.parametrize("value", [0, 1, None, "false", [], object()])
def test_record_flags_require_exact_booleans(field: str, value: object) -> None:
    values: dict[str, object] = {
        "is_stattrak": False,
        "is_souvenir": False,
        "has_special_seed": False,
    }
    values[field] = value

    with pytest.raises(BuffListingFactsValidationError) as exc_info:
        BuffListingFactsRecord(
            listing_id="listing-001",
            market_hash_name="Item",
            is_stattrak=values["is_stattrak"],  # type: ignore[arg-type]
            is_souvenir=values["is_souvenir"],  # type: ignore[arg-type]
            has_special_seed=values["has_special_seed"],  # type: ignore[arg-type]
        )

    assert exc_info.value.field == field


def test_lookup_status_vocabulary_is_stable() -> None:
    assert tuple((status.name, status.value) for status in BuffListingFactsLookupStatus) == (
        ("FOUND", "found"),
        ("MISSING", "missing"),
    )


def test_lookup_result_binds_normalized_query_and_copies_facts() -> None:
    facts = BuffListingEligibilityFacts(
        is_stattrak=True,
        is_souvenir=False,
        has_special_seed=False,
    )
    result = BuffListingFactsLookupResult(
        status=BuffListingFactsLookupStatus.FOUND,
        listing_id=" listing-001 ",
        market_hash_name=" Item ",
        facts=facts,
    )

    assert result.listing_id == "listing-001"
    assert result.market_hash_name == "Item"
    assert result.facts == facts
    assert result.facts is not facts


@pytest.mark.parametrize(
    ("status", "facts"),
    [
        (BuffListingFactsLookupStatus.FOUND, None),
        (
            BuffListingFactsLookupStatus.MISSING,
            BuffListingEligibilityFacts(
                is_stattrak=False,
                is_souvenir=False,
                has_special_seed=False,
            ),
        ),
        ("found", None),
    ],
)
def test_lookup_result_rejects_invalid_status_facts_combinations(
    status: object,
    facts: BuffListingEligibilityFacts | None,
) -> None:
    with pytest.raises(BuffListingFactsValidationError):
        BuffListingFactsLookupResult(
            status=status,  # type: ignore[arg-type]
            listing_id="listing-001",
            market_hash_name="Item",
            facts=facts,
        )


def test_lookup_result_is_frozen_and_repr_suppressed() -> None:
    result = BuffListingFactsLookupResult(
        status=BuffListingFactsLookupStatus.MISSING,
        listing_id="secret-listing",
        market_hash_name="secret-item",
        facts=None,
    )

    with pytest.raises(FrozenInstanceError):
        result.status = BuffListingFactsLookupStatus.FOUND  # type: ignore[misc]

    assert "secret-listing" not in repr(result)
    assert "secret-item" not in repr(result)


def test_loads_project_owned_v1_fixture() -> None:
    records = load_buff_listing_facts_fixture(FIXTURE_PATH)

    assert len(records) == 4
    assert records[0] == _record(
        listing_id="synthetic-listing-001",
        market_hash_name="AK-47 | Redline (Field-Tested)",
    )
    assert records[1].is_stattrak is True
    assert records[2].is_souvenir is True
    assert records[3].has_special_seed is True


def test_mapping_parser_and_file_loader_are_equivalent() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert parse_buff_listing_facts_fixture(payload) == (
        load_buff_listing_facts_fixture(FIXTURE_PATH)
    )


def test_parser_preserves_order_and_returns_tuple() -> None:
    payload = _payload(
        [
            _raw_record(listing_id="listing-002", market_hash_name="Second"),
            _raw_record(listing_id="listing-001", market_hash_name="First"),
        ]
    )

    records = parse_buff_listing_facts_fixture(payload)

    assert type(records) is tuple
    assert tuple(record.listing_id for record in records) == (
        "listing-002",
        "listing-001",
    )


def test_empty_records_array_returns_empty_tuple() -> None:
    assert parse_buff_listing_facts_fixture(_payload([])) == ()


@pytest.mark.parametrize("value", [True, False, 0, 2, 1.0, "1", None])
def test_schema_version_requires_exact_integer_one(value: object) -> None:
    payload = _payload()
    payload["schema_version"] = value

    with pytest.raises(BuffListingFactsParseError) as exc_info:
        parse_buff_listing_facts_fixture(payload)

    _assert_parse_error(
        exc_info,
        field="schema_version",
        cause=BuffListingFactsCause.FIXTURE_SCHEMA,
    )
    assert BUFF_LISTING_FACTS_SCHEMA_VERSION == 1


@pytest.mark.parametrize("value", ["BUFF", " buff", "buff ", "", None, 1])
def test_source_requires_exact_canonical_buff(value: object) -> None:
    payload = _payload()
    payload["source"] = value

    with pytest.raises(BuffListingFactsParseError) as exc_info:
        parse_buff_listing_facts_fixture(payload)

    _assert_parse_error(
        exc_info,
        field="source",
        cause=BuffListingFactsCause.FIXTURE_SCHEMA,
    )
    assert BUFF_LISTING_FACTS_SOURCE == "buff"


@pytest.mark.parametrize("change", ["missing", "unknown"])
def test_top_level_missing_and_unknown_fields_fail_closed(change: str) -> None:
    payload = _payload()
    if change == "missing":
        del payload["source"]
    else:
        payload["Cookie"] = "secret"

    with pytest.raises(BuffListingFactsParseError) as exc_info:
        parse_buff_listing_facts_fixture(payload)

    _assert_parse_error(
        exc_info,
        field="payload",
        cause=BuffListingFactsCause.FIXTURE_SCHEMA,
    )


@pytest.mark.parametrize("value", [(), "records", b"records", {}, None])
def test_records_requires_exact_list(value: object) -> None:
    payload = _payload()
    payload["records"] = value

    with pytest.raises(BuffListingFactsParseError) as exc_info:
        parse_buff_listing_facts_fixture(payload)

    _assert_parse_error(
        exc_info,
        field="records",
        cause=BuffListingFactsCause.FIXTURE_SCHEMA,
    )


@pytest.mark.parametrize("value", [None, [], "record", 1])
def test_record_requires_mapping(value: object) -> None:
    with pytest.raises(BuffListingFactsParseError) as exc_info:
        parse_buff_listing_facts_fixture(_payload([value]))

    _assert_parse_error(
        exc_info,
        field="records",
        cause=BuffListingFactsCause.FIXTURE_SCHEMA,
        record_index=0,
    )


@pytest.mark.parametrize("change", ["missing", "unknown"])
def test_record_missing_and_unknown_fields_fail_closed(change: str) -> None:
    record = _raw_record()
    if change == "missing":
        del record["is_stattrak"]
    else:
        record["seller_id"] = "secret-seller"

    with pytest.raises(BuffListingFactsParseError) as exc_info:
        parse_buff_listing_facts_fixture(_payload([record]))

    _assert_parse_error(
        exc_info,
        field="records",
        cause=BuffListingFactsCause.FIXTURE_SCHEMA,
        record_index=0,
    )


@pytest.mark.parametrize(
    "field",
    ["is_stattrak", "is_souvenir", "has_special_seed"],
)
@pytest.mark.parametrize("value", [0, 1, "false", None, []])
def test_parser_flags_require_exact_json_booleans(field: str, value: object) -> None:
    with pytest.raises(BuffListingFactsParseError) as exc_info:
        parse_buff_listing_facts_fixture(
            _payload([_raw_record(**{field: value})])
        )

    _assert_parse_error(
        exc_info,
        field=field,
        cause=BuffListingFactsCause.FIXTURE_SCHEMA,
        record_index=0,
    )


def test_parser_strips_identity_before_duplicate_checks() -> None:
    records = parse_buff_listing_facts_fixture(
        _payload(
            [
                _raw_record(
                    listing_id=" listing-001 ",
                    market_hash_name=" Item ",
                ),
                _raw_record(
                    listing_id="listing-002",
                    market_hash_name="item",
                ),
            ]
        )
    )

    assert records[0].listing_id == "listing-001"
    assert records[0].market_hash_name == "Item"
    assert records[1].market_hash_name == "item"


def test_duplicate_canonical_identity_fails_closed() -> None:
    with pytest.raises(BuffListingFactsParseError) as exc_info:
        parse_buff_listing_facts_fixture(
            _payload(
                [
                    _raw_record(
                        listing_id="listing-001",
                        market_hash_name="Item",
                    ),
                    _raw_record(
                        listing_id=" listing-001 ",
                        market_hash_name=" Item ",
                    ),
                ]
            )
        )

    _assert_parse_error(
        exc_info,
        field="records",
        cause=BuffListingFactsCause.DUPLICATE_IDENTITY,
        record_index=1,
    )


def test_listing_id_collision_with_different_name_fails_closed() -> None:
    with pytest.raises(BuffListingFactsParseError) as exc_info:
        parse_buff_listing_facts_fixture(
            _payload(
                [
                    _raw_record(market_hash_name="First Item"),
                    _raw_record(market_hash_name="Second Item"),
                ]
            )
        )

    _assert_parse_error(
        exc_info,
        field="records",
        cause=BuffListingFactsCause.LISTING_ID_COLLISION,
        record_index=1,
    )


def test_case_distinct_listing_ids_remain_distinct() -> None:
    records = parse_buff_listing_facts_fixture(
        _payload(
            [
                _raw_record(listing_id="Listing-001", market_hash_name="Item"),
                _raw_record(listing_id="listing-001", market_hash_name="Item"),
            ]
        )
    )

    assert len(records) == 2


def test_malformed_later_record_returns_no_partial_tuple() -> None:
    payload = _payload(
        [
            _raw_record(listing_id="listing-001"),
            _raw_record(listing_id="listing-002", is_stattrak="false"),
        ]
    )

    with pytest.raises(BuffListingFactsParseError) as exc_info:
        parse_buff_listing_facts_fixture(payload)

    assert exc_info.value.record_index == 1


def test_file_loader_rejects_malformed_json_without_leaking_content(
    tmp_path: Path,
) -> None:
    path = tmp_path / "Cookie=dummy-secret.json"
    path.write_text('{"password":"dummy-secret"', encoding="utf-8")

    with pytest.raises(BuffListingFactsParseError) as exc_info:
        load_buff_listing_facts_fixture(path)

    _assert_parse_error(
        exc_info,
        field="json",
        cause=BuffListingFactsCause.JSON_DECODE,
    )
    rendered = f"{exc_info.value!s} {exc_info.value!r}"
    assert "dummy-secret" not in rendered
    assert str(path) not in rendered


@pytest.mark.parametrize(
    "serialized",
    [
        '{"schema_version":1,"schema_version":1,"source":"buff","records":[]}',
        (
            '{"schema_version":1,"source":"buff","records":['
            '{"listing_id":"a","listing_id":"a","market_hash_name":"A",'
            '"is_stattrak":false,"is_souvenir":false,'
            '"has_special_seed":false}]}'
        ),
    ],
)
def test_file_loader_rejects_duplicate_json_keys(
    tmp_path: Path,
    serialized: str,
) -> None:
    path = tmp_path / "facts.json"
    path.write_text(serialized, encoding="utf-8")

    with pytest.raises(BuffListingFactsParseError) as exc_info:
        load_buff_listing_facts_fixture(path)

    _assert_parse_error(
        exc_info,
        field="json",
        cause=BuffListingFactsCause.JSON_DECODE,
    )


def test_file_read_error_is_safe_and_distinct(tmp_path: Path) -> None:
    path = tmp_path / "token=dummy-secret.json"

    with pytest.raises(BuffListingFactsParseError) as exc_info:
        load_buff_listing_facts_fixture(path)

    _assert_parse_error(
        exc_info,
        field="path",
        cause=BuffListingFactsCause.FILE_READ,
    )
    assert "dummy-secret" not in repr(exc_info.value)


def test_mapping_input_mutation_does_not_change_parsed_records() -> None:
    record = _raw_record()
    records_list: list[object] = [record]
    payload = _payload(records_list)

    parsed = parse_buff_listing_facts_fixture(payload)
    record["is_stattrak"] = True
    record["listing_id"] = "changed"
    records_list.clear()
    payload.clear()

    assert parsed == (_record(),)


def test_reentrant_record_cannot_remove_later_malformed_record() -> None:
    records: list[object] = []

    class MutatingRecord(dict[str, object]):
        def __getitem__(self, key: str) -> object:
            if len(records) > 1:
                records.pop()
            return super().__getitem__(key)

    records.extend(
        [
            MutatingRecord(_raw_record()),
            _raw_record(listing_id="listing-002", is_stattrak="false"),
        ]
    )

    with pytest.raises(BuffListingFactsParseError) as exc_info:
        parse_buff_listing_facts_fixture(_payload(records))

    assert exc_info.value.record_index == 1


def test_caller_raised_contract_errors_are_sanitized() -> None:
    class HostileMapping(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            raise BuffListingFactsParseError(
                field="Cookie=dummy-secret",
                cause=BuffListingFactsCause.JSON_DECODE,
                record_index=999,
            )

        def __iter__(self) -> Iterator[str]:
            return iter(("schema_version", "source", "records"))

        def __len__(self) -> int:
            return 3

    with pytest.raises(BuffListingFactsParseError) as exc_info:
        parse_buff_listing_facts_fixture(HostileMapping())

    error = exc_info.value
    assert error.field == "payload"
    assert error.record_index is None
    assert "dummy-secret" not in f"{error!s} {error!r}"


def test_ordinary_path_read_exception_is_safely_classified() -> None:
    class HostilePath(type(FIXTURE_PATH)):
        def read_text(self, *args: object, **kwargs: object) -> str:
            raise ValueError("Cookie=dummy-secret")

    with pytest.raises(BuffListingFactsParseError) as exc_info:
        load_buff_listing_facts_fixture(HostilePath("unused"))

    _assert_parse_error(
        exc_info,
        field="path",
        cause=BuffListingFactsCause.FILE_READ,
    )
    assert "dummy-secret" not in repr(exc_info.value)


def test_memory_error_from_mapping_is_not_wrapped() -> None:
    class ExhaustedMapping(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            raise MemoryError("password=dummy-secret")

        def __iter__(self) -> Iterator[str]:
            raise MemoryError("password=dummy-secret")

        def __len__(self) -> int:
            raise MemoryError("password=dummy-secret")

    with pytest.raises(MemoryError, match="dummy-secret"):
        parse_buff_listing_facts_fixture(ExhaustedMapping())


def test_keyboard_interrupt_is_not_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(_payload: object) -> tuple[BuffListingFactsRecord, ...]:
        raise KeyboardInterrupt

    monkeypatch.setattr(facts_module, "_parse_fixture", interrupt)

    with pytest.raises(KeyboardInterrupt):
        parse_buff_listing_facts_fixture(_payload())


def test_provider_protocol_exposes_narrow_async_lookup() -> None:
    method = BuffListingFactsProvider.lookup_facts

    assert ast.parse(
        "async def lookup_facts(candidate):\n    pass\n"
    ).body[0].name == method.__name__  # type: ignore[union-attr]
    assert get_type_hints(method) == {
        "candidate": BuffTradableCandidate,
        "return": BuffListingFactsLookupResult,
    }
    public_methods = {
        name
        for name, value in BuffListingFactsProvider.__dict__.items()
        if not name.startswith("_") and callable(value)
    }
    assert public_methods == {"lookup_facts"}


def test_provider_returns_found_for_exact_identity() -> None:
    provider = OfflineBuffListingFactsProvider(
        [_record(is_stattrak=True, has_special_seed=True)]
    )

    result = asyncio.run(provider.lookup_facts(_candidate()))

    assert result.status is BuffListingFactsLookupStatus.FOUND
    assert result.listing_id == "listing-001"
    assert result.market_hash_name == "AK-47 | Redline (Field-Tested)"
    assert result.facts == BuffListingEligibilityFacts(
        is_stattrak=True,
        is_souvenir=False,
        has_special_seed=True,
    )


def test_provider_identity_is_independent_of_candidate_goods_id() -> None:
    provider = OfflineBuffListingFactsProvider([_record(is_stattrak=True)])

    results = [
        asyncio.run(provider.lookup_facts(_candidate(goods_id=goods_id)))
        for goods_id in (None, "goods-001", "goods-002")
    ]

    assert all(result.status is BuffListingFactsLookupStatus.FOUND for result in results)
    assert results[0] == results[1] == results[2]
    assert not hasattr(results[0], "goods_id")
    assert tuple(field.name for field in fields(BuffListingFactsRecord)) == (
        "listing_id",
        "market_hash_name",
        "is_stattrak",
        "is_souvenir",
        "has_special_seed",
    )


def test_provider_returns_missing_without_all_false_fallback() -> None:
    provider = OfflineBuffListingFactsProvider([])

    result = asyncio.run(provider.lookup_facts(_candidate()))

    assert result.status is BuffListingFactsLookupStatus.MISSING
    assert result.facts is None


def test_known_id_with_wrong_name_returns_same_missing_semantics() -> None:
    provider = OfflineBuffListingFactsProvider(
        [_record(is_stattrak=True, is_souvenir=True, has_special_seed=True)]
    )

    absent = asyncio.run(
        provider.lookup_facts(
            _candidate(listing_id="absent", market_hash_name="Unknown")
        )
    )
    mismatch = asyncio.run(
        provider.lookup_facts(
            _candidate(listing_id="listing-001", market_hash_name="Wrong Item")
        )
    )

    assert absent.status is mismatch.status is BuffListingFactsLookupStatus.MISSING
    assert absent.facts is mismatch.facts is None
    assert mismatch.market_hash_name == "Wrong Item"
    assert "AK-47 | Redline" not in repr(mismatch)


def test_repeated_lookup_is_deterministic_and_returns_fresh_facts() -> None:
    provider = OfflineBuffListingFactsProvider([_record(is_souvenir=True)])
    candidate = _candidate()

    first = asyncio.run(provider.lookup_facts(candidate))
    second = asyncio.run(provider.lookup_facts(candidate))

    assert first == second
    assert first is not second
    assert first.facts is not second.facts


def test_provider_constructor_rejects_duplicate_identity() -> None:
    with pytest.raises(BuffListingFactsValidationError) as exc_info:
        OfflineBuffListingFactsProvider([_record(), _record()])

    assert exc_info.value.field == "records"
    assert exc_info.value.cause is BuffListingFactsCause.DUPLICATE_IDENTITY


def test_provider_constructor_rejects_listing_id_collision() -> None:
    with pytest.raises(BuffListingFactsValidationError) as exc_info:
        OfflineBuffListingFactsProvider(
            [_record(market_hash_name="First"), _record(market_hash_name="Second")]
        )

    assert exc_info.value.cause is BuffListingFactsCause.LISTING_ID_COLLISION


def test_provider_defensively_copies_records() -> None:
    record = _record(is_stattrak=True)
    records = [record]
    provider = OfflineBuffListingFactsProvider(records)

    object.__setattr__(record, "is_stattrak", False)
    records.clear()
    result = asyncio.run(provider.lookup_facts(_candidate()))

    assert result.facts is not None
    assert result.facts.is_stattrak is True


def test_provider_does_not_modify_candidate() -> None:
    provider = OfflineBuffListingFactsProvider([_record()])
    candidate = _candidate()
    before = dict(candidate.__dict__)

    asyncio.run(provider.lookup_facts(candidate))

    assert candidate.__dict__ == before


def test_facts_feed_existing_eligibility_evaluator_directly() -> None:
    provider = OfflineBuffListingFactsProvider([_record(is_souvenir=True)])
    candidate = _candidate()
    result = asyncio.run(provider.lookup_facts(candidate))

    assert result.facts is not None
    decision = evaluate_buff_listing_eligibility(
        candidate,
        result.facts,
        BuffListingEligibilityPolicy(),
    )

    assert decision.reasons == (
        BuffListingIneligibilityReason.SOUVENIR_DISALLOWED,
    )


def test_name_and_paint_seed_never_infer_classification() -> None:
    name = "StatTrak™ Souvenir Synthetic Special Seed Item"
    provider = OfflineBuffListingFactsProvider(
        [_record(market_hash_name=name)]
    )

    result = asyncio.run(
        provider.lookup_facts(_candidate(market_hash_name=name, paint_seed=661))
    )

    assert result.facts == BuffListingEligibilityFacts(
        is_stattrak=False,
        is_souvenir=False,
        has_special_seed=False,
    )


def test_explicit_special_seed_does_not_require_candidate_paint_seed() -> None:
    provider = OfflineBuffListingFactsProvider([_record(has_special_seed=True)])

    result = asyncio.run(provider.lookup_facts(_candidate(paint_seed=None)))

    assert result.facts is not None
    assert result.facts.has_special_seed is True


def test_errors_and_repr_do_not_leak_listing_or_secret_data() -> None:
    secret = "Cookie=Bearer-dummy-token-password"

    with pytest.raises(BuffListingFactsValidationError) as validation_exc:
        _record(listing_id=secret, market_hash_name=" ")
    with pytest.raises(BuffListingFactsParseError) as parse_exc:
        parse_buff_listing_facts_fixture(
            _payload([_raw_record(listing_id=secret, is_stattrak=secret)])
        )

    rendered = " ".join(
        [
            str(validation_exc.value),
            repr(validation_exc.value),
            str(parse_exc.value),
            repr(parse_exc.value),
        ]
    )
    assert secret not in rendered
    assert "dummy-token" not in rendered


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            module = node.module.casefold()
            names.add(module)
            names.update(f"{module}.{alias.name.casefold()}" for alias in node.names)
    return names


def test_module_has_no_external_or_runtime_wiring_imports() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "buff_listing_facts.py"
    )
    imported = _imported_names(module_path)
    forbidden = {
        "app.clients",
        "app.config",
        "app.jobs",
        "buff_listing_parser",
        "evaluate_buff_listing_eligibility",
        "fastapi",
        "httpx",
        "market_scan",
        "metadata_provider",
        "os",
        "pipeline",
        "price_provider",
        "recipe_solver",
        "redis",
        "risk_filter",
        "scheduler",
        "steamdt",
        "threading",
        "valuation",
    }

    assert not any(
        fragment in name for name in imported for fragment in forbidden
    )


def test_provider_does_not_call_parser_evaluator_or_create_background_work() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "buff_listing_facts.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert called_names.isdisjoint(
        {
            "evaluate_buff_listing_eligibility",
            "load_buff_listing_fixture",
            "normalize_buff_listing",
            "parse_buff_listing_fixture",
        }
    )
    assert called_attributes.isdisjoint(
        {
            "create_task",
            "getenv",
            "request",
            "start",
            "to_thread",
            "write_bytes",
            "write_text",
        }
    )


def test_runtime_and_downstream_modules_do_not_reverse_import_facts() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = [
        root / "app" / "main.py",
        root / "app" / "config.py",
        root / "app" / "services" / "market_scan_service.py",
        root / "app" / "services" / "recipe_solver.py",
        root / "app" / "services" / "risk_filter.py",
        root / "app" / "services" / "metadata_provider.py",
        root / "app" / "services" / "price_provider.py",
        root / "app" / "services" / "valuation_service.py",
        root / "app" / "services" / "pipeline_service.py",
        root / "app" / "jobs" / "scheduler.py",
    ]

    for path in paths:
        assert "app.services.buff_listing_facts" not in _imported_names(path)
