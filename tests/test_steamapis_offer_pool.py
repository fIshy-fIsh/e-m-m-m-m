from __future__ import annotations

import ast
import asyncio
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from inspect import Parameter, signature
from pathlib import Path
from typing import get_type_hints

import pytest

import app.services.steamapis_offer_pool as pool_module
from app.services.market_scan_service import CandidateListing
from app.services.steamapis_listing import (
    SteamApisListingEventType,
    SteamApisListingObservation,
    make_steamapis_source_offer_id,
)
from app.services.steamapis_offer_pool import (
    SteamApisOfferPool,
    SteamApisOfferPoolError,
    SteamApisOfferPoolSnapshot,
)

BASE_TIME = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
DEFAULT_NOW = BASE_TIME + timedelta(minutes=5)
DEFAULT_TTL = timedelta(minutes=10)
PURCHASE_LINK = "https://example.invalid/manual/offer?opaque=dummy-secret"
INSPECT_LINK = "steam://rungame/730/dummy-inspect"
MARKET_NAME = "AK-47 | Synthetic (Field-Tested)"
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "steamapis_offer_pool.py"
)


class MutableClock:
    def __init__(self, current: datetime = DEFAULT_NOW) -> None:
        self.current: object = current
        self.calls = 0
        self.error: BaseException | None = None

    def __call__(self) -> datetime:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.current  # type: ignore[return-value]


def _observation(
    *,
    link_suffix: str = "one",
    event_type: SteamApisListingEventType = SteamApisListingEventType.ADDED,
    market_hash_name: str = MARKET_NAME,
    price_cny: Decimal = Decimal("123.45"),
    float_value: Decimal = Decimal("0.1734"),
    paint_seed: int | None = 42,
    days_trade_locked: int | None = 2,
    message_timestamp: datetime = BASE_TIME,
) -> SteamApisListingObservation:
    purchase_link = f"{PURCHASE_LINK}-{link_suffix}"
    return SteamApisListingObservation(
        source_offer_id=make_steamapis_source_offer_id(
            "Buff163",
            "CS2",
            purchase_link,
        ),
        event_type=event_type,
        marketplace="Buff163",
        game="CS2",
        market_hash_name=market_hash_name,
        purchase_link=purchase_link,
        inspect_link=INSPECT_LINK,
        price_cny=price_cny,
        float_value=float_value,
        paint_index=675,
        paint_seed=paint_seed,
        days_trade_locked=days_trade_locked,
        found_at=message_timestamp - timedelta(minutes=1),
        message_timestamp=message_timestamp,
        stickers=(),
    )


def _pool(
    *,
    max_size: int = 10,
    ttl: timedelta = DEFAULT_TTL,
    clock: MutableClock | None = None,
) -> tuple[SteamApisOfferPool, MutableClock]:
    selected_clock = clock or MutableClock()
    return (
        SteamApisOfferPool(max_size=max_size, ttl=ttl, now=selected_clock),
        selected_clock,
    )


def _ids(snapshot: SteamApisOfferPoolSnapshot) -> tuple[str, ...]:
    return tuple(observation.source_offer_id for observation in snapshot.observations)


def test_public_api_is_small_and_exact() -> None:
    assert pool_module.__all__ == (
        "SteamApisOfferPoolError",
        "SteamApisOfferPoolSnapshot",
        "SteamApisOfferPool",
    )
    assert [field.name for field in fields(SteamApisOfferPoolSnapshot)] == [
        "observations"
    ]
    public_pool_names = {
        name for name in vars(SteamApisOfferPool) if not name.startswith("_")
    }
    assert public_pool_names == {
        "ingest",
        "snapshot",
        "get_observation",
        "get_purchase_link",
        "snapshot_candidates",
    }


def test_public_signatures_and_type_hints_are_exact() -> None:
    constructor = list(signature(SteamApisOfferPool).parameters.values())
    assert [parameter.name for parameter in constructor] == ["max_size", "ttl", "now"]
    assert all(parameter.kind is Parameter.KEYWORD_ONLY for parameter in constructor)
    assert get_type_hints(SteamApisOfferPool.ingest) == {
        "observation": SteamApisListingObservation,
        "return": type(None),
    }
    assert get_type_hints(SteamApisOfferPool.snapshot)["return"] is (
        SteamApisOfferPoolSnapshot
    )
    assert get_type_hints(SteamApisOfferPool.snapshot_candidates)["return"] == tuple[
        CandidateListing, ...
    ]


def test_snapshot_is_frozen_keyword_only_tuple_backed_and_repr_safe() -> None:
    observation = _observation()
    snapshot = SteamApisOfferPoolSnapshot(observations=(observation,))

    assert type(snapshot.observations) is tuple
    assert snapshot.observations == (observation,)
    with pytest.raises(TypeError):
        SteamApisOfferPoolSnapshot((observation,))  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        snapshot.observations = ()  # type: ignore[misc]
    rendered = repr(snapshot)
    assert observation.purchase_link not in rendered
    assert observation.inspect_link not in rendered
    assert observation.market_hash_name not in rendered


@pytest.mark.parametrize("max_size", [0, -1, True, 1.0, "1"])
def test_rejects_invalid_max_size(max_size: object) -> None:
    with pytest.raises(SteamApisOfferPoolError):
        SteamApisOfferPool(  # type: ignore[arg-type]
            max_size=max_size,
            ttl=DEFAULT_TTL,
            now=MutableClock(),
        )


@pytest.mark.parametrize(
    "ttl",
    [timedelta(0), timedelta(microseconds=-1), 60, None],
)
def test_rejects_invalid_ttl(ttl: object) -> None:
    with pytest.raises(SteamApisOfferPoolError):
        SteamApisOfferPool(  # type: ignore[arg-type]
            max_size=1,
            ttl=ttl,
            now=MutableClock(),
        )


def test_constructor_and_operations_validate_clock_once_each() -> None:
    pool, clock = _pool()
    assert clock.calls == 1

    observation = _observation()
    pool.ingest(observation)
    pool.snapshot()
    pool.get_observation(observation.source_offer_id)
    pool.get_purchase_link(observation.source_offer_id)
    pool.snapshot_candidates()

    assert clock.calls == 6


@pytest.mark.parametrize(
    "clock_result",
    [datetime(2026, 8, 12, 10, 0), "now", None],
)
def test_rejects_invalid_clock_result(clock_result: object) -> None:
    clock = MutableClock()
    clock.current = clock_result

    with pytest.raises(SteamApisOfferPoolError) as exc_info:
        SteamApisOfferPool(max_size=1, ttl=DEFAULT_TTL, now=clock)

    assert str(exc_info.value) == "invalid SteamApis offer pool contract"


def test_rejects_non_callable_clock_and_redacts_raising_clock() -> None:
    with pytest.raises(SteamApisOfferPoolError):
        SteamApisOfferPool(max_size=1, ttl=DEFAULT_TTL, now=None)  # type: ignore[arg-type]

    clock = MutableClock()
    clock.error = RuntimeError(
        f"Cookie=dummy-cookie {PURCHASE_LINK} {INSPECT_LINK} {MARKET_NAME}"
    )
    with pytest.raises(SteamApisOfferPoolError) as exc_info:
        SteamApisOfferPool(max_size=1, ttl=DEFAULT_TTL, now=clock)

    rendered = f"{exc_info.value!s} {exc_info.value!r}"
    assert rendered == (
        "invalid SteamApis offer pool contract "
        "SteamApisOfferPoolError('invalid SteamApis offer pool contract')"
    )
    assert "dummy-cookie" not in rendered
    assert PURCHASE_LINK not in rendered
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


def test_aware_non_utc_clock_is_normalized_for_expiry() -> None:
    east = timezone(timedelta(hours=8))
    clock = MutableClock(datetime(2026, 8, 12, 18, 9, 59, 999999, tzinfo=east))
    pool, _ = _pool(clock=clock)
    observation = _observation()

    pool.ingest(observation)

    assert pool.get_observation(observation.source_offer_id) == observation


@pytest.mark.parametrize(
    "event_type",
    [SteamApisListingEventType.ADDED, SteamApisListingEventType.UPDATED],
)
def test_added_and_updated_can_first_insert(
    event_type: SteamApisListingEventType,
) -> None:
    pool, _ = _pool()
    observation = _observation(event_type=event_type)

    assert pool.ingest(observation) is None

    assert pool.get_observation(observation.source_offer_id) == observation


@pytest.mark.parametrize(
    "event_type",
    [SteamApisListingEventType.ADDED, SteamApisListingEventType.UPDATED],
)
def test_newer_observation_replaces_regardless_of_event_type(
    event_type: SteamApisListingEventType,
) -> None:
    pool, _ = _pool()
    original = _observation()
    newer = _observation(
        event_type=event_type,
        price_cny=Decimal("99.99"),
        float_value=Decimal("0.11"),
        paint_seed=777,
        message_timestamp=BASE_TIME + timedelta(minutes=1),
    )
    pool.ingest(original)

    pool.ingest(newer)

    assert pool.get_observation(original.source_offer_id) == newer


def test_older_observation_is_ignored() -> None:
    pool, _ = _pool()
    newer = _observation(message_timestamp=BASE_TIME + timedelta(minutes=1))
    older = _observation(price_cny=Decimal("1.00"), message_timestamp=BASE_TIME)
    pool.ingest(newer)

    pool.ingest(older)

    assert pool.get_observation(newer.source_offer_id) == newer


def test_identical_equal_timestamp_is_idempotent() -> None:
    pool, _ = _pool()
    observation = _observation()
    pool.ingest(observation)

    assert pool.ingest(observation) is None

    assert pool.snapshot().observations == (observation,)


def test_conflicting_equal_timestamp_fails_closed_and_preserves_state() -> None:
    pool, _ = _pool()
    original = _observation()
    conflicting = _observation(price_cny=Decimal("1.00"))
    pool.ingest(original)

    with pytest.raises(SteamApisOfferPoolError) as exc_info:
        pool.ingest(conflicting)

    assert str(exc_info.value) == "invalid SteamApis offer pool contract"
    assert pool.get_observation(original.source_offer_id) == original


def test_different_source_ids_coexist() -> None:
    pool, _ = _pool()
    first = _observation(link_suffix="first")
    second = _observation(link_suffix="second")

    pool.ingest(first)
    pool.ingest(second)

    assert set(_ids(pool.snapshot())) == {
        first.source_offer_id,
        second.source_offer_id,
    }


def test_ingest_defensively_reconstructs_and_rejects_tampering() -> None:
    pool, _ = _pool()
    observation = _observation()
    pool.ingest(observation)
    stored = pool.get_observation(observation.source_offer_id)
    assert stored == observation
    assert stored is not observation

    tampered = _observation(link_suffix="tampered")
    object.__setattr__(tampered, "price_cny", Decimal("NaN"))
    with pytest.raises(SteamApisOfferPoolError):
        pool.ingest(tampered)


@pytest.mark.parametrize(
    ("advance", "present"),
    [
        (timedelta(minutes=9, seconds=59, microseconds=999999), True),
        (timedelta(minutes=10), False),
        (timedelta(minutes=11), False),
    ],
)
def test_ttl_boundary_is_inclusive(advance: timedelta, present: bool) -> None:
    clock = MutableClock(BASE_TIME)
    pool, _ = _pool(clock=clock)
    observation = _observation()
    pool.ingest(observation)
    clock.current = BASE_TIME + advance

    assert (pool.get_observation(observation.source_offer_id) is not None) is present


def test_expired_incoming_observation_is_not_stored() -> None:
    pool, _ = _pool()
    expired = _observation(message_timestamp=BASE_TIME - timedelta(minutes=5))

    assert pool.ingest(expired) is None

    assert pool.snapshot().observations == ()


def test_expiry_runs_on_ingest_snapshot_and_both_lookups() -> None:
    methods = ("ingest", "snapshot", "get_observation", "get_purchase_link")
    for method_name in methods:
        clock = MutableClock(BASE_TIME)
        pool, _ = _pool(clock=clock)
        stale = _observation(link_suffix=method_name)
        pool.ingest(stale)
        clock.current = BASE_TIME + DEFAULT_TTL

        if method_name == "ingest":
            pool.ingest(
                _observation(
                    link_suffix="fresh",
                    message_timestamp=BASE_TIME + DEFAULT_TTL,
                )
            )
        elif method_name == "snapshot":
            pool.snapshot()
        elif method_name == "get_observation":
            assert pool.get_observation(stale.source_offer_id) is None
        else:
            assert pool.get_purchase_link(stale.source_offer_id) is None

        assert stale.source_offer_id not in _ids(pool.snapshot())


def test_invalid_operation_clock_does_not_evict_or_mutate() -> None:
    clock = MutableClock(BASE_TIME)
    pool, _ = _pool(clock=clock)
    observation = _observation()
    pool.ingest(observation)
    clock.current = datetime(2026, 8, 12, 10, 10)

    with pytest.raises(SteamApisOfferPoolError):
        pool.snapshot()

    clock.current = BASE_TIME + timedelta(minutes=9)
    assert pool.get_observation(observation.source_offer_id) == observation


def test_capacity_evicts_oldest_observation() -> None:
    clock = MutableClock(BASE_TIME + timedelta(minutes=5))
    pool, _ = _pool(max_size=2, clock=clock)
    oldest = _observation(link_suffix="old", message_timestamp=BASE_TIME)
    middle = _observation(
        link_suffix="middle",
        message_timestamp=BASE_TIME + timedelta(minutes=1),
    )
    newest = _observation(
        link_suffix="new",
        message_timestamp=BASE_TIME + timedelta(minutes=2),
    )

    for observation in (oldest, middle, newest):
        pool.ingest(observation)

    assert set(_ids(pool.snapshot())) == {
        middle.source_offer_id,
        newest.source_offer_id,
    }


def test_capacity_tie_evicts_lexically_ascending_source_id() -> None:
    pool, _ = _pool(max_size=1)
    first = _observation(link_suffix="first")
    second = _observation(link_suffix="second")

    pool.ingest(first)
    pool.ingest(second)

    assert _ids(pool.snapshot()) == (max(first.source_offer_id, second.source_offer_id),)


def test_repeated_overflow_is_bounded_and_deterministic() -> None:
    observations = tuple(
        _observation(
            link_suffix=str(index),
            message_timestamp=BASE_TIME + timedelta(seconds=index),
        )
        for index in range(5)
    )
    first_pool, _ = _pool(max_size=2)
    second_pool, _ = _pool(max_size=2)

    for observation in observations:
        first_pool.ingest(observation)
    for observation in reversed(observations):
        second_pool.ingest(observation)

    expected = {item.source_offer_id for item in observations[-2:]}
    assert set(_ids(first_pool.snapshot())) == expected
    assert set(_ids(second_pool.snapshot())) == expected


def test_ttl_eviction_precedes_capacity_eviction() -> None:
    clock = MutableClock(BASE_TIME)
    pool, _ = _pool(max_size=1, ttl=timedelta(minutes=2), clock=clock)
    expiring = _observation()
    pool.ingest(expiring)
    clock.current = BASE_TIME + timedelta(minutes=2)
    fresh = _observation(
        link_suffix="fresh",
        message_timestamp=BASE_TIME + timedelta(minutes=2),
    )

    pool.ingest(fresh)

    assert pool.snapshot().observations == (fresh,)


def test_incoming_oldest_observation_can_evict_itself() -> None:
    pool, _ = _pool(max_size=1)
    current = _observation(
        link_suffix="current",
        message_timestamp=BASE_TIME + timedelta(minutes=1),
    )
    incoming = _observation(link_suffix="incoming", message_timestamp=BASE_TIME)
    pool.ingest(current)

    pool.ingest(incoming)

    assert pool.snapshot().observations == (current,)


def test_snapshot_uses_exact_stable_sort_order() -> None:
    observations = (
        _observation(link_suffix="z", market_hash_name="B", price_cny=Decimal("1")),
        _observation(link_suffix="a", market_hash_name="A", price_cny=Decimal("2")),
        _observation(
            link_suffix="b",
            market_hash_name="A",
            price_cny=Decimal("1"),
            float_value=Decimal("0.2"),
        ),
        _observation(
            link_suffix="c",
            market_hash_name="A",
            price_cny=Decimal("1"),
            float_value=Decimal("0.1"),
            message_timestamp=BASE_TIME + timedelta(seconds=1),
        ),
        _observation(
            link_suffix="d",
            market_hash_name="A",
            price_cny=Decimal("1"),
            float_value=Decimal("0.1"),
        ),
        _observation(
            link_suffix="e",
            market_hash_name="A",
            price_cny=Decimal("1"),
            float_value=Decimal("0.1"),
        ),
    )
    pool, _ = _pool(max_size=len(observations))
    for observation in reversed(observations):
        pool.ingest(observation)

    snapshot = pool.snapshot()

    assert snapshot.observations == tuple(
        sorted(
            observations,
            key=lambda item: (
                item.market_hash_name,
                item.price_cny,
                item.float_value,
                item.message_timestamp,
                item.source_offer_id,
            ),
        )
    )
    assert pool.snapshot().observations == snapshot.observations


def test_snapshot_preserves_duplicate_market_names_and_is_independent() -> None:
    pool, _ = _pool()
    first = _observation(link_suffix="first")
    second = _observation(link_suffix="second")
    pool.ingest(first)
    retained = pool.snapshot()
    pool.ingest(second)

    assert retained.observations == (first,)
    assert len(pool.snapshot().observations) == 2


def test_provenance_lookup_returns_observation_and_opaque_link() -> None:
    pool, _ = _pool()
    observation = _observation()
    pool.ingest(observation)

    retained = pool.get_observation(observation.source_offer_id)

    assert retained == observation
    assert retained is not observation
    assert pool.get_purchase_link(observation.source_offer_id) == (
        observation.purchase_link
    )


def test_valid_unknown_provenance_returns_none() -> None:
    pool, _ = _pool()
    unknown = "0" * 64

    assert pool.get_observation(unknown) is None
    assert pool.get_purchase_link(unknown) is None


@pytest.mark.parametrize("invalid", [None, "", "A" * 64, "g" * 64, "0" * 63])
def test_invalid_source_id_fails_with_fixed_error(invalid: object) -> None:
    pool, _ = _pool()

    with pytest.raises(SteamApisOfferPoolError) as exc_info:
        pool.get_observation(invalid)  # type: ignore[arg-type]

    assert str(exc_info.value) == "invalid SteamApis offer pool contract"


def test_candidate_projection_reuses_adapter_once_in_snapshot_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, _ = _pool()
    first = _observation(link_suffix="first", market_hash_name="B")
    second = _observation(link_suffix="second", market_hash_name="A")
    pool.ingest(first)
    pool.ingest(second)
    calls: list[SteamApisListingObservation] = []

    def recording_adapter(observation: SteamApisListingObservation) -> CandidateListing:
        calls.append(observation)
        return CandidateListing(
            goods_id=f"steamapis:buff163:{observation.source_offer_id}",
            listing_id=f"steamapis:buff163:{observation.source_offer_id}",
            market_hash_name=observation.market_hash_name,
            price_cny=observation.price_cny,
            float_value=float(observation.float_value),
            paint_seed=observation.paint_seed,
            inspect_link=observation.inspect_link,
            source="steamapis:buff163",
            scanned_at=observation.message_timestamp,
            raw=None,
        )

    monkeypatch.setattr(
        pool_module,
        "adapt_steamapis_listing_to_candidate",
        recording_adapter,
    )

    candidates = pool.snapshot_candidates()

    assert calls == list(pool.snapshot().observations)
    assert tuple(candidate.market_hash_name for candidate in candidates) == ("A", "B")
    assert all(
        observation.purchase_link not in repr(candidate)
        for observation, candidate in zip(calls, candidates, strict=True)
    )


def test_updated_observation_changes_candidate_economics_without_storage() -> None:
    pool, _ = _pool()
    original = _observation()
    updated = _observation(
        event_type=SteamApisListingEventType.UPDATED,
        price_cny=Decimal("50.00"),
        float_value=Decimal("0.1"),
        message_timestamp=BASE_TIME + timedelta(minutes=1),
    )
    pool.ingest(original)
    first_candidate = pool.snapshot_candidates()[0]
    pool.ingest(updated)
    second_candidate = pool.snapshot_candidates()[0]

    assert first_candidate.price_cny == original.price_cny
    assert second_candidate.price_cny == updated.price_cny
    assert "CandidateListing" not in repr(pool.__dict__)


def test_candidate_projection_does_not_filter_trade_lock() -> None:
    pool, _ = _pool()
    unknown = _observation(link_suffix="unknown", days_trade_locked=None)
    locked = _observation(link_suffix="locked", days_trade_locked=7)
    pool.ingest(unknown)
    pool.ingest(locked)

    assert len(pool.snapshot_candidates()) == 2


def test_candidate_projection_failure_is_fixed_and_returns_no_partial_tuple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, _ = _pool()
    first = _observation(link_suffix="first", market_hash_name="A")
    second = _observation(link_suffix="second", market_hash_name="B")
    pool.ingest(first)
    pool.ingest(second)
    calls: list[str] = []

    original_adapter = pool_module.adapt_steamapis_listing_to_candidate

    def staged_adapter(observation: SteamApisListingObservation) -> CandidateListing:
        calls.append(observation.source_offer_id)
        if len(calls) == 2:
            raise RuntimeError(
                f"token=dummy-token {observation.purchase_link} {MARKET_NAME}"
            )
        return original_adapter(observation)

    monkeypatch.setattr(pool_module, "adapt_steamapis_listing_to_candidate", staged_adapter)

    with pytest.raises(SteamApisOfferPoolError) as exc_info:
        pool.snapshot_candidates()

    assert len(calls) == 2
    rendered = f"{exc_info.value!s} {exc_info.value!r}"
    assert rendered == (
        "invalid SteamApis offer pool contract "
        "SteamApisOfferPoolError('invalid SteamApis offer pool contract')"
    )
    assert "dummy-token" not in rendered
    assert first.purchase_link not in rendered
    assert second.purchase_link not in rendered
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


def test_expired_observation_is_not_projected() -> None:
    clock = MutableClock(BASE_TIME)
    pool, _ = _pool(clock=clock)
    pool.ingest(_observation())
    clock.current = BASE_TIME + DEFAULT_TTL

    assert pool.snapshot_candidates() == ()


@pytest.mark.parametrize(
    "error",
    [MemoryError("resource-dummy"), asyncio.CancelledError(), KeyboardInterrupt()],
)
def test_clock_memory_and_control_flow_errors_propagate(error: BaseException) -> None:
    clock = MutableClock()
    pool, _ = _pool(clock=clock)
    clock.error = error

    with pytest.raises(type(error)) as exc_info:
        pool.snapshot()

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


def test_pool_imports_only_required_domains_and_standard_library() -> None:
    assert _imported_modules(MODULE_PATH) == {
        "__future__",
        "collections.abc",
        "dataclasses",
        "datetime",
        "decimal",
        "app.services.market_scan_service",
        "app.services.steamapis_candidate_adapter",
        "app.services.steamapis_listing",
    }


def test_pool_has_no_external_runtime_background_or_url_calls() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    called_names = {
        node.func.id.casefold()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert called_names.isdisjoint(
        {
            "create_task",
            "getenv",
            "open",
            "parse_qs",
            "qualify",
            "request",
            "sleep",
            "solve_recipes",
            "thread",
            "urlopen",
            "urlparse",
            "urlsplit",
        }
    )
    forbidden_import_fragments = {
        "asyncio",
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
        "thread",
        "urllib",
        "websocket",
    }
    assert all(
        fragment not in module
        for module in _imported_modules(MODULE_PATH)
        for fragment in forbidden_import_fragments
    )


def test_protected_runtime_modules_do_not_reverse_import_pool() -> None:
    project_root = Path(__file__).resolve().parents[1]
    paths = [
        project_root / "app" / "main.py",
        project_root / "app" / "config.py",
        project_root / "app" / "services" / "steamapis_listing.py",
        project_root / "app" / "services" / "steamapis_candidate_adapter.py",
        project_root / "app" / "services" / "buff_listing_solver_adapter.py",
        project_root / "app" / "services" / "market_scan_service.py",
        project_root / "app" / "services" / "recipe_solver.py",
        project_root / "app" / "services" / "valuation_service.py",
        project_root / "app" / "services" / "pipeline_service.py",
        project_root / "app" / "jobs" / "scheduler.py",
    ]

    for path in paths:
        assert "app.services.steamapis_offer_pool" not in _imported_modules(path)
