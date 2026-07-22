import ast
import asyncio
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.clients.steamdt_client import SteamDTPlatformPrice
from app.clients.steamdt_errors import (
    SteamDTApiError,
    SteamDTHttpStatusError,
    SteamDTRateLimitError,
    SteamDTResponseParseError,
    SteamDTTransportError,
)
from app.services.steamdt_price_snapshot_source import (
    SteamDTSinglePriceSnapshotSource,
)

BASE_TIME = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


class ManualClock:
    def __init__(self, value: datetime) -> None:
        self.value = value
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return self.value


class FakeCandidateClient:
    def __init__(
        self,
        result: object,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[str] = []
        self.close_calls = 0

    async def get_price_single_candidates(
        self,
        market_hash_name: str,
    ) -> object:
        self.calls.append(market_hash_name)
        if self.error is not None:
            raise self.error
        return self.result

    async def aclose(self) -> None:
        self.close_calls += 1


def _run(coro):
    return asyncio.run(coro)


def _candidate(
    platform: str,
    *,
    item_id: str,
    price: str,
    raw: dict[str, object] | None = None,
) -> SteamDTPlatformPrice:
    return SteamDTPlatformPrice(
        platform=platform,
        platform_item_id=item_id,
        sell_price_cny=Decimal(price),
        sell_count=3,
        bidding_price_cny=Decimal("9.8765"),
        bidding_count=2,
        update_time="opaque-time",
        raw=raw,
    )


def test_source_fetches_canonical_item_once_and_preserves_candidates_without_raw() -> None:
    raw = {"Authorization": "Bearer dummy-secret", "nested": {"mutable": True}}
    candidates = [
        _candidate("steam", item_id="first", price="10.123400", raw=raw),
        _candidate("steam", item_id="duplicate", price="10.123400", raw=raw),
    ]
    client = FakeCandidateClient(candidates)
    clock = ManualClock(BASE_TIME)
    source = SteamDTSinglePriceSnapshotSource(client, clock=clock)  # type: ignore[arg-type]

    snapshot = _run(source.fetch_price_snapshot("AK-47 | Redline"))

    assert client.calls == ["AK-47 | Redline"]
    assert clock.calls == 1
    assert snapshot.market_hash_name == "AK-47 | Redline"
    assert snapshot.source == "steamdt"
    assert snapshot.observed_at == BASE_TIME
    assert [candidate.platform for candidate in snapshot.candidates] == [
        "steam",
        "steam",
    ]
    assert [candidate.platform_item_id for candidate in snapshot.candidates] == [
        "first",
        "duplicate",
    ]
    assert snapshot.candidates[0].sell_price_cny == Decimal("10.123400")
    assert snapshot.candidates[0].sell_count == 3
    assert snapshot.candidates[0].bidding_price_cny == Decimal("9.8765")
    assert snapshot.candidates[0].bidding_count == 2
    assert snapshot.candidates[0].update_time == "opaque-time"
    assert all(candidate.raw is None for candidate in snapshot.candidates)
    assert client.close_calls == 0


def test_source_reads_clock_after_success_and_normalizes_to_utc() -> None:
    non_utc = BASE_TIME.astimezone(timezone(timedelta(hours=8)))
    client = FakeCandidateClient([])
    clock = ManualClock(non_utc)
    source = SteamDTSinglePriceSnapshotSource(client, clock=clock)  # type: ignore[arg-type]

    snapshot = _run(source.fetch_price_snapshot("A"))

    assert snapshot.candidates == ()
    assert snapshot.observed_at == BASE_TIME
    assert snapshot.observed_at.tzinfo is UTC
    assert clock.calls == 1


@pytest.mark.parametrize(
    "error",
    [
        SteamDTTransportError("transport"),
        SteamDTHttpStatusError("status", status_code=503),
        SteamDTApiError("api", error_code=1),
        SteamDTRateLimitError("limited", retry_after_seconds=30),
        SteamDTResponseParseError("parse"),
    ],
)
def test_source_propagates_typed_client_errors_without_reading_clock(
    error: BaseException,
) -> None:
    client = FakeCandidateClient([], error=error)
    clock = ManualClock(BASE_TIME)
    source = SteamDTSinglePriceSnapshotSource(client, clock=clock)  # type: ignore[arg-type]

    with pytest.raises(type(error)) as exc_info:
        _run(source.fetch_price_snapshot("A"))

    assert exc_info.value is error
    assert client.calls == ["A"]
    assert clock.calls == 0


@pytest.mark.parametrize("invalid_result", [None, "prices", [object()]])
def test_source_rejects_invalid_client_results_before_reading_clock(
    invalid_result: object,
) -> None:
    client = FakeCandidateClient(invalid_result)
    clock = ManualClock(BASE_TIME)
    source = SteamDTSinglePriceSnapshotSource(client, clock=clock)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="candidate"):
        _run(source.fetch_price_snapshot("A"))

    assert clock.calls == 0


@pytest.mark.parametrize("invalid_name", ["", " A", "A "])
def test_source_rejects_noncanonical_item_before_client_call(invalid_name: str) -> None:
    client = FakeCandidateClient([])
    clock = ManualClock(BASE_TIME)
    source = SteamDTSinglePriceSnapshotSource(client, clock=clock)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="market_hash_name"):
        _run(source.fetch_price_snapshot(invalid_name))

    assert client.calls == []
    assert clock.calls == 0


def test_source_rejects_naive_clock_through_fetched_snapshot_contract() -> None:
    client = FakeCandidateClient([])
    clock = ManualClock(datetime(2026, 7, 22, 12, 0))
    source = SteamDTSinglePriceSnapshotSource(client, clock=clock)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="timezone-aware"):
        _run(source.fetch_price_snapshot("A"))

    assert client.calls == ["A"]
    assert clock.calls == 1


def test_runtime_boundaries_do_not_import_concrete_snapshot_source() -> None:
    project_root = Path(__file__).resolve().parents[1]
    runtime_paths = [
        project_root / "app" / "services" / "price_provider.py",
        project_root / "app" / "services" / "valuation_service.py",
        project_root / "app" / "services" / "pipeline_service.py",
        project_root / "app" / "services" / "pipeline_alert_service.py",
        project_root / "app" / "jobs" / "scheduler.py",
        project_root / "app" / "main.py",
        project_root / "app" / "config.py",
        project_root / "app" / "services" / "price_cache_factory.py",
        project_root / "app" / "services" / "steamdt_rate_limiter_factory.py",
    ]
    for path in runtime_paths:
        source = path.read_text(encoding="utf-8")
        assert "steamdt_price_snapshot_source" not in source
        assert "SteamDTSinglePriceSnapshotSource" not in source


def test_source_module_has_no_selection_cache_runtime_or_redis_dependencies() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "steamdt_price_snapshot_source.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.casefold() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.add(node.module.casefold())
            imports.update(alias.name.casefold() for alias in node.names)
    source = module_path.read_text(encoding="utf-8").lower()

    forbidden_import_fragments = {
        "redis",
        "price_cache_factory",
        "steamdt_rate_limiter_factory",
        "price_provider",
        "pipeline",
        "scheduler",
        "fastapi",
        "app.config",
    }
    assert not any(
        fragment.casefold() in imported
        for imported in imports
        for fragment in forbidden_import_fragments
    )
    for forbidden_text in (
        "select_steamdt_price_quote",
        "get_avg_price",
        "asyncio.create_task",
        "os.environ",
        ".put(",
        ".get(",
        ".aclose(",
    ):
        assert forbidden_text not in source
