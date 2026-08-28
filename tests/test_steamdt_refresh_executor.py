import ast
import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.clients.steamdt_errors import (
    SteamDTApiError,
    SteamDTHttpStatusError,
    SteamDTRateLimitError,
    SteamDTResponseParseError,
    SteamDTTransportError,
)
from app.services.price_cache import (
    PriceCacheKey,
    PriceCachePolicy,
    PriceCacheWriteResult,
)
from app.services.price_cache_codec import PriceCacheCodecError
from app.services.redis_price_cache import PriceCacheBackendError
from app.services.steamdt_price_cache_adapter import (
    SteamDTPriceCacheAdapterError,
    SteamDTPriceCacheAdapterErrorReason,
)
from app.services.steamdt_price_refresh_service import (
    SteamDTPriceRefreshResult,
    SteamDTPriceRefreshStatus,
    SteamDTPriceRefreshValidationError,
)
from app.services.steamdt_refresh_executor import (
    SteamDTRefreshExecutionReport,
    SteamDTRefreshExecutor,
    SteamDTRefreshExecutorValidationError,
    SteamDTRefreshItemExecutionResult,
    SteamDTRefreshItemExecutionStatus,
)
from app.services.steamdt_refresh_planner import (
    SteamDTRefreshPlan,
    SteamDTRefreshPlanner,
)

BASE_TIME = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
RefreshBehavior = Callable[
    [str, PriceCachePolicy],
    Awaitable[object],
]


def _run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def _policy() -> PriceCachePolicy:
    return PriceCachePolicy(
        fresh_ttl=timedelta(minutes=5),
        stale_ttl=timedelta(minutes=10),
        stale_grace_ttl=timedelta(minutes=15),
    )


def _plan(names: list[str], *, chunk_size: int = 2) -> SteamDTRefreshPlan:
    return SteamDTRefreshPlanner(chunk_size=chunk_size).plan(names)


def _refresh_result(
    name: str,
    *,
    write_result: PriceCacheWriteResult | None = PriceCacheWriteResult.CREATED,
) -> SteamDTPriceRefreshResult:
    if write_result is None:
        return SteamDTPriceRefreshResult(
            status=SteamDTPriceRefreshStatus.NO_CANDIDATES,
            key=PriceCacheKey(name),
            observed_at=BASE_TIME,
            candidate_count=0,
            write_result=None,
        )
    return SteamDTPriceRefreshResult(
        status=SteamDTPriceRefreshStatus.CACHE_PUT_COMPLETED,
        key=PriceCacheKey(name),
        observed_at=BASE_TIME,
        candidate_count=1,
        write_result=write_result,
    )


class FakeRefresher:
    def __init__(self, behavior: RefreshBehavior | None = None) -> None:
        self.behavior = behavior
        self.calls: list[tuple[str, PriceCachePolicy]] = []

    async def refresh_one(
        self,
        market_hash_name: str,
        policy: PriceCachePolicy,
    ) -> object:
        self.calls.append((market_hash_name, policy))
        if self.behavior is not None:
            return await self.behavior(market_hash_name, policy)
        return _refresh_result(market_hash_name)


def _success_item_result(
    plan: SteamDTRefreshPlan,
    unique_index: int,
    *,
    chunk_index: int = 0,
    write_result: PriceCacheWriteResult | None = PriceCacheWriteResult.CREATED,
) -> SteamDTRefreshItemExecutionResult:
    item = plan.ordered_unique_items[unique_index]
    return SteamDTRefreshItemExecutionResult(
        item=item,
        chunk_index=chunk_index,
        unique_item_index=unique_index,
        status=SteamDTRefreshItemExecutionStatus.SUCCEEDED,
        refresh_result=_refresh_result(
            item.market_hash_name,
            write_result=write_result,
        ),
    )


@pytest.mark.parametrize("invalid", [0, -1, True, False, 1.5, "1", None])
def test_executor_rejects_invalid_max_concurrency(invalid: object) -> None:
    with pytest.raises(SteamDTRefreshExecutorValidationError) as exc_info:
        SteamDTRefreshExecutor(
            FakeRefresher(),
            max_concurrency=invalid,  # type: ignore[arg-type]
        )

    assert exc_info.value.field == "max_concurrency"


@pytest.mark.parametrize("invalid", [object(), None, 1])
def test_executor_rejects_collaborator_without_callable_refresh_one(
    invalid: object,
) -> None:
    with pytest.raises(SteamDTRefreshExecutorValidationError) as exc_info:
        SteamDTRefreshExecutor(invalid, max_concurrency=1)  # type: ignore[arg-type]

    assert exc_info.value.field == "refresher"
    assert repr(invalid) not in str(exc_info.value)


def test_execute_validates_plan_policy_and_source_before_refresh() -> None:
    refresher = FakeRefresher()
    executor = SteamDTRefreshExecutor(refresher, max_concurrency=1)
    custom_source_plan = SteamDTRefreshPlanner(
        chunk_size=1,
        source="custom",
    ).plan(["A"])

    async def scenario() -> None:
        with pytest.raises(SteamDTRefreshExecutorValidationError) as plan_error:
            await executor.execute(object(), _policy())  # type: ignore[arg-type]
        assert plan_error.value.field == "plan"
        with pytest.raises(SteamDTRefreshExecutorValidationError) as policy_error:
            await executor.execute(_plan(["A"]), object())  # type: ignore[arg-type]
        assert policy_error.value.field == "policy"
        with pytest.raises(SteamDTRefreshExecutorValidationError) as source_error:
            await executor.execute(custom_source_plan, _policy())
        assert source_error.value.field == "plan"

    _run(scenario())
    assert refresher.calls == []


def test_execute_revalidates_a_tampered_policy_before_refresh() -> None:
    refresher = FakeRefresher()
    executor = SteamDTRefreshExecutor(refresher, max_concurrency=1)
    policy = _policy()
    object.__setattr__(policy, "fresh_ttl", timedelta(0))

    with pytest.raises(SteamDTRefreshExecutorValidationError) as exc_info:
        _run(executor.execute(_plan(["A"]), policy))

    assert exc_info.value.field == "policy"
    assert refresher.calls == []


def test_empty_custom_source_plan_is_rejected_before_refresh() -> None:
    refresher = FakeRefresher()
    executor = SteamDTRefreshExecutor(refresher, max_concurrency=1)
    plan = SteamDTRefreshPlanner(chunk_size=1, source="custom").plan([])

    with pytest.raises(SteamDTRefreshExecutorValidationError):
        _run(executor.execute(plan, _policy()))

    assert refresher.calls == []


def test_execute_revalidates_a_tampered_plan_before_refresh() -> None:
    refresher = FakeRefresher()
    executor = SteamDTRefreshExecutor(refresher, max_concurrency=1)
    plan = _plan(["A"])
    object.__setattr__(plan, "chunks", ())

    with pytest.raises(SteamDTRefreshExecutorValidationError) as exc_info:
        _run(executor.execute(plan, _policy()))

    assert exc_info.value.field == "plan"
    assert refresher.calls == []


def test_empty_plan_returns_complete_empty_report_without_refresh() -> None:
    refresher = FakeRefresher()
    plan = _plan([])
    policy = _policy()

    report = _run(
        SteamDTRefreshExecutor(refresher, max_concurrency=3).execute(plan, policy)
    )

    assert report.plan is plan
    assert report.policy is policy
    assert report.max_concurrency == 3
    assert report.item_results == ()
    assert report.total_count == 0
    assert report.success_count == 0
    assert report.failure_count == 0
    assert report.chunk_count == 0
    assert report.completed_chunk_count == 0
    assert refresher.calls == []


def test_unique_items_are_called_once_with_canonical_names_and_same_policy() -> None:
    refresher = FakeRefresher()
    plan = _plan([" A ", "B", "A", " B "])
    original_plan = plan
    policy = _policy()

    report = _run(
        SteamDTRefreshExecutor(refresher, max_concurrency=2).execute(plan, policy)
    )

    assert [name for name, _ in refresher.calls] == ["A", "B"]
    assert all(call_policy is policy for _, call_policy in refresher.calls)
    assert report.plan is original_plan
    assert report.plan.ordered_unique_market_hash_names == ("A", "B")
    assert [item.occurrence_count for item in report.plan.ordered_unique_items] == [
        2,
        2,
    ]
    assert [result.market_hash_name for result in report.item_results] == ["A", "B"]


@pytest.mark.parametrize("write_result", list(PriceCacheWriteResult))
def test_cache_write_outcome_is_preserved_exactly(
    write_result: PriceCacheWriteResult,
) -> None:
    async def behavior(name: str, _policy_value: PriceCachePolicy) -> object:
        return _refresh_result(name, write_result=write_result)

    report = _run(
        SteamDTRefreshExecutor(
            FakeRefresher(behavior),
            max_concurrency=1,
        ).execute(_plan(["A"]), _policy())
    )

    refresh_result = report.item_results[0].refresh_result
    assert refresh_result is not None
    assert refresh_result.write_result is write_result
    assert report.cache_put_completed_count == 1


def test_no_candidates_remains_a_success_without_a_write_outcome() -> None:
    async def behavior(name: str, _policy_value: PriceCachePolicy) -> object:
        return _refresh_result(name, write_result=None)

    report = _run(
        SteamDTRefreshExecutor(
            FakeRefresher(behavior),
            max_concurrency=1,
        ).execute(_plan(["A"]), _policy())
    )

    item_result = report.item_results[0]
    assert item_result.status == SteamDTRefreshItemExecutionStatus.SUCCEEDED
    assert item_result.refresh_result is not None
    assert item_result.refresh_result.status == SteamDTPriceRefreshStatus.NO_CANDIDATES
    assert item_result.refresh_result.write_result is None
    assert report.no_candidates_count == 1
    assert report.failure_count == 0


def test_aggregate_report_counts_every_refresh_outcome() -> None:
    outcomes = {
        "none": None,
        "created": PriceCacheWriteResult.CREATED,
        "replaced": PriceCacheWriteResult.REPLACED,
        "older": PriceCacheWriteResult.IGNORED_OLDER,
        "equal": PriceCacheWriteResult.UNCHANGED_EQUAL,
    }

    async def behavior(name: str, _policy_value: PriceCachePolicy) -> object:
        if name == "failure":
            raise RuntimeError("failed")
        return _refresh_result(name, write_result=outcomes[name])

    report = _run(
        SteamDTRefreshExecutor(
            FakeRefresher(behavior),
            max_concurrency=3,
        ).execute(
            _plan([*outcomes, "failure"], chunk_size=3),
            _policy(),
        )
    )

    assert report.total_count == 6
    assert report.success_count == 5
    assert report.failure_count == 1
    assert report.no_candidates_count == 1
    assert report.cache_put_completed_count == 4
    assert report.created_count == 1
    assert report.replaced_count == 1
    assert report.ignored_older_count == 1
    assert report.unchanged_equal_count == 1
    assert report.chunk_count == 2
    assert report.completed_chunk_count == 2


def test_next_chunk_waits_until_every_current_chunk_item_completes() -> None:
    first_chunk_started = asyncio.Event()
    release_first_chunk = asyncio.Event()
    started: list[str] = []

    async def behavior(name: str, _policy_value: PriceCachePolicy) -> object:
        started.append(name)
        if len(started) == 2:
            first_chunk_started.set()
        if name in {"A", "B"}:
            await release_first_chunk.wait()
        return _refresh_result(name)

    async def scenario() -> SteamDTRefreshExecutionReport:
        task = asyncio.create_task(
            SteamDTRefreshExecutor(
                FakeRefresher(behavior),
                max_concurrency=2,
            ).execute(_plan(["A", "B", "C"], chunk_size=2), _policy())
        )
        await asyncio.wait_for(first_chunk_started.wait(), timeout=1)
        assert started == ["A", "B"]
        release_first_chunk.set()
        return await asyncio.wait_for(task, timeout=1)

    report = _run(scenario())
    assert started == ["A", "B", "C"]
    assert [result.chunk_index for result in report.item_results] == [0, 0, 1]
    assert [result.unique_item_index for result in report.item_results] == [0, 1, 2]


def test_active_refreshes_never_exceed_max_concurrency() -> None:
    two_active = asyncio.Event()
    release = asyncio.Event()
    active = 0
    max_active = 0
    started: list[str] = []

    async def behavior(name: str, _policy_value: PriceCachePolicy) -> object:
        nonlocal active, max_active
        started.append(name)
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            two_active.set()
        try:
            await release.wait()
            return _refresh_result(name)
        finally:
            active -= 1

    async def scenario() -> SteamDTRefreshExecutionReport:
        task = asyncio.create_task(
            SteamDTRefreshExecutor(
                FakeRefresher(behavior),
                max_concurrency=2,
            ).execute(_plan(["A", "B", "C", "D"], chunk_size=4), _policy())
        )
        await asyncio.wait_for(two_active.wait(), timeout=1)
        assert len(started) == 2
        release.set()
        return await asyncio.wait_for(task, timeout=1)

    report = _run(scenario())
    assert max_active == 2
    assert report.total_count == 4


def test_max_concurrency_one_executes_strictly_serially() -> None:
    active = 0
    max_active = 0

    async def behavior(name: str, _policy_value: PriceCachePolicy) -> object:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1
        return _refresh_result(name)

    report = _run(
        SteamDTRefreshExecutor(
            FakeRefresher(behavior),
            max_concurrency=1,
        ).execute(_plan(["A", "B", "C"], chunk_size=3), _policy())
    )

    assert max_active == 1
    assert report.total_count == 3


def test_capacity_larger_than_chunk_size_creates_no_extra_calls() -> None:
    refresher = FakeRefresher()

    report = _run(
        SteamDTRefreshExecutor(refresher, max_concurrency=20).execute(
            _plan(["A", "B"], chunk_size=2),
            _policy(),
        )
    )

    assert len(refresher.calls) == 2
    assert report.total_count == 2


def test_reverse_completion_order_still_returns_plan_order() -> None:
    release = {name: asyncio.Event() for name in ["A", "B", "C"]}
    all_started = asyncio.Event()
    completion_order: list[str] = []
    started = 0

    async def behavior(name: str, _policy_value: PriceCachePolicy) -> object:
        nonlocal started
        started += 1
        if started == 3:
            all_started.set()
        await release[name].wait()
        completion_order.append(name)
        return _refresh_result(name)

    async def scenario() -> SteamDTRefreshExecutionReport:
        task = asyncio.create_task(
            SteamDTRefreshExecutor(
                FakeRefresher(behavior),
                max_concurrency=3,
            ).execute(_plan(["A", "B", "C"], chunk_size=3), _policy())
        )
        await asyncio.wait_for(all_started.wait(), timeout=1)
        for name in ["C", "B", "A"]:
            release[name].set()
            while name not in completion_order:
                await asyncio.sleep(0)
        return await asyncio.wait_for(task, timeout=1)

    report = _run(scenario())
    assert completion_order == ["C", "B", "A"]
    assert [result.market_hash_name for result in report.item_results] == [
        "A",
        "B",
        "C",
    ]


def _typed_failures() -> list[Exception]:
    return [
        SteamDTTransportError("transport"),
        SteamDTHttpStatusError("status", status_code=500),
        SteamDTApiError("api"),
        SteamDTRateLimitError("limited"),
        SteamDTResponseParseError("parse"),
        SteamDTPriceCacheAdapterError(
            field="candidate",
            reason=SteamDTPriceCacheAdapterErrorReason.INVALID_VALUE,
        ),
        PriceCacheBackendError("put", "unavailable"),
        PriceCacheCodecError("record", "corrupt"),
    ]


@pytest.mark.parametrize("error", _typed_failures())
def test_typed_item_failure_is_retained_without_retry(error: Exception) -> None:
    async def behavior(_name: str, _policy_value: PriceCachePolicy) -> object:
        raise error

    refresher = FakeRefresher(behavior)
    report = _run(
        SteamDTRefreshExecutor(refresher, max_concurrency=1).execute(
            _plan(["A"]),
            _policy(),
        )
    )

    item_result = report.item_results[0]
    assert item_result.status == SteamDTRefreshItemExecutionStatus.FAILED
    assert item_result.error is error
    assert item_result.error_type == type(error).__name__
    assert item_result.refresh_result is None
    assert len(refresher.calls) == 1


def test_failures_do_not_cancel_siblings_or_future_chunks() -> None:
    first_error = RuntimeError("first")
    second_error = ValueError("second")

    async def behavior(name: str, _policy_value: PriceCachePolicy) -> object:
        if name == "A":
            raise first_error
        if name == "B":
            raise second_error
        return _refresh_result(name)

    refresher = FakeRefresher(behavior)
    report = _run(
        SteamDTRefreshExecutor(refresher, max_concurrency=2).execute(
            _plan(["A", "B", "C"], chunk_size=2),
            _policy(),
        )
    )

    assert [name for name, _ in refresher.calls] == ["A", "B", "C"]
    assert [result.error for result in report.item_results] == [
        first_error,
        second_error,
        None,
    ]
    assert report.success_count == 1
    assert report.failure_count == 2


@pytest.mark.parametrize("invalid_return", [None, object(), "result"])
def test_invalid_collaborator_return_is_an_isolated_contract_failure(
    invalid_return: object,
) -> None:
    async def behavior(_name: str, _policy_value: PriceCachePolicy) -> object:
        return invalid_return

    report = _run(
        SteamDTRefreshExecutor(
            FakeRefresher(behavior),
            max_concurrency=1,
        ).execute(_plan(["A", "B"]), _policy())
    )

    assert report.failure_count == 2
    assert all(
        isinstance(result.error, SteamDTPriceRefreshValidationError)
        for result in report.item_results
    )
    assert all(result.refresh_result is None for result in report.item_results)


def test_tampered_refresh_result_becomes_an_isolated_contract_failure() -> None:
    invalid = _refresh_result("A")
    object.__setattr__(invalid, "candidate_count", 0)

    async def behavior(_name: str, _policy_value: PriceCachePolicy) -> object:
        return invalid

    report = _run(
        SteamDTRefreshExecutor(
            FakeRefresher(behavior),
            max_concurrency=1,
        ).execute(_plan(["A", "B"]), _policy())
    )

    assert report.failure_count == 2
    assert all(
        isinstance(result.error, SteamDTPriceRefreshValidationError)
        for result in report.item_results
    )


def test_wrong_key_result_is_an_isolated_contract_failure() -> None:
    async def behavior(_name: str, _policy_value: PriceCachePolicy) -> object:
        return _refresh_result("different")

    report = _run(
        SteamDTRefreshExecutor(
            FakeRefresher(behavior),
            max_concurrency=1,
        ).execute(_plan(["A"]), _policy())
    )

    assert report.failure_count == 1
    assert isinstance(
        report.item_results[0].error,
        SteamDTPriceRefreshValidationError,
    )


def test_error_details_are_not_exposed_by_item_or_report_repr() -> None:
    secret = (
        "api-key-value Authorization: Bearer bearer-secret "
        "redis://user:password@localhost/15 payload"
    )
    error = RuntimeError(secret)

    async def behavior(_name: str, _policy_value: PriceCachePolicy) -> object:
        raise error

    report = _run(
        SteamDTRefreshExecutor(
            FakeRefresher(behavior),
            max_concurrency=1,
        ).execute(_plan(["A"]), _policy())
    )

    item_result = report.item_results[0]
    assert item_result.error is error
    assert item_result.error_type == "RuntimeError"
    assert secret not in repr(item_result)
    assert secret not in repr(report)


def test_caller_cancellation_cleans_up_workers_and_stops_future_chunks() -> None:
    workers_started = asyncio.Event()
    block = asyncio.Event()
    started: list[str] = []
    cancelled: list[str] = []

    async def behavior(name: str, _policy_value: PriceCachePolicy) -> object:
        started.append(name)
        if len(started) == 2:
            workers_started.set()
        try:
            await block.wait()
            return _refresh_result(name)
        except asyncio.CancelledError:
            cancelled.append(name)
            raise

    async def scenario() -> None:
        task = asyncio.create_task(
            SteamDTRefreshExecutor(
                FakeRefresher(behavior),
                max_concurrency=2,
            ).execute(_plan(["A", "B", "C"], chunk_size=2), _policy())
        )
        await asyncio.wait_for(workers_started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.done()
        assert [
            pending
            for pending in asyncio.all_tasks()
            if pending is not asyncio.current_task() and not pending.done()
        ] == []

    _run(scenario())
    assert started == ["A", "B"]
    assert set(cancelled) == {"A", "B"}


def test_child_cancellation_cancels_sibling_and_never_starts_queued_item() -> None:
    sibling_started = asyncio.Event()
    cancelled: list[str] = []
    calls: list[str] = []

    async def behavior(name: str, _policy_value: PriceCachePolicy) -> object:
        calls.append(name)
        if name == "A":
            await sibling_started.wait()
            raise asyncio.CancelledError("child-stop")
        if name == "B":
            sibling_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(name)
                raise
        return _refresh_result(name)

    with pytest.raises(asyncio.CancelledError) as exc_info:
        _run(
            asyncio.wait_for(
                SteamDTRefreshExecutor(
                    FakeRefresher(behavior),
                    max_concurrency=2,
                ).execute(_plan(["A", "B", "C"], chunk_size=3), _policy()),
                timeout=1,
            )
        )

    assert exc_info.value.args == ("child-stop",)
    assert calls == ["A", "B"]
    assert cancelled == ["B"]


def test_child_cancellation_propagates_without_an_item_failure_report() -> None:
    calls: list[str] = []

    async def behavior(name: str, _policy_value: PriceCachePolicy) -> object:
        calls.append(name)
        if name == "A":
            raise asyncio.CancelledError
        return _refresh_result(name)

    with pytest.raises(asyncio.CancelledError):
        _run(
            SteamDTRefreshExecutor(
                FakeRefresher(behavior),
                max_concurrency=1,
            ).execute(_plan(["A", "B"], chunk_size=2), _policy())
        )

    assert calls == ["A"]


def test_item_result_is_immutable_and_exposes_safe_derived_identity() -> None:
    plan = _plan(["A"])
    result = _success_item_result(plan, 0)

    assert result.key == PriceCacheKey("A")
    assert result.market_hash_name == "A"
    assert result.error_type is None
    with pytest.raises(FrozenInstanceError):
        result.chunk_index = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"chunk_index": True}, "chunk_index"),
        ({"unique_item_index": -1}, "unique_item_index"),
        ({"status": "succeeded"}, "status"),
        ({"refresh_result": None}, "refresh_result"),
        ({"error": RuntimeError("bad")}, "error"),
    ],
)
def test_success_item_result_rejects_contradictory_fields(
    changes: dict[str, object],
    field: str,
) -> None:
    valid = _success_item_result(_plan(["A"]), 0)

    with pytest.raises(SteamDTRefreshExecutorValidationError) as exc_info:
        replace(valid, **changes)

    assert exc_info.value.field == field


def test_failure_item_result_requires_only_an_ordinary_error() -> None:
    item = _plan(["A"]).ordered_unique_items[0]
    valid = SteamDTRefreshItemExecutionResult(
        item=item,
        chunk_index=0,
        unique_item_index=0,
        status=SteamDTRefreshItemExecutionStatus.FAILED,
        error=RuntimeError("bad"),
    )

    invalid_changes = [
        {"error": None},
        {"error": asyncio.CancelledError()},
        {"refresh_result": _refresh_result("A")},
    ]
    for changes in invalid_changes:
        with pytest.raises(SteamDTRefreshExecutorValidationError):
            replace(valid, **changes)


def test_success_item_result_rejects_a_different_full_key() -> None:
    plan = _plan(["A"])
    wrong = replace(_refresh_result("A"), key=PriceCacheKey("B"))

    with pytest.raises(SteamDTRefreshExecutorValidationError) as exc_info:
        SteamDTRefreshItemExecutionResult(
            item=plan.ordered_unique_items[0],
            chunk_index=0,
            unique_item_index=0,
            status=SteamDTRefreshItemExecutionStatus.SUCCEEDED,
            refresh_result=wrong,
        )

    assert exc_info.value.field == "refresh_result"


def test_report_defensively_copies_results_and_is_immutable() -> None:
    plan = _plan(["A"])
    results = [_success_item_result(plan, 0)]
    report = SteamDTRefreshExecutionReport(
        plan=plan,
        policy=_policy(),
        max_concurrency=1,
        item_results=results,  # type: ignore[arg-type]
    )
    results.clear()

    assert len(report.item_results) == 1
    with pytest.raises(FrozenInstanceError):
        report.max_concurrency = 2  # type: ignore[misc]
    with pytest.raises(AttributeError):
        report.item_results.clear()  # type: ignore[attr-defined]


def test_report_revalidates_tampered_item_result_invariants() -> None:
    plan = _plan(["A"])
    item_result = _success_item_result(plan, 0)
    object.__setattr__(item_result, "refresh_result", None)

    with pytest.raises(SteamDTRefreshExecutorValidationError) as exc_info:
        SteamDTRefreshExecutionReport(
            plan=plan,
            policy=_policy(),
            max_concurrency=1,
            item_results=(item_result,),
        )

    assert exc_info.value.field == "refresh_result"


def test_report_rejects_missing_extra_reordered_and_wrong_chunk_results() -> None:
    plan = _plan(["A", "B", "C"], chunk_size=2)
    first = _success_item_result(plan, 0, chunk_index=0)
    second = _success_item_result(plan, 1, chunk_index=0)
    third = _success_item_result(plan, 2, chunk_index=1)
    policy = _policy()

    wrong_item_result = _success_item_result(plan, 1, chunk_index=0)
    object.__setattr__(wrong_item_result, "unique_item_index", 2)
    invalid_sets = [
        (first, second),
        (first, second, third, third),
        (second, first, third),
        (first, replace(second, unique_item_index=0), third),
        (first, second, replace(third, chunk_index=0)),
        (first, second, wrong_item_result),
    ]
    for item_results in invalid_sets:
        with pytest.raises(SteamDTRefreshExecutorValidationError):
            SteamDTRefreshExecutionReport(
                plan=plan,
                policy=policy,
                max_concurrency=2,
                item_results=item_results,
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


def test_executor_dependencies_and_calls_stay_within_d5b_boundaries() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "app" / "services" / "steamdt_refresh_executor.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = _imported_names(path)
    forbidden_imports = {
        "fastapi",
        "httpx",
        "os",
        "redis",
        "app.config",
        "app.clients",
        "price_cache_factory",
        "price_provider",
        "pipeline",
        "scheduler",
        "steamdt_cached_price_resolver",
        "steamdt_price_snapshot_source",
        "steamdt_rate_limiter",
    }
    assert not any(
        forbidden in imported
        for imported in imports
        for forbidden in forbidden_imports
    )

    forbidden_calls = {
        "aclose",
        "delete",
        "fetch_price_snapshot",
        "get",
        "get_price_batch",
        "put",
        "resolve",
        "sleep",
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not forbidden_calls.intersection(called_attributes)


def test_runtime_modules_and_dry_runs_do_not_import_executor() -> None:
    root = Path(__file__).resolve().parents[1]
    runtime_paths = [
        root / "app" / "clients" / "steamdt_client.py",
        root / "app" / "services" / "steamdt_price_snapshot_source.py",
        root / "app" / "services" / "steamdt_price_refresh_service.py",
        root / "app" / "services" / "steamdt_cached_price_resolver.py",
        root / "app" / "services" / "price_provider.py",
        root / "app" / "services" / "pipeline_service.py",
        root / "app" / "jobs" / "scheduler.py",
        root / "app" / "main.py",
        root / "app" / "config.py",
        root / "scripts" / "run_mock_pipeline.py",
        root / "scripts" / "run_scheduler_once.py",
        root / "scripts" / "docker_smoke_test.py",
    ]

    for path in runtime_paths:
        imports = _imported_names(path)
        assert "app.services.steamdt_refresh_executor" not in imports
        assert "steamdt_refresh_executor" not in imports
