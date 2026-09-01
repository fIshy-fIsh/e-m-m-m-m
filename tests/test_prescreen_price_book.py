"""Phase 16D — Immutable pre-screen price book tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.prescreen_price_book import (
    PreScreenPriceBook,
    PreScreenPriceBookError,
    build_prescreen_price_book,
)
from app.services.steamdt_batch_prescreen import (
    SteamDTBatchPreScreenDiagnostics,
    SteamDTBatchPreScreenResult,
    SteamDTBuffPreScreenQuote,
)


def _quote(name: str) -> SteamDTBuffPreScreenQuote:
    return SteamDTBuffPreScreenQuote(
        market_hash_name=name,
        sell_price_cny=Decimal("1.25"),
        sell_count=3,
        update_time="opaque",
    )


def test_price_book_exact_lookup_and_deterministic_iteration() -> None:
    b = _quote("B")
    a = _quote("A")
    book = PreScreenPriceBook(quotes_by_name={"B": b, "A": a})
    assert book.quoted_names == ("A", "B")
    assert book.quote_for("A") is a
    assert book.quote_for(" a ") is None
    with pytest.raises(TypeError):
        book.quotes_by_name["C"] = _quote("C")  # type: ignore[index]


def test_price_book_rejects_key_quote_identity_mismatch() -> None:
    with pytest.raises(PreScreenPriceBookError):
        PreScreenPriceBook(quotes_by_name={"A": _quote("B")})


def test_build_from_phase16c_result_retains_no_raw_transport() -> None:
    quote = _quote("A")
    result = SteamDTBatchPreScreenResult(
        requested_market_hash_names=("A", "B"),
        quotes=(quote,),
        missing_market_hash_names=("B",),
        terminal_selection_failures=(),
        diagnostics=SteamDTBatchPreScreenDiagnostics(
            logical_requested_names=2,
            unique_names=2,
            duplicates_suppressed=0,
            chunk_count=1,
            transport_attempted_names=2,
            selected_names=1,
            missing_names=1,
            terminal_selection_failures=0,
            transport_errors=(),
        ),
    )
    book = build_prescreen_price_book(result)
    assert book.quote_for("A") is quote
    assert book.missing_names == ("B",)
    assert not hasattr(book, "raw")
