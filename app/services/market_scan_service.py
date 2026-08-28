from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.clients.buff_client import BuffClient, BuffSellOrder


@dataclass(frozen=True)
class CandidateListing:
    """Internal candidate listing produced by Market Scanner."""

    goods_id: str
    listing_id: str
    market_hash_name: str | None
    price_cny: Decimal
    float_value: float | None
    paint_seed: int | None
    inspect_link: str | None
    source: str = "buff"
    scanned_at: datetime = datetime.now(UTC)
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.goods_id.strip():
            raise ValueError("goods_id cannot be empty")
        if not self.listing_id.strip():
            raise ValueError("listing_id cannot be empty")
        if self.price_cny < 0:
            raise ValueError("price_cny must be greater than or equal to 0")
        if self.float_value is not None and not 0.0 <= self.float_value <= 1.0:
            raise ValueError("float_value must be between 0 and 1")
        if self.scanned_at.tzinfo is None:
            raise ValueError("scanned_at must be timezone-aware")


@dataclass(frozen=True)
class ScanFilterConfig:
    """Filtering controls for one market scan pass."""

    max_price_cny: Decimal | None = None
    max_float: float | None = None
    limit_per_goods: int | None = None
    require_float: bool = False

    def __post_init__(self) -> None:
        if self.max_price_cny is not None and self.max_price_cny < 0:
            raise ValueError("max_price_cny must be greater than or equal to 0")
        if self.max_float is not None and not 0.0 <= self.max_float <= 1.0:
            raise ValueError("max_float must be between 0 and 1")
        if self.limit_per_goods is not None and self.limit_per_goods <= 0:
            raise ValueError("limit_per_goods must be greater than 0")


@dataclass(frozen=True)
class ScanRunResult:
    """Aggregated output of one scanner run or sub-run."""

    candidates: list[CandidateListing]
    errors: list[str]
    scanned_goods_ids: list[str]
    started_at: datetime
    finished_at: datetime



def scan_goods(
    buff_client: BuffClient,
    goods_id: str,
    config: ScanFilterConfig | None = None,
) -> ScanRunResult:
    """Scan one BUFF goods_id and return filtered candidate listings."""

    started_at = datetime.now(UTC)
    config = config or ScanFilterConfig()

    try:
        sell_orders = _run_async(buff_client.get_sell_orders(goods_id))
    except Exception as exc:
        finished_at = datetime.now(UTC)
        return ScanRunResult(
            candidates=[],
            errors=[f"Failed to scan goods_id={goods_id}: {exc}"],
            scanned_goods_ids=[goods_id],
            started_at=started_at,
            finished_at=finished_at,
        )

    scanned_at = datetime.now(UTC)
    candidates = [
        _convert_sell_order_to_candidate(order, scanned_at=scanned_at)
        for order in sell_orders
    ]
    candidates = _apply_filters(candidates, config)
    candidates = _deduplicate_candidates(candidates)
    candidates = _sort_candidates(candidates)
    candidates = _apply_limit(candidates, config.limit_per_goods)

    finished_at = datetime.now(UTC)
    return ScanRunResult(
        candidates=candidates,
        errors=[],
        scanned_goods_ids=[goods_id],
        started_at=started_at,
        finished_at=finished_at,
    )



def scan_watchlist(
    buff_client: BuffClient,
    goods_ids: list[str],
    config: ScanFilterConfig | None = None,
) -> ScanRunResult:
    """Scan multiple goods_ids and merge candidate listings with error isolation."""

    started_at = datetime.now(UTC)
    config = config or ScanFilterConfig()

    if not goods_ids:
        finished_at = datetime.now(UTC)
        return ScanRunResult(
            candidates=[],
            errors=[],
            scanned_goods_ids=[],
            started_at=started_at,
            finished_at=finished_at,
        )

    all_candidates: list[CandidateListing] = []
    all_errors: list[str] = []
    scanned_goods_ids: list[str] = []

    for goods_id in goods_ids:
        result = scan_goods(buff_client, goods_id, config)
        scanned_goods_ids.extend(result.scanned_goods_ids)
        all_candidates.extend(result.candidates)
        all_errors.extend(result.errors)

    all_candidates = _deduplicate_candidates(all_candidates)
    all_candidates = _sort_candidates_globally(all_candidates)

    finished_at = datetime.now(UTC)
    return ScanRunResult(
        candidates=all_candidates,
        errors=all_errors,
        scanned_goods_ids=scanned_goods_ids,
        started_at=started_at,
        finished_at=finished_at,
    )



def _convert_sell_order_to_candidate(
    sell_order: BuffSellOrder,
    *,
    scanned_at: datetime,
) -> CandidateListing:
    """Convert one BUFF sell order into a candidate listing."""

    return CandidateListing(
        goods_id=sell_order.goods_id,
        listing_id=sell_order.listing_id,
        market_hash_name=sell_order.market_hash_name,
        price_cny=sell_order.price_cny,
        float_value=sell_order.float_value,
        paint_seed=sell_order.paint_seed,
        inspect_link=sell_order.inspect_link,
        scanned_at=scanned_at,
        raw=dict(sell_order.raw),
    )



def _apply_filters(
    candidates: list[CandidateListing],
    config: ScanFilterConfig,
) -> list[CandidateListing]:
    """Apply market scan filters to candidate listings."""

    filtered = candidates

    if config.max_price_cny is not None:
        filtered = [
            candidate
            for candidate in filtered
            if candidate.price_cny <= config.max_price_cny
        ]

    if config.require_float:
        filtered = [candidate for candidate in filtered if candidate.float_value is not None]

    if config.max_float is not None:
        filtered = [
            candidate
            for candidate in filtered
            if candidate.float_value is not None and candidate.float_value <= config.max_float
        ]

    return filtered



def _deduplicate_candidates(candidates: list[CandidateListing]) -> list[CandidateListing]:
    """Keep the first occurrence of each listing_id."""

    seen_listing_ids: set[str] = set()
    deduplicated: list[CandidateListing] = []
    for candidate in candidates:
        if candidate.listing_id in seen_listing_ids:
            continue
        seen_listing_ids.add(candidate.listing_id)
        deduplicated.append(candidate)
    return deduplicated



def _sort_candidates(candidates: list[CandidateListing]) -> list[CandidateListing]:
    """Sort candidate listings by float ascending, None last, then price ascending."""

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.float_value is None,
            candidate.float_value if candidate.float_value is not None else float("inf"),
            candidate.price_cny,
        ),
    )



def _sort_candidates_globally(candidates: list[CandidateListing]) -> list[CandidateListing]:
    """Sort candidate listings globally by goods_id, float ascending, None last, then price."""

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.goods_id,
            candidate.float_value is None,
            candidate.float_value if candidate.float_value is not None else float("inf"),
            candidate.price_cny,
        ),
    )



def _apply_limit(
    candidates: list[CandidateListing],
    limit_per_goods: int | None,
) -> list[CandidateListing]:
    """Apply the per-goods candidate limit after filtering, deduping, and sorting."""

    if limit_per_goods is None:
        return candidates
    return candidates[:limit_per_goods]



def _run_async(coro: Any) -> Any:
    """Execute an async BUFF client call from the synchronous scanner layer."""

    import asyncio

    return asyncio.run(coro)
