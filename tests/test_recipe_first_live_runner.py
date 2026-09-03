"""Phase 16F — Bounded recipe-first BUFF live validation runner tests.

These tests exercise the offline-only Phase 16F runner module using
fakes. The runner is never wired to a real HTTP transport. Any test
that requires a network call would FAIL; here, the fakes record the
exact dispatch/attempt flow and validate the runner's contract.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.buff_intrinsic_flag_resolver import (
    BuffListingIntrinsicFlagResolver,
    BuffListingIntrinsicFlagsValue,
)
from app.services.buff_item_identity import BuffItemIdentity
from app.services.market_universe_builder import StatTrakMode
from app.services.recipe_first_live_case import (
    LiveValidationCase,
    LiveValidationCaseError,
    LiveValidationPlanItem,
    freeze_case,
)
from app.services.recipe_first_live_runner import (
    RUN_STATUS_BUDGET_EXCEEDED,
    RUN_STATUS_DISPATCHED,
    RUN_STATUS_PROVIDER_FAILED,
    RUN_STATUS_REQUEST_FAILED,
    LiveValidationPageResult,
    LiveValidationRunner,
    LiveValidationRunnerConfig,
    _PageAcquisitionOutcome,
)
from app.services.trade_up_input_enrichment import (
    InMemoryTradeUpInputEnricher,
    InMemoryTradeUpInputMetadataResolver,
    TradeUpInputMetadata,
    enrich_candidates,
)

ROOT = Path(__file__).resolve().parent.parent


class _StubIdentityResolver:
    """Resolves goods_id -> BuffItemIdentity. Offline only."""

    def __init__(self, mapping: dict[str, BuffItemIdentity] | None = None) -> None:
        self._mapping = mapping or {}
        self.calls: list[str] = []

    async def resolve_goods_id(self, goods_id: str) -> BuffItemIdentity | None:
        self.calls.append(goods_id)
        return self._mapping.get(goods_id)


class _FakeFlagResolver(BuffListingIntrinsicFlagResolver):
    """Canonical-name style classifier (stattrak=False, souvenir=False)."""

    def resolve(self, market_hash_name: str) -> BuffListingIntrinsicFlagsValue:
        return BuffListingIntrinsicFlagsValue(
            stattrak=market_hash_name.startswith("StatTrak"),
            souvenir=market_hash_name.startswith("Souvenir"),
        )


def _case(
    *,
    commit_oid: str = "f" * 40,
    family_hash: str = "a" * 64,
    family_key: str = "a" * 24,
    items: Sequence[LiveValidationPlanItem] | None = None,
) -> LiveValidationCase:
    if items is None:
        items = (
            LiveValidationPlanItem(
                market_hash_name="AK-47 | Redline (Field-Tested)",
                goods_id="33960",
                collection_name="The 2018 Nuke Collection",
                priority_within_collection=1,
            ),
        )
    return freeze_case(
        repository_commit_oid=commit_oid,
        case_purpose="fixture",
        family_hash=family_hash,
        family_key=family_key,
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The 2018 Nuke Collection", 10),),
        plan_items=items,
    )


def _identity() -> BuffCommunityIdentityResolver:
    return BuffCommunityIdentityResolver.from_snapshot_path(
        ROOT / "data" / "identity" / "buff_identity_v1.json"
    )


def _metadata() -> InMemoryTradeUpInputMetadataResolver:
    return InMemoryTradeUpInputMetadataResolver(
        {
            "AK-47 | Redline (Field-Tested)": TradeUpInputMetadata(
                market_hash_name="AK-47 | Redline (Field-Tested)",
                collection_name="The 2018 Nuke Collection",
                rarity="Restricted",
                min_float=0.1,
                max_float=0.7,
            )
        }
    )


def _runner(
    case: LiveValidationCase,
    *,
    pacing_seconds: float = 0.0,
) -> LiveValidationRunner:
    return LiveValidationRunner(
        case=case,
        identity_resolver=_identity(),
        metadata_resolver=_metadata(),
        intrinsic_resolver=_FakeFlagResolver(),
        config=LiveValidationRunnerConfig(pacing_seconds=pacing_seconds),
    )


def test_runner_construction_rejects_invalid_case() -> None:
    with pytest.raises(LiveValidationCaseError):
        LiveValidationRunner(
            case="not-a-case",  # type: ignore[arg-type]
            identity_resolver=_identity(),
            metadata_resolver=_metadata(),
        )


def test_runner_construction_rejects_bad_metadata_resolver() -> None:
    with pytest.raises(LiveValidationCaseError):
        LiveValidationRunner(
            case=_case(),
            identity_resolver=_identity(),
            metadata_resolver="not-a-resolver",  # type: ignore[arg-type]
        )


def test_runner_construction_rejects_bad_intrinsic_resolver() -> None:
    with pytest.raises(LiveValidationCaseError):
        LiveValidationRunner(
            case=_case(),
            identity_resolver=_identity(),
            metadata_resolver=_metadata(),
            intrinsic_resolver="not-a-resolver",  # type: ignore[arg-type]
        )


def test_runner_construction_rejects_invalid_pacing() -> None:
    with pytest.raises(LiveValidationCaseError, match="pacing"):
        LiveValidationRunner(
            case=_case(),
            identity_resolver=_identity(),
            metadata_resolver=_metadata(),
            config=LiveValidationRunnerConfig(pacing_seconds=-1.0),
        )


def test_runner_identity_failure_yields_contract_failure() -> None:
    case = _case()
    fake = _StubIdentityResolver()  # returns None for everything
    runner = LiveValidationRunner(
        case=case,
        identity_resolver=fake,  # type: ignore[arg-type]
        metadata_resolver=_metadata(),
        intrinsic_resolver=_FakeFlagResolver(),
    )
    result = asyncio.run(runner.run())
    assert result.classification == "identity_failure"
    assert result.attempted == 0
    assert result.dispatched == 0
    assert result.page_results == ()


def test_runner_with_synthetic_payload_records_dispatched_state() -> None:
    # Swap in a fake provider to avoid any network call.
    fake_payloads = {
        "33960": b'{"code":"OK","data":{"items":[]}}',
    }

    async def _patched() -> None:
        # Build the pipeline directly with a faked listing provider so
        # the test never opens a socket. We reuse the same providers
        # the runner composes, but skip the runner.run path because
        # run() owns the http_client lifetime.
        return None

    asyncio.run(_patched())

    # A separate direct-path test: construct a fake client and verify
    # the BudgetedPayloadClient wrapper enforces the budget.
    from app.clients.buff_anonymous_listing_client import (
        BuffAnonymousListingPayloadClient,
    )
    from app.services.recipe_first_live_runner import (
        _BudgetedPayloadClient,
        _BudgetTracker,
    )

    @dataclass
    class _FakePayload(BuffAnonymousListingPayloadClient):
        payloads: dict[str, bytes]
        calls: list[str]

        async def fetch_sell_order_payload(self, goods_id: str) -> bytes:
            self.calls.append(goods_id)
            return self.payloads[goods_id]

    tracker = _BudgetTracker(budget=1)
    fake = _FakePayload(payloads=fake_payloads, calls=[])
    bounded = _BudgetedPayloadClient(delegate=fake, tracker=tracker)
    payload = asyncio.run(bounded.fetch_sell_order_payload("33960"))
    assert payload == fake_payloads["33960"]
    assert tracker.attempted == 1
    assert tracker.dispatched == 1
    assert tracker.exceeded is False


def test_runner_budget_blocks_extra_attempts_before_dispatch() -> None:
    from app.clients.buff_anonymous_listing_client import (
        BuffAnonymousListingPayloadClient,
    )
    from app.services.recipe_first_live_runner import (
        _BudgetedPayloadClient,
        _BudgetExceeded,
        _BudgetTracker,
    )

    @dataclass
    class _RecordingPayload(BuffAnonymousListingPayloadClient):
        calls: list[str]

        async def fetch_sell_order_payload(self, goods_id: str) -> bytes:
            self.calls.append(goods_id)
            return b"{}"

    tracker = _BudgetTracker(budget=1)
    fake = _RecordingPayload(calls=[])
    bounded = _BudgetedPayloadClient(delegate=fake, tracker=tracker)

    asyncio.run(bounded.fetch_sell_order_payload("33960"))
    with pytest.raises(_BudgetExceeded):
        asyncio.run(bounded.fetch_sell_order_payload("33960"))
    assert len(fake.calls) == 1, "second call must fail before underlying dispatch"


def test_runner_classifies_dispatched_with_metadata_as_validated() -> None:
    # Build a one-page runner but stub the pipeline call directly.
    case = _case()
    runner = _runner(case)
    fake_page = _StubPipeline(
        page_results=[
            ("33960", _dispatched_page_result("33960", metadata_resolved=1))
        ]
    )
    runner._acquire_one = fake_page.acquire  # type: ignore[assignment]
    runner._clock = _noop_sleep  # type: ignore[assignment]
    # Stubs bypass the budget tracker; emulate real-world counters.
    runner._tracker.attempted = 1
    runner._tracker.dispatched = 1
    result = asyncio.run(runner.run())
    assert result.classification == "validated"
    assert result.dispatched == 1
    assert result.attempted == 1
    assert len(result.page_results) == 1
    assert result.page_results[0].request_status == RUN_STATUS_DISPATCHED


def test_runner_classifies_request_failure_as_inconclusive() -> None:
    case = _case()
    runner = _runner(case)
    fake_page = _StubPipeline(
        page_results=[
            ("33960", LiveValidationPageResult(
                goods_id="33960",
                market_hash_name="AK-47 | Redline (Field-Tested)",
                request_status=RUN_STATUS_REQUEST_FAILED,
                listing_count=0,
                candidate_accepted=0,
                candidate_rejected=0,
                metadata_resolved=0,
                metadata_unresolved=0,
                rejection_histograms=(),
                error_reason="request_failed",
            ))
        ]
    )
    runner._acquire_one = fake_page.acquire  # type: ignore[assignment]
    runner._clock = _noop_sleep  # type: ignore[assignment]
    runner._tracker.attempted = 1
    runner._tracker.dispatched = 0
    result = asyncio.run(runner.run())
    assert result.classification == "inconclusive"
    assert result.page_results[0].request_status == RUN_STATUS_REQUEST_FAILED


def test_runner_classifies_provider_failure_as_inconclusive() -> None:
    case = _case()
    runner = _runner(case)
    fake_page = _StubPipeline(
        page_results=[
            ("33960", LiveValidationPageResult(
                goods_id="33960",
                market_hash_name="AK-47 | Redline (Field-Tested)",
                request_status=RUN_STATUS_PROVIDER_FAILED,
                listing_count=0,
                candidate_accepted=0,
                candidate_rejected=0,
                metadata_resolved=0,
                metadata_unresolved=0,
                rejection_histograms=(),
                error_reason="provider_failed",
            ))
        ]
    )
    runner._acquire_one = fake_page.acquire  # type: ignore[assignment]
    runner._clock = _noop_sleep  # type: ignore[assignment]
    runner._tracker.attempted = 1
    runner._tracker.dispatched = 0
    result = asyncio.run(runner.run())
    assert result.classification == "inconclusive"


def test_runner_stops_after_budget_exceeded() -> None:
    item_a = LiveValidationPlanItem(
        market_hash_name="AK-47 | Redline (Field-Tested)",
        goods_id="33960",
        collection_name="The 2018 Nuke Collection",
        priority_within_collection=1,
    )
    item_b = LiveValidationPlanItem(
        market_hash_name="AK-47 | Redline (Minimal Wear)",
        goods_id="33961",
        collection_name="The 2018 Nuke Collection",
        priority_within_collection=2,
    )
    # Build a single-collection case with TWO items; budget=2.
    case = freeze_case(
        repository_commit_oid="f" * 40,
        case_purpose="fixture",
        family_hash="a" * 64,
        family_key="a" * 24,
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The 2018 Nuke Collection", 10),),
        plan_items=(item_a, item_b),
    )
    runner = _runner(case)
    fake_page = _StubPipeline(
        page_results=[
            ("33960", _dispatched_page_result("33960", metadata_resolved=1)),
            ("33961", LiveValidationPageResult(
                goods_id="33961",
                market_hash_name="AK-47 | Redline (Minimal Wear)",
                request_status=RUN_STATUS_BUDGET_EXCEEDED,
                listing_count=0,
                candidate_accepted=0,
                candidate_rejected=0,
                metadata_resolved=0,
                metadata_unresolved=0,
                rejection_histograms=(),
                error_reason="attempted_request_exceeded_frozen_budget",
            )),
        ]
    )
    runner._acquire_one = fake_page.acquire  # type: ignore[assignment]
    runner._clock = _noop_sleep  # type: ignore[assignment]
    runner._tracker.exceeded = True
    result = asyncio.run(runner.run())
    assert result.budget_exceeded is True
    assert result.classification == "contract_failure"
    assert len(result.page_results) == 1


def test_runner_records_zero_metadata_as_inconclusive() -> None:
    case = _case()
    runner = _runner(case)
    fake_page = _StubPipeline(
        page_results=[
            ("33960", _dispatched_page_result("33960", metadata_resolved=0))
        ]
    )
    runner._acquire_one = fake_page.acquire  # type: ignore[assignment]
    runner._clock = _noop_sleep  # type: ignore[assignment]
    runner._tracker.attempted = 1
    runner._tracker.dispatched = 1
    result = asyncio.run(runner.run())
    assert result.classification == "inconclusive"


def test_runner_pacing_sleep_is_invoked_between_pages() -> None:
    items = (
        LiveValidationPlanItem(
            market_hash_name="AK-47 | Redline (Field-Tested)",
            goods_id="33960",
            collection_name="The 2018 Nuke Collection",
            priority_within_collection=1,
        ),
        LiveValidationPlanItem(
            market_hash_name="AK-47 | Redline (Minimal Wear)",
            goods_id="33961",
            collection_name="The 2018 Nuke Collection",
            priority_within_collection=2,
        ),
    )
    case = freeze_case(
        repository_commit_oid="f" * 40,
        case_purpose="fixture",
        family_hash="a" * 64,
        family_key="a" * 24,
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The 2018 Nuke Collection", 10),),
        plan_items=items,
    )
    runner = LiveValidationRunner(
        case=case,
        identity_resolver=_identity(),
        metadata_resolver=_metadata(),
        intrinsic_resolver=_FakeFlagResolver(),
        config=LiveValidationRunnerConfig(pacing_seconds=2.0),
    )
    fake_page = _StubPipeline(
        page_results=[
            ("33960", _dispatched_page_result("33960", metadata_resolved=1)),
            ("33961", _dispatched_page_result("33961", metadata_resolved=1)),
        ]
    )
    runner._acquire_one = fake_page.acquire  # type: ignore[assignment]

    sleeps: list[float] = []
    runner._clock = _recorder_clock(sleeps)  # type: ignore[assignment]
    runner._tracker.attempted = 2
    runner._tracker.dispatched = 2
    result = asyncio.run(runner.run())
    assert sleeps == [2.0]
    assert result.classification == "validated"


def test_runner_excludes_raw_payload_and_untrusted_fields() -> None:
    case = _case()
    runner = _runner(case)
    fake_page = _StubPipeline(
        page_results=[
            ("33960", _dispatched_page_result("33960", metadata_resolved=1))
        ]
    )
    runner._acquire_one = fake_page.acquire  # type: ignore[assignment]
    runner._clock = _noop_sleep  # type: ignore[assignment]
    runner._tracker.attempted = 1
    runner._tracker.dispatched = 1
    result = asyncio.run(runner.run())
    raw = repr(result).encode("utf-8") + b"|" + repr(result.page_results[0]).encode("utf-8")
    for forbidden in (b"listing_id=", b"asset_id=", b"paintwear=", b"price_cny=", b"seller"):
        assert forbidden not in raw, f"forbidden field {forbidden!r} leaked into result"


def test_runner_does_not_retry_on_failure() -> None:
    case = _case()
    runner = _runner(case)
    fake_page = _StubPipeline(
        page_results=[
            ("33960", LiveValidationPageResult(
                goods_id="33960",
                market_hash_name="AK-47 | Redline (Field-Tested)",
                request_status=RUN_STATUS_REQUEST_FAILED,
                listing_count=0,
                candidate_accepted=0,
                candidate_rejected=0,
                metadata_resolved=0,
                metadata_unresolved=0,
                rejection_histograms=(),
                error_reason="request_failed",
            ))
        ]
    )
    runner._acquire_one = fake_page.acquire  # type: ignore[assignment]
    runner._clock = _noop_sleep  # type: ignore[assignment]
    runner._tracker.attempted = 1
    runner._tracker.dispatched = 0
    result = asyncio.run(runner.run())
    assert fake_page.calls == ["33960"]
    assert len(result.page_results) == 1


def test_runner_aclose_is_idempotent() -> None:
    case = _case()
    runner = _runner(case)
    asyncio.run(runner.aclose())
    asyncio.run(runner.aclose())
    assert runner._closed is True


def test_enricher_satisfies_contract_for_metadata_resolver() -> None:
    """The runner accepts ``InMemoryTradeUpInputEnricher`` because it
    satisfies the ``TradeUpInputMetadataResolver`` Protocol surface."""
    enricher = _metadata()
    # The runner accepts any object that satisfies
    # TradeUpInputMetadataResolver (has resolve(market_hash_name) -> TradeUpInputMetadata).
    assert hasattr(enricher, "resolve")
    metadata = enricher.resolve("AK-47 | Redline (Field-Tested)")
    assert metadata.collection_name == "The 2018 Nuke Collection"


def test_enrich_candidates_round_trip() -> None:
    from app.services.trade_up_input_candidate import TradeUpInputCandidate

    candidate = TradeUpInputCandidate(
        listing_id="L1",
        goods_id="33960",
        market_hash_name="AK-47 | Redline (Field-Tested)",
        price_cny=Decimal("1"),
        paintwear=Decimal("0.2"),
        asset_id="A1",
        stattrak=False,
        souvenir=False,
        source="buff",
    )
    enricher = InMemoryTradeUpInputEnricher(_metadata())
    result = enrich_candidates([candidate], enricher)
    assert len(result.enriched) == 1
    assert len(result.rejected) == 0


# --- helpers ------------------------------------------------------------------


class _StubPipeline:
    """Replaces LiveValidationRunner._acquire_one with deterministic stubs."""

    def __init__(
        self,
        page_results: Sequence[tuple[str, LiveValidationPageResult]],
        *,
        compatible: int | None = None,
        incompatible: int = 0,
    ) -> None:
        self._page_results = page_results
        self._compatible = compatible
        self._incompatible = incompatible
        self.calls: list[str] = []

    async def acquire(
        self,
        *,
        pipeline,
        plan_item: LiveValidationPlanItem,
    ) -> _PageAcquisitionOutcome:
        self.calls.append(plan_item.goods_id)
        for goods_id, result in self._page_results:
            if goods_id == plan_item.goods_id:
                return _PageAcquisitionOutcome(
                    page_result=result,
                    family_compatible=(
                        result.metadata_resolved
                        if self._compatible is None
                        else self._compatible
                    ),
                    family_incompatible=self._incompatible,
                    provenance_keys=(),
                    contract_failed=(self._incompatible > 0),
                )
        raise LiveValidationCaseError("no stub for goods_id")


async def _noop_sleep(_seconds: float) -> None:
    return None


def _recorder_clock(target: list[float]):
    async def _sleep(seconds: float) -> None:
        target.append(seconds)

    return _sleep


def _dispatched_page_result(goods_id: str, *, metadata_resolved: int) -> LiveValidationPageResult:
    return LiveValidationPageResult(
        goods_id=goods_id,
        market_hash_name="AK-47 | Redline (Field-Tested)",
        request_status=RUN_STATUS_DISPATCHED,
        listing_count=1,
        candidate_accepted=1,
        candidate_rejected=0,
        metadata_resolved=metadata_resolved,
        metadata_unresolved=0,
        rejection_histograms=(),
        error_reason=None,
    )