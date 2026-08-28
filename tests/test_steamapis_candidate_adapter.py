import ast
import asyncio
import builtins
from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import get_type_hints

import pytest

import app.services.steamapis_candidate_adapter as adapter_module
from app.services.market_scan_service import CandidateListing
from app.services.steamapis_candidate_adapter import (
    SteamApisCandidateAdapterError,
    adapt_steamapis_listing_to_candidate,
)
from app.services.steamapis_listing import (
    SteamApisListingEventType,
    SteamApisListingObservation,
    SteamApisSticker,
    make_steamapis_source_offer_id,
)

FOUND_AT = datetime(2026, 8, 11, 8, 15, tzinfo=UTC)
MESSAGE_TIMESTAMP = datetime(2026, 8, 11, 8, 16, 30, 123000, tzinfo=UTC)
PURCHASE_LINK = "https://example.invalid/manual/purchase?opaque=dummy-secret"
INSPECT_LINK = "steam://rungame/730/dummy-inspect"
MARKET_NAME = "AK-47 | Synthetic (Field-Tested)"
SOURCE = "steamapis:buff163"


def _observation(**changes: object) -> SteamApisListingObservation:
    values: dict[str, object] = {
        "source_offer_id": make_steamapis_source_offer_id(
            "Buff163",
            "CS2",
            PURCHASE_LINK,
        ),
        "event_type": SteamApisListingEventType.ADDED,
        "marketplace": "Buff163",
        "game": "CS2",
        "market_hash_name": MARKET_NAME,
        "purchase_link": PURCHASE_LINK,
        "inspect_link": INSPECT_LINK,
        "price_cny": Decimal("123.4500000000000000000000001"),
        "float_value": Decimal("0.1734000000000000001"),
        "paint_index": 675,
        "paint_seed": 42,
        "days_trade_locked": 2,
        "found_at": FOUND_AT,
        "message_timestamp": MESSAGE_TIMESTAMP,
        "stickers": (SteamApisSticker(name="Synthetic", wear=Decimal("0"), slot=0),),
    }
    values.update(changes)
    return SteamApisListingObservation(**values)  # type: ignore[arg-type]


def _expected_id(observation: SteamApisListingObservation) -> str:
    return f"{SOURCE}:{observation.source_offer_id}"


def test_public_api_is_small_and_exact() -> None:
    assert adapter_module.__all__ == (
        "SteamApisCandidateAdapterError",
        "adapt_steamapis_listing_to_candidate",
    )
    hints = get_type_hints(adapt_steamapis_listing_to_candidate)
    assert hints == {
        "observation": SteamApisListingObservation,
        "return": CandidateListing,
    }


def test_adapts_observation_to_existing_candidate_listing() -> None:
    observation = _observation()

    candidate = adapt_steamapis_listing_to_candidate(observation)

    assert type(candidate) is CandidateListing
    assert candidate == CandidateListing(
        goods_id=_expected_id(observation),
        listing_id=_expected_id(observation),
        market_hash_name=MARKET_NAME,
        price_cny=Decimal("123.4500000000000000000000001"),
        float_value=builtins.float(Decimal("0.1734000000000000001")),
        paint_seed=42,
        inspect_link=INSPECT_LINK,
        source=SOURCE,
        scanned_at=MESSAGE_TIMESTAMP,
        raw=None,
    )


def test_source_local_identity_and_source_use_exact_namespace() -> None:
    observation = _observation()

    candidate = adapt_steamapis_listing_to_candidate(observation)

    assert candidate.goods_id == _expected_id(observation)
    assert candidate.listing_id == _expected_id(observation)
    assert candidate.goods_id == candidate.listing_id
    assert candidate.source == SOURCE
    assert candidate.goods_id.removeprefix(f"{SOURCE}:") == observation.source_offer_id


def test_preserves_decimal_price_object_and_precision() -> None:
    price = Decimal("123.4500000000000000000000001")

    candidate = adapt_steamapis_listing_to_candidate(_observation(price_cny=price))

    assert candidate.price_cny is price
    assert type(candidate.price_cny) is Decimal
    assert str(candidate.price_cny) == "123.4500000000000000000000001"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (Decimal("0"), 0.0),
        (
            Decimal("0.12345678901234567890123456789"),
            builtins.float(Decimal("0.12345678901234567890123456789")),
        ),
        (Decimal("1"), 1.0),
    ],
)
def test_converts_decimal_float_at_legacy_boundary(
    source: Decimal,
    expected: float,
) -> None:
    candidate = adapt_steamapis_listing_to_candidate(
        _observation(float_value=source)
    )

    assert type(candidate.float_value) is float
    assert candidate.float_value == expected


def test_converts_only_observation_float_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation = _observation()
    converted: list[object] = []

    def recording_float(value: object) -> float:
        converted.append(value)
        return builtins.float(value)  # type: ignore[arg-type]

    monkeypatch.setattr(adapter_module, "_to_float", recording_float)

    candidate = adapt_steamapis_listing_to_candidate(observation)

    assert converted == [observation.float_value]
    assert candidate.price_cny is observation.price_cny


def test_preserves_paint_seed_and_documented_inspect_link() -> None:
    candidate = adapt_steamapis_listing_to_candidate(
        _observation(paint_seed=999, inspect_link=INSPECT_LINK)
    )

    assert candidate.paint_seed == 999
    assert candidate.inspect_link == INSPECT_LINK


def test_preserves_nullable_inspect_link_without_purchase_fallback() -> None:
    observation = _observation(inspect_link=None)

    candidate = adapt_steamapis_listing_to_candidate(observation)

    assert candidate.inspect_link is None
    assert observation.purchase_link == PURCHASE_LINK


def test_uses_message_timestamp_instead_of_found_at() -> None:
    observation = _observation()
    assert observation.message_timestamp != observation.found_at

    candidate = adapt_steamapis_listing_to_candidate(observation)

    assert candidate.scanned_at == observation.message_timestamp
    assert candidate.scanned_at != observation.found_at
    assert candidate.scanned_at.tzinfo is UTC


def test_candidate_retains_no_raw_or_purchase_link() -> None:
    observation = _observation()

    candidate = adapt_steamapis_listing_to_candidate(observation)
    candidate_values = tuple(getattr(candidate, field.name) for field in fields(candidate))

    assert candidate.raw is None
    assert observation.purchase_link not in candidate_values
    assert observation.purchase_link not in repr(candidate)
    assert observation.purchase_link == PURCHASE_LINK


def test_repeated_adaptation_is_deterministic_and_independent() -> None:
    observation = _observation()

    first = adapt_steamapis_listing_to_candidate(observation)
    second = adapt_steamapis_listing_to_candidate(observation)

    assert first == second
    assert first is not second


def test_adaptation_does_not_modify_observation() -> None:
    observation = _observation()
    snapshot = _observation()

    adapt_steamapis_listing_to_candidate(observation)

    assert observation == snapshot
    assert observation.purchase_link == PURCHASE_LINK


def test_updated_economics_do_not_change_source_local_identity() -> None:
    added = _observation()
    updated = _observation(
        event_type=SteamApisListingEventType.UPDATED,
        price_cny=Decimal("99.99"),
        float_value=Decimal("0.111111"),
        paint_seed=777,
        message_timestamp=datetime(2026, 8, 11, 9, 0, tzinfo=UTC),
    )

    added_candidate = adapt_steamapis_listing_to_candidate(added)
    updated_candidate = adapt_steamapis_listing_to_candidate(updated)

    assert added.source_offer_id == updated.source_offer_id
    assert added_candidate.goods_id == updated_candidate.goods_id
    assert added_candidate.listing_id == updated_candidate.listing_id
    assert added_candidate.price_cny != updated_candidate.price_cny


def test_different_source_offer_ids_produce_different_candidate_ids() -> None:
    first = _observation()
    other_link = "https://example.invalid/manual/purchase?opaque=other"
    second = _observation(
        source_offer_id=make_steamapis_source_offer_id("Buff163", "CS2", other_link),
        purchase_link=other_link,
    )

    first_candidate = adapt_steamapis_listing_to_candidate(first)
    second_candidate = adapt_steamapis_listing_to_candidate(second)

    assert first.source_offer_id != second.source_offer_id
    assert first_candidate.goods_id != second_candidate.goods_id
    assert first_candidate.listing_id != second_candidate.listing_id


@pytest.mark.parametrize("invalid", [None, object(), "offer", CandidateListing])
def test_rejects_wrong_input_type_with_fixed_error(invalid: object) -> None:
    with pytest.raises(SteamApisCandidateAdapterError) as exc_info:
        adapt_steamapis_listing_to_candidate(invalid)  # type: ignore[arg-type]

    assert type(exc_info.value) is SteamApisCandidateAdapterError
    assert str(exc_info.value) == "invalid SteamApis candidate adapter contract"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is False


def test_rejects_observation_subclass() -> None:
    class ObservationSubclass(SteamApisListingObservation):
        pass

    source = _observation()
    subclassed = ObservationSubclass(
        **{field.name: getattr(source, field.name) for field in fields(source)}
    )

    with pytest.raises(SteamApisCandidateAdapterError):
        adapt_steamapis_listing_to_candidate(subclassed)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("marketplace", "buff163"),
        ("game", "cs2"),
        ("source_offer_id", "0" * 64),
        ("purchase_link", "https://example.invalid/tampered"),
        ("price_cny", Decimal("NaN")),
        ("float_value", Decimal("Infinity")),
        ("float_value", Decimal("-0.01")),
        ("float_value", Decimal("1.01")),
        ("message_timestamp", datetime(2026, 8, 11, 8, 16)),
    ],
)
def test_revalidates_tampered_observation(field: str, value: object) -> None:
    observation = _observation()
    object.__setattr__(observation, field, value)

    with pytest.raises(SteamApisCandidateAdapterError) as exc_info:
        adapt_steamapis_listing_to_candidate(observation)

    assert str(exc_info.value) == "invalid SteamApis candidate adapter contract"
    assert exc_info.value.__cause__ is None


@pytest.mark.parametrize("converted", [float("nan"), float("inf"), -0.1, 1.1])
def test_rejects_unsafe_post_conversion_float(
    monkeypatch: pytest.MonkeyPatch,
    converted: float,
) -> None:
    monkeypatch.setattr(adapter_module, "_to_float", lambda _value: converted)

    with pytest.raises(SteamApisCandidateAdapterError):
        adapt_steamapis_listing_to_candidate(_observation())


def test_candidate_construction_failure_is_fixed_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_construction(**_values: object) -> CandidateListing:
        raise RuntimeError(
            f"Cookie=dummy-cookie {PURCHASE_LINK} {INSPECT_LINK} {MARKET_NAME}"
        )

    monkeypatch.setattr(adapter_module, "CandidateListing", fail_construction)

    with pytest.raises(SteamApisCandidateAdapterError) as exc_info:
        adapt_steamapis_listing_to_candidate(_observation())

    rendered = f"{exc_info.value!s} {exc_info.value!r}"
    assert rendered == (
        "invalid SteamApis candidate adapter contract "
        "SteamApisCandidateAdapterError('invalid SteamApis candidate adapter contract')"
    )
    assert "dummy-cookie" not in rendered
    assert PURCHASE_LINK not in rendered
    assert INSPECT_LINK not in rendered
    assert MARKET_NAME not in rendered
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


def test_candidate_memory_error_propagates_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = MemoryError("resource-dummy-secret")

    def fail_construction(**_values: object) -> CandidateListing:
        raise expected

    monkeypatch.setattr(adapter_module, "CandidateListing", fail_construction)

    with pytest.raises(MemoryError) as exc_info:
        adapt_steamapis_listing_to_candidate(_observation())

    assert exc_info.value is expected


@pytest.mark.parametrize("error", [asyncio.CancelledError(), KeyboardInterrupt()])
def test_candidate_base_exceptions_propagate_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    def fail_construction(**_values: object) -> CandidateListing:
        raise error

    monkeypatch.setattr(adapter_module, "CandidateListing", fail_construction)

    with pytest.raises(type(error)) as exc_info:
        adapt_steamapis_listing_to_candidate(_observation())

    assert exc_info.value is error


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module.casefold())
    return modules


def test_adapter_imports_only_domain_destination_and_standard_library() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "steamapis_candidate_adapter.py"
    )

    assert _imported_modules(module_path) == {
        "__future__",
        "math",
        "app.services.market_scan_service",
        "app.services.steamapis_listing",
    }


def test_adapter_has_no_external_runtime_or_url_parser_calls() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "steamapis_candidate_adapter.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    called_names = {
        node.func.id.casefold()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    forbidden_calls = {
        "adapt_qualified_buff_listing",
        "create_task",
        "create_thread",
        "getenv",
        "lookup_facts",
        "open",
        "parse_qs",
        "qualify",
        "sleep",
        "solve_recipes",
        "urlparse",
        "urlsplit",
    }

    assert called_names.isdisjoint(forbidden_calls)
    imports = _imported_modules(module_path)
    forbidden_import_fragments = {
        "buff_listing",
        "client",
        "config",
        "discord",
        "fastapi",
        "metadata",
        "pipeline",
        "redis",
        "recipe_solver",
        "scheduler",
        "steamdt",
        "urllib",
        "websocket",
    }
    assert all(
        fragment not in module
        for module in imports
        for fragment in forbidden_import_fragments
    )


def test_runtime_modules_do_not_reverse_import_adapter() -> None:
    project_root = Path(__file__).resolve().parents[1]
    runtime_paths = [
        project_root / "app" / "main.py",
        project_root / "app" / "config.py",
        project_root / "app" / "services" / "steamapis_listing.py",
        project_root / "app" / "services" / "buff_listing_solver_adapter.py",
        project_root / "app" / "services" / "market_scan_service.py",
        project_root / "app" / "services" / "recipe_solver.py",
        project_root / "app" / "services" / "valuation_service.py",
        project_root / "app" / "services" / "pipeline_service.py",
        project_root / "app" / "jobs" / "scheduler.py",
    ]

    for path in runtime_paths:
        assert "app.services.steamapis_candidate_adapter" not in _imported_modules(path)
