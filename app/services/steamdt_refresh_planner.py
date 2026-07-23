from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import cast

from app.services.price_cache import DEFAULT_PRICE_CACHE_SOURCE, PriceCacheKey

_SOURCE_VALIDATION_ITEM = "__steamdt_refresh_plan_source__"


class SteamDTRefreshPlannerValidationError(ValueError):
    """A planner input or public plan model violated the planning contract."""

    def __init__(
        self,
        message: str,
        *,
        field: str,
        input_index: int | None = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.input_index = input_index


@dataclass(frozen=True)
class SteamDTRefreshPlanItem:
    """One canonical first-seen item in a deterministic refresh plan."""

    key: PriceCacheKey
    first_seen_input_index: int
    occurrence_count: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.key, PriceCacheKey):
            raise SteamDTRefreshPlannerValidationError(
                "plan item key must be a PriceCacheKey",
                field="key",
            )
        _require_exact_int(
            self.first_seen_input_index,
            field="first_seen_input_index",
            minimum=0,
        )
        _require_exact_int(
            self.occurrence_count,
            field="occurrence_count",
            minimum=1,
        )

    @property
    def market_hash_name(self) -> str:
        return self.key.market_hash_name


@dataclass(frozen=True)
class SteamDTRefreshPlanChunk:
    """One zero-based local partition of future refresh work."""

    chunk_index: int
    start_unique_index: int
    items: tuple[SteamDTRefreshPlanItem, ...]

    def __post_init__(self) -> None:
        _require_exact_int(self.chunk_index, field="chunk_index", minimum=0)
        _require_exact_int(
            self.start_unique_index,
            field="start_unique_index",
            minimum=0,
        )
        items = _require_item_tuple(self.items, field="items")
        if not items:
            raise SteamDTRefreshPlannerValidationError(
                "plan chunk must contain at least one item",
                field="items",
            )
        if len({item.key for item in items}) != len(items):
            raise SteamDTRefreshPlannerValidationError(
                "plan chunk item keys must be unique",
                field="items",
            )
        if any(
            current.first_seen_input_index >= following.first_seen_input_index
            for current, following in zip(items, items[1:], strict=False)
        ):
            raise SteamDTRefreshPlannerValidationError(
                "plan chunk first-seen indices must be strictly increasing",
                field="items",
            )
        object.__setattr__(self, "items", items)

    @property
    def size(self) -> int:
        return len(self.items)

    @property
    def keys(self) -> tuple[PriceCacheKey, ...]:
        return tuple(item.key for item in self.items)

    @property
    def market_hash_names(self) -> tuple[str, ...]:
        return tuple(item.market_hash_name for item in self.items)


@dataclass(frozen=True)
class SteamDTRefreshPlan:
    """Immutable, fully validated local grouping of canonical refresh items."""

    source: str
    chunk_size: int
    ordered_unique_items: tuple[SteamDTRefreshPlanItem, ...]
    chunks: tuple[SteamDTRefreshPlanChunk, ...]

    def __post_init__(self) -> None:
        source = _canonicalize_source(self.source)
        _require_exact_int(self.chunk_size, field="chunk_size", minimum=1)
        items = _require_item_tuple(
            self.ordered_unique_items,
            field="ordered_unique_items",
        )
        chunks = _require_chunk_tuple(self.chunks)

        if len({item.key for item in items}) != len(items):
            raise SteamDTRefreshPlannerValidationError(
                "plan item keys must be globally unique",
                field="ordered_unique_items",
            )
        if any(
            item.key
            != PriceCacheKey(
                market_hash_name=item.key.market_hash_name,
                source=source,
            )
            for item in items
        ):
            raise SteamDTRefreshPlannerValidationError(
                "plan item keys must match the planner cache-key identity",
                field="ordered_unique_items",
            )
        self._validate_first_seen_metadata(items)
        self._validate_chunks(items, chunks)

        object.__setattr__(self, "source", source)
        object.__setattr__(self, "ordered_unique_items", items)
        object.__setattr__(self, "chunks", chunks)

    @property
    def input_count(self) -> int:
        return sum(item.occurrence_count for item in self.ordered_unique_items)

    @property
    def unique_count(self) -> int:
        return len(self.ordered_unique_items)

    @property
    def duplicate_count(self) -> int:
        return self.input_count - self.unique_count

    @property
    def ordered_unique_keys(self) -> tuple[PriceCacheKey, ...]:
        return tuple(item.key for item in self.ordered_unique_items)

    @property
    def ordered_unique_market_hash_names(self) -> tuple[str, ...]:
        return tuple(item.market_hash_name for item in self.ordered_unique_items)

    def _validate_first_seen_metadata(
        self,
        items: tuple[SteamDTRefreshPlanItem, ...],
    ) -> None:
        if not items:
            return
        if items[0].first_seen_input_index != 0:
            raise SteamDTRefreshPlannerValidationError(
                "the first plan item must be first seen at input index zero",
                field="ordered_unique_items",
            )

        preceding_occurrence_capacity = 0
        previous_first_seen = -1
        input_count = sum(item.occurrence_count for item in items)
        for unique_index, item in enumerate(items):
            first_seen = item.first_seen_input_index
            if first_seen <= previous_first_seen:
                raise SteamDTRefreshPlannerValidationError(
                    "plan first-seen indices must be strictly increasing",
                    field="ordered_unique_items",
                )
            if first_seen < unique_index or first_seen >= input_count:
                raise SteamDTRefreshPlannerValidationError(
                    "plan first-seen index is inconsistent with plan counts",
                    field="ordered_unique_items",
                )
            if unique_index > 0 and first_seen > preceding_occurrence_capacity:
                raise SteamDTRefreshPlannerValidationError(
                    "plan first-seen index exceeds prior occurrence capacity",
                    field="ordered_unique_items",
                )
            preceding_occurrence_capacity += item.occurrence_count
            previous_first_seen = first_seen

    def _validate_chunks(
        self,
        items: tuple[SteamDTRefreshPlanItem, ...],
        chunks: tuple[SteamDTRefreshPlanChunk, ...],
    ) -> None:
        if not items:
            if chunks:
                raise SteamDTRefreshPlannerValidationError(
                    "empty plans cannot contain chunks",
                    field="chunks",
                )
            return

        expected_chunk_count = (len(items) + self.chunk_size - 1) // self.chunk_size
        if len(chunks) != expected_chunk_count:
            raise SteamDTRefreshPlannerValidationError(
                "plan chunk count does not match items and chunk size",
                field="chunks",
            )

        for chunk_index, chunk in enumerate(chunks):
            expected_start = chunk_index * self.chunk_size
            expected_items = items[expected_start : expected_start + self.chunk_size]
            if chunk.chunk_index != chunk_index:
                raise SteamDTRefreshPlannerValidationError(
                    "plan chunk indices must be contiguous from zero",
                    field="chunks",
                )
            if chunk.start_unique_index != expected_start:
                raise SteamDTRefreshPlannerValidationError(
                    "plan chunk start index does not match its position",
                    field="chunks",
                )
            if chunk.items != expected_items:
                raise SteamDTRefreshPlannerValidationError(
                    "plan chunk items must exactly partition ordered items",
                    field="chunks",
                )


@dataclass(frozen=True)
class SteamDTRefreshPlanner:
    """Build deterministic local refresh plans without executing any work."""

    chunk_size: int
    source: str = DEFAULT_PRICE_CACHE_SOURCE

    def __post_init__(self) -> None:
        _require_exact_int(self.chunk_size, field="chunk_size", minimum=1)
        object.__setattr__(self, "source", _canonicalize_source(self.source))

    def plan(self, market_hash_names: Iterable[str]) -> SteamDTRefreshPlan:
        if isinstance(market_hash_names, (str, bytes)):
            raise SteamDTRefreshPlannerValidationError(
                "market_hash_names must be an iterable of item names",
                field="market_hash_names",
            )
        try:
            indexed_items = enumerate(market_hash_names)
        except TypeError as exc:
            raise SteamDTRefreshPlannerValidationError(
                "market_hash_names must be an iterable of item names",
                field="market_hash_names",
            ) from exc

        keys: list[PriceCacheKey] = []
        first_seen_indices: list[int] = []
        occurrence_counts: list[int] = []
        positions_by_key: dict[PriceCacheKey, int] = {}

        for input_index, market_hash_name in indexed_items:
            try:
                key = PriceCacheKey(
                    market_hash_name=market_hash_name,
                    source=self.source,
                )
            except (TypeError, ValueError) as exc:
                raise SteamDTRefreshPlannerValidationError(
                    f"invalid market_hash_name at input index {input_index}",
                    field="market_hash_name",
                    input_index=input_index,
                ) from exc

            if key not in positions_by_key:
                positions_by_key[key] = len(keys)
                keys.append(key)
                first_seen_indices.append(input_index)
                occurrence_counts.append(1)
            else:
                occurrence_counts[positions_by_key[key]] += 1

        items = tuple(
            SteamDTRefreshPlanItem(
                key=key,
                first_seen_input_index=first_seen_indices[position],
                occurrence_count=occurrence_counts[position],
            )
            for position, key in enumerate(keys)
        )
        chunks = tuple(
            SteamDTRefreshPlanChunk(
                chunk_index=start // self.chunk_size,
                start_unique_index=start,
                items=items[start : start + self.chunk_size],
            )
            for start in range(0, len(items), self.chunk_size)
        )
        return SteamDTRefreshPlan(
            source=self.source,
            chunk_size=self.chunk_size,
            ordered_unique_items=items,
            chunks=chunks,
        )


def _canonicalize_source(value: object) -> str:
    try:
        key = PriceCacheKey(
            market_hash_name=_SOURCE_VALIDATION_ITEM,
            source=cast("str", value),
        )
    except (TypeError, ValueError) as exc:
        raise SteamDTRefreshPlannerValidationError(
            "source must be valid under the PriceCacheKey contract",
            field="source",
        ) from exc
    return key.source


def _require_exact_int(value: object, *, field: str, minimum: int) -> int:
    if type(value) is not int:
        raise SteamDTRefreshPlannerValidationError(
            f"{field} must be an int",
            field=field,
        )
    if value < minimum:
        raise SteamDTRefreshPlannerValidationError(
            f"{field} must be greater than or equal to {minimum}",
            field=field,
        )
    return value


def _require_item_tuple(
    values: Sequence[SteamDTRefreshPlanItem],
    *,
    field: str,
) -> tuple[SteamDTRefreshPlanItem, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise SteamDTRefreshPlannerValidationError(
            f"{field} must be a sequence of plan items",
            field=field,
        )
    items = tuple(values)
    if any(not isinstance(item, SteamDTRefreshPlanItem) for item in items):
        raise SteamDTRefreshPlannerValidationError(
            f"{field} must contain only plan items",
            field=field,
        )
    return items


def _require_chunk_tuple(
    values: Sequence[SteamDTRefreshPlanChunk],
) -> tuple[SteamDTRefreshPlanChunk, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise SteamDTRefreshPlannerValidationError(
            "chunks must be a sequence of plan chunks",
            field="chunks",
        )
    chunks = tuple(values)
    if any(not isinstance(chunk, SteamDTRefreshPlanChunk) for chunk in chunks):
        raise SteamDTRefreshPlannerValidationError(
            "chunks must contain only plan chunks",
            field="chunks",
        )
    return chunks
