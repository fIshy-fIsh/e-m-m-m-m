"""Phase 16D — Immutable strict-BUFF pre-screen price evidence.

This boundary consumes normalized Phase 16C results only. It performs no
transport, retains no raw provider payload, and uses exact market names.
SteamDT ``update_time`` values remain opaque diagnostics and are never parsed
or ordered here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.services.steamdt_batch_prescreen import (
    SteamDTBatchPreScreenResult,
    SteamDTBuffPreScreenQuote,
)

__all__ = (
    "PreScreenPriceBook",
    "PreScreenPriceBookError",
    "build_prescreen_price_book",
)


class PreScreenPriceBookError(ValueError):
    """Normalized pre-screen evidence violated the exact-name contract."""


def _exact_text(value: object, *, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise PreScreenPriceBookError(f"{field} must be an exact non-empty string")
    return value


def _unique_exact_names(values: tuple[str, ...], *, field: str) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise PreScreenPriceBookError(f"{field} must be an exact tuple")
    checked = tuple(_exact_text(value, field=field) for value in values)
    if len(set(checked)) != len(checked):
        raise PreScreenPriceBookError(f"{field} must not contain duplicates")
    return tuple(sorted(checked))


@dataclass(frozen=True, kw_only=True, repr=False)
class PreScreenPriceBook:
    """Pure immutable exact-name lookup over strict BUFF quotes."""

    quotes_by_name: Mapping[str, SteamDTBuffPreScreenQuote]
    missing_names: tuple[str, ...] = ()
    terminal_failures: tuple[tuple[str, str], ...] = ()
    transport_errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.quotes_by_name, Mapping):
            raise PreScreenPriceBookError("quotes_by_name must be a mapping")
        normalized: dict[str, SteamDTBuffPreScreenQuote] = {}
        for raw_name, quote in self.quotes_by_name.items():
            name = _exact_text(raw_name, field="quote key")
            if type(quote) is not SteamDTBuffPreScreenQuote:
                raise PreScreenPriceBookError(
                    "quotes_by_name values must be SteamDTBuffPreScreenQuote"
                )
            if quote.market_hash_name != name:
                raise PreScreenPriceBookError(
                    "quote key must equal quote.market_hash_name exactly"
                )
            if name in normalized:
                raise PreScreenPriceBookError("duplicate exact quote name")
            normalized[name] = quote

        missing = _unique_exact_names(self.missing_names, field="missing_names")
        if type(self.terminal_failures) is not tuple:
            raise PreScreenPriceBookError("terminal_failures must be an exact tuple")
        failures: list[tuple[str, str]] = []
        failure_names: set[str] = set()
        for entry in self.terminal_failures:
            if type(entry) is not tuple or len(entry) != 2:
                raise PreScreenPriceBookError(
                    "terminal_failures entries must be (exact_name, reason)"
                )
            name = _exact_text(entry[0], field="terminal failure name")
            reason = _exact_text(entry[1], field="terminal failure reason")
            if name in failure_names:
                raise PreScreenPriceBookError("duplicate terminal failure name")
            failure_names.add(name)
            failures.append((name, reason))
        if type(self.transport_errors) is not tuple or any(
            type(value) is not str or not value
            for value in self.transport_errors
        ):
            raise PreScreenPriceBookError(
                "transport_errors must be tuple[non-empty str, ...]"
            )
        quote_names = set(normalized)
        if quote_names.intersection(missing) or quote_names.intersection(failure_names):
            raise PreScreenPriceBookError(
                "one exact name cannot be both quoted and missing/failed"
            )

        object.__setattr__(
            self,
            "quotes_by_name",
            MappingProxyType(dict(sorted(normalized.items()))),
        )
        object.__setattr__(self, "missing_names", missing)
        object.__setattr__(
            self,
            "terminal_failures",
            tuple(sorted(failures)),
        )

    def quote_for(self, market_hash_name: str) -> SteamDTBuffPreScreenQuote | None:
        """Return one strict quote by exact name; never normalize the key."""

        if type(market_hash_name) is not str:
            return None
        return self.quotes_by_name.get(market_hash_name)

    @property
    def quoted_names(self) -> tuple[str, ...]:
        return tuple(self.quotes_by_name)

    @property
    def terminal_failure_names(self) -> tuple[str, ...]:
        return tuple(name for name, _reason in self.terminal_failures)


def build_prescreen_price_book(
    result: SteamDTBatchPreScreenResult,
) -> PreScreenPriceBook:
    """Copy one normalized Phase 16C result into immutable pure evidence."""

    if type(result) is not SteamDTBatchPreScreenResult:
        raise PreScreenPriceBookError("result must be SteamDTBatchPreScreenResult")
    quotes: dict[str, SteamDTBuffPreScreenQuote] = {}
    for quote in result.quotes:
        if quote.market_hash_name in quotes:
            raise PreScreenPriceBookError("duplicate quote in Phase 16C result")
        quotes[quote.market_hash_name] = quote
    return PreScreenPriceBook(
        quotes_by_name=quotes,
        missing_names=result.missing_market_hash_names,
        terminal_failures=result.terminal_selection_failures,
        transport_errors=result.diagnostics.transport_errors,
    )
