"""Phase 16C — Strict SteamDT BUFF batch pre-screen boundary.

The resolver reuses the existing SteamDT batch transport, existing
batch response parser, and strict BUFF selector
`select_buff_output_price`. The generic transport's selected quotes
are ignored; its raw response is parsed into selector-before platform
candidates, then the strict BUFF policy is applied.

This is ranking/pruning evidence only. It is not final valuation
and has no production scanner caller in Phase 16C.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.clients.steamdt_client import (
    SteamDTBatchPriceResult,
    parse_price_batch_response,
)
from app.clients.steamdt_price_selection import (
    SteamDTPriceSelectionConfig,
    SteamDTPriceSelectionStrategy,
)
from app.services.steamdt_buff_price_policy import (
    SteamDTBuffPriceSelectionError,
    select_buff_output_price,
)
from app.services.steamdt_market_data import SteamDTMarketDataResult

__all__ = (
    "PRESCREEN_BATCH_CHUNK_SIZE",
    "SteamDTBatchPreScreenDiagnostics",
    "SteamDTBatchPreScreenError",
    "SteamDTBatchPreScreenQuote",
    "SteamDTBatchPreScreenRequest",
    "SteamDTBatchPreScreenResolver",
    "SteamDTBatchPreScreenResult",
    "SteamDTBuffPreScreenQuote",
    "build_steamdt_batch_prescreen_resolver",
)

PRESCREEN_BATCH_CHUNK_SIZE = 10
_SOURCE = "steamdt:buff-prescreen"
_TRANSPORT_SELECTION_CONFIG = SteamDTPriceSelectionConfig(
    strategy=SteamDTPriceSelectionStrategy.LOWEST_POSITIVE_SELL_PRICE,
    require_sell_count=False,
    require_bidding_price=False,
    fallback_to_lowest_positive=False,
)


class SteamDTBatchTransport(Protocol):
    async def get_price_batch_with_selection(
        self,
        market_hash_names: list[str],
        *,
        selection_config: SteamDTPriceSelectionConfig | None = None,
        avg_prices_by_name: dict[str, Decimal] | None = None,
    ) -> SteamDTBatchPriceResult: ...


class SteamDTBatchPreScreenError(ValueError):
    """A batch pre-screen contract violation."""


def _exact_name(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise SteamDTBatchPreScreenError(
            "market_hash_name must be an exact non-empty string"
        )
    return value


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamDTBatchPreScreenRequest:
    market_hash_names: Sequence[str]

    def __post_init__(self) -> None:
        if isinstance(self.market_hash_names, (str, bytes)) or not isinstance(
            self.market_hash_names, Sequence
        ):
            raise SteamDTBatchPreScreenError(
                "market_hash_names must be a sequence of strings"
            )
        for name in self.market_hash_names:
            _exact_name(name)


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamDTBuffPreScreenQuote:
    market_hash_name: str
    sell_price_cny: Decimal
    sell_count: int | None
    update_time: int | str | None
    source: str = _SOURCE

    def __post_init__(self) -> None:
        _exact_name(self.market_hash_name)
        if type(self.sell_price_cny) is not Decimal:
            raise SteamDTBatchPreScreenError("sell_price_cny must be Decimal")
        if not self.sell_price_cny.is_finite() or self.sell_price_cny <= 0:
            raise SteamDTBatchPreScreenError(
                "sell_price_cny must be positive and finite"
            )
        if self.sell_count is not None and (
            type(self.sell_count) is not int or self.sell_count < 0
        ):
            raise SteamDTBatchPreScreenError("invalid sell_count")
        if self.update_time is not None and type(self.update_time) not in (
            int,
            str,
        ):
            raise SteamDTBatchPreScreenError("invalid update_time")


SteamDTBatchPreScreenQuote = SteamDTBuffPreScreenQuote


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamDTBatchPreScreenDiagnostics:
    logical_requested_names: int
    unique_names: int
    duplicates_suppressed: int
    chunk_count: int
    transport_attempted_names: int
    selected_names: int
    missing_names: int
    terminal_selection_failures: int
    transport_errors: tuple[str, ...]

    def __post_init__(self) -> None:
        counts = (
            self.logical_requested_names,
            self.unique_names,
            self.duplicates_suppressed,
            self.chunk_count,
            self.transport_attempted_names,
            self.selected_names,
            self.missing_names,
            self.terminal_selection_failures,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            raise SteamDTBatchPreScreenError(
                "diagnostic counters must be non-negative integers"
            )
        if type(self.transport_errors) is not tuple or any(
            type(value) is not str for value in self.transport_errors
        ):
            raise SteamDTBatchPreScreenError(
                "transport_errors must be tuple[str, ...]"
            )


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamDTBatchPreScreenResult:
    requested_market_hash_names: tuple[str, ...]
    quotes: tuple[SteamDTBuffPreScreenQuote, ...]
    missing_market_hash_names: tuple[str, ...]
    terminal_selection_failures: tuple[tuple[str, str], ...]
    diagnostics: SteamDTBatchPreScreenDiagnostics

    def __post_init__(self) -> None:
        if type(self.requested_market_hash_names) is not tuple:
            raise SteamDTBatchPreScreenError("requested names must be tuple")
        if type(self.quotes) is not tuple or any(
            type(value) is not SteamDTBuffPreScreenQuote for value in self.quotes
        ):
            raise SteamDTBatchPreScreenError("quotes contain invalid values")
        if type(self.missing_market_hash_names) is not tuple:
            raise SteamDTBatchPreScreenError("missing names must be tuple")
        if type(self.terminal_selection_failures) is not tuple:
            raise SteamDTBatchPreScreenError(
                "terminal_selection_failures must be tuple"
            )
        if type(self.diagnostics) is not SteamDTBatchPreScreenDiagnostics:
            raise SteamDTBatchPreScreenError("invalid diagnostics")


def _normalise_names(names: Sequence[str]) -> tuple[tuple[str, ...], int]:
    seen: set[str] = set()
    unique: list[str] = []
    duplicates = 0
    for value in names:
        name = _exact_name(value)
        if name in seen:
            duplicates += 1
        else:
            seen.add(name)
            unique.append(name)
    return tuple(unique), duplicates


def _chunks(values: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    return tuple(
        values[index : index + PRESCREEN_BATCH_CHUNK_SIZE]
        for index in range(0, len(values), PRESCREEN_BATCH_CHUNK_SIZE)
    )


def _response_names(raw: object) -> tuple[str, ...]:
    if type(raw) is not dict:
        raise SteamDTBatchPreScreenError("batch transport returned no raw payload")
    data = raw.get("data")
    if type(data) is not list:
        raise SteamDTBatchPreScreenError("batch raw payload data must be list")
    names: list[str] = []
    for item in data:
        if type(item) is not dict:
            raise SteamDTBatchPreScreenError("batch item must be object")
        names.append(_exact_name(item.get("marketHashName")))
    return tuple(names)


@dataclass(frozen=True, kw_only=True, repr=False)
class SteamDTBatchPreScreenResolver:
    client: SteamDTBatchTransport

    def __post_init__(self) -> None:
        method = getattr(self.client, "get_price_batch_with_selection", None)
        if not callable(method):
            raise SteamDTBatchPreScreenError(
                "client must expose get_price_batch_with_selection"
            )

    async def prescreen(
        self,
        request: SteamDTBatchPreScreenRequest,
    ) -> SteamDTBatchPreScreenResult:
        if type(request) is not SteamDTBatchPreScreenRequest:
            raise SteamDTBatchPreScreenError("invalid pre-screen request")
        logical = tuple(request.market_hash_names)
        unique, duplicates = _normalise_names(logical)
        chunks = _chunks(unique)
        selected: dict[str, SteamDTBuffPreScreenQuote] = {}
        missing: set[str] = set()
        failures: dict[str, str] = {}
        transport_errors: list[str] = []
        attempted = 0

        for chunk in chunks:
            attempted += len(chunk)
            try:
                transport_result = await self.client.get_price_batch_with_selection(
                    list(chunk),
                    selection_config=_TRANSPORT_SELECTION_CONFIG,
                )
                if type(transport_result.raw) is not dict:
                    raise SteamDTBatchPreScreenError(
                        "batch transport returned no raw payload"
                    )
                raw_payload = transport_result.raw
                names = _response_names(raw_payload)
                if len(set(names)) != len(names):
                    raise SteamDTBatchPreScreenError(
                        "duplicate response entries for one exact name"
                    )
                if set(names) - set(chunk):
                    raise SteamDTBatchPreScreenError(
                        "batch response contains unsolicited exact names"
                    )
                parsed = parse_price_batch_response(
                    list(chunk),
                    raw_payload,
                    endpoint="phase16c_batch_prescreen",
                )
            except MemoryError:
                raise
            except Exception as exc:
                transport_errors.append(type(exc).__name__)
                missing.update(chunk)
                continue

            for name in chunk:
                candidates = parsed.get(name)
                if candidates is None:
                    missing.add(name)
                    continue
                try:
                    strict = select_buff_output_price(
                        market_data=SteamDTMarketDataResult(
                            market_hash_name=name,
                            quotes=tuple(candidates),
                        )
                    )
                except MemoryError:
                    raise
                except SteamDTBuffPriceSelectionError as exc:
                    failures[name] = exc.reason.value
                    missing.add(name)
                    continue
                selected[name] = SteamDTBuffPreScreenQuote(
                    market_hash_name=name,
                    sell_price_cny=strict.sell_price_cny,
                    sell_count=strict.sell_count,
                    update_time=strict.update_time,
                )

        ordered_quotes = tuple(selected[name] for name in unique if name in selected)
        ordered_missing = tuple(name for name in unique if name in missing)
        ordered_failures = tuple(
            (name, failures[name]) for name in unique if name in failures
        )
        diagnostics = SteamDTBatchPreScreenDiagnostics(
            logical_requested_names=len(logical),
            unique_names=len(unique),
            duplicates_suppressed=duplicates,
            chunk_count=len(chunks),
            transport_attempted_names=attempted,
            selected_names=len(ordered_quotes),
            missing_names=len(ordered_missing),
            terminal_selection_failures=len(ordered_failures),
            transport_errors=tuple(transport_errors),
        )
        return SteamDTBatchPreScreenResult(
            requested_market_hash_names=unique,
            quotes=ordered_quotes,
            missing_market_hash_names=ordered_missing,
            terminal_selection_failures=ordered_failures,
            diagnostics=diagnostics,
        )


def build_steamdt_batch_prescreen_resolver(
    *,
    client: SteamDTBatchTransport,
    chunk_size: int = PRESCREEN_BATCH_CHUNK_SIZE,
) -> SteamDTBatchPreScreenResolver:
    """Build the strict resolver with the frozen project chunk size."""

    if chunk_size != PRESCREEN_BATCH_CHUNK_SIZE:
        raise SteamDTBatchPreScreenError(
            f"chunk_size must equal {PRESCREEN_BATCH_CHUNK_SIZE}"
        )
    return SteamDTBatchPreScreenResolver(client=client)
