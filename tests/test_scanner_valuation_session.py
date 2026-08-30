"""Phase 14B — Run-scoped valuation session unit tests.

Covers the contract frozen by Phase 14A / 14A-R1:
- Prepare has ZERO provider calls.
- Stage B uses only NEW LIVE names from the plan.
- Memo SUCCESS and TERMINAL FAILURE reuse within a run.
- Exact-name contract: case-sensitive, no fuzzy match, no whitespace alias.
- Session lifetime: no cross-run memo.
- Prepared-plan safety: cannot reuse a foreign/stale/already-executed plan.
- Provider quote identity mismatch fails closed.
- Omitted names fail closed.
- MemoryError propagates verbatim.
- No Phase 12D cache dependency in 14B.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.clients.steamdt_client import SteamDTPriceQuote
from app.clients.steamdt_price_selection import SteamDTPriceSelectionResult
from app.services.price_cache import (
    CachedPriceSnapshot,
    InMemoryPriceCache,
    NormalizedPriceCandidate,
    PriceCacheKey,
    PriceCacheLookup,
    PriceCachePolicy,
    PriceCacheReadPolicy,
    PriceCacheState,
    PriceCacheWriteResult,
)
from app.services.price_cache_codec import PriceCacheCodecError
from app.services.price_provider import (
    MockPriceProvider,
    PriceLookupResult,
    PriceProvider,
    PriceQuote,
)
from app.services.redis_price_cache import PriceCacheBackendError
from app.services.scanner_cached_buff_price_resolver import (
    ScannerCachedBuffPriceResolver,
)
from app.services.scanner_cached_buff_price_selector import (
    SCANNER_STRICT_BUFF_SOURCE,
)
from app.services.scanner_valuation_session import (
    RunScopedValuationSession,
    ScannerSessionError,
)
from app.services.steamdt_cached_price_resolver import (
    SteamDTCachedPriceResolution,
    SteamDTCachedPriceResolutionStatus,
    SteamDTCachedPriceResolver,
    SteamDTCachedPriceResolverError,
)
from app.services.steamdt_price_cache_adapter import SteamDTPriceCacheAdapterError
from app.services.tradeup_engine import TradeupResult
from app.services.valuation_service import ValuationConfig


def _quote(name: str, price: str = "100") -> PriceQuote:
    return PriceQuote(
        market_hash_name=name,
        price_cny=Decimal(price),
        source="session-test",
    )


def _tradeup_result(
    name: str,
    *,
    probability: float = 1.0,
    price: Decimal = Decimal("0"),
) -> TradeupResult:
    return TradeupResult(
        output_market_hash_name=name,
        probability=probability,
        output_float=0.05,
        output_wear="Factory New",
        estimated_price_cny=price,
        expected_value_contribution=Decimal("0"),
    )


class RecordingPriceProvider(MockPriceProvider):
    def __init__(self, names: tuple[str, ...]) -> None:
        super().__init__(
            {
                name: _quote(name, "200")
                for name in names
            }
        )
        self.calls: list[tuple[str, ...]] = []

    async def get_prices(
        self, market_hash_names: list[str]
    ) -> PriceLookupResult:
        self.calls.append(tuple(market_hash_names))
        return await super().get_prices(market_hash_names)


class UnexpectedExceptionProvider(PriceProvider):
    async def get_price(self, market_hash_name: str) -> PriceQuote:
        raise RuntimeError("API key=AKIA-LEAK-XYZ")

    async def get_prices(
        self, market_hash_names: list[str]
    ) -> PriceLookupResult:
        raise RuntimeError("API key=AKIA-LEAK-XYZ")


def _session(
    provider: PriceProvider,
    *,
    session_id: int = 1,
    config: ValuationConfig | None = None,
    cached_price_resolver: ScannerCachedBuffPriceResolver | None = None,
) -> RunScopedValuationSession:
    return RunScopedValuationSession(
        price_provider=provider,
        valuation_config=config or ValuationConfig(),
        session_id=session_id,
        cached_price_resolver=cached_price_resolver,
    )


def _cache_candidate(
    *,
    platform: str = "BUFF",
    price: str | None = "150",
) -> NormalizedPriceCandidate:
    return NormalizedPriceCandidate(
        platform=platform,
        platform_item_id=f"{platform}-id",
        sell_price_cny=None if price is None else Decimal(price),
        sell_count=10,
        bidding_price_cny=Decimal("1"),
        bidding_count=10,
        source_update_time="opaque",
    )


class ManualCacheClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _cached_resolver(cache: InMemoryPriceCache) -> ScannerCachedBuffPriceResolver:
    return ScannerCachedBuffPriceResolver(cache)


async def _put_snapshot(
    cache: InMemoryPriceCache,
    name: str,
    *,
    observed_at: datetime,
    candidates: tuple[NormalizedPriceCandidate, ...] | None = None,
    policy: PriceCachePolicy | None = None,
) -> None:
    snapshot = CachedPriceSnapshot(
        key=PriceCacheKey(market_hash_name=name),
        candidates=candidates or (_cache_candidate(),),
        observed_at=observed_at,
        stored_at=observed_at,
        policy=policy
        or PriceCachePolicy(
            fresh_ttl=timedelta(minutes=1),
            stale_ttl=timedelta(minutes=1),
            stale_grace_ttl=timedelta(minutes=1),
        ),
    )
    assert await cache.put(snapshot) == PriceCacheWriteResult.CREATED


class RecordingCacheReader:
    def __init__(
        self,
        *,
        lookup: PriceCacheLookup | None = None,
        error: Exception | None = None,
    ) -> None:
        self.lookup = lookup
        self.error = error
        self.calls: list[tuple[str, PriceCacheReadPolicy]] = []

    async def get(
        self,
        key: PriceCacheKey,
        *,
        read_policy: PriceCacheReadPolicy = PriceCacheReadPolicy.FRESH_ONLY,
    ) -> PriceCacheLookup:
        self.calls.append((key.market_hash_name, read_policy))
        if self.error is not None:
            raise self.error
        return self.lookup or PriceCacheLookup.missing(key)


# A. Prepare has ZERO provider calls.


@pytest.mark.parametrize("session_id", [True, -1, 1.0, "1"])
def test_session_id_must_be_exact_non_negative_integer(
    session_id: object,
) -> None:
    with pytest.raises(TypeError, match="non-negative integer"):
        RunScopedValuationSession(
            price_provider=RecordingPriceProvider(()),
            valuation_config=ValuationConfig(),
            session_id=session_id,  # type: ignore[arg-type]
        )


def test_prepare_zero_provider_calls() -> None:
    provider = RecordingPriceProvider(("A", "B", "C", "D", "E", "F", "G", "H", "I", "J"))
    session = _session(provider)
    plan = asyncio.run(
        session.prepare_output_prices(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"])
    )
    assert provider.calls == []
    assert plan.new_live_names == (
        "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    )
    assert plan.memo_successes == ()
    assert plan.memo_terminal_failures == ()
    assert session.live_demand == 10
    assert session.run_reuse_hits == 0
    assert session.cache_hits_fresh_selected == 0
    assert session.cache_misses == 0
    assert session.cache_policy_blocked == 0
    assert session.cache_expired == 0
    assert session.cache_selection_failures == 0


# B. Success memo reuse.


def test_success_memo_reuse_across_recipes() -> None:
    provider = RecordingPriceProvider(
        ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K")
    )
    session = _session(provider)

    # First recipe: A..J — all 10 NEW LIVE.
    plan1 = asyncio.run(
        session.prepare_output_prices(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"])
    )
    assert plan1.new_live_names == (
        "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    )
    assert session.live_demand == 10
    assert session.run_reuse_hits == 0

    tradeup_results1 = [
        _tradeup_result(name, price=Decimal("200")) for name in plan1.requested_names
    ]
    result1 = asyncio.run(session.resolve_prepared(plan1, tradeup_results1))
    assert len(provider.calls) == 1
    assert provider.calls[0] == (
        "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    )
    assert result1.valuation_result.tradeup_results
    assert session.live_attempted == 10
    assert session.live_succeeded == 10

    # Second recipe: A..I + K — only K is NEW LIVE.
    plan2 = asyncio.run(
        session.prepare_output_prices(["A", "B", "C", "D", "E", "F", "G", "H", "I", "K"])
    )
    assert plan2.new_live_names == ("K",)
    assert plan2.memo_successes == ("A", "B", "C", "D", "E", "F", "G", "H", "I")
    assert plan2.memo_terminal_failures == ()
    assert session.run_reuse_hits == 9
    assert session.run_reuse_successes == 9
    assert session.run_reuse_failures == 0

    tradeup_results2 = [
        _tradeup_result(name, price=Decimal("200")) for name in plan2.requested_names
    ]
    result2 = asyncio.run(session.resolve_prepared(plan2, tradeup_results2))
    # Provider is called ONLY for K.
    assert len(provider.calls) == 2
    assert provider.calls[1] == ("K",)
    assert result2.valuation_result.tradeup_results
    assert session.live_attempted == 11
    assert session.live_succeeded == 11

    # Completed-run invariants.
    assert session.run_reuse_hits == session.run_reuse_successes + session.run_reuse_failures
    assert session.live_demand == session.live_attempted + session.live_atomically_blocked
    assert session.live_attempted == session.live_succeeded + session.live_failed


# C. Failure reuse.


def test_failure_reuse_within_run() -> None:
    # First recipe: X (success), Y (failure via missing).
    # Second recipe: X (memo success), Y (memo failure), Z (new).
    provider = RecordingPriceProvider(("X", "Z"))

    class FirstYMissing(RecordingPriceProvider):
        async def get_prices(
            self, market_hash_names: list[str]
        ) -> PriceLookupResult:
            if tuple(market_hash_names) == ("X", "Y"):
                self.calls.append(tuple(market_hash_names))
                # X succeeds, Y missing.
                return PriceLookupResult(
                    quotes={"X": _quote("X", "200")},
                    missing=["Y"],
                    errors=[],
                )
            return await super().get_prices(market_hash_names)

    provider = FirstYMissing(("X", "Y", "Z"))
    session = _session(provider)

    plan1 = asyncio.run(session.prepare_output_prices(["X", "Y"]))
    assert plan1.new_live_names == ("X", "Y")
    tradeup_results1 = [_tradeup_result(n) for n in plan1.requested_names]
    result1 = asyncio.run(session.resolve_prepared(plan1, tradeup_results1))
    # Recipe 1 incomplete because Y failed.
    assert not result1.valuation_result.tradeup_results or any(
        r.estimated_price_cny == Decimal("0") for r in result1.valuation_result.tradeup_results
    )

    plan2 = asyncio.run(session.prepare_output_prices(["X", "Y", "Z"]))
    assert plan2.new_live_names == ("Z",)
    assert plan2.memo_successes == ("X",)
    assert plan2.memo_terminal_failures == ("Y",)
    tradeup_results2 = [_tradeup_result(n) for n in plan2.requested_names]
    result2 = asyncio.run(session.resolve_prepared(plan2, tradeup_results2))

    # Provider received EXACTLY one live call (for Recipe 1, X+Y).
    # Recipe 2's resolve_prepared did NOT call the provider for Y.
    assert provider.calls == [("X", "Y"), ("Z",)]
    assert session.live_demand == 3
    assert session.live_attempted == 3
    assert session.live_succeeded == 2  # X and Z
    assert session.live_failed == 1  # Y
    assert session.run_reuse_hits == 2  # X memo success, Y memo failure
    assert session.run_reuse_successes == 1
    assert session.run_reuse_failures == 1
    # Recipe 2 incomplete (Y failed) → no metrics/risk on this side.
    assert result2.valuation_result.missing_market_hash_names == ["Y"]
    assert "Y" not in result2.valuation_result.price_lookup_result.quotes
    assert any(
        "RUN_REUSE_TERMINAL_FAILURE" in error
        for error in result2.valuation_result.price_lookup_result.errors
    )


# D. Exact key.


def test_exact_key_case_sensitive() -> None:
    provider = RecordingPriceProvider(("M4A1-S | Knight (Factory New)",))
    session = _session(provider)
    plan = asyncio.run(
        session.prepare_output_prices(["m4a1-s | knight (factory new)"])
    )
    # Case differs → different key → NEW LIVE.
    assert plan.new_live_names == ("m4a1-s | knight (factory new)",)
    plan2 = asyncio.run(
        session.prepare_output_prices(["M4A1-S | Knight (Factory New)"])
    )
    assert plan2.new_live_names == ("M4A1-S | Knight (Factory New)",)
    assert plan2.memo_successes == ()
    assert plan2.memo_terminal_failures == ()


def test_exact_key_rejects_whitespace_alias() -> None:
    provider = RecordingPriceProvider(())
    session = _session(provider)
    with pytest.raises(ScannerSessionError, match="surrounding whitespace"):
        asyncio.run(session.prepare_output_prices(["  AK-47 | Redline  "]))


def test_exact_key_rejects_non_string() -> None:
    provider = RecordingPriceProvider(())
    session = _session(provider)
    with pytest.raises(ScannerSessionError, match="must be a string"):
        asyncio.run(session.prepare_output_prices(["AK-47 | Redline", 123]))


def test_exact_key_rejects_empty() -> None:
    provider = RecordingPriceProvider(())
    session = _session(provider)
    with pytest.raises(ScannerSessionError, match="non-empty"):
        asyncio.run(session.prepare_output_prices([""]))


def test_prepare_rejects_bare_string_sequence() -> None:
    provider = RecordingPriceProvider(())
    session = _session(provider)
    with pytest.raises(ScannerSessionError, match="sequence of exact names"):
        asyncio.run(session.prepare_output_prices("ABC"))


# E. Session lifetime: no cross-run memo.


def test_session_lifetime_no_cross_run_memo() -> None:
    provider = RecordingPriceProvider(("A",))
    # Run 1.
    s1 = _session(provider)
    plan = asyncio.run(s1.prepare_output_prices(["A"]))
    assert plan.new_live_names == ("A",)
    asyncio.run(s1.resolve_prepared(plan, [_tradeup_result("A")]))
    # Run 2: brand new session; A is NEW LIVE again.
    s2 = _session(provider)
    plan2 = asyncio.run(s2.prepare_output_prices(["A"]))
    assert plan2.new_live_names == ("A",)
    assert plan2.memo_successes == ()
    assert plan2.memo_terminal_failures == ()
    asyncio.run(s2.resolve_prepared(plan2, [_tradeup_result("A")]))
    assert len(provider.calls) == 2  # one call per session.


# F. Prepared-plan safety.


def test_plan_cannot_be_executed_twice() -> None:
    provider = RecordingPriceProvider(("A",))
    session = _session(provider)
    plan = asyncio.run(session.prepare_output_prices(["A"]))
    asyncio.run(session.resolve_prepared(plan, [_tradeup_result("A")]))
    with pytest.raises(ScannerSessionError, match="cannot be executed twice"):
        asyncio.run(session.resolve_prepared(plan, [_tradeup_result("A")]))
    # Provider only called once.
    assert provider.calls == [("A",)]


def test_plan_cannot_be_blocked_after_executed() -> None:
    provider = RecordingPriceProvider(("A",))
    session = _session(provider)
    plan = asyncio.run(session.prepare_output_prices(["A"]))
    asyncio.run(session.resolve_prepared(plan, [_tradeup_result("A")]))
    with pytest.raises(ScannerSessionError, match="cannot be executed twice"):
        session.record_atomically_blocked(plan)


def test_plan_cannot_be_executed_after_blocked() -> None:
    provider = RecordingPriceProvider(("A",))
    session = _session(provider)
    plan = asyncio.run(session.prepare_output_prices(["A"]))
    session.record_atomically_blocked(plan)
    with pytest.raises(ScannerSessionError, match="already marked blocked"):
        asyncio.run(session.resolve_prepared(plan, [_tradeup_result("A")]))


def test_plan_from_foreign_session_rejected() -> None:
    provider = RecordingPriceProvider(("A",))
    s1 = _session(provider, session_id=1)
    s2 = _session(provider, session_id=2)
    plan = asyncio.run(s1.prepare_output_prices(["A"]))
    with pytest.raises(ScannerSessionError, match="session_id"):
        asyncio.run(s2.resolve_prepared(plan, [_tradeup_result("A")]))


def test_plan_from_foreign_session_with_same_public_id_rejected() -> None:
    provider = RecordingPriceProvider(("A",))
    s1 = _session(provider, session_id=1)
    s2 = _session(provider, session_id=1)
    plan = asyncio.run(s1.prepare_output_prices(["A"]))
    with pytest.raises(ScannerSessionError, match="session_id"):
        asyncio.run(s2.resolve_prepared(plan, [_tradeup_result("A")]))


def test_copied_plan_with_modified_classification_rejected() -> None:
    provider = RecordingPriceProvider(("A",))
    session = _session(provider)
    plan = asyncio.run(session.prepare_output_prices(["A"]))
    copied = replace(plan, new_live_names=())
    with pytest.raises(ScannerSessionError, match="canonical session plan"):
        asyncio.run(session.resolve_prepared(copied, [_tradeup_result("A")]))
    assert provider.calls == []


def test_stale_plan_rejected_after_memo_changes() -> None:
    provider = RecordingPriceProvider(("A", "B"))
    session = _session(provider)
    stale = asyncio.run(session.prepare_output_prices(["A"]))
    active = asyncio.run(session.prepare_output_prices(["B"]))
    asyncio.run(session.resolve_prepared(active, [_tradeup_result("B")]))
    with pytest.raises(ScannerSessionError, match="stale"):
        asyncio.run(session.resolve_prepared(stale, [_tradeup_result("A")]))
    assert provider.calls == [("B",)]


def test_plan_rejects_mismatched_tradeup_results() -> None:
    provider = RecordingPriceProvider(("A",))
    session = _session(provider)
    plan = asyncio.run(session.prepare_output_prices(["A"]))
    with pytest.raises(ScannerSessionError, match="requested_names"):
        asyncio.run(
            session.resolve_prepared(plan, [_tradeup_result("B")])
        )


# G. Provider quote identity mismatch.


def test_quote_identity_mismatch_fails_closed() -> None:
    class MismatchedProvider(PriceProvider):
        async def get_price(self, market_hash_name: str) -> PriceQuote:
            return _quote("DIFFERENT_NAME", "200")

        async def get_prices(
            self, market_hash_names: list[str]
        ) -> PriceLookupResult:
            return PriceLookupResult(
                quotes={
                    "DIFFERENT_NAME": _quote("DIFFERENT_NAME", "200")
                },
                missing=[],
                errors=[],
            )

    session = _session(MismatchedProvider())
    plan = asyncio.run(session.prepare_output_prices(["REQUESTED"]))
    result = asyncio.run(
        session.resolve_prepared(plan, [_tradeup_result("REQUESTED")])
    )
    # Memo recorded as terminal failure; valuation incomplete.
    assert "REQUESTED" in result.valuation_result.missing_market_hash_names
    assert session.live_failed == 1
    assert session.live_succeeded == 0


# H. Omitted / invalid / extra provider results.


def test_omitted_name_fails_closed() -> None:
    # Provider omits the requested name from both quotes and missing.
    class OmitProvider(PriceProvider):
        async def get_price(self, market_hash_name: str) -> PriceQuote:
            raise AssertionError("single get_price should not be called by resolve_prepared")

        async def get_prices(
            self, market_hash_names: list[str]
        ) -> PriceLookupResult:
            return PriceLookupResult(
                quotes={},
                missing=[],
                errors=[],
            )

    session = _session(OmitProvider())
    plan = asyncio.run(session.prepare_output_prices(["X"]))
    result = asyncio.run(session.resolve_prepared(plan, [_tradeup_result("X")]))
    assert "X" in result.valuation_result.missing_market_hash_names
    assert session.live_failed == 1


def test_non_positive_live_quote_fails_closed() -> None:
    provider = RecordingPriceProvider(("X",))
    provider.quotes_by_name["X"] = _quote("X", "0")
    session = _session(provider)
    plan = asyncio.run(session.prepare_output_prices(["X"]))
    result = asyncio.run(session.resolve_prepared(plan, [_tradeup_result("X")]))
    assert result.valuation_result.missing_market_hash_names == ["X"]
    assert session.live_succeeded == 0
    assert session.live_failed == 1


def test_non_finite_live_quote_fails_closed() -> None:
    provider = RecordingPriceProvider(("X",))
    malformed = object.__new__(PriceQuote)
    object.__setattr__(malformed, "market_hash_name", "X")
    object.__setattr__(malformed, "price_cny", Decimal("NaN"))
    object.__setattr__(malformed, "source", "session-test")
    object.__setattr__(malformed, "raw", None)
    provider.quotes_by_name["X"] = malformed
    session = _session(provider)
    plan = asyncio.run(session.prepare_output_prices(["X"]))
    result = asyncio.run(session.resolve_prepared(plan, [_tradeup_result("X")]))
    assert result.valuation_result.missing_market_hash_names == ["X"]
    assert session.live_succeeded == 0
    assert session.live_failed == 1


def test_unexpected_extra_quote_does_not_satisfy_requested_name() -> None:
    class ExtraQuoteProvider(PriceProvider):
        async def get_price(self, market_hash_name: str) -> PriceQuote:
            return _quote("EXTRA")

        async def get_prices(
            self, market_hash_names: list[str]
        ) -> PriceLookupResult:
            return PriceLookupResult(
                quotes={"EXTRA": _quote("EXTRA")},
                missing=[],
                errors=[],
            )

    session = _session(ExtraQuoteProvider())
    plan = asyncio.run(session.prepare_output_prices(["X"]))
    result = asyncio.run(session.resolve_prepared(plan, [_tradeup_result("X")]))
    assert result.valuation_result.price_lookup_result.quotes == {}
    assert result.valuation_result.missing_market_hash_names == ["X"]
    assert session.live_failed == 1


def test_valid_requested_quote_plus_extra_quote_fails_closed() -> None:
    class ExtraQuoteProvider(PriceProvider):
        async def get_price(self, market_hash_name: str) -> PriceQuote:
            return _quote(market_hash_name)

        async def get_prices(
            self, market_hash_names: list[str]
        ) -> PriceLookupResult:
            return PriceLookupResult(
                quotes={"X": _quote("X"), "EXTRA": _quote("EXTRA")},
                missing=[],
                errors=[],
            )

    session = _session(ExtraQuoteProvider())
    plan = asyncio.run(session.prepare_output_prices(["X"]))
    result = asyncio.run(session.resolve_prepared(plan, [_tradeup_result("X")]))
    assert result.valuation_result.price_lookup_result.quotes == {}
    assert result.valuation_result.missing_market_hash_names == ["X"]
    assert session.live_succeeded == 0
    assert session.live_failed == 1


def test_valid_requested_quote_plus_extra_missing_fails_closed() -> None:
    class ExtraMissingProvider(PriceProvider):
        async def get_price(self, market_hash_name: str) -> PriceQuote:
            return _quote(market_hash_name)

        async def get_prices(
            self, market_hash_names: list[str]
        ) -> PriceLookupResult:
            return PriceLookupResult(
                quotes={"X": _quote("X")},
                missing=["EXTRA"],
                errors=[],
            )

    session = _session(ExtraMissingProvider())
    plan = asyncio.run(session.prepare_output_prices(["X"]))
    result = asyncio.run(session.resolve_prepared(plan, [_tradeup_result("X")]))
    assert result.valuation_result.price_lookup_result.quotes == {}
    assert result.valuation_result.missing_market_hash_names == ["X"]
    assert session.live_succeeded == 0
    assert session.live_failed == 1


def test_valid_quote_plus_unmapped_provider_error_fails_closed() -> None:
    class ErrorProvider(PriceProvider):
        async def get_price(self, market_hash_name: str) -> PriceQuote:
            return _quote(market_hash_name)

        async def get_prices(
            self, market_hash_names: list[str]
        ) -> PriceLookupResult:
            return PriceLookupResult(
                quotes={"X": _quote("X")},
                missing=[],
                errors=["Authorization: Bearer SECRET"],
            )

    session = _session(ErrorProvider())
    plan = asyncio.run(session.prepare_output_prices(["X"]))
    result = asyncio.run(session.resolve_prepared(plan, [_tradeup_result("X")]))
    assert result.valuation_result.price_lookup_result.quotes == {}
    assert result.valuation_result.missing_market_hash_names == ["X"]
    assert session.live_succeeded == 0
    assert session.live_failed == 1
    assert all(
        "SECRET" not in error
        for error in result.valuation_result.price_lookup_result.errors
    )


def test_unmatched_provider_error_cardinality_fails_whole_batch() -> None:
    class ErrorProvider(PriceProvider):
        async def get_price(self, market_hash_name: str) -> PriceQuote:
            return _quote(market_hash_name)

        async def get_prices(
            self, market_hash_names: list[str]
        ) -> PriceLookupResult:
            return PriceLookupResult(
                quotes={"X": _quote("X")},
                missing=["Y"],
                errors=["ERR1", "ERR2"],
            )

    session = _session(ErrorProvider())
    plan = asyncio.run(session.prepare_output_prices(["X", "Y"]))
    result = asyncio.run(
        session.resolve_prepared(
            plan,
            [_tradeup_result("X"), _tradeup_result("Y")],
        )
    )
    assert result.valuation_result.price_lookup_result.quotes == {}
    assert result.valuation_result.missing_market_hash_names == ["X", "Y"]
    assert session.live_succeeded == 0
    assert session.live_failed == 2


def test_contradictory_quote_and_missing_result_fails_closed() -> None:
    class ContradictoryProvider(PriceProvider):
        async def get_price(self, market_hash_name: str) -> PriceQuote:
            return _quote(market_hash_name)

        async def get_prices(
            self, market_hash_names: list[str]
        ) -> PriceLookupResult:
            return PriceLookupResult(
                quotes={"X": _quote("X")},
                missing=["X"],
                errors=[],
            )

    session = _session(ContradictoryProvider())
    plan = asyncio.run(session.prepare_output_prices(["X"]))
    result = asyncio.run(session.resolve_prepared(plan, [_tradeup_result("X")]))
    assert result.valuation_result.price_lookup_result.quotes == {}
    assert result.valuation_result.missing_market_hash_names == ["X"]
    assert session.live_succeeded == 0
    assert session.live_failed == 1


def test_malformed_nested_quote_field_fails_closed_without_payload() -> None:
    class SecretString:
        def strip(self) -> str:
            raise RuntimeError("Bearer SECRET-NESTED")

    malformed = object.__new__(PriceQuote)
    object.__setattr__(malformed, "market_hash_name", "X")
    object.__setattr__(malformed, "price_cny", Decimal("1"))
    object.__setattr__(malformed, "source", SecretString())
    object.__setattr__(malformed, "raw", None)

    class MalformedNestedProvider(PriceProvider):
        async def get_price(self, market_hash_name: str) -> PriceQuote:
            return malformed

        async def get_prices(
            self,
            market_hash_names: list[str],
        ) -> PriceLookupResult:
            return PriceLookupResult(
                quotes={"X": malformed},
                missing=[],
                errors=[],
            )

    session = _session(MalformedNestedProvider())
    plan = asyncio.run(session.prepare_output_prices(["X"]))
    result = asyncio.run(session.resolve_prepared(plan, [_tradeup_result("X")]))
    assert result.valuation_result.missing_market_hash_names == ["X"]
    assert session.live_failed == 1
    assert all(
        "SECRET-NESTED" not in error
        for error in result.valuation_result.price_lookup_result.errors
    )


def test_malformed_provider_result_fails_closed_without_payload() -> None:
    class MalformedProvider(PriceProvider):
        async def get_price(self, market_hash_name: str) -> PriceQuote:
            return _quote(market_hash_name)

        async def get_prices(  # type: ignore[override]
            self, market_hash_names: list[str]
        ) -> object:
            return {"Authorization": "Bearer SECRET"}

    session = _session(MalformedProvider())
    plan = asyncio.run(session.prepare_output_prices(["X"]))
    result = asyncio.run(session.resolve_prepared(plan, [_tradeup_result("X")]))
    assert result.valuation_result.missing_market_hash_names == ["X"]
    assert all(
        "SECRET" not in error
        for error in result.valuation_result.price_lookup_result.errors
    )
    assert session.live_failed == 1


# I. MemoryError / BaseException propagation.


def test_memory_error_propagates_verbatim() -> None:
    sentinel = MemoryError("session sentinel")

    class MemoryProvider(PriceProvider):
        async def get_price(self, market_hash_name: str) -> PriceQuote:
            raise sentinel

        async def get_prices(
            self,
            market_hash_names: list[str],
        ) -> PriceLookupResult:
            raise sentinel

    session = _session(MemoryProvider())
    plan = asyncio.run(session.prepare_output_prices(["A"]))

    async def run() -> None:
        with pytest.raises(MemoryError) as exc_info:
            await session.resolve_prepared(plan, [_tradeup_result("A")])
        assert exc_info.value is sentinel

    asyncio.run(run())


def test_non_exception_base_exception_propagates_verbatim() -> None:
    sentinel = asyncio.CancelledError("cancel sentinel")

    class CancelProvider(PriceProvider):
        async def get_price(self, market_hash_name: str) -> PriceQuote:
            raise sentinel

        async def get_prices(
            self,
            market_hash_names: list[str],
        ) -> PriceLookupResult:
            raise sentinel

    session = _session(CancelProvider())
    plan = asyncio.run(session.prepare_output_prices(["A"]))

    async def run() -> None:
        with pytest.raises(asyncio.CancelledError) as exc_info:
            await session.resolve_prepared(plan, [_tradeup_result("A")])
        assert exc_info.value is sentinel

    asyncio.run(run())


# J. Phase 14C permits only the scanner-owned cache read seam.


def test_phase_14c_cache_dependency_is_read_only_and_narrow() -> None:
    import ast
    from pathlib import Path

    import app.services.scanner_orchestrator as orchestrator_module
    import app.services.scanner_valuation_session as session_module

    forbidden_modules = {
        "app.services.price_cache_codec",
        "app.services.redis_price_cache",
        "app.services.price_cache_factory",
        "app.services.steamdt_price_cache_adapter",
        "app.services.steamdt_price_snapshot_source",
        "app.services.steamdt_price_refresh_service",
        "app.services.steamdt_refresh_planner",
        "app.services.steamdt_refresh_executor",
    }
    forbidden_symbols = {
        "PriceCache",
        "InMemoryPriceCache",
        "RedisPriceCache",
        "SteamDTPriceRefreshService",
        "SteamDTRefreshPlanner",
        "SteamDTRefreshExecutor",
    }
    forbidden_attributes = {"put", "delete", "clear", "purge_expired", "refresh_one"}

    for module in (session_module, orchestrator_module):
        path = Path(module.__file__ or "")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_modules: set[str] = set()
        referenced_names: set[str] = set()
        referenced_attributes: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)
            elif isinstance(node, ast.Name):
                referenced_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced_attributes.add(node.attr)
        assert forbidden_modules.isdisjoint(imported_modules)
        assert forbidden_symbols.isdisjoint(referenced_names)
        assert forbidden_attributes.isdisjoint(referenced_attributes)



# Unexpected ordinary exception from generic provider → fail-closed, no payload leak.


def test_unexpected_provider_exception_is_fail_closed() -> None:
    session = _session(UnexpectedExceptionProvider())
    plan = asyncio.run(session.prepare_output_prices(["A"]))
    result = asyncio.run(session.resolve_prepared(plan, [_tradeup_result("A")]))
    # All names become terminal failures; secret never reaches errors.
    assert "A" in result.valuation_result.missing_market_hash_names
    for error in result.valuation_result.price_lookup_result.errors:
        assert "AKIA-LEAK" not in error
        assert "API key" not in error


def test_interleaved_memo_and_live_failures_preserve_requested_order() -> None:
    class OrderedFailureProvider(PriceProvider):
        async def get_price(self, market_hash_name: str) -> PriceQuote:
            return _quote(market_hash_name)

        async def get_prices(
            self,
            market_hash_names: list[str],
        ) -> PriceLookupResult:
            if market_hash_names == ["B"]:
                return PriceLookupResult(
                    quotes={},
                    missing=["B"],
                    errors=[],
                )
            if market_hash_names == ["A", "C"]:
                return PriceLookupResult(
                    quotes={},
                    missing=["A", "C"],
                    errors=[],
                )
            raise AssertionError("unexpected provider input")

    session = _session(OrderedFailureProvider())
    first = asyncio.run(session.prepare_output_prices(["B"]))
    asyncio.run(session.resolve_prepared(first, [_tradeup_result("B")]))
    second = asyncio.run(session.prepare_output_prices(["A", "B", "C"]))
    result = asyncio.run(
        session.resolve_prepared(
            second,
            [
                _tradeup_result("A"),
                _tradeup_result("B"),
                _tradeup_result("C"),
            ],
        )
    )
    assert result.valuation_result.missing_market_hash_names == ["A", "B", "C"]
    assert len(result.valuation_result.price_lookup_result.errors) == 3


def test_provider_exception_preserves_prior_memo_success() -> None:
    class LaterExceptionProvider(PriceProvider):
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        async def get_price(self, market_hash_name: str) -> PriceQuote:
            return _quote(market_hash_name)

        async def get_prices(
            self,
            market_hash_names: list[str],
        ) -> PriceLookupResult:
            names = tuple(market_hash_names)
            self.calls.append(names)
            if names == ("A",):
                return PriceLookupResult(
                    quotes={"A": _quote("A")},
                    missing=[],
                    errors=[],
                )
            raise RuntimeError("Bearer SECRET-TOKEN")

    provider = LaterExceptionProvider()
    session = _session(provider)
    first = asyncio.run(session.prepare_output_prices(["A"]))
    asyncio.run(session.resolve_prepared(first, [_tradeup_result("A")]))
    second = asyncio.run(session.prepare_output_prices(["A", "B"]))
    result = asyncio.run(
        session.resolve_prepared(
            second,
            [_tradeup_result("A"), _tradeup_result("B")],
        )
    )

    assert provider.calls == [("A",), ("B",)]
    assert result.valuation_result.price_lookup_result.quotes == {
        "A": _quote("A")
    }
    assert result.valuation_result.missing_market_hash_names == ["B"]
    assert session.run_reuse_successes == 1
    assert session.live_succeeded == 1
    assert session.live_failed == 1
    assert all(
        "SECRET-TOKEN" not in error
        for error in result.valuation_result.price_lookup_result.errors
    )




# K. Phase 14C FRESH_ONLY cache integration.


def test_fresh_strict_buff_hit_completes_without_live_provider() -> None:
    now = datetime(2026, 8, 29, 12, 0, 30, tzinfo=UTC)
    clock = ManualCacheClock(now)
    cache = InMemoryPriceCache(clock=clock)
    asyncio.run(_put_snapshot(cache, "A", observed_at=now - timedelta(seconds=30)))
    provider = RecordingPriceProvider(("A",))
    session = _session(provider, cached_price_resolver=_cached_resolver(cache))

    plan = asyncio.run(session.prepare_output_prices(["A"]))
    assert provider.calls == []
    assert plan.memo_revision == 1
    assert plan.cache_hits_fresh_selected == ("A",)
    assert plan.new_live_names == ()
    result = asyncio.run(session.resolve_prepared(plan, [_tradeup_result("A")]))

    assert provider.calls == []
    assert result.valuation_result.missing_market_hash_names == []
    quote = result.valuation_result.price_lookup_result.quotes["A"]
    assert quote.source == SCANNER_STRICT_BUFF_SOURCE
    assert quote.price_cny == Decimal("150")
    assert session.cache_hits_fresh_selected == 1
    assert session.live_demand == 0
    assert session.live_attempted == 0


def test_all_ten_fresh_outputs_use_zero_live_demand() -> None:
    names = tuple(f"Fresh {index}" for index in range(10))
    now = datetime(2026, 8, 29, 12, 0, 30, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=ManualCacheClock(now))

    async def populate() -> None:
        for name in names:
            await _put_snapshot(cache, name, observed_at=now - timedelta(seconds=1))

    asyncio.run(populate())
    provider = RecordingPriceProvider(names)
    session = _session(provider, cached_price_resolver=_cached_resolver(cache))
    plan = asyncio.run(session.prepare_output_prices(names))
    result = asyncio.run(
        session.resolve_prepared(plan, [_tradeup_result(name) for name in names])
    )

    assert plan.cache_hits_fresh_selected == names
    assert plan.new_live_names == ()
    assert len(result.valuation_result.price_lookup_result.quotes) == 10
    assert provider.calls == []
    assert session.cache_hits_fresh_selected == 10
    assert session.live_demand == 0
    assert session.live_attempted == 0


def test_nine_fresh_plus_one_miss_calls_live_only_for_miss() -> None:
    names = tuple(f"Mixed {index}" for index in range(10))
    now = datetime(2026, 8, 29, 12, 0, 30, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=ManualCacheClock(now))

    async def populate() -> None:
        for name in names[:9]:
            await _put_snapshot(cache, name, observed_at=now - timedelta(seconds=1))

    asyncio.run(populate())
    provider = RecordingPriceProvider(names)
    session = _session(provider, cached_price_resolver=_cached_resolver(cache))
    plan = asyncio.run(session.prepare_output_prices(names))
    result = asyncio.run(
        session.resolve_prepared(plan, [_tradeup_result(name) for name in names])
    )

    assert plan.cache_hits_fresh_selected == names[:9]
    assert plan.cache_misses == (names[9],)
    assert plan.new_live_names == (names[9],)
    assert provider.calls == [(names[9],)]
    assert len(result.valuation_result.price_lookup_result.quotes) == 10
    assert session.cache_hits_fresh_selected == 9
    assert session.cache_misses == 1
    assert session.live_demand == 1
    assert session.live_attempted == 1


@pytest.mark.parametrize(
    ("age", "expected_field"),
    [
        (timedelta(minutes=1), "cache_policy_blocked"),
        (timedelta(minutes=2), "cache_policy_blocked"),
        (timedelta(minutes=3), "cache_expired"),
    ],
)
def test_fresh_only_never_consumes_stale_or_expired_snapshot(
    age: timedelta,
    expected_field: str,
) -> None:
    now = datetime(2026, 8, 29, 12, 3, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=ManualCacheClock(now))
    asyncio.run(_put_snapshot(cache, "A", observed_at=now - age))
    provider = RecordingPriceProvider(("A",))
    session = _session(provider, cached_price_resolver=_cached_resolver(cache))

    plan = asyncio.run(session.prepare_output_prices(["A"]))
    assert plan.new_live_names == ("A",)
    assert getattr(plan, expected_field) == ("A",)
    assert plan.cache_hits_fresh_selected == ()
    asyncio.run(session.resolve_prepared(plan, [_tradeup_result("A")]))
    assert provider.calls == [("A",)]


def test_fresh_selection_failure_is_terminal_and_reused_without_cache_or_live() -> None:
    now = datetime(2026, 8, 29, 12, 0, 30, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=ManualCacheClock(now))
    asyncio.run(
        _put_snapshot(
            cache,
            "A",
            observed_at=now - timedelta(seconds=1),
            candidates=(_cache_candidate(platform="Steam", price="1"),),
        )
    )
    resolver = _cached_resolver(cache)
    provider = RecordingPriceProvider(("A",))
    session = _session(provider, cached_price_resolver=resolver)

    first = asyncio.run(session.prepare_output_prices(["A"]))
    assert first.cache_terminal_selection_failures == ("A",)
    assert first.new_live_names == ()
    result = asyncio.run(session.resolve_prepared(first, [_tradeup_result("A")]))
    assert result.valuation_result.missing_market_hash_names == ["A"]
    assert result.valuation_result.price_lookup_result.errors == [
        "CACHE_SELECTION_TERMINAL_FAILURE: reason=buff_record_missing: "
        "item_index=0"
    ]
    second = asyncio.run(session.prepare_output_prices(["A"]))
    assert second.memo_terminal_failures == ("A",)
    reused = asyncio.run(session.resolve_prepared(second, [_tradeup_result("A")]))
    assert reused.valuation_result.price_lookup_result.errors == [
        "CACHE_SELECTION_TERMINAL_FAILURE: reason=buff_record_missing: "
        "item_index=0"
    ]
    assert second.cache_terminal_selection_failures == ()
    assert second.new_live_names == ()
    assert provider.calls == []
    assert session.cache_selection_failures == 1
    assert session.run_reuse_failures == 1


def test_selected_non_fresh_resolution_fails_closed_before_memo() -> None:
    name = "A"
    now = datetime(2026, 8, 29, 12, 1, tzinfo=UTC)
    snapshot = CachedPriceSnapshot(
        key=PriceCacheKey(market_hash_name=name),
        candidates=(_cache_candidate(),),
        observed_at=now - timedelta(minutes=1),
        stored_at=now - timedelta(minutes=1),
        policy=PriceCachePolicy(
            fresh_ttl=timedelta(minutes=1),
            stale_ttl=timedelta(minutes=1),
        ),
    )
    stale_lookup = PriceCacheLookup(
        key=snapshot.key,
        hit=True,
        state=PriceCacheState.STALE,
        snapshot=snapshot,
        age=timedelta(minutes=1),
        needs_refresh=True,
        policy_blocked=False,
        expired=False,
    )
    resolution = SteamDTCachedPriceResolution(
        status=SteamDTCachedPriceResolutionStatus.SELECTED,
        lookup=stale_lookup,
        selection_result=SteamDTPriceSelectionResult(
            market_hash_name=name,
            quote=SteamDTPriceQuote(
                market_hash_name=name,
                price_cny=Decimal("150"),
                source=SCANNER_STRICT_BUFF_SOURCE,
            ),
            selected_platform="BUFF",
            selected_strategy="strict_buff_sell_price",
            reason_codes=["strict_buff_selected"],
            candidate_decisions=[],
        ),
    )

    with pytest.raises(ScannerSessionError, match="must be fresh"):
        RunScopedValuationSession._validate_cache_resolution(name, resolution)


def test_raw_generic_cached_resolver_is_rejected_by_public_session_api() -> None:
    cache = InMemoryPriceCache()
    generic = SteamDTCachedPriceResolver(cache)

    with pytest.raises(TypeError, match="ScannerCachedBuffPriceResolver"):
        RunScopedValuationSession(
            price_provider=RecordingPriceProvider(("A",)),
            valuation_config=ValuationConfig(),
            session_id=1,
            cached_price_resolver=generic,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "error",
    [
        PriceCacheBackendError("get", "unavailable"),
        PriceCacheCodecError("payload_json", "corrupt"),
    ],
)
def test_cache_backend_and_codec_errors_propagate_without_live(
    error: Exception,
) -> None:
    reader = RecordingCacheReader(error=error)
    resolver = ScannerCachedBuffPriceResolver(reader)
    provider = RecordingPriceProvider(("A",))
    session = _session(provider, cached_price_resolver=resolver)

    with pytest.raises(type(error)) as exc_info:
        asyncio.run(session.prepare_output_prices(["A"]))

    assert exc_info.value is error
    assert provider.calls == []
    assert session.live_demand == 0


def test_cache_adapter_error_propagates_without_live() -> None:
    now = datetime(2026, 8, 29, 12, 0, 30, tzinfo=UTC)
    candidate = _cache_candidate()
    object.__setattr__(candidate, "source_update_time", True)
    snapshot = CachedPriceSnapshot(
        key=PriceCacheKey(market_hash_name="A"),
        candidates=(candidate,),
        observed_at=now - timedelta(seconds=1),
        stored_at=now - timedelta(seconds=1),
        policy=PriceCachePolicy(fresh_ttl=timedelta(minutes=1)),
    )
    lookup = PriceCacheLookup(
        key=snapshot.key,
        hit=True,
        state=PriceCacheState.FRESH,
        snapshot=snapshot,
        age=timedelta(seconds=1),
        needs_refresh=False,
        policy_blocked=False,
        expired=False,
    )
    reader = RecordingCacheReader(lookup=lookup)
    resolver = ScannerCachedBuffPriceResolver(reader)
    provider = RecordingPriceProvider(("A",))
    session = _session(provider, cached_price_resolver=resolver)

    with pytest.raises(SteamDTPriceCacheAdapterError):
        asyncio.run(session.prepare_output_prices(["A"]))
    assert provider.calls == []
    assert session.live_demand == 0


def test_resolver_contract_error_propagates_without_live() -> None:
    key = PriceCacheKey(market_hash_name="B")
    reader = RecordingCacheReader(lookup=PriceCacheLookup.missing(key))
    resolver = ScannerCachedBuffPriceResolver(reader)
    provider = RecordingPriceProvider(("A",))
    session = _session(provider, cached_price_resolver=resolver)

    with pytest.raises(SteamDTCachedPriceResolverError, match="different key"):
        asyncio.run(session.prepare_output_prices(["A"]))
    assert provider.calls == []
    assert session.live_demand == 0


def test_cache_success_survives_atomic_block_but_miss_is_read_again() -> None:
    now = datetime(2026, 8, 29, 12, 0, 30, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=ManualCacheClock(now))
    asyncio.run(_put_snapshot(cache, "A", observed_at=now - timedelta(seconds=1)))

    class TrackingReader:
        def __init__(self, delegate: InMemoryPriceCache) -> None:
            self.delegate = delegate
            self.calls: list[str] = []

        async def get(
            self,
            key: PriceCacheKey,
            *,
            read_policy: PriceCacheReadPolicy = PriceCacheReadPolicy.FRESH_ONLY,
        ) -> PriceCacheLookup:
            self.calls.append(key.market_hash_name)
            return await self.delegate.get(key, read_policy=read_policy)

    tracking = TrackingReader(cache)
    resolver = ScannerCachedBuffPriceResolver(tracking)
    provider = RecordingPriceProvider(("B",))
    session = _session(provider, cached_price_resolver=resolver)

    blocked = asyncio.run(session.prepare_output_prices(["A", "B"]))
    assert blocked.cache_hits_fresh_selected == ("A",)
    assert blocked.cache_misses == ("B",)
    session.record_atomically_blocked(blocked)
    later = asyncio.run(session.prepare_output_prices(["A", "B"]))

    assert later.memo_successes == ("A",)
    assert later.cache_misses == ("B",)
    assert later.new_live_names == ("B",)
    assert tracking.calls == ["A", "B", "B"]
    assert provider.calls == []
    assert session.cache_hits_fresh_selected == 1
    assert session.cache_misses == 2
    assert session.run_reuse_successes == 1
    assert session.live_atomically_blocked == 1


def test_live_success_is_not_written_to_persistent_cache_or_shared_across_runs() -> None:
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    cache = InMemoryPriceCache(clock=ManualCacheClock(now))
    resolver = _cached_resolver(cache)
    provider = RecordingPriceProvider(("X",))

    first_session = _session(
        provider,
        session_id=1,
        cached_price_resolver=resolver,
    )
    first = asyncio.run(first_session.prepare_output_prices(["X"]))
    assert first.cache_misses == ("X",)
    asyncio.run(first_session.resolve_prepared(first, [_tradeup_result("X")]))
    same_run = asyncio.run(first_session.prepare_output_prices(["X"]))
    assert same_run.memo_successes == ("X",)
    assert same_run.cache_misses == ()

    persistent = asyncio.run(
        cache.get(
            PriceCacheKey(market_hash_name="X"),
            read_policy=PriceCacheReadPolicy.FRESH_ONLY,
        )
    )
    assert persistent.hit is False
    assert persistent.state is None

    second_session = _session(
        provider,
        session_id=2,
        cached_price_resolver=resolver,
    )
    second = asyncio.run(second_session.prepare_output_prices(["X"]))
    assert second.cache_misses == ("X",)
    asyncio.run(second_session.resolve_prepared(second, [_tradeup_result("X")]))

    assert provider.calls == [("X",), ("X",)]
    assert first_session.cache_misses == 1
    assert second_session.cache_misses == 1


def test_prepared_plan_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    provider = RecordingPriceProvider(("A",))
    session = _session(provider)
    plan = asyncio.run(session.prepare_output_prices(["A"]))
    with pytest.raises(FrozenInstanceError):
        plan.new_live_names = ("B",)  # type: ignore[misc]
