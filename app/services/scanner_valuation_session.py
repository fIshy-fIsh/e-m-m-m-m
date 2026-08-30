"""Phase 14C — Run-scoped exact-name valuation session with cache reads.

Scanner-owned lifetime: EXACTLY one ``LiveScannerOrchestrator.run_once()``
call. Two-stage contract:

  Stage A — ``prepare_output_prices(names)``
      Consults the run memo first, then optionally reads the existing Phase 12D
      cache sequentially with ``PriceCacheReadPolicy.FRESH_ONLY``. ZERO live
      provider calls. Fresh strict-BUFF selections and terminal selection
      failures enter the run memo immediately; miss, expired, and
      policy-blocked names become ordered NEW LIVE demand.

  Stage B — ``resolve_prepared(plan, tradeup_results)``
      Called ONLY after the orchestrator's atomic-cap admission. Calls the
      underlying ``PriceProvider.get_prices`` ONLY for ``plan.new_live_names``;
      never re-reads or writes the persistent cache. Builds a full logical
      ``PriceLookupResult`` from memo + cache + live results, and applies the
      existing ``ValuationService`` for valuation field application.

The optional cache resolver may outlive a run. The session memo never does.
Scanner write-after-live, refresh services, and background work are absent.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from app.services.price_cache import PriceCacheKey, PriceCacheState
from app.services.price_provider import (
    PriceLookupResult,
    PriceProvider,
    PriceQuote,
)
from app.services.scanner_cached_buff_price_resolver import (
    ScannerCachedBuffPriceResolver,
)
from app.services.scanner_cached_buff_price_selector import (
    SCANNER_STRICT_BUFF_SELECTION_STRATEGY,
    SCANNER_STRICT_BUFF_SOURCE,
)
from app.services.steamdt_cached_price_resolver import (
    SteamDTCachedPriceResolution,
    SteamDTCachedPriceResolutionStatus,
)
from app.services.tradeup_engine import TradeupResult
from app.services.valuation_service import (
    ValuationConfig,
    ValuationResult,
    ValuationService,
)

__all__ = (
    "PreparedOutputPricePlan",
    "RunScopedValuationSession",
    "ScannerSessionError",
    "SessionValuationResult",
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ScannerSessionError(RuntimeError):
    """Raised when a scanner session contract is violated.

    Contract violations include foreign plans, stale plans, plans that
    have already been executed, plans that have already been marked
    blocked, malformed exact names, and mismatched plan/recipe shape.
    """


# ---------------------------------------------------------------------------
# Internal memo
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class _MemoEntry:
    """One entry in the run-scoped memo; one per exact output name."""

    kind: str  # "success" or "failure"
    quote: PriceQuote | None = None
    failure_reason: str | None = None


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class PreparedOutputPricePlan:
    """Immutable plan returned by Stage A ``prepare_output_prices``.

    Tied to the session that created it via ``session_id``.
    Has a unique ``plan_id`` to detect double-execution / double-block.
    """

    session_id: int
    session_token: object = field(repr=False, compare=False)
    plan_id: int
    memo_revision: int
    requested_names: tuple[str, ...]
    memo_successes: tuple[str, ...] = ()
    memo_terminal_failures: tuple[str, ...] = ()
    cache_hits_fresh_selected: tuple[str, ...] = ()
    cache_terminal_selection_failures: tuple[str, ...] = ()
    cache_misses: tuple[str, ...] = ()
    cache_policy_blocked: tuple[str, ...] = ()
    cache_expired: tuple[str, ...] = ()
    new_live_names: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class SessionValuationResult:
    """Result returned by Stage B ``resolve_prepared``.

    Wraps the underlying ``ValuationResult`` plus the per-recipe
    discriminator deltas recorded by the session.
    """

    valuation_result: ValuationResult
    live_attempted_delta: int
    live_succeeded_delta: int
    live_failed_delta: int
    run_reuse_hits_delta: int
    run_reuse_successes_delta: int
    run_reuse_failures_delta: int


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class RunScopedValuationSession:
    """Scanner-owned run-scoped exact-name valuation reuse session.

    Lifetime: one ``LiveScannerOrchestrator.run_once()`` call.
    """

    def __init__(
        self,
        *,
        price_provider: PriceProvider,
        valuation_config: ValuationConfig,
        session_id: int,
        cached_price_resolver: ScannerCachedBuffPriceResolver | None = None,
    ) -> None:
        if price_provider is None:
            raise TypeError("price_provider is required")
        if valuation_config is None:
            raise TypeError("valuation_config is required")
        if type(session_id) is not int or session_id < 0:
            raise TypeError("session_id must be a non-negative integer")
        if cached_price_resolver is not None and type(
            cached_price_resolver
        ) is not ScannerCachedBuffPriceResolver:
            raise TypeError(
                "cached_price_resolver must be a ScannerCachedBuffPriceResolver"
            )
        self._price_provider = price_provider
        self._valuation_config = valuation_config
        self._cached_price_resolver = cached_price_resolver
        self._session_id = session_id
        self._session_token = object()
        self._memo: dict[str, _MemoEntry] = {}
        self._memo_revision = 0
        self._prepared_plans: dict[int, PreparedOutputPricePlan] = {}
        self._executed_plan_ids: set[int] = set()
        self._blocked_plan_ids: set[int] = set()
        self._next_plan_id = 0
        # Per-session cumulative discriminator counters (cleared per session).
        self._run_reuse_hits = 0
        self._run_reuse_successes = 0
        self._run_reuse_failures = 0
        self._cache_hits_fresh_selected = 0
        self._cache_misses = 0
        self._cache_policy_blocked = 0
        self._cache_expired = 0
        self._cache_selection_failures = 0
        self._live_demand = 0
        self._live_attempted = 0
        self._live_succeeded = 0
        self._live_failed = 0
        self._live_atomically_blocked = 0

    @property
    def session_id(self) -> int:
        return self._session_id

    @property
    def run_reuse_hits(self) -> int:
        return self._run_reuse_hits

    @property
    def run_reuse_successes(self) -> int:
        return self._run_reuse_successes

    @property
    def run_reuse_failures(self) -> int:
        return self._run_reuse_failures

    @property
    def cache_hits_fresh_selected(self) -> int:
        return self._cache_hits_fresh_selected

    @property
    def cache_misses(self) -> int:
        return self._cache_misses

    @property
    def cache_policy_blocked(self) -> int:
        return self._cache_policy_blocked

    @property
    def cache_expired(self) -> int:
        return self._cache_expired

    @property
    def cache_selection_failures(self) -> int:
        return self._cache_selection_failures

    @property
    def live_demand(self) -> int:
        return self._live_demand

    @property
    def live_attempted(self) -> int:
        return self._live_attempted

    @property
    def live_succeeded(self) -> int:
        return self._live_succeeded

    @property
    def live_failed(self) -> int:
        return self._live_failed

    @property
    def live_atomically_blocked(self) -> int:
        return self._live_atomically_blocked

    def _allocate_plan_id(self) -> int:
        pid = self._next_plan_id
        self._next_plan_id += 1
        return pid

    @staticmethod
    def _validate_name(name: object) -> str:
        if type(name) is not str:
            raise ScannerSessionError(
                f"output_market_hash_name must be a string, got "
                f"{type(name).__name__}"
            )
        if not name:
            raise ScannerSessionError(
                "output_market_hash_name must be non-empty"
            )
        if name != name.strip():
            raise ScannerSessionError(
                "output_market_hash_name has surrounding whitespace"
            )
        return name

    async def prepare_output_prices(
        self,
        market_hash_names: Sequence[str],
    ) -> PreparedOutputPricePlan:
        """Stage A: classify names via memo then FRESH_ONLY cache reads.

        This method never calls the live provider. Cache selected/failure
        outcomes enter the run memo before the canonical plan is finalized.
        Miss, expired, and policy-blocked outcomes remain unmemoized NEW LIVE
        demand and can therefore be re-read after an atomic block.
        """
        if type(market_hash_names) in {str, bytes}:
            raise ScannerSessionError(
                "market_hash_names must be a sequence of exact names"
            )
        unique_names: list[str] = []
        seen: set[str] = set()
        for raw in market_hash_names:
            name = self._validate_name(raw)
            if name in seen:
                continue
            seen.add(name)
            unique_names.append(name)

        memo_successes: list[str] = []
        memo_terminal_failures: list[str] = []
        cache_hits_fresh_selected: list[str] = []
        cache_terminal_selection_failures: list[str] = []
        cache_misses: list[str] = []
        cache_policy_blocked: list[str] = []
        cache_expired: list[str] = []
        unresolved_names: list[str] = []

        for name in unique_names:
            entry = self._memo.get(name)
            if entry is None:
                unresolved_names.append(name)
                continue
            if entry.kind == "success":
                memo_successes.append(name)
                self._run_reuse_hits += 1
                self._run_reuse_successes += 1
            else:
                memo_terminal_failures.append(name)
                self._run_reuse_hits += 1
                self._run_reuse_failures += 1

        new_live_names: list[str] = []
        if self._cached_price_resolver is None:
            new_live_names.extend(unresolved_names)
        else:
            for name in unresolved_names:
                resolution = await self._cached_price_resolver.resolve(name)
                status, cached_quote, failure_reason = (
                    self._validate_cache_resolution(name, resolution)
                )
                if status == SteamDTCachedPriceResolutionStatus.SELECTED:
                    assert cached_quote is not None
                    self._memo[name] = _MemoEntry(
                        kind="success",
                        quote=cached_quote,
                    )
                    cache_hits_fresh_selected.append(name)
                    self._cache_hits_fresh_selected += 1
                    self._memo_revision += 1
                    continue
                if status == SteamDTCachedPriceResolutionStatus.SELECTION_FAILURE:
                    assert failure_reason is not None
                    self._memo[name] = _MemoEntry(
                        kind="failure",
                        failure_reason=failure_reason,
                    )
                    cache_terminal_selection_failures.append(name)
                    self._cache_selection_failures += 1
                    self._memo_revision += 1
                    continue
                if status == SteamDTCachedPriceResolutionStatus.MISS:
                    cache_misses.append(name)
                    self._cache_misses += 1
                elif status == SteamDTCachedPriceResolutionStatus.POLICY_BLOCKED:
                    cache_policy_blocked.append(name)
                    self._cache_policy_blocked += 1
                elif status == SteamDTCachedPriceResolutionStatus.EXPIRED:
                    cache_expired.append(name)
                    self._cache_expired += 1
                else:  # pragma: no cover - guarded by exact enum validation
                    raise ScannerSessionError(
                        "cached resolver returned an unsupported status"
                    )
                new_live_names.append(name)

        self._live_demand += len(new_live_names)

        plan = PreparedOutputPricePlan(
            session_id=self._session_id,
            session_token=self._session_token,
            plan_id=self._allocate_plan_id(),
            memo_revision=self._memo_revision,
            requested_names=tuple(unique_names),
            memo_successes=tuple(memo_successes),
            memo_terminal_failures=tuple(memo_terminal_failures),
            cache_hits_fresh_selected=tuple(cache_hits_fresh_selected),
            cache_terminal_selection_failures=tuple(
                cache_terminal_selection_failures
            ),
            cache_misses=tuple(cache_misses),
            cache_policy_blocked=tuple(cache_policy_blocked),
            cache_expired=tuple(cache_expired),
            new_live_names=tuple(new_live_names),
        )
        self._prepared_plans[plan.plan_id] = plan
        return plan

    @staticmethod
    def _validate_cache_resolution(
        requested_name: str,
        resolution: object,
    ) -> tuple[
        SteamDTCachedPriceResolutionStatus,
        PriceQuote | None,
        str | None,
    ]:
        if type(resolution) is not SteamDTCachedPriceResolution:
            raise ScannerSessionError(
                "cached resolver returned an invalid resolution"
            )
        expected_key = PriceCacheKey(market_hash_name=requested_name)
        if resolution.lookup.key != expected_key:
            raise ScannerSessionError(
                "cached resolver returned a mismatched cache key"
            )
        if type(resolution.status) is not SteamDTCachedPriceResolutionStatus:
            raise ScannerSessionError(
                "cached resolver returned an invalid status"
            )
        cached_quote: PriceQuote | None = None
        failure_reason: str | None = None
        if resolution.status == SteamDTCachedPriceResolutionStatus.SELECTED:
            if resolution.lookup.state is not PriceCacheState.FRESH:
                raise ScannerSessionError(
                    "cached selected resolution must be fresh"
                )
            cached_quote = RunScopedValuationSession._cache_quote(
                requested_name,
                resolution,
            )
        elif resolution.status == SteamDTCachedPriceResolutionStatus.SELECTION_FAILURE:
            if resolution.lookup.state is not PriceCacheState.FRESH:
                raise ScannerSessionError(
                    "cached selection failure resolution must be fresh"
                )
            selection = resolution.selection_result
            if (
                selection is None
                or selection.market_hash_name != requested_name
                or selection.quote is not None
                or selection.selected_platform is not None
                or selection.selected_strategy
                != SCANNER_STRICT_BUFF_SELECTION_STRATEGY
                or not resolution.selection_failure_reason_codes
                or any(
                    type(reason) is not str or not reason
                    for reason in resolution.selection_failure_reason_codes
                )
            ):
                raise ScannerSessionError(
                    "cached resolver returned an invalid selection failure"
                )
            failure_reason = (
                "CACHE_SELECTION_TERMINAL_FAILURE: reason="
                f"{resolution.selection_failure_reason_codes[0]}"
            )
        elif resolution.status not in {
            SteamDTCachedPriceResolutionStatus.MISS,
            SteamDTCachedPriceResolutionStatus.POLICY_BLOCKED,
            SteamDTCachedPriceResolutionStatus.EXPIRED,
        }:
            raise ScannerSessionError(
                "cached resolver returned an unsupported status"
            )
        return resolution.status, cached_quote, failure_reason

    @staticmethod
    def _cache_quote(
        requested_name: str,
        resolution: SteamDTCachedPriceResolution,
    ) -> PriceQuote:
        selection = resolution.selection_result
        quote = resolution.quote
        if (
            selection is None
            or quote is None
            or selection.market_hash_name != requested_name
            or selection.selected_platform != "BUFF"
            or selection.selected_strategy
            != SCANNER_STRICT_BUFF_SELECTION_STRATEGY
            or type(quote.market_hash_name) is not str
            or quote.market_hash_name != requested_name
            or type(quote.source) is not str
            or quote.source != SCANNER_STRICT_BUFF_SOURCE
            or type(quote.price_cny) is not Decimal
            or not quote.price_cny.is_finite()
            or quote.price_cny <= 0
        ):
            raise ScannerSessionError(
                "cached resolver returned an invalid strict BUFF quote"
            )
        return PriceQuote(
            market_hash_name=requested_name,
            price_cny=quote.price_cny,
            source=SCANNER_STRICT_BUFF_SOURCE,
            raw=None,
        )

    async def resolve_prepared(
        self,
        plan: PreparedOutputPricePlan,
        tradeup_results: list[TradeupResult],
    ) -> SessionValuationResult:
        """Stage B: live resolution for new exact names only.

        The plan must be from THIS session, unexecuted, and the requested
        names must match the tradeup_results' first-seen unique outputs.
        """
        self._validate_plan(plan)
        logical_names = self._tradeup_result_names(tradeup_results)
        if logical_names != plan.requested_names:
            raise ScannerSessionError(
                "prepared plan requested_names do not match tradeup_results"
            )
        # Mark executed only after all no-I/O contract validation succeeds,
        # so a malformed call cannot consume the valid plan.
        self._executed_plan_ids.add(plan.plan_id)

        # Resolve NEW LIVE names and update the run memo. The full logical
        # lookup is assembled afterward in exact requested-name order.
        live_lookup = PriceLookupResult(quotes={}, missing=[], errors=[])
        live_attempted_before = self._live_attempted
        live_succeeded_before = self._live_succeeded
        live_failed_before = self._live_failed
        if plan.new_live_names:
            # Charge the live budget the moment the live call is attempted,
            # even if the call later fails. The task spec says: "an actually
            # attempted live call consumes budget even if it fails".
            self._live_attempted += len(plan.new_live_names)
            try:
                live_lookup = await self._price_provider.get_prices(
                    list(plan.new_live_names),
                )
            except MemoryError:
                raise
            except Exception:
                # Ordinary Exception (e.g. RuntimeError, ValueError).
                # Treat all NEW LIVE names as terminal failures; preserve
                # memoed successes. Do not leak raw exception payloads.
                # BaseException subclasses that are NOT Exception
                # subclasses (KeyboardInterrupt / SystemExit /
                # CancelledError / GeneratorExit) are not caught here
                # and propagate naturally.
                live_lookup = PriceLookupResult(
                    quotes={},
                    missing=list(plan.new_live_names),
                    errors=[
                        f"LIVE_LOOKUP_FAILED: item_index={index}, "
                        "reason=PROVIDER_EXCEPTION"
                        for index, _ in enumerate(plan.new_live_names)
                    ],
                )

        normalized_live_lookup = self._normalize_lookup(
            plan.new_live_names,
            live_lookup,
        )
        for index, name in enumerate(plan.new_live_names):
            quote = normalized_live_lookup.quotes.get(name)
            if (
                name not in normalized_live_lookup.missing
                and self._is_valid_matching_quote(name, quote)
            ):
                assert quote is not None
                self._memo[name] = _MemoEntry(kind="success", quote=quote)
                self._live_succeeded += 1
                continue

            # Terminal failure: missing, mismatched/invalid identity or
            # price, unexpected extra quote, or omitted requested name.
            reason = self._failure_reason(
                index,
                name,
                normalized_live_lookup,
            )
            self._memo[name] = _MemoEntry(
                kind="failure", failure_reason=reason
            )
            self._live_failed += 1

        if plan.new_live_names:
            self._memo_revision += 1

        merged_quotes: dict[str, PriceQuote] = {}
        merged_missing: list[str] = []
        merged_errors: list[str] = []
        for index, name in enumerate(plan.requested_names):
            entry = self._memo.get(name)
            if entry is None:
                raise ScannerSessionError(
                    "prepared plan resolution left an unresolved name"
                )
            if entry.kind == "success":
                if not self._is_valid_matching_quote(name, entry.quote):
                    raise ScannerSessionError(
                        "memo success entry has no valid matching quote"
                    )
                assert entry.quote is not None
                merged_quotes[name] = entry.quote
                continue
            merged_missing.append(name)
            if name in plan.memo_terminal_failures:
                reason = (
                    entry.failure_reason
                    if entry.failure_reason is not None
                    and entry.failure_reason.startswith(
                        "CACHE_SELECTION_TERMINAL_FAILURE: reason="
                    )
                    else "RUN_REUSE_TERMINAL_FAILURE"
                )
            elif name in plan.cache_terminal_selection_failures:
                reason = entry.failure_reason or "CACHE_SELECTION_TERMINAL_FAILURE"
            else:
                reason = "LIVE_LOOKUP_TERMINAL_FAILURE"
            merged_errors.append(f"{reason}: item_index={index}")

        # Build a session-local fixed provider and apply valuation
        # field application via the existing ValuationService. This
        # preserves every Protected Core contract (no copy of math).
        merged_lookup = PriceLookupResult(
            quotes=merged_quotes,
            missing=merged_missing,
            errors=merged_errors,
        )
        fixed_provider = _FixedProvider(
            lookup=merged_lookup,
            expected_names=plan.requested_names,
        )
        valuation_service = ValuationService(
            price_provider=fixed_provider,
            config=self._valuation_config,
        )
        valuation_result = await valuation_service.value_tradeup_results(
            tradeup_results,
        )

        return SessionValuationResult(
            valuation_result=valuation_result,
            live_attempted_delta=self._live_attempted - live_attempted_before,
            live_succeeded_delta=self._live_succeeded - live_succeeded_before,
            live_failed_delta=self._live_failed - live_failed_before,
            run_reuse_hits_delta=len(plan.memo_successes)
            + len(plan.memo_terminal_failures),
            run_reuse_successes_delta=len(plan.memo_successes),
            run_reuse_failures_delta=len(plan.memo_terminal_failures),
        )

    @staticmethod
    def _is_valid_matching_quote(
        requested_name: str,
        quote: PriceQuote | None,
    ) -> bool:
        return (
            isinstance(quote, PriceQuote)
            and type(quote.market_hash_name) is str
            and quote.market_hash_name == requested_name
            and quote.market_hash_name == quote.market_hash_name.strip()
            and type(quote.source) is str
            and bool(quote.source.strip())
            and type(quote.price_cny) is Decimal
            and quote.price_cny.is_finite()
            and quote.price_cny > 0
        )

    @staticmethod
    def _normalize_lookup(
        requested_names: tuple[str, ...],
        lookup: object,
    ) -> PriceLookupResult:
        """Validate an injected provider result without replaying raw errors.

        Any malformed/contradictory/unexpected provider shape invalidates
        the entire NEW LIVE batch. A structurally valid mixed result may
        preserve matching quotes and map provider-reported errors to the
        exact ``missing`` names using bounded item-index codes.
        """
        try:
            if not isinstance(lookup, PriceLookupResult):
                return RunScopedValuationSession._invalid_lookup(
                    requested_names,
                    reason="INVALID_PROVIDER_RESULT",
                )
            if (
                type(lookup.quotes) is not dict
                or type(lookup.missing) is not list
                or type(lookup.errors) is not list
            ):
                return RunScopedValuationSession._invalid_lookup(
                    requested_names,
                    reason="INVALID_PROVIDER_RESULT",
                )
            if any(
                type(name) is not str or type(quote) is not PriceQuote
                for name, quote in lookup.quotes.items()
            ) or any(type(name) is not str for name in lookup.missing) or any(
                type(error) is not str for error in lookup.errors
            ):
                return RunScopedValuationSession._invalid_lookup(
                    requested_names,
                    reason="INVALID_PROVIDER_RESULT",
                )

            requested_set = set(requested_names)
            quote_names = set(lookup.quotes)
            missing_names = set(lookup.missing)
            if (
                len(missing_names) != len(lookup.missing)
                or not quote_names.issubset(requested_set)
                or not missing_names.issubset(requested_set)
                or bool(quote_names & missing_names)
            ):
                return RunScopedValuationSession._invalid_lookup(
                    requested_names,
                    reason="UNEXPECTED_PROVIDER_RESULT",
                )

            for key, quote in lookup.quotes.items():
                if not RunScopedValuationSession._is_valid_matching_quote(
                    key,
                    quote,
                ):
                    return RunScopedValuationSession._invalid_lookup(
                        requested_names,
                        reason="INVALID_OR_MISMATCHED_QUOTE",
                    )

            if lookup.errors and (
                not missing_names
                or len(lookup.errors) != len(lookup.missing)
            ):
                return RunScopedValuationSession._invalid_lookup(
                    requested_names,
                    reason="PROVIDER_REPORTED_ERROR",
                )

            bounded_errors = [
                "LIVE_LOOKUP_FAILED: "
                f"item_index={requested_names.index(name)}, "
                "reason=PROVIDER_REPORTED_ERROR"
                for name in lookup.missing
            ] if lookup.errors else []
            return PriceLookupResult(
                quotes=dict(lookup.quotes),
                missing=list(lookup.missing),
                errors=bounded_errors,
            )
        except MemoryError:
            raise
        except Exception:
            return RunScopedValuationSession._invalid_lookup(
                requested_names,
                reason="INVALID_PROVIDER_RESULT",
            )

    @staticmethod
    def _invalid_lookup(
        requested_names: tuple[str, ...],
        *,
        reason: str,
    ) -> PriceLookupResult:
        return PriceLookupResult(
            quotes={},
            missing=list(requested_names),
            errors=[
                f"LIVE_LOOKUP_FAILED: item_index={index}, reason={reason}"
                for index, _ in enumerate(requested_names)
            ],
        )

    @staticmethod
    def _failure_reason(
        index: int,
        name: str,
        lookup: PriceLookupResult,
    ) -> str:
        quote = lookup.quotes.get(name)
        if quote is not None:
            reason = "INVALID_OR_MISMATCHED_QUOTE"
        elif name in lookup.missing:
            reason = (
                "PROVIDER_REPORTED_ERROR"
                if lookup.errors
                else "PROVIDER_MISSING"
            )
        else:
            reason = "NOT_PROVIDED"
        return f"LIVE_LOOKUP_FAILED: item_index={index}, reason={reason}"

    def record_atomically_blocked(
        self,
        plan: PreparedOutputPricePlan,
    ) -> None:
        """Record that this plan's new LIVE names were atomically blocked.

        Called by the orchestrator when the cap preflight blocks the
        recipe AFTER prepare but BEFORE resolve_prepared. Memo is NOT
        updated for the blocked NEW LIVE names — a later recipe must
        re-prepare them, re-classify them as NEW LIVE, and either be
        admitted or blocked again.
        """
        self._validate_plan(plan)
        self._blocked_plan_ids.add(plan.plan_id)
        self._live_atomically_blocked += len(plan.new_live_names)

    @staticmethod
    def _tradeup_result_names(
        tradeup_results: Sequence[TradeupResult],
    ) -> tuple[str, ...]:
        names: list[str] = []
        seen: set[str] = set()
        for result in tradeup_results:
            if not isinstance(result, TradeupResult):
                raise ScannerSessionError(
                    "tradeup_results must contain only TradeupResult values"
                )
            name = RunScopedValuationSession._validate_name(
                result.output_market_hash_name
            )
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
        return tuple(names)

    def _validate_plan(
        self,
        plan: PreparedOutputPricePlan,
    ) -> None:
        if not isinstance(plan, PreparedOutputPricePlan):
            raise ScannerSessionError(
                f"plan must be a PreparedOutputPricePlan, got {type(plan).__name__}"
            )
        if plan.session_id != self._session_id or (
            plan.session_token is not self._session_token
        ):
            raise ScannerSessionError(
                f"prepared plan session_id {plan.session_id} does not match "
                f"session {self._session_id}"
            )
        if self._prepared_plans.get(plan.plan_id) is not plan:
            raise ScannerSessionError(
                f"prepared plan {plan.plan_id} is not the canonical session plan"
            )
        if plan.plan_id in self._executed_plan_ids:
            raise ScannerSessionError(
                f"prepared plan {plan.plan_id} cannot be executed twice"
            )
        if plan.plan_id in self._blocked_plan_ids:
            raise ScannerSessionError(
                f"prepared plan {plan.plan_id} is already marked blocked"
            )
        if plan.memo_revision != self._memo_revision:
            raise ScannerSessionError(
                f"prepared plan {plan.plan_id} is stale: memo revision "
                f"{plan.memo_revision} != {self._memo_revision}"
            )


# ---------------------------------------------------------------------------
# Internal fixed provider
# ---------------------------------------------------------------------------


class _FixedProvider:
    """A PriceProvider that returns one exact pre-computed lookup.

    The fixed provider is session-local and called once by the existing
    ``ValuationService``. Exact requested-name equality is required so
    accidental plan/result drift fails closed rather than being filtered
    into a partial lookup.
    """

    def __init__(
        self,
        *,
        lookup: PriceLookupResult,
        expected_names: tuple[str, ...],
    ) -> None:
        self._lookup = lookup
        self._expected_names = expected_names
        self._used = False

    async def get_price(self, market_hash_name: str) -> PriceQuote:
        raise ScannerSessionError(
            "scanner session fixed provider does not support single lookup"
        )

    async def get_prices(
        self,
        market_hash_names: list[str],
    ) -> PriceLookupResult:
        if self._used:
            raise ScannerSessionError(
                "scanner session fixed provider cannot be used twice"
            )
        requested_names = tuple(market_hash_names)
        if requested_names != self._expected_names:
            raise ScannerSessionError(
                "scanner session fixed provider requested names do not match "
                "prepared plan"
            )
        self._used = True
        return PriceLookupResult(
            quotes=dict(self._lookup.quotes),
            missing=list(self._lookup.missing),
            errors=list(self._lookup.errors),
        )
