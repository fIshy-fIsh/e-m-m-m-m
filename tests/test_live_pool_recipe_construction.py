from __future__ import annotations

import ast
import asyncio
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from inspect import Parameter, signature
from pathlib import Path
from typing import get_type_hints

import pytest

import app.services.live_pool_recipe_construction as pool_construction_module
from app.services.live_metadata_catalog import (
    LiveCandidateClassification,
    LiveCandidateRejectionReason,
    SkinMetadataCatalog,
)
from app.services.live_pool_recipe_construction import (
    LivePoolRecipeConstructionError,
    LivePoolRecipeConstructionResult,
    construct_live_recipes_from_pool,
)
from app.services.live_recipe_construction import LiveRecipeConstructionResult
from app.services.metadata_models import SkinMetadata
from app.services.recipe_solver import RecipeSolverConfig
from app.services.steamapis_listing import (
    SteamApisListingEventType,
    SteamApisListingObservation,
    make_steamapis_source_offer_id,
)
from app.services.steamapis_offer_pool import SteamApisOfferPool

BASE_TIME = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
POOL_NOW = BASE_TIME + timedelta(minutes=5)
DEFAULT_TTL = timedelta(hours=1)
FIXED_ERROR = "Live pool recipe construction failed"
PURCHASE_BASE = "https://example.invalid/manual/current-pool"
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "live_pool_recipe_construction.py"
)


class MutableClock:
    def __init__(self, current: datetime = POOL_NOW) -> None:
        self.current = current
        self.calls = 0
        self.error: BaseException | None = None

    def __call__(self) -> datetime:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.current


class RaisingPool:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.snapshot_calls = 0

    def snapshot(self) -> object:
        self.snapshot_calls += 1
        raise self.error


class IntSubclass(int):
    pass


class DirectBaseException(BaseException):
    pass


def _observation(
    *,
    index: int,
    market_hash_name: str,
    price_cny: str,
    float_value: str,
    paint_seed: int,
    link_group: str = "eligible",
    event_type: SteamApisListingEventType = SteamApisListingEventType.ADDED,
    message_timestamp: datetime = BASE_TIME,
) -> SteamApisListingObservation:
    purchase_link = f"{PURCHASE_BASE}/{link_group}/{index}"
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
        inspect_link=f"steam://inspect/current-pool-{index}",
        price_cny=Decimal(price_cny),
        float_value=Decimal(float_value),
        paint_index=100 + index,
        paint_seed=paint_seed,
        days_trade_locked=None,
        found_at=message_timestamp - timedelta(minutes=1),
        message_timestamp=message_timestamp,
        stickers=(),
    )


def _skin(
    *,
    market_hash_name: str,
    rarity: str,
    collection_name: str,
) -> SkinMetadata:
    return SkinMetadata(
        market_hash_name=market_hash_name,
        name=market_hash_name,
        weapon="Synthetic Weapon",
        rarity=rarity,
        category="Rifle",
        collection_name=collection_name,
        min_float=0.0,
        max_float=1.0,
        stattrak=False,
        souvenir=False,
        raw={"discarded": "synthetic"},
    )


def _skins() -> list[SkinMetadata]:
    return [
        _skin(
            market_hash_name="Alpha Input",
            rarity="Restricted",
            collection_name="Collection Alpha",
        ),
        _skin(
            market_hash_name="Beta Input",
            rarity="Restricted",
            collection_name="Collection Beta",
        ),
        _skin(
            market_hash_name="Alpha Output",
            rarity="Classified",
            collection_name="Collection Alpha",
        ),
        _skin(
            market_hash_name="Beta Output",
            rarity="Classified",
            collection_name="Collection Beta",
        ),
    ]


def _observations(*, include_rejected: bool = True) -> list[SteamApisListingObservation]:
    observations = [
        _observation(
            index=index,
            market_hash_name="Alpha Input" if index < 6 else "Beta Input",
            price_cny=f"{10 + index}.00",
            float_value=f"0.{10 + index}",
            paint_seed=700 + index,
        )
        for index in range(11)
    ]
    if include_rejected:
        observations.append(
            _observation(
                index=99,
                market_hash_name="Unknown Input",
                price_cny="1.00",
                float_value="0.01",
                paint_seed=999,
                link_group="rejected",
            )
        )
    return observations


def _config() -> RecipeSolverConfig:
    return RecipeSolverConfig(
        input_rarity="Restricted",
        input_count=10,
        sell_fee_rate=Decimal("0.025"),
        max_candidates_per_collection=None,
        target_stattrak=False,
        target_souvenir=False,
    )


def _pool(
    observations: list[SteamApisListingObservation] | None = None,
    *,
    max_size: int = 100,
    ttl: timedelta = DEFAULT_TTL,
    clock: MutableClock | None = None,
) -> tuple[SteamApisOfferPool, MutableClock]:
    selected_clock = clock or MutableClock()
    pool = SteamApisOfferPool(
        max_size=max_size,
        ttl=ttl,
        now=selected_clock,
    )
    for observation in observations or []:
        pool.ingest(observation)
    return pool, selected_clock


def _context() -> tuple[SteamApisOfferPool, SkinMetadataCatalog, RecipeSolverConfig]:
    pool, _ = _pool(_observations())
    return pool, SkinMetadataCatalog(skins=_skins()), _config()


def _empty_construction() -> LiveRecipeConstructionResult:
    return LiveRecipeConstructionResult(
        classification=LiveCandidateClassification(
            eligible=(),
            rejected=(),
            buckets=(),
        ),
        recipes=(),
    )


def _construct(
    pool: SteamApisOfferPool,
    catalog: SkinMetadataCatalog,
    config: RecipeSolverConfig,
) -> LivePoolRecipeConstructionResult:
    return construct_live_recipes_from_pool(
        pool=pool,
        catalog=catalog,
        solver_config=config,
    )


def _assert_fixed_error(
    pool: object,
    catalog: SkinMetadataCatalog,
    config: RecipeSolverConfig,
) -> LivePoolRecipeConstructionError:
    with pytest.raises(LivePoolRecipeConstructionError) as exc_info:
        construct_live_recipes_from_pool(
            pool=pool,  # type: ignore[arg-type]
            catalog=catalog,
            solver_config=config,
        )
    assert str(exc_info.value) == FIXED_ERROR
    assert repr(exc_info.value) == f"LivePoolRecipeConstructionError('{FIXED_ERROR}')"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True
    return exc_info.value


def test_public_api_signature_and_fields_are_exact() -> None:
    assert pool_construction_module.__all__ == (
        "LivePoolRecipeConstructionError",
        "LivePoolRecipeConstructionResult",
        "construct_live_recipes_from_pool",
    )
    assert [field.name for field in fields(LivePoolRecipeConstructionResult)] == [
        "snapshot_observation_count",
        "construction",
    ]
    parameters = list(signature(construct_live_recipes_from_pool).parameters.values())
    assert [(value.name, value.kind) for value in parameters] == [
        ("pool", Parameter.KEYWORD_ONLY),
        ("catalog", Parameter.KEYWORD_ONLY),
        ("solver_config", Parameter.KEYWORD_ONLY),
    ]
    hints = get_type_hints(construct_live_recipes_from_pool)
    assert hints["pool"] is SteamApisOfferPool
    assert hints["catalog"] is SkinMetadataCatalog
    assert hints["solver_config"] is RecipeSolverConfig
    assert hints["return"] is LivePoolRecipeConstructionResult


def test_result_is_frozen_keyword_only_repr_hidden_and_detached() -> None:
    construction = _empty_construction()
    result = LivePoolRecipeConstructionResult(
        snapshot_observation_count=0,
        construction=construction,
    )

    assert result.snapshot_observation_count == 0
    assert result.construction == construction
    assert result.construction is not construction
    assert "snapshot_observation_count" not in repr(result)
    with pytest.raises(TypeError):
        LivePoolRecipeConstructionResult(0, construction)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.snapshot_observation_count = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    "count",
    [-1, True, 1.0, "1", None, IntSubclass(1)],
)
def test_result_rejects_invalid_snapshot_counts(count: object) -> None:
    with pytest.raises(LivePoolRecipeConstructionError) as exc_info:
        LivePoolRecipeConstructionResult(
            snapshot_observation_count=count,  # type: ignore[arg-type]
            construction=_empty_construction(),
        )

    assert str(exc_info.value) == FIXED_ERROR
    assert exc_info.value.__cause__ is None


def test_result_rejects_wrong_construction_type_and_count_mismatch() -> None:
    with pytest.raises(LivePoolRecipeConstructionError):
        LivePoolRecipeConstructionResult(
            snapshot_observation_count=0,
            construction=None,  # type: ignore[arg-type]
        )
    with pytest.raises(LivePoolRecipeConstructionError):
        LivePoolRecipeConstructionResult(
            snapshot_observation_count=1,
            construction=_empty_construction(),
        )


def test_empty_pool_is_valid_empty_construction() -> None:
    pool, _ = _pool()

    result = _construct(pool, SkinMetadataCatalog(skins=_skins()), _config())

    assert result.snapshot_observation_count == 0
    assert result.construction.classification.eligible == ()
    assert result.construction.classification.rejected == ()
    assert result.construction.recipes == ()


def test_rejected_only_pool_is_valid_and_preserves_rejection() -> None:
    rejected = _observation(
        index=99,
        market_hash_name="Unknown Input",
        price_cny="1.00",
        float_value="0.01",
        paint_seed=999,
        link_group="rejected-only",
    )
    pool, _ = _pool([rejected])

    result = _construct(pool, SkinMetadataCatalog(skins=_skins()), _config())

    assert result.snapshot_observation_count == 1
    assert result.construction.classification.eligible == ()
    assert len(result.construction.classification.rejected) == 1
    assert result.construction.classification.rejected[0].reason_code is (
        LiveCandidateRejectionReason.METADATA_NOT_FOUND
    )
    assert result.construction.recipes == ()


def test_real_current_pool_constructs_one_multi_collection_recipe() -> None:
    pool, catalog, config = _context()

    result = _construct(pool, catalog, config)

    classification = result.construction.classification
    assert result.snapshot_observation_count == 12
    assert len(classification.eligible) == 11
    assert len(classification.rejected) == 1
    assert classification.buckets[0].affected_collections == frozenset(
        {"Collection Alpha", "Collection Beta"}
    )
    assert len(result.construction.recipes) == 1
    recipe = result.construction.recipes[0]
    assert len(recipe.recipe.input_items) == 10
    assert {item.collection_name for item in recipe.recipe.input_items} == {
        "Collection Alpha",
        "Collection Beta",
    }
    assert len(recipe.selected_source_offer_ids) == 10
    assert len(set(recipe.selected_source_offer_ids)) == 10


def test_selected_source_ids_remain_step_2e_order_without_wrapper_copy() -> None:
    pool, catalog, config = _context()

    first = _construct(pool, catalog, config)
    second = _construct(pool, catalog, config)

    first_ids = first.construction.recipes[0].selected_source_offer_ids
    assert first.snapshot_observation_count == second.snapshot_observation_count
    assert first.construction == second.construction
    assert first_ids == second.construction.recipes[0].selected_source_offer_ids
    assert all(source_id not in repr(first) for source_id in first_ids)
    assert PURCHASE_BASE not in repr(first)


def test_snapshot_and_step_2e_are_each_called_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, catalog, config = _context()
    captured_snapshot = pool.snapshot()
    snapshot_calls = 0
    construction_calls = 0
    original_construct = pool_construction_module.construct_live_recipes

    def snapshot() -> object:
        nonlocal snapshot_calls
        snapshot_calls += 1
        return captured_snapshot

    def construct(**kwargs: object) -> LiveRecipeConstructionResult:
        nonlocal construction_calls
        construction_calls += 1
        assert kwargs == {
            "snapshot": captured_snapshot,
            "catalog": catalog,
            "solver_config": config,
        }
        return original_construct(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(pool, "snapshot", snapshot)
    monkeypatch.setattr(pool_construction_module, "construct_live_recipes", construct)

    result = _construct(pool, catalog, config)

    assert result.snapshot_observation_count == 12
    assert snapshot_calls == 1
    assert construction_calls == 1


def test_newer_update_is_used_and_older_update_does_not_resurface() -> None:
    observations = _observations(include_rejected=False)[:10]
    original = observations[0]
    newer = _observation(
        index=0,
        market_hash_name="Alpha Input",
        price_cny="0.50",
        float_value="0.01",
        paint_seed=808,
        event_type=SteamApisListingEventType.UPDATED,
        message_timestamp=BASE_TIME + timedelta(minutes=1),
    )
    older = _observation(
        index=0,
        market_hash_name="Alpha Input",
        price_cny="999.00",
        float_value="0.99",
        paint_seed=909,
        event_type=SteamApisListingEventType.UPDATED,
        message_timestamp=BASE_TIME - timedelta(minutes=1),
    )
    pool, _ = _pool(observations)
    pool.ingest(newer)
    pool.ingest(older)

    result = _construct(pool, SkinMetadataCatalog(skins=_skins()), _config())

    selected = result.construction.recipes[0].recipe.input_items
    matching = [item for item in selected if item.market_hash_name == original.market_hash_name]
    assert any(item.price_cny == Decimal("0.50") for item in matching)
    assert all(item.price_cny != Decimal("999.00") for item in matching)
    binding = next(
        item
        for item in result.construction.classification.eligible
        if item.source_offer_id == original.source_offer_id
    )
    assert binding.candidate.price_cny == Decimal("0.50")
    assert binding.candidate.paint_seed == 808


def test_snapshot_lazily_evicts_expired_before_construction() -> None:
    clock = MutableClock(BASE_TIME)
    valid = _observations(include_rejected=False)[:10]
    expired = _observation(
        index=99,
        market_hash_name="Unknown Input",
        price_cny="1.00",
        float_value="0.01",
        paint_seed=999,
        link_group="expires",
    )
    pool, _ = _pool([*valid, expired], ttl=timedelta(minutes=10), clock=clock)
    calls_before = clock.calls
    clock.current = BASE_TIME + timedelta(minutes=10)

    result = _construct(pool, SkinMetadataCatalog(skins=_skins()), _config())

    assert result.snapshot_observation_count == 0
    assert result.construction.classification.eligible == ()
    assert result.construction.classification.rejected == ()
    assert clock.calls == calls_before + 1


def test_capacity_evicted_history_does_not_resurface() -> None:
    observations = _observations(include_rejected=False)
    pool, _ = _pool(observations, max_size=10)
    retained_ids = {
        observation.source_offer_id for observation in pool.snapshot().observations
    }
    evicted_ids = {
        observation.source_offer_id for observation in observations
    } - retained_ids

    result = _construct(pool, SkinMetadataCatalog(skins=_skins()), _config())

    classified_ids = {
        binding.source_offer_id
        for binding in result.construction.classification.eligible
    }
    assert result.snapshot_observation_count == 10
    assert len(evicted_ids) == 1
    assert evicted_ids.isdisjoint(classified_ids)
    assert len(result.construction.recipes) == 1


def test_snapshot_clock_failure_is_wrapped_and_skips_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, clock = _pool(_observations())
    sensitive = f"Cookie=secret {PURCHASE_BASE} market price float seed"
    clock.error = RuntimeError(sensitive)
    construction_calls = 0

    def construct(**_kwargs: object) -> LiveRecipeConstructionResult:
        nonlocal construction_calls
        construction_calls += 1
        return _empty_construction()

    monkeypatch.setattr(pool_construction_module, "construct_live_recipes", construct)

    error = _assert_fixed_error(pool, SkinMetadataCatalog(skins=_skins()), _config())

    assert construction_calls == 0
    assert sensitive not in f"{error!s} {error!r}"


def test_construction_failure_is_wrapped_after_one_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, catalog, config = _context()
    sensitive = f"apiKey=secret {PURCHASE_BASE} source-id price float seed"
    clock_calls = 0
    original_snapshot = pool.snapshot

    def snapshot() -> object:
        nonlocal clock_calls
        clock_calls += 1
        return original_snapshot()

    def construct(**_kwargs: object) -> LiveRecipeConstructionResult:
        raise RuntimeError(sensitive)

    monkeypatch.setattr(pool, "snapshot", snapshot)
    monkeypatch.setattr(pool_construction_module, "construct_live_recipes", construct)

    error = _assert_fixed_error(pool, catalog, config)

    assert clock_calls == 1
    assert sensitive not in f"{error!s} {error!r}"


def test_ttl_eviction_remains_after_later_construction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = MutableClock(BASE_TIME)
    expired = _observation(
        index=1,
        market_hash_name="Alpha Input",
        price_cny="10.00",
        float_value="0.10",
        paint_seed=1,
    )
    pool, _ = _pool([expired], ttl=timedelta(minutes=10), clock=clock)
    clock.current = BASE_TIME + timedelta(minutes=10)

    def construct(**_kwargs: object) -> LiveRecipeConstructionResult:
        raise RuntimeError("late synthetic failure")

    monkeypatch.setattr(pool_construction_module, "construct_live_recipes", construct)

    _assert_fixed_error(pool, SkinMetadataCatalog(skins=_skins()), _config())

    assert pool.snapshot().observations == ()


@pytest.mark.parametrize(
    "error",
    [MemoryError("memory"), asyncio.CancelledError("cancel")],
)
@pytest.mark.parametrize("stage", ["snapshot", "construction"])
def test_memory_and_cancellation_propagate_by_identity(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    error: BaseException,
) -> None:
    catalog = SkinMetadataCatalog(skins=_skins())
    config = _config()
    if stage == "snapshot":
        pool: object = RaisingPool(error)
    else:
        pool, _ = _pool()

        def construct(**_kwargs: object) -> LiveRecipeConstructionResult:
            raise error

        monkeypatch.setattr(pool_construction_module, "construct_live_recipes", construct)

    with pytest.raises(type(error)) as exc_info:
        construct_live_recipes_from_pool(
            pool=pool,  # type: ignore[arg-type]
            catalog=catalog,
            solver_config=config,
        )

    assert exc_info.value is error


@pytest.mark.parametrize(
    "error",
    [KeyboardInterrupt("interrupt"), DirectBaseException("direct")],
)
def test_other_base_exceptions_propagate_by_identity(error: BaseException) -> None:
    pool = RaisingPool(error)

    with pytest.raises(type(error)) as exc_info:
        construct_live_recipes_from_pool(
            pool=pool,  # type: ignore[arg-type]
            catalog=SkinMetadataCatalog(skins=_skins()),
            solver_config=_config(),
        )

    assert exc_info.value is error


def test_architecture_is_one_snapshot_one_step_2e_without_forbidden_boundaries() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    assert imports == {
        "__future__",
        "asyncio",
        "dataclasses",
        "app.services.live_metadata_catalog",
        "app.services.live_recipe_construction",
        "app.services.recipe_solver",
        "app.services.steamapis_offer_pool",
    }
    assert calls.count("snapshot") == 1
    assert calls.count("construct_live_recipes") == 1
    forbidden_calls = {
        "classify_steamapis_snapshot",
        "adapt_steamapis_listing_to_candidate",
        "construct_recipe_selections",
        "solve_recipes",
        "ingest",
        "get_observation",
        "get_purchase_link",
        "snapshot_candidates",
        "value_live_recipes",
        "calculate_opportunity_metrics",
        "evaluate_opportunity",
        "run_steamapis_offer_session",
        "create_task",
        "gather",
        "sleep",
        "run_in_executor",
    }
    assert forbidden_calls.isdisjoint(calls)
    assert not any(
        fragment in imported
        for imported in imports
        for fragment in (
            "websocket",
            "steamapis_offer_session",
            "valuation",
            "steamdt",
            "buff",
            "redis",
            "discord",
            "fastapi",
            "sqlalchemy",
            "scheduler",
            "logging",
            "config",
        )
    )
    assert "purchaseLink" not in source
    assert "purchase_link" not in source
    assert "source_offer_id" not in source
    assert "while " not in source
