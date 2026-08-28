import ast
from collections.abc import Iterator
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from app.services.price_cache import PriceCacheKey
from app.services.steamdt_refresh_planner import (
    SteamDTRefreshPlan,
    SteamDTRefreshPlanChunk,
    SteamDTRefreshPlanItem,
    SteamDTRefreshPlanner,
    SteamDTRefreshPlannerValidationError,
)


class OneShotItems:
    def __init__(self, values: list[object]) -> None:
        self.values = values
        self.iter_calls = 0
        self.yielded = 0

    def __iter__(self) -> Iterator[object]:
        self.iter_calls += 1
        if self.iter_calls > 1:
            raise AssertionError("input iterable was consumed more than once")
        for value in self.values:
            self.yielded += 1
            yield value


def _item(
    name: str,
    *,
    first_seen: int = 0,
    occurrences: int = 1,
    source: str = "steamdt",
) -> SteamDTRefreshPlanItem:
    return SteamDTRefreshPlanItem(
        key=PriceCacheKey(market_hash_name=name, source=source),
        first_seen_input_index=first_seen,
        occurrence_count=occurrences,
    )


def _plan_for_items(
    items: tuple[SteamDTRefreshPlanItem, ...],
    *,
    chunk_size: int = 2,
    source: str = "steamdt",
) -> SteamDTRefreshPlan:
    chunks = tuple(
        SteamDTRefreshPlanChunk(
            chunk_index=start // chunk_size,
            start_unique_index=start,
            items=items[start : start + chunk_size],
        )
        for start in range(0, len(items), chunk_size)
    )
    return SteamDTRefreshPlan(
        source=source,
        chunk_size=chunk_size,
        ordered_unique_items=items,
        chunks=chunks,
    )


def test_empty_input_builds_a_canonical_empty_plan() -> None:
    plan = SteamDTRefreshPlanner(chunk_size=3, source=" steamdt ").plan(iter(()))

    assert plan.source == "steamdt"
    assert plan.chunk_size == 3
    assert plan.input_count == 0
    assert plan.unique_count == 0
    assert plan.duplicate_count == 0
    assert plan.ordered_unique_items == ()
    assert plan.ordered_unique_keys == ()
    assert plan.ordered_unique_market_hash_names == ()
    assert plan.chunks == ()


def test_stable_dedup_uses_complete_canonical_keys_and_auditable_counts() -> None:
    plan = SteamDTRefreshPlanner(chunk_size=2).plan(
        [" A ", "B", "A", " A ", "a"]
    )

    assert plan.ordered_unique_market_hash_names == ("A", "B", "a")
    assert plan.ordered_unique_keys == (
        PriceCacheKey(market_hash_name="A"),
        PriceCacheKey(market_hash_name="B"),
        PriceCacheKey(market_hash_name="a"),
    )
    assert [item.first_seen_input_index for item in plan.ordered_unique_items] == [
        0,
        1,
        4,
    ]
    assert [item.occurrence_count for item in plan.ordered_unique_items] == [3, 1, 1]
    assert plan.input_count == 5
    assert plan.unique_count == 3
    assert plan.duplicate_count == 2
    assert [chunk.chunk_index for chunk in plan.chunks] == [0, 1]
    assert [chunk.start_unique_index for chunk in plan.chunks] == [0, 2]
    assert [chunk.size for chunk in plan.chunks] == [2, 1]
    assert [chunk.market_hash_names for chunk in plan.chunks] == [
        ("A", "B"),
        ("a",),
    ]


def test_single_item_preserves_the_full_default_cache_key() -> None:
    plan = SteamDTRefreshPlanner(chunk_size=4).plan([" AK-47 | Redline "])

    assert plan.ordered_unique_keys == (
        PriceCacheKey(market_hash_name="AK-47 | Redline"),
    )
    assert plan.ordered_unique_items[0].market_hash_name == "AK-47 | Redline"
    assert plan.ordered_unique_items[0].first_seen_input_index == 0
    assert plan.ordered_unique_items[0].occurrence_count == 1


@pytest.mark.parametrize(
    ("names", "chunk_size", "expected_chunks"),
    [
        (["A", "B", "C"], 1, (("A",), ("B",), ("C",))),
        (["A", "B", "C", "D"], 2, (("A", "B"), ("C", "D"))),
        (
            ["A", "B", "C", "D", "E"],
            2,
            (("A", "B"), ("C", "D"), ("E",)),
        ),
        (["A", "B"], 5, (("A", "B"),)),
    ],
)
def test_chunking_is_contiguous_and_zero_based(
    names: list[str],
    chunk_size: int,
    expected_chunks: tuple[tuple[str, ...], ...],
) -> None:
    plan = SteamDTRefreshPlanner(chunk_size=chunk_size).plan(names)

    assert tuple(chunk.market_hash_names for chunk in plan.chunks) == expected_chunks
    assert tuple(chunk.chunk_index for chunk in plan.chunks) == tuple(
        range(len(expected_chunks))
    )
    assert tuple(chunk.start_unique_index for chunk in plan.chunks) == tuple(
        index * chunk_size for index in range(len(expected_chunks))
    )
    assert tuple(item for chunk in plan.chunks for item in chunk.items) == (
        plan.ordered_unique_items
    )
    assert all(chunk.size == chunk_size for chunk in plan.chunks[:-1])
    assert 1 <= plan.chunks[-1].size <= chunk_size


def test_one_shot_iterable_is_consumed_exactly_once() -> None:
    names = OneShotItems(["A", "B", "A"])

    plan = SteamDTRefreshPlanner(chunk_size=2).plan(names)  # type: ignore[arg-type]

    assert names.iter_calls == 1
    assert names.yielded == 3
    assert plan.ordered_unique_market_hash_names == ("A", "B")


def test_invalid_midstream_item_fails_closed_without_consuming_later_values() -> None:
    names = OneShotItems(["A", None, "not-consumed"])

    with pytest.raises(SteamDTRefreshPlannerValidationError) as exc_info:
        SteamDTRefreshPlanner(chunk_size=2).plan(names)  # type: ignore[arg-type]

    assert exc_info.value.field == "market_hash_name"
    assert exc_info.value.input_index == 1
    assert str(exc_info.value) == "invalid market_hash_name at input index 1"
    assert isinstance(exc_info.value.__cause__, TypeError)
    assert names.iter_calls == 1
    assert names.yielded == 2


def test_plan_is_detached_from_mutable_input_and_model_sequences() -> None:
    names = ["A", "B"]
    planner = SteamDTRefreshPlanner(chunk_size=2)
    plan = planner.plan(names)
    item_list = list(plan.ordered_unique_items)
    chunk_list = list(plan.chunks)

    copied_plan = SteamDTRefreshPlan(
        source="steamdt",
        chunk_size=2,
        ordered_unique_items=item_list,  # type: ignore[arg-type]
        chunks=chunk_list,  # type: ignore[arg-type]
    )
    names[:] = ["changed"]
    item_list.clear()
    chunk_list.clear()

    assert copied_plan == plan
    assert copied_plan.ordered_unique_market_hash_names == ("A", "B")


def test_planning_is_deterministic_for_equivalent_ordered_inputs() -> None:
    first = SteamDTRefreshPlanner(chunk_size=2).plan(iter([" A ", "B", "A"]))
    second = SteamDTRefreshPlanner(chunk_size=2).plan(["A", " B ", " A"])

    assert first == second
    assert first.chunks == second.chunks


def test_valid_custom_source_uses_price_cache_key_semantics() -> None:
    plan = SteamDTRefreshPlanner(chunk_size=1, source=" CustomSource ").plan(["A"])

    assert plan.source == "CustomSource"
    assert plan.ordered_unique_keys == (
        PriceCacheKey(market_hash_name="A", source="CustomSource"),
    )


@pytest.mark.parametrize("invalid", ["A", b"A", 7, None])
def test_invalid_top_level_iterable_fails_closed(invalid: object) -> None:
    with pytest.raises(SteamDTRefreshPlannerValidationError) as exc_info:
        SteamDTRefreshPlanner(chunk_size=1).plan(invalid)  # type: ignore[arg-type]

    assert exc_info.value.field == "market_hash_names"
    assert exc_info.value.input_index is None


@pytest.mark.parametrize("invalid", [None, 7, b"A", "", "   "])
def test_invalid_item_reports_zero_based_input_index(invalid: object) -> None:
    with pytest.raises(SteamDTRefreshPlannerValidationError) as exc_info:
        SteamDTRefreshPlanner(chunk_size=1).plan(["A", invalid])  # type: ignore[list-item]

    assert exc_info.value.field == "market_hash_name"
    assert exc_info.value.input_index == 1
    assert isinstance(exc_info.value.__cause__, (TypeError, ValueError))
    assert repr(invalid) not in str(exc_info.value)


@pytest.mark.parametrize("invalid", [0, -1, 1.0, True, False, "1", None])
def test_invalid_chunk_size_rejects_non_positive_or_non_exact_int(invalid: object) -> None:
    with pytest.raises(SteamDTRefreshPlannerValidationError) as exc_info:
        SteamDTRefreshPlanner(chunk_size=invalid)  # type: ignore[arg-type]

    assert exc_info.value.field == "chunk_size"


@pytest.mark.parametrize("invalid", [None, 7, "", "   "])
def test_invalid_source_fails_through_price_cache_key_contract(invalid: object) -> None:
    with pytest.raises(SteamDTRefreshPlannerValidationError) as exc_info:
        SteamDTRefreshPlanner(chunk_size=1, source=invalid)  # type: ignore[arg-type]

    assert exc_info.value.field == "source"
    assert isinstance(exc_info.value.__cause__, (TypeError, ValueError))


def test_planner_plan_item_chunk_and_plan_are_immutable() -> None:
    planner = SteamDTRefreshPlanner(chunk_size=1)
    plan = planner.plan(["A"])
    item = plan.ordered_unique_items[0]
    chunk = plan.chunks[0]

    with pytest.raises(FrozenInstanceError):
        planner.chunk_size = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        item.occurrence_count = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        chunk.chunk_index = 1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.source = "other"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        plan.ordered_unique_items.append(item)  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        chunk.items.clear()  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"key": object(), "first_seen_input_index": 0}, "key"),
        (
            {
                "key": PriceCacheKey("A"),
                "first_seen_input_index": True,
            },
            "first_seen_input_index",
        ),
        (
            {
                "key": PriceCacheKey("A"),
                "first_seen_input_index": -1,
            },
            "first_seen_input_index",
        ),
        (
            {
                "key": PriceCacheKey("A"),
                "first_seen_input_index": 0,
                "occurrence_count": True,
            },
            "occurrence_count",
        ),
        (
            {
                "key": PriceCacheKey("A"),
                "first_seen_input_index": 0,
                "occurrence_count": 0,
            },
            "occurrence_count",
        ),
    ],
)
def test_plan_item_public_invariants(kwargs: dict[str, object], field: str) -> None:
    with pytest.raises(SteamDTRefreshPlannerValidationError) as exc_info:
        SteamDTRefreshPlanItem(**kwargs)  # type: ignore[arg-type]

    assert exc_info.value.field == field


def test_plan_chunk_public_invariants() -> None:
    first = _item("A")
    second = _item("B", first_seen=1)
    valid = SteamDTRefreshPlanChunk(
        chunk_index=0,
        start_unique_index=0,
        items=(first, second),
    )

    invalid_values = [
        {"chunk_index": True},
        {"start_unique_index": -1},
        {"items": ()},
        {"items": (first, first)},
        {"items": (second, first)},
        {"items": (object(),)},
    ]
    for changes in invalid_values:
        with pytest.raises(SteamDTRefreshPlannerValidationError):
            replace(valid, **changes)  # type: ignore[arg-type]


def test_plan_public_invariants_reject_inconsistent_items() -> None:
    first = _item("A", occurrences=2)
    second = _item("B", first_seen=2)
    valid = _plan_for_items((first, second))

    invalid_item_sets = [
        (first, first),
        (first, _item("B", first_seen=2, source="other")),
        (
            first,
            SteamDTRefreshPlanItem(
                key=PriceCacheKey(market_hash_name="B", game="other"),
                first_seen_input_index=2,
            ),
        ),
        (
            first,
            SteamDTRefreshPlanItem(
                key=PriceCacheKey(
                    market_hash_name="B",
                    snapshot_type="other",
                ),
                first_seen_input_index=2,
            ),
        ),
        (_item("A", first_seen=1),),
        (first, _item("B", first_seen=0)),
        (_item("A"), _item("B", first_seen=2)),
        (object(),),
    ]
    for items in invalid_item_sets:
        with pytest.raises(SteamDTRefreshPlannerValidationError):
            SteamDTRefreshPlan(
                source="steamdt",
                chunk_size=2,
                ordered_unique_items=items,  # type: ignore[arg-type]
                chunks=(),
            )

    assert valid.input_count == 3


def test_plan_public_invariants_reject_inconsistent_chunks() -> None:
    items = (_item("A"), _item("B", first_seen=1), _item("C", first_seen=2))
    valid = _plan_for_items(items, chunk_size=2)
    first_chunk, final_chunk = valid.chunks

    invalid_chunk_sets = [
        (),
        (first_chunk,),
        (first_chunk, final_chunk, final_chunk),
        (replace(first_chunk, chunk_index=1), final_chunk),
        (first_chunk, replace(final_chunk, start_unique_index=1)),
        (replace(first_chunk, items=(items[0],)), final_chunk),
        (first_chunk, replace(final_chunk, items=(items[1],))),
        (object(),),
    ]
    for chunks in invalid_chunk_sets:
        with pytest.raises(SteamDTRefreshPlannerValidationError):
            SteamDTRefreshPlan(
                source="steamdt",
                chunk_size=2,
                ordered_unique_items=items,
                chunks=chunks,  # type: ignore[arg-type]
            )


def test_empty_plan_rejects_chunks_and_nonempty_plan_requires_chunks() -> None:
    item = _item("A")
    chunk = SteamDTRefreshPlanChunk(
        chunk_index=0,
        start_unique_index=0,
        items=(item,),
    )

    with pytest.raises(SteamDTRefreshPlannerValidationError):
        SteamDTRefreshPlan(
            source="steamdt",
            chunk_size=1,
            ordered_unique_items=(),
            chunks=(chunk,),
        )
    with pytest.raises(SteamDTRefreshPlannerValidationError):
        SteamDTRefreshPlan(
            source="steamdt",
            chunk_size=1,
            ordered_unique_items=(item,),
            chunks=(),
        )


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.add(node.module.casefold())
            imports.update(alias.name.casefold() for alias in node.names)
    return imports


def test_planner_has_only_pure_domain_dependencies_and_no_side_effect_calls() -> None:
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / "app" / "services" / "steamdt_refresh_planner.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports = _imported_names(module_path)
    forbidden_imports = {
        "asyncio",
        "fastapi",
        "httpx",
        "os",
        "redis",
        "threading",
        "time",
        "app.config",
        "app.clients",
        "price_cache_factory",
        "price_provider",
        "pipeline",
        "scheduler",
        "steamdt_cached_price_resolver",
        "steamdt_price_refresh_service",
        "steamdt_price_snapshot_source",
        "steamdt_rate_limiter",
    }
    assert not any(
        fragment in imported
        for imported in imports
        for fragment in forbidden_imports
    )
    assert not any(
        isinstance(node, (ast.AsyncFunctionDef, ast.Await)) for node in ast.walk(tree)
    )

    forbidden_calls = {
        "create_task",
        "delete",
        "fetch_price_snapshot",
        "get",
        "put",
        "purge_expired",
        "refresh_one",
        "sleep",
        "submit",
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not forbidden_calls.intersection(called_attributes)


def test_runtime_modules_and_dry_runs_do_not_import_planner() -> None:
    project_root = Path(__file__).resolve().parents[1]
    runtime_paths = [
        project_root / "app" / "clients" / "steamdt_client.py",
        project_root / "app" / "services" / "steamdt_price_cache_adapter.py",
        project_root / "app" / "services" / "steamdt_cached_price_resolver.py",
        project_root / "app" / "services" / "steamdt_price_refresh_service.py",
        project_root / "app" / "services" / "steamdt_price_snapshot_source.py",
        project_root / "app" / "services" / "price_provider.py",
        project_root / "app" / "services" / "price_cache_factory.py",
        project_root / "app" / "services" / "steamdt_rate_limiter_factory.py",
        project_root / "app" / "services" / "valuation_service.py",
        project_root / "app" / "services" / "pipeline_service.py",
        project_root / "app" / "services" / "pipeline_alert_service.py",
        project_root / "app" / "jobs" / "scheduler.py",
        project_root / "app" / "main.py",
        project_root / "app" / "config.py",
        project_root / "scripts" / "run_mock_pipeline.py",
        project_root / "scripts" / "run_scheduler_once.py",
        project_root / "scripts" / "docker_smoke_test.py",
        project_root / "scripts" / "steamdt_price_snapshot_smoke.py",
    ]

    for path in runtime_paths:
        imports = _imported_names(path)
        assert "app.services.steamdt_refresh_planner" not in imports
        assert "steamdt_refresh_planner" not in imports
        assert not any(name.startswith("steamdtrefreshplan") for name in imports)
