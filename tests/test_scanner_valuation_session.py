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
from decimal import Decimal

import pytest

from app.services.price_provider import (
    MockPriceProvider,
    PriceLookupResult,
    PriceProvider,
    PriceQuote,
)
from app.services.scanner_valuation_session import (
    RunScopedValuationSession,
    ScannerSessionError,
)
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
) -> RunScopedValuationSession:
    return RunScopedValuationSession(
        price_provider=provider,
        valuation_config=config or ValuationConfig(),
        session_id=session_id,
    )


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


# J. No Phase 12D cache dependency.


def test_no_phase_12d_cache_dependency() -> None:
    """Neither Phase 14B production module imports Phase 12D cache code."""
    import ast
    from pathlib import Path

    import app.services.scanner_orchestrator as orchestrator_module
    import app.services.scanner_valuation_session as session_module

    forbidden_modules = {
        "app.services.price_cache",
        "app.services.price_cache_codec",
        "app.services.redis_price_cache",
        "app.services.price_cache_factory",
        "app.services.steamdt_price_cache_adapter",
        "app.services.steamdt_cached_price_resolver",
        "app.services.steamdt_price_snapshot_source",
        "app.services.steamdt_price_refresh_service",
        "app.services.steamdt_refresh_planner",
        "app.services.steamdt_refresh_executor",
    }
    forbidden_symbols = {
        "PriceCache",
        "PriceCacheReadPolicy",
        "InMemoryPriceCache",
        "RedisPriceCache",
        "SteamDTCachedPriceResolver",
        "SteamDTPriceRefreshService",
    }

    for module in (session_module, orchestrator_module):
        path = Path(module.__file__ or "")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_modules: set[str] = set()
        referenced_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)
            elif isinstance(node, ast.Name):
                referenced_names.add(node.id)
        assert forbidden_modules.isdisjoint(imported_modules), (
            f"{path} imports Phase 12D cache modules"
        )
        assert forbidden_symbols.isdisjoint(referenced_names), (
            f"{path} references Phase 12D cache symbols"
        )


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


# PreparedOutputPricePlan is a frozen dataclass; cannot mutate.


def test_prepared_plan_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    provider = RecordingPriceProvider(("A",))
    session = _session(provider)
    plan = asyncio.run(session.prepare_output_prices(["A"]))
    with pytest.raises(FrozenInstanceError):
        plan.new_live_names = ("B",)  # type: ignore[misc]
