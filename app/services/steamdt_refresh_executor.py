from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, cast

from app.services.price_cache import (
    DEFAULT_PRICE_CACHE_SOURCE,
    PriceCacheKey,
    PriceCachePolicy,
    PriceCacheWriteResult,
)
from app.services.steamdt_price_refresh_service import (
    SteamDTPriceRefreshResult,
    SteamDTPriceRefreshStatus,
    SteamDTPriceRefreshValidationError,
)
from app.services.steamdt_refresh_planner import (
    SteamDTRefreshPlan,
    SteamDTRefreshPlanChunk,
    SteamDTRefreshPlanItem,
    SteamDTRefreshPlannerValidationError,
)


class SteamDTPriceRefresher(Protocol):
    async def refresh_one(
        self,
        market_hash_name: str,
        policy: PriceCachePolicy,
    ) -> SteamDTPriceRefreshResult:
        """Refresh one canonical SteamDT item without transferring ownership."""


class SteamDTRefreshExecutorValidationError(ValueError):
    """An executor input or public execution model violated its contract."""

    def __init__(self, message: str, *, field: str) -> None:
        super().__init__(message)
        self.field = field


class SteamDTRefreshItemExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class SteamDTRefreshItemExecutionResult:
    """One plan-correlated refresh outcome with safely retained failure detail."""

    item: SteamDTRefreshPlanItem
    chunk_index: int
    unique_item_index: int
    status: SteamDTRefreshItemExecutionStatus
    refresh_result: SteamDTPriceRefreshResult | None = None
    error: Exception | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.item, SteamDTRefreshPlanItem):
            raise SteamDTRefreshExecutorValidationError(
                "item must be a SteamDT refresh plan item",
                field="item",
            )
        _require_nonnegative_exact_int(self.chunk_index, field="chunk_index")
        _require_nonnegative_exact_int(
            self.unique_item_index,
            field="unique_item_index",
        )
        if not isinstance(self.status, SteamDTRefreshItemExecutionStatus):
            raise SteamDTRefreshExecutorValidationError(
                "status must be a SteamDT refresh item execution status",
                field="status",
            )

        if self.status == SteamDTRefreshItemExecutionStatus.SUCCEEDED:
            if not isinstance(self.refresh_result, SteamDTPriceRefreshResult):
                raise SteamDTRefreshExecutorValidationError(
                    "successful item result requires a refresh result",
                    field="refresh_result",
                )
            if self.error is not None:
                raise SteamDTRefreshExecutorValidationError(
                    "successful item result cannot contain an error",
                    field="error",
                )
            _validate_public_refresh_result(
                self.refresh_result,
                expected_key=self.item.key,
            )
        else:
            if self.refresh_result is not None:
                raise SteamDTRefreshExecutorValidationError(
                    "failed item result cannot contain a refresh result",
                    field="refresh_result",
                )
            if not isinstance(self.error, Exception):
                raise SteamDTRefreshExecutorValidationError(
                    "failed item result requires an ordinary exception",
                    field="error",
                )

    @property
    def key(self) -> PriceCacheKey:
        return self.item.key

    @property
    def market_hash_name(self) -> str:
        return self.item.market_hash_name

    @property
    def error_type(self) -> str | None:
        if self.error is None:
            return None
        return type(self.error).__name__


@dataclass(frozen=True)
class SteamDTRefreshExecutionReport:
    """Complete immutable report in the plan's unique-item order."""

    plan: SteamDTRefreshPlan
    policy: PriceCachePolicy
    max_concurrency: int
    item_results: tuple[SteamDTRefreshItemExecutionResult, ...]

    def __post_init__(self) -> None:
        plan = _validate_plan(self.plan)
        _validate_policy(self.policy)
        _require_positive_exact_int(self.max_concurrency, field="max_concurrency")
        results = _require_result_tuple(self.item_results)

        if len(results) != plan.unique_count:
            raise SteamDTRefreshExecutorValidationError(
                "item result count must match the plan unique count",
                field="item_results",
            )

        chunk_index_by_unique_index = tuple(
            chunk.chunk_index
            for chunk in plan.chunks
            for _item in chunk.items
        )
        for unique_item_index, result in enumerate(results):
            result = SteamDTRefreshItemExecutionResult(
                item=result.item,
                chunk_index=result.chunk_index,
                unique_item_index=result.unique_item_index,
                status=result.status,
                refresh_result=result.refresh_result,
                error=result.error,
            )
            if result.unique_item_index != unique_item_index:
                raise SteamDTRefreshExecutorValidationError(
                    "item results must use contiguous plan-order indices",
                    field="item_results",
                )
            if result.item != plan.ordered_unique_items[unique_item_index]:
                raise SteamDTRefreshExecutorValidationError(
                    "item results must follow the plan item order",
                    field="item_results",
                )
            if result.chunk_index != chunk_index_by_unique_index[unique_item_index]:
                raise SteamDTRefreshExecutorValidationError(
                    "item result chunk index must match the plan",
                    field="item_results",
                )

        object.__setattr__(self, "item_results", results)

    @property
    def total_count(self) -> int:
        return len(self.item_results)

    @property
    def success_count(self) -> int:
        return sum(
            result.status == SteamDTRefreshItemExecutionStatus.SUCCEEDED
            for result in self.item_results
        )

    @property
    def failure_count(self) -> int:
        return self.total_count - self.success_count

    @property
    def no_candidates_count(self) -> int:
        return self._refresh_status_count(SteamDTPriceRefreshStatus.NO_CANDIDATES)

    @property
    def cache_put_completed_count(self) -> int:
        return self._refresh_status_count(
            SteamDTPriceRefreshStatus.CACHE_PUT_COMPLETED
        )

    @property
    def created_count(self) -> int:
        return self._write_result_count(PriceCacheWriteResult.CREATED)

    @property
    def replaced_count(self) -> int:
        return self._write_result_count(PriceCacheWriteResult.REPLACED)

    @property
    def ignored_older_count(self) -> int:
        return self._write_result_count(PriceCacheWriteResult.IGNORED_OLDER)

    @property
    def unchanged_equal_count(self) -> int:
        return self._write_result_count(PriceCacheWriteResult.UNCHANGED_EQUAL)

    @property
    def chunk_count(self) -> int:
        return len(self.plan.chunks)

    @property
    def completed_chunk_count(self) -> int:
        return self.chunk_count

    def _refresh_status_count(self, status: SteamDTPriceRefreshStatus) -> int:
        return sum(
            result.refresh_result is not None
            and result.refresh_result.status == status
            for result in self.item_results
        )

    def _write_result_count(self, write_result: PriceCacheWriteResult) -> int:
        return sum(
            result.refresh_result is not None
            and result.refresh_result.write_result == write_result
            for result in self.item_results
        )


class SteamDTRefreshExecutor:
    """Execute validated local chunks with bounded single-item concurrency."""

    def __init__(
        self,
        refresher: SteamDTPriceRefresher,
        *,
        max_concurrency: int,
    ) -> None:
        refresh_one = getattr(refresher, "refresh_one", None)
        if not callable(refresh_one):
            raise SteamDTRefreshExecutorValidationError(
                "refresher must provide a callable refresh_one",
                field="refresher",
            )
        _require_positive_exact_int(max_concurrency, field="max_concurrency")
        self._refresher = refresher
        self._max_concurrency = max_concurrency

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency

    async def execute(
        self,
        plan: SteamDTRefreshPlan,
        policy: PriceCachePolicy,
    ) -> SteamDTRefreshExecutionReport:
        validated_plan = _validate_plan(plan)
        _validate_policy(policy)
        item_results: list[SteamDTRefreshItemExecutionResult] = []

        for chunk in validated_plan.chunks:
            item_results.extend(
                await self._execute_chunk(
                    chunk,
                    policy,
                )
            )

        return SteamDTRefreshExecutionReport(
            plan=validated_plan,
            policy=policy,
            max_concurrency=self._max_concurrency,
            item_results=tuple(item_results),
        )

    async def _execute_chunk(
        self,
        chunk: SteamDTRefreshPlanChunk,
        policy: PriceCachePolicy,
    ) -> tuple[SteamDTRefreshItemExecutionResult, ...]:
        results: list[SteamDTRefreshItemExecutionResult | None] = [
            None
        ] * chunk.size
        next_local_index = 0
        child_cancellation: asyncio.CancelledError | None = None

        class _ChildCancellation(Exception):
            pass

        async def worker() -> None:
            nonlocal next_local_index, child_cancellation
            while next_local_index < chunk.size:
                local_index = next_local_index
                next_local_index += 1
                item = chunk.items[local_index]
                unique_item_index = chunk.start_unique_index + local_index
                try:
                    results[local_index] = await self._execute_item(
                        item=item,
                        chunk_index=chunk.chunk_index,
                        unique_item_index=unique_item_index,
                        policy=policy,
                    )
                except asyncio.CancelledError as exc:
                    if child_cancellation is None:
                        child_cancellation = exc
                    raise _ChildCancellation from exc

        worker_count = min(self._max_concurrency, chunk.size)
        try:
            async with asyncio.TaskGroup() as task_group:
                for _ in range(worker_count):
                    task_group.create_task(worker())
        except* _ChildCancellation:
            if child_cancellation is None:
                raise asyncio.CancelledError from None
            raise child_cancellation from None

        if any(result is None for result in results):
            raise asyncio.CancelledError
        return cast(
            "tuple[SteamDTRefreshItemExecutionResult, ...]",
            tuple(results),
        )

    async def _execute_item(
        self,
        *,
        item: SteamDTRefreshPlanItem,
        chunk_index: int,
        unique_item_index: int,
        policy: PriceCachePolicy,
    ) -> SteamDTRefreshItemExecutionResult:
        try:
            refresh_result = await self._refresher.refresh_one(
                item.market_hash_name,
                policy,
            )
            if not isinstance(refresh_result, SteamDTPriceRefreshResult):
                raise SteamDTPriceRefreshValidationError(
                    "SteamDT price refresher returned an invalid result"
                )
            try:
                _validate_public_refresh_result(
                    refresh_result,
                    expected_key=item.key,
                )
            except SteamDTRefreshExecutorValidationError as exc:
                raise SteamDTPriceRefreshValidationError(
                    "SteamDT price refresher returned an invalid result"
                ) from exc
        except Exception as error:
            return SteamDTRefreshItemExecutionResult(
                item=item,
                chunk_index=chunk_index,
                unique_item_index=unique_item_index,
                status=SteamDTRefreshItemExecutionStatus.FAILED,
                error=error,
            )

        return SteamDTRefreshItemExecutionResult(
            item=item,
            chunk_index=chunk_index,
            unique_item_index=unique_item_index,
            status=SteamDTRefreshItemExecutionStatus.SUCCEEDED,
            refresh_result=refresh_result,
        )


def _validate_public_refresh_result(
    value: SteamDTPriceRefreshResult,
    *,
    expected_key: PriceCacheKey,
) -> None:
    try:
        SteamDTPriceRefreshResult(
            status=value.status,
            key=value.key,
            observed_at=value.observed_at,
            candidate_count=value.candidate_count,
            write_result=value.write_result,
        )
    except (TypeError, ValueError) as exc:
        raise SteamDTRefreshExecutorValidationError(
            "refresh result must satisfy its public contract",
            field="refresh_result",
        ) from exc
    if value.key != expected_key:
        raise SteamDTRefreshExecutorValidationError(
            "refresh result key must match the planned item key",
            field="refresh_result",
        )


def _validate_plan(value: object) -> SteamDTRefreshPlan:
    if not isinstance(value, SteamDTRefreshPlan):
        raise SteamDTRefreshExecutorValidationError(
            "plan must be a SteamDT refresh plan",
            field="plan",
        )
    try:
        validated = SteamDTRefreshPlan(
            source=value.source,
            chunk_size=value.chunk_size,
            ordered_unique_items=value.ordered_unique_items,
            chunks=value.chunks,
        )
    except SteamDTRefreshPlannerValidationError as exc:
        raise SteamDTRefreshExecutorValidationError(
            "plan must satisfy the SteamDT refresh plan contract",
            field="plan",
        ) from exc
    if validated.source != DEFAULT_PRICE_CACHE_SOURCE:
        raise SteamDTRefreshExecutorValidationError(
            "plan source is incompatible with the SteamDT refresh service",
            field="plan",
        )
    return value


def _validate_policy(value: object) -> PriceCachePolicy:
    if not isinstance(value, PriceCachePolicy):
        raise SteamDTRefreshExecutorValidationError(
            "policy must be a price cache policy",
            field="policy",
        )
    try:
        PriceCachePolicy(
            fresh_ttl=value.fresh_ttl,
            stale_ttl=value.stale_ttl,
            stale_grace_ttl=value.stale_grace_ttl,
        )
    except (TypeError, ValueError) as exc:
        raise SteamDTRefreshExecutorValidationError(
            "policy must satisfy the price cache policy contract",
            field="policy",
        ) from exc
    return value


def _require_result_tuple(
    values: Sequence[SteamDTRefreshItemExecutionResult],
) -> tuple[SteamDTRefreshItemExecutionResult, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise SteamDTRefreshExecutorValidationError(
            "item_results must be a sequence of execution results",
            field="item_results",
        )
    results = tuple(values)
    if any(
        not isinstance(result, SteamDTRefreshItemExecutionResult)
        for result in results
    ):
        raise SteamDTRefreshExecutorValidationError(
            "item_results must contain only execution results",
            field="item_results",
        )
    return results


def _require_positive_exact_int(value: object, *, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise SteamDTRefreshExecutorValidationError(
            f"{field} must be a positive int",
            field=field,
        )
    return value


def _require_nonnegative_exact_int(value: object, *, field: str) -> int:
    if type(value) is not int or value < 0:
        raise SteamDTRefreshExecutorValidationError(
            f"{field} must be a nonnegative int",
            field=field,
        )
    return value
