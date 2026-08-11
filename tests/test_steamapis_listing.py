from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from decimal import Decimal
from inspect import Parameter, signature
from pathlib import Path
from typing import get_type_hints

import pytest

from app.services.steamapis_listing import (
    SteamApisListingEventType,
    SteamApisListingObservation,
    SteamApisListingParseError,
    SteamApisMessageKind,
    SteamApisParsedMessage,
    SteamApisSticker,
    make_steamapis_source_offer_id,
    parse_steamapis_message,
)

MODULE_PATH = Path(__file__).parents[1] / "app" / "services" / "steamapis_listing.py"
PURCHASE_LINK = "https://example.test/manual/offer?opaque=one"
INSPECT_LINK = "steam://inspect/example"
MESSAGE_TIMESTAMP_MS = 1_721_234_567_890
FOUND_AT_SECONDS = 1_721_234_500


def _offer_payload(
    *,
    event_type: str = "Added",
    marketplace: str = "Buff163",
    game: str = "CS2",
    data_overrides: dict[str, object] | None = None,
    envelope_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "name": "AK-47 | Redline (Field-Tested)",
        "purchaseLink": PURCHASE_LINK,
        "priceUSD": 15.25,
        "priceEUR": 14.20,
        "priceCNY": 109.123400,
        "priceRUB": 1400,
        "daysTradeLocked": 0,
        "foundAt": FOUND_AT_SECONDS,
        "inspectLink": INSPECT_LINK,
        "float": 0.123456789012345678,
        "paintIndex": 282,
        "paintSeed": 321,
        "stickers": None,
    }
    if data_overrides:
        data.update(data_overrides)
    payload: dict[str, object] = {
        "type": "offer",
        "eventType": event_type,
        "marketplace": marketplace,
        "game": game,
        "timestamp": MESSAGE_TIMESTAMP_MS,
        "data": data,
    }
    if envelope_overrides:
        payload.update(envelope_overrides)
    return payload


def _parse_offer(**kwargs: object) -> SteamApisListingObservation:
    result = parse_steamapis_message(json.dumps(_offer_payload(**kwargs)))
    assert result.kind is SteamApisMessageKind.OFFER
    assert result.offer is not None
    return result.offer


def _make_observation() -> SteamApisListingObservation:
    return _parse_offer()


def test_public_enum_values_and_signatures_are_exact() -> None:
    assert [(value.name, value.value) for value in SteamApisListingEventType] == [
        ("ADDED", "Added"),
        ("UPDATED", "Updated"),
    ]
    assert [(value.name, value.value) for value in SteamApisMessageKind] == [
        ("SUBSCRIBED", "subscribed"),
        ("OFFER", "offer"),
        ("IGNORED", "ignored"),
        ("ERROR", "error"),
    ]
    parse_parameters = list(signature(parse_steamapis_message).parameters.values())
    assert [(parameter.name, parameter.kind) for parameter in parse_parameters] == [
        ("payload", Parameter.POSITIONAL_OR_KEYWORD)
    ]
    assert get_type_hints(parse_steamapis_message)["return"] is SteamApisParsedMessage
    identity_parameters = list(
        signature(make_steamapis_source_offer_id).parameters.values()
    )
    assert [parameter.name for parameter in identity_parameters] == [
        "marketplace",
        "game",
        "purchase_link",
    ]
    assert all(
        parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        for parameter in identity_parameters
    )
    assert get_type_hints(make_steamapis_source_offer_id)["return"] is str


def test_public_models_have_exact_fields() -> None:
    assert [field.name for field in fields(SteamApisSticker)] == [
        "name",
        "wear",
        "slot",
    ]
    assert [field.name for field in fields(SteamApisListingObservation)] == [
        "source_offer_id",
        "event_type",
        "marketplace",
        "game",
        "market_hash_name",
        "purchase_link",
        "inspect_link",
        "price_cny",
        "float_value",
        "paint_index",
        "paint_seed",
        "days_trade_locked",
        "found_at",
        "message_timestamp",
        "stickers",
    ]
    assert [field.name for field in fields(SteamApisParsedMessage)] == [
        "kind",
        "offer",
        "ignore_reason",
    ]


def test_public_models_are_frozen_keyword_only_and_repr_hidden() -> None:
    observation = _make_observation()
    result = SteamApisParsedMessage(kind=SteamApisMessageKind.OFFER, offer=observation)

    with pytest.raises(TypeError):
        SteamApisSticker("Sticker", Decimal("0"), 0)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        observation.purchase_link = "changed"  # type: ignore[misc]
    assert PURCHASE_LINK not in repr(observation)
    assert INSPECT_LINK not in repr(observation)
    assert observation.market_hash_name not in repr(observation)
    assert PURCHASE_LINK not in repr(result)
    assert repr(observation).startswith("<app.services.steamapis_listing.")


def test_parsed_message_enforces_kind_invariants_and_copies_offer() -> None:
    observation = _make_observation()
    result = SteamApisParsedMessage(kind=SteamApisMessageKind.OFFER, offer=observation)

    assert result.offer == observation
    assert result.offer is not observation
    with pytest.raises(SteamApisListingParseError):
        SteamApisParsedMessage(kind=SteamApisMessageKind.OFFER)
    with pytest.raises(SteamApisListingParseError):
        SteamApisParsedMessage(
            kind=SteamApisMessageKind.IGNORED,
            offer=observation,
            ignore_reason="other_game",
        )
    with pytest.raises(SteamApisListingParseError):
        SteamApisParsedMessage(kind=SteamApisMessageKind.IGNORED)
    with pytest.raises(SteamApisListingParseError):
        SteamApisParsedMessage(
            kind=SteamApisMessageKind.ERROR,
            ignore_reason="other_game",
        )


def test_parse_subscribed_message_with_extra_fields() -> None:
    result = parse_steamapis_message(
        json.dumps({"type": "subscribed", "subscriptions": ["Buff163"], "future": 1})
    )

    assert result == SteamApisParsedMessage(kind=SteamApisMessageKind.SUBSCRIBED)


def test_parse_server_error_discards_server_text() -> None:
    server_text = "secret-apiKey=synthetic-token purchase=https://secret.test"
    result = parse_steamapis_message(
        json.dumps({"type": "error", "message": server_text, "details": {"raw": 1}})
    )

    assert result == SteamApisParsedMessage(kind=SteamApisMessageKind.ERROR)
    assert server_text not in repr(result)


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [("Added", SteamApisListingEventType.ADDED), ("Updated", SteamApisListingEventType.UPDATED)],
)
def test_parse_complete_added_and_updated_offer(
    event_type: str,
    expected: SteamApisListingEventType,
) -> None:
    offer = _parse_offer(event_type=event_type)

    assert offer.event_type is expected
    assert offer.marketplace == "Buff163"
    assert offer.game == "CS2"
    assert offer.market_hash_name == "AK-47 | Redline (Field-Tested)"
    assert offer.purchase_link == PURCHASE_LINK
    assert offer.inspect_link == INSPECT_LINK
    assert offer.paint_index == 282
    assert offer.paint_seed == 321
    assert offer.days_trade_locked == 0
    assert offer.stickers == ()


def test_parser_preserves_exact_decimal_cny_and_float() -> None:
    serialized = json.dumps(_offer_payload())
    serialized = serialized.replace("109.1234", "109.123400")
    serialized = serialized.replace("0.12345678901234568", "0.123456789012345678")

    result = parse_steamapis_message(serialized)

    assert result.offer is not None
    assert result.offer.price_cny == Decimal("109.123400")
    assert result.offer.float_value == Decimal("0.123456789012345678")
    assert result.offer.price_cny.as_tuple().exponent == -6
    assert result.offer.float_value.as_tuple().exponent == -18


def test_parser_accepts_integer_cny_and_float_as_decimal() -> None:
    offer = _parse_offer(data_overrides={"priceCNY": 10, "float": 0})

    assert offer.price_cny == Decimal("10")
    assert offer.float_value == Decimal("0")
    assert type(offer.price_cny) is Decimal
    assert type(offer.float_value) is Decimal


def test_nullable_offer_fields_are_normalized() -> None:
    offer = _parse_offer(
        data_overrides={
            "inspectLink": None,
            "paintIndex": None,
            "paintSeed": None,
            "daysTradeLocked": None,
            "stickers": None,
        }
    )

    assert offer.inspect_link is None
    assert offer.paint_index is None
    assert offer.paint_seed is None
    assert offer.days_trade_locked is None
    assert offer.stickers == ()


def test_valid_stickers_preserve_order_duplicates_and_values() -> None:
    raw_stickers = [
        {"name": "Sticker A", "wear": 0.1250, "slot": 0},
        {"name": "Sticker A", "wear": 1, "slot": 1, "future": "ignored"},
    ]
    offer = _parse_offer(data_overrides={"stickers": raw_stickers})

    assert offer.stickers == (
        SteamApisSticker(name="Sticker A", wear=Decimal("0.125"), slot=0),
        SteamApisSticker(name="Sticker A", wear=Decimal("1"), slot=1),
    )
    assert type(offer.stickers) is tuple


def test_timestamps_use_documented_units_and_utc() -> None:
    offer = _parse_offer()

    assert offer.message_timestamp == datetime(
        2024, 7, 17, 16, 42, 47, 890000, tzinfo=UTC
    )
    assert offer.found_at == datetime(2024, 7, 17, 16, 41, 40, tzinfo=UTC)
    assert offer.message_timestamp.tzinfo is UTC
    assert offer.found_at.tzinfo is UTC


def test_unknown_additional_fields_are_tolerated_and_not_retained() -> None:
    offer = _parse_offer(
        data_overrides={"futureData": {"opaque": "value"}},
        envelope_overrides={"futureEnvelope": [1, 2, 3]},
    )

    assert "futureData" not in {field.name for field in fields(offer)}
    assert "futureEnvelope" not in {field.name for field in fields(offer)}
    assert not hasattr(offer, "raw")
    assert not hasattr(offer, "price_usd")
    assert not hasattr(offer, "owner_id")


def test_source_offer_id_matches_exact_known_preimage() -> None:
    expected = hashlib.sha256(
        f"Buff163\x00CS2\x00{PURCHASE_LINK}".encode()
    ).hexdigest()

    actual = make_steamapis_source_offer_id(" Buff163 ", " CS2 ", f" {PURCHASE_LINK} ")

    assert actual == expected
    assert len(actual) == 64
    assert actual == actual.lower()
    assert all(character in "0123456789abcdef" for character in actual)
    assert PURCHASE_LINK not in actual


def test_added_updated_and_changed_economics_keep_source_offer_id() -> None:
    added = _parse_offer(event_type="Added")
    updated = _parse_offer(
        event_type="Updated",
        data_overrides={"priceCNY": 999.99, "float": 0.999, "paintSeed": 999},
        envelope_overrides={"timestamp": MESSAGE_TIMESTAMP_MS + 1000},
    )

    assert added.source_offer_id == updated.source_offer_id


def test_different_purchase_links_change_source_offer_id() -> None:
    first = _parse_offer()
    second = _parse_offer(
        data_overrides={"purchaseLink": "https://example.test/manual/offer?opaque=two"}
    )

    assert first.source_offer_id != second.source_offer_id


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"marketplace": "OtherMarket"}, "other_marketplace"),
        ({"game": "DOTA2"}, "other_game"),
        ({"data_overrides": {"priceCNY": None}}, "missing_price_cny"),
        ({"data_overrides": {"float": None}}, "missing_float"),
    ],
)
def test_supported_ignored_outcomes(kwargs: dict[str, object], reason: str) -> None:
    result = parse_steamapis_message(json.dumps(_offer_payload(**kwargs)))

    assert result == SteamApisParsedMessage(
        kind=SteamApisMessageKind.IGNORED,
        ignore_reason=reason,
    )


@pytest.mark.parametrize("field", ["priceCNY", "float"])
def test_missing_price_or_float_is_ignored(field: str) -> None:
    payload = _offer_payload()
    data = payload["data"]
    assert isinstance(data, dict)
    del data[field]

    result = parse_steamapis_message(json.dumps(payload))

    assert result.kind is SteamApisMessageKind.IGNORED
    assert result.ignore_reason == (
        "missing_price_cny" if field == "priceCNY" else "missing_float"
    )


def test_other_source_is_ignored_before_target_data_validation() -> None:
    payload = _offer_payload(marketplace="OtherMarket")
    payload["data"] = {"unrelated": "shape"}

    result = parse_steamapis_message(json.dumps(payload))

    assert result.ignore_reason == "other_marketplace"


@pytest.mark.parametrize(
    ("payload", "reason_code"),
    [
        ("not-json", "invalid_json"),
        ("[]", "invalid_envelope"),
        (json.dumps({}), "invalid_envelope"),
        (json.dumps({"type": "Offer"}), "invalid_envelope"),
        (json.dumps({"type": "future"}), "invalid_envelope"),
        (json.dumps(_offer_payload(event_type="Removed")), "unsupported_event"),
    ],
)
def test_invalid_json_envelopes_and_event_types_fail_closed(
    payload: str,
    reason_code: str,
) -> None:
    with pytest.raises(SteamApisListingParseError) as exc_info:
        parse_steamapis_message(payload)

    assert str(exc_info.value) == "invalid SteamApis market message"
    assert exc_info.value.reason_code == reason_code
    assert exc_info.value.__cause__ is None


def test_offer_requires_full_documented_envelope() -> None:
    for field in ("eventType", "marketplace", "game", "timestamp", "data"):
        payload = _offer_payload()
        del payload[field]
        with pytest.raises(SteamApisListingParseError) as exc_info:
            parse_steamapis_message(json.dumps(payload))
        assert exc_info.value.reason_code == "invalid_envelope"


def test_offer_requires_full_documented_data_keys_except_ignored_targets() -> None:
    for field in (
        "name",
        "purchaseLink",
        "priceUSD",
        "priceEUR",
        "priceRUB",
        "daysTradeLocked",
        "foundAt",
        "inspectLink",
        "paintIndex",
        "paintSeed",
        "stickers",
    ):
        payload = _offer_payload()
        data = payload["data"]
        assert isinstance(data, dict)
        del data[field]
        with pytest.raises(SteamApisListingParseError) as exc_info:
            parse_steamapis_message(json.dumps(payload))
        assert exc_info.value.reason_code == "invalid_offer"


@pytest.mark.parametrize(
    ("field", "value", "reason_code"),
    [
        ("name", " ", "invalid_offer"),
        ("purchaseLink", None, "invalid_offer"),
        ("purchaseLink", " ", "invalid_offer"),
        ("inspectLink", 1, "invalid_offer"),
        ("paintIndex", True, "invalid_offer"),
        ("paintIndex", -1, "invalid_offer"),
        ("paintIndex", 1.5, "invalid_offer"),
        ("paintSeed", False, "invalid_offer"),
        ("paintSeed", -1, "invalid_offer"),
        ("daysTradeLocked", True, "invalid_offer"),
        ("daysTradeLocked", -1, "invalid_offer"),
    ],
)
def test_invalid_offer_identity_and_integer_fields_fail_closed(
    field: str,
    value: object,
    reason_code: str,
) -> None:
    with pytest.raises(SteamApisListingParseError) as exc_info:
        parse_steamapis_message(
            json.dumps(_offer_payload(data_overrides={field: value}))
        )

    assert exc_info.value.reason_code == reason_code


@pytest.mark.parametrize(
    ("value", "reason_code"),
    [
        (True, "invalid_price"),
        ("10.00", "invalid_price"),
        (0, "invalid_price"),
        (-1, "invalid_price"),
        ({}, "invalid_price"),
    ],
)
def test_invalid_price_values_fail_closed(value: object, reason_code: str) -> None:
    with pytest.raises(SteamApisListingParseError) as exc_info:
        parse_steamapis_message(
            json.dumps(_offer_payload(data_overrides={"priceCNY": value}))
        )

    assert exc_info.value.reason_code == reason_code


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("priceUSD", None),
        ("priceUSD", True),
        ("priceUSD", 0),
        ("priceEUR", "14.20"),
        ("priceEUR", -1),
        ("priceRUB", False),
        ("priceRUB", {}),
    ],
)
def test_discarded_currency_fields_still_follow_documented_types(
    field: str,
    value: object,
) -> None:
    with pytest.raises(SteamApisListingParseError) as exc_info:
        parse_steamapis_message(
            json.dumps(_offer_payload(data_overrides={field: value}))
        )

    assert exc_info.value.reason_code == "invalid_offer"


def test_nullable_discarded_currencies_are_accepted_but_not_retained() -> None:
    offer = _parse_offer(data_overrides={"priceEUR": None, "priceRUB": None})

    assert not hasattr(offer, "price_eur")
    assert not hasattr(offer, "price_rub")


@pytest.mark.parametrize("value", [True, "0.1", -0.1, 1.1, {}, []])
def test_invalid_float_values_fail_closed(value: object) -> None:
    with pytest.raises(SteamApisListingParseError) as exc_info:
        parse_steamapis_message(
            json.dumps(_offer_payload(data_overrides={"float": value}))
        )

    assert exc_info.value.reason_code == "invalid_float"


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_constants_are_rejected_everywhere(constant: str) -> None:
    payload = json.dumps(_offer_payload())
    payload = payload[:-1] + f', "future": {constant}' + "}"

    with pytest.raises(SteamApisListingParseError) as exc_info:
        parse_steamapis_message(payload)

    assert exc_info.value.reason_code == "invalid_json"


def test_fractional_documented_timestamps_preserve_subsecond_precision() -> None:
    payload = _offer_payload(
        envelope_overrides={"timestamp": 1_721_234_567_890.5},
        data_overrides={"foundAt": 1_721_234_500.25},
    )

    result = parse_steamapis_message(json.dumps(payload))

    assert result.offer is not None
    assert result.offer.message_timestamp.microsecond == 890500
    assert result.offer.found_at.microsecond == 250000


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timestamp", True),
        ("timestamp", -1),
        ("timestamp", "1"),
        ("timestamp", 10**30),
        ("foundAt", True),
        ("foundAt", -1),
        ("foundAt", "1"),
        ("foundAt", 10**30),
    ],
)
def test_invalid_timestamps_fail_closed(field: str, value: object) -> None:
    if field == "timestamp":
        payload = _offer_payload(envelope_overrides={field: value})
    else:
        payload = _offer_payload(data_overrides={field: value})

    with pytest.raises(SteamApisListingParseError) as exc_info:
        parse_steamapis_message(json.dumps(payload))

    assert exc_info.value.reason_code == "invalid_timestamp"


@pytest.mark.parametrize(
    "stickers",
    [
        {},
        [None],
        [{"name": "Sticker", "wear": 0.1}],
        [{"name": " ", "wear": 0.1, "slot": 0}],
        [{"name": "Sticker", "wear": True, "slot": 0}],
        [{"name": "Sticker", "wear": -0.1, "slot": 0}],
        [{"name": "Sticker", "wear": 1.1, "slot": 0}],
        [{"name": "Sticker", "wear": 0.1, "slot": True}],
        [{"name": "Sticker", "wear": 0.1, "slot": -1}],
    ],
)
def test_malformed_sticker_fails_whole_offer(stickers: object) -> None:
    with pytest.raises(SteamApisListingParseError) as exc_info:
        parse_steamapis_message(
            json.dumps(_offer_payload(data_overrides={"stickers": stickers}))
        )

    assert exc_info.value.reason_code == "invalid_sticker"


@pytest.mark.parametrize(
    "payload",
    [
        '{"type":"subscribed","type":"offer"}',
        '{"type":"offer","eventType":"Added","eventType":"Updated"}',
        (
            '{"type":"offer","eventType":"Added","marketplace":"Buff163",'
            '"game":"CS2","timestamp":1,"data":{"name":"A","name":"B"}}'
        ),
        (
            '{"type":"offer","eventType":"Added","marketplace":"Buff163",'
            '"game":"CS2","timestamp":1,"data":{"name":"A","purchaseLink":"L",'
            '"priceUSD":1,"priceEUR":1,"priceCNY":1,"priceRUB":1,'
            '"daysTradeLocked":0,"foundAt":1,"inspectLink":null,"float":0.1,'
            '"paintIndex":null,"paintSeed":null,"stickers":['
            '{"name":"S","wear":0.1,"wear":0.2,"slot":0}]}}'
        ),
    ],
)
def test_duplicate_json_keys_at_any_depth_are_rejected(payload: str) -> None:
    with pytest.raises(SteamApisListingParseError) as exc_info:
        parse_steamapis_message(payload)

    assert exc_info.value.reason_code == "invalid_json"


def test_error_and_repr_redaction_never_reflects_input() -> None:
    sensitive_values = [
        PURCHASE_LINK,
        INSPECT_LINK,
        "AK-47 | Secret",
        "apiKey=synthetic-secret-token",
        "Authorization: Bearer synthetic-secret",
        "Cookie: secret-cookie",
    ]
    raw_payload = json.dumps(
        {
            "type": "offer",
            "eventType": "Removed",
            "marketplace": "Buff163",
            "game": "CS2",
            "timestamp": 1,
            "data": {"purchaseLink": " ".join(sensitive_values)},
        }
    )

    with pytest.raises(SteamApisListingParseError) as exc_info:
        parse_steamapis_message(raw_payload)

    public_text = f"{str(exc_info.value)} {repr(exc_info.value)}"
    assert public_text == (
        "invalid SteamApis market message "
        "SteamApisListingParseError('invalid SteamApis market message')"
    )
    assert all(value not in public_text for value in sensitive_values)
    assert raw_payload not in public_text
    assert exc_info.value.__cause__ is None


def test_parser_rejects_nonexact_string_without_exposing_value() -> None:
    with pytest.raises(SteamApisListingParseError) as exc_info:
        parse_steamapis_message(b"apiKey=secret")  # type: ignore[arg-type]

    assert str(exc_info.value) == "invalid SteamApis market message"


def test_parse_error_constructor_rejects_unknown_reason_without_leak() -> None:
    secret = "apiKey=synthetic-secret"
    with pytest.raises(ValueError) as exc_info:
        SteamApisListingParseError(reason_code=secret)

    assert str(exc_info.value) == "invalid SteamApis market message"
    assert secret not in repr(exc_info.value)


def test_module_imports_only_standard_library() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots <= {
        "__future__",
        "hashlib",
        "json",
        "collections",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
    }
    assert not imported_roots & {
        "app",
        "httpx",
        "redis",
        "fastapi",
        "os",
        "asyncio",
        "threading",
        "websockets",
    }


def test_module_has_no_network_environment_file_or_background_calls() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden_names = {
        "getenv",
        "request",
        "post",
        "connect",
        "create_task",
        "to_thread",
        "open",
        "read_text",
        "write_text",
        "write_bytes",
        "start",
    }
    called_names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called_names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called_names.add(node.func.attr)

    assert not called_names & forbidden_names


def test_protected_runtime_modules_do_not_import_new_parser() -> None:
    protected_paths = [
        Path(__file__).parents[1] / "app" / "services" / "pipeline_service.py",
        Path(__file__).parents[1] / "app" / "jobs" / "scheduler.py",
        Path(__file__).parents[1] / "app" / "main.py",
        Path(__file__).parents[1] / "app" / "services" / "market_scan_service.py",
        Path(__file__).parents[1] / "app" / "services" / "recipe_solver.py",
    ]

    for path in protected_paths:
        assert "steamapis_listing" not in path.read_text(encoding="utf-8")
