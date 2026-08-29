# Phase 14A — Scanner Valuation Integration Design Freeze — Plan

## Status

- **Design freeze only.** No application code, test code, Protected Core edit, live request, scheduler, market execution, login, Cookie, browser automation, risk-control bypass, mass scraping, or invented BUFF / SteamDT endpoint.
- **Date:** 2026-08-29 (initial design freeze); revised 2026-08-29 under Phase 14A-R1 design coherence correction.
- **Branch:** `feature/scanner-valuation-integration`.
- **Baseline:** `24c95c029f583d5cc0b0a67986e48c06d0ef7957` (post-R0-D canonical main after PR #3 merge). Upstream and local synchronized at `0 0`.
- **Recommended architecture:** scanner-owned run-scoped valuation session boundary, narrow additive seam, no global cache manager, **two-stage prepare/execute contract**. The future class / API name is not frozen; choose the narrowest compatible interface after the 14B implementation begins.
- **Recommended implementation sequence:** 14B (run-scoped exact-name reuse, current strict live provider path only, no persistent cache yet) → 14C (Phase 12D cache integration under `FRESH_ONLY`, strict BUFF cache-selection adapter, READ-only, no scheduler, no write-after-live) → 14D (CLI + scale/live validation).

## Numbered task groups

### 1. Confirm current scanner valuation path and audit boundary

1. Lock the current scanner valuation chain as recorded in `requirements.md` — `LiveScannerOrchestrator.run_once` → per-recipe `_unique_output_names` → atomic preflight → `_evaluate_selection` → `ValuationService.value_tradeup_results` → `self.price_provider.get_prices` → `SteamDTBuffPriceProvider.get_prices`.
2. Lock the atomic preflight as the ONLY mutator of `valuation_requests_used` (`app/services/scanner_orchestrator.py:439`), and document the line that blocks an entire recipe before any provider call (`app/services/scanner_orchestrator.py:417-428`).
3. Lock `valuation_requests_attempted` increment location (`app/services/scanner_orchestrator.py:442-444`) — ADMITTED recipes only.
4. Lock `valuation_requests_blocked` increment location (`app/services/scanner_orchestrator.py:425-427`) — `requested_count` for blocked recipes, with `valuation_requests_used` NOT incremented.
5. Lock the absence of any Phase 12D cache import in the scanner-to-price chain (verified by grep).
6. Lock the absence of any run-scope memoization across recipe valuation calls (`SteamDTBuffPriceProvider.get_prices` only dedupes within ONE call).
7. Lock the existing `LiveRecipeEvaluation`, `ScannerRunStageCounters`, and `ScannerRunDiagnostics` shape as the surface that future counters must extend.
8. Lock the strict BUFF vs generic-selector facts:
   - `select_buff_output_price` is the ONLY strict BUFF selector; it is raise-based, bid-blind, requires exactly one BUFF record, positive finite sell price.
   - `select_steamdt_price_quote` is a **generic cross-platform** selector and CANNOT be configured strict BUFF-only (`SteamDTPriceSelectionConfig` has no platform field).
   - `SteamDTCachedPriceResolver.resolve` defaults to `select_steamdt_price_quote` — so its out-of-the-box behavior is cross-platform.
9. Lock the failure-handling facts:
   - `SteamDTBuffPriceProvider.get_prices` catches `SteamDTBuffPriceSelectionError` and other `Exception` per-name, converts to `PriceLookupResult.missing` + `prices.errors` with redacted text.
   - `MemoryError` propagates by identity (bare `raise` at `steamdt_buff_price_provider.py:52-53`).
   - Other `BaseException` subclasses propagate (no `except BaseException` anywhere).
   - `ValuationService.value_tradeup_results` catches `Exception` (excluding `MemoryError`) and converts to a `ValuationResult` with `warnings` / `missing_market_hash_names`; this is the secondary conversion site.
10. Lock `PriceLookupResult` shape: `quotes: dict[str, PriceQuote]`, `missing: list[str]`, `errors: list[str]`.
11. Lock `SteamDTCachedPriceResolutionStatus` shape: exactly five values `SELECTED`, `MISS`, `POLICY_BLOCKED`, `EXPIRED`, `SELECTION_FAILURE`. No `BACKEND_ERROR`, no `CODEC_ERROR`.
12. Lock `PriceCacheBackendError(RuntimeError)` and `PriceCacheCodecError(ValueError)` propagation: both reach the resolver's caller as the same object raised by `RedisPriceCache` / the codec, with original type, attributes, `__cause__`, and traceback intact (zero `try`/`except` in `steamdt_cached_price_resolver.py`).
13. Lock `PriceCacheLookup` 8-field shape: `key`, `hit`, `state`, `snapshot`, `age`, `needs_refresh`, `policy_blocked`, `expired` (note `expired` is distinct from `policy_blocked`).
14. Treat the existing `live_recipe_valuation.py` and `valuation_service.py` as Protected Core. Any cross-recipe reuse requires explicit migration authorization under the existing Protected-Core rules.

Deliverable: the verified audit summary above (preserved in `requirements.md`).

### 2. Freeze the seam: scanner-owned run-scoped valuation session — TWO-STAGE contract

1. Introduce a scanner-owned `RunScopedValuationSession` boundary that lives **outside** `valuation_service.py` and `live_recipe_valuation.py`. The session owns:
   - the run-scoped exact-name memo (success / terminal failure);
   - (Phase 14C) the call into `SteamDTCachedPriceResolver` (read-only);
   - (Phase 14C) the call into the existing strict live provider path for NEW LIVE demand;
   - the accounting counter updates (additive migration; see task group 7).
2. The session exposes a **two-stage contract** to the orchestrator. The future class / method names are not frozen; the contract is.

   **STAGE A — PREPARE / PLAN** (no live SteamDT calls are issued during this stage)

   ```text
   conceptual signature (14B):
     prepare_output_prices(names: tuple[str, ...]) -> PreparedResolutionPlan
     - consult run memo only
     - classify memo success / memo terminal failure / NEW LIVE demand
     - ZERO SteamDT live calls

   conceptual signature (14C):
     prepare_output_prices(names: tuple[str, ...]) -> PreparedResolutionPlan
     - consult run memo first
     - perform FRESH_ONLY cache reads next in deterministic first-seen order
     - classify strict-BUFF fresh hit / strict-BUFF terminal selection failure / miss-expired-policy-blocked needing live
     - cache backend/codec/contract exceptions propagate by identity from the cache-read seam
     - backend/codec/contract errors are NOT a MISS, NOT a live candidate, NOT a memo entry
     - ZERO SteamDT live calls

   PreparedResolutionPlan exposes:
     - memo_successes: tuple[str, ...]
     - memo_terminal_failures: tuple[str, ...]
     - cache_hits_fresh_selected: tuple[str, ...]
     - cache_terminal_selection_failures: tuple[str, ...]
     - cache_misses_or_refresh_candidates: tuple[str, ...]   (ordered NEW LIVE names; first-seen order)
     - live_demand: int   (count of NEW LIVE names)
   ```

   **STAGE B — EXECUTE / RESOLVE PREPARED** (only after orchestrator atomic-cap admission)

   ```text
   conceptual signature (14B and 14C):
     resolve_prepared(plan: PreparedResolutionPlan) -> SessionResolutionResult
     - may issue live SteamDT calls ONLY for `cache_misses_or_refresh_candidates` (Phase 14C)
       or for `NEW LIVE demand` (14B)
     - returns per-name statuses:
         SessionResolutionSuccess(market_hash_name, quote)
         SessionResolutionTerminalFailure(market_hash_name, reason)
     - populates run memo
     - increments discriminators per outcome
   ```

3. The orchestrator's atomic preflight HOLDS `live_demand` from the `PreparedResolutionPlan`. The orchestrator:
   - For an admitted recipe: increments `valuation_requests_used += live_demand`; calls `resolve_prepared(plan)`; updates legacy counters; updates discriminators per outcome.
   - For a blocked recipe: increments `valuation_requests_blocked += requested_count`; records `live_atomically_blocked += live_demand`; NEVER calls `resolve_prepared`; never issues a SteamDT live call.
4. The session does NOT resolve BUFF listing identity. It does NOT alter recipe enumeration. It does NOT cache-cross-reference with `BuffCommunityIdentityResolver` or any other identity resolver.
5. The session never observes raw provider fields; it only observes the existing strict `SteamDTBuffOutputPrice` shape returned by `SteamDTBuffPriceProvider` (for 14B), or the resolver's `SteamDTCachedPriceResolution` shape plus the strict live provider shape (for 14C).
6. The session never weakens the strict BUFF selector. The strict BUFF behavior is composed by reusing / adapting `select_buff_output_price`; the resolver's default `select_steamdt_price_quote` selector is replaced or wrapped for scanner use. See task group 4.
7. Future implementation must reuse the current `ValuationService` behavior after price resolution; do not duplicate valuation formulas.

Deliverable: the two-stage frozen contract above.

### 3. Freeze exact-name reuse semantics

1. **Run-level reuse key** is the canonical `output_market_hash_name` string itself — byte-exact, no fuzzy matching, no case folding, no aliases, no `goods_id` substitution, no `platformItemId` substitution.
2. Current canonicalization is the Steam community market canonical name (e.g. `M4A1-S | Knight (Factory New)`) used by `TradeupResult` / `OutputCandidate.market_hash_name` throughout the engine path. Phase 14A-R1 does not introduce a hidden normalization layer; it reuses the existing canonical form.
3. The canonical form is the value the orchestrator already passes into `ValuationService.value_tradeup_results` via `recipe.tradeup_results`. Phase 14 implementation must consume the same canonical form.
4. Cache key (`PriceCacheKey.market_hash_name`) is the same canonical form. The deterministic sha256 digest in `PriceCacheKey` already normalizes `currency` to uppercase and rejects non-`CNY` currencies.
5. **Run-scoped memo** behavior within one `run_once()`:
   - After `resolve_prepared`, for every name in `PriceLookupResult.quotes` (live provider outcome), the memo records success with the resolved `PriceQuote`.
   - For every name in `PriceLookupResult.missing`, the memo records terminal failure with the corresponding `errors` entry as the memoed reason.
   - During `prepare_output_prices`, names already memoed (success or terminal failure) are excluded from any cache lookup and from `live_demand`.
   - Successful exact-name resolution is reused (no second cache lookup, no second provider call).
   - Terminal exact-name failure (live provider outcome `missing`, fresh-cache strict-BUFF selection failure, or 14C backend/codec-propagated runtime error during `prepare`) is reused as failure; no automatic same-name retry.
6. The memo dies at end of `run_once()`. It is NOT persisted. It is NOT shared across `run_once()` calls. It is NOT a second persistent cache.
7. No persistent negative caching in Phase 14B or 14C. A negative outcome in the run memo is reused only within that run.

Deliverable: the exact-name reuse contract above.

### 4. Freeze strict-BUFF cache selection (Phase 14C)

1. `select_steamdt_price_quote` is **NOT** the strict BUFF selector. Its `SteamDTPriceSelectionConfig` has no platform field; its default strategy `LIQUIDITY_AWARE_SELL_PRICE` with `fallback_to_lowest_positive=True` will happily return a non-BUFF quote. The current `SteamDTCachedPriceResolver` defaults to this generic selector.
2. **Phase 14C MUST inject a strict-BUFF cache-selection adapter** behaviorally equivalent to `select_buff_output_price`. The adapter enforces:
   - exact case-sensitive platform `== "BUFF"` (matches `_BUFF_PLATFORM = "BUFF"` in `steamdt_buff_price_policy.py:12`);
   - exactly one BUFF record in the cached candidates (otherwise `DUPLICATE_BUFF_RECORDS`);
   - `sell_price_cny` must be present, `Decimal`, finite, strictly positive;
   - never reads `bidding_price_cny` / `bidding_count`;
   - never falls back to another platform;
   - never uses `fallback_to_lowest_positive`.
3. **Prefer adapting / reusing `select_buff_output_price`** rather than reimplementing the rules. If the adapter must translate `SteamDTPlatformPrice`-equivalent candidates into the shape `select_buff_output_price` expects, the translation must be byte-exact.
4. **`SteamDTCachedPriceResolver` is NOT modified in R1** or in 14C; the strict-BUFF adapter is composed at the session level, not at the resolver level. The resolver's default cross-platform selector is replaced/wrapped for scanner use by the adapter; the resolver is unchanged.
5. The adapter propagates strict-BUFF selection failure (e.g. `DUPLICATE_BUFF_RECORDS`, `BUFF_SELL_PRICE_MISSING`, `BUFF_SELL_PRICE_NON_FINITE`, `BUFF_SELL_PRICE_NON_POSITIVE`, `BUFF_RECORD_MISSING`) as terminal cache-selection failures; the session memo records them as terminal failures with the corresponding `SteamDTBuffPriceSelectionReason`.

Deliverable: the strict-BUFF cache-selection adapter contract above.

### 5. Freeze FRESH_ONLY persistent-cache policy (Phase 14C)

1. Initial scanner integration uses **`PriceCacheReadPolicy.FRESH_ONLY`**.
2. Outcome classification (under FRESH_ONLY):

   | Cache lookup outcome | Session classification | Live demand? |
   |---|---|---|
   | `FRESH + SELECTED` (strict BUFF via the adapter) | memo success (after Stage B confirms via strict live provider if writeback is on; or directly success if not) | NO |
   | `FRESH + SELECTION_FAILURE` (strict BUFF via the adapter) | memo terminal failure | NO |
   | `MISS` (`state=None, hit=False`) | live-refresh candidate if budget allows | YES |
   | `EXPIRED` (`expired=True`) | live-refresh candidate if budget allows | YES |
   | `STALE` / `STALE_GRACE` / `POLICY_BLOCKED` under FRESH_ONLY | live-refresh candidate if budget allows | YES |
   | `PriceCacheBackendError` / `PriceCacheCodecError` / `SteamDTPriceCacheAdapterError` | propagate by identity; NOT a miss; NOT a live candidate; NOT a memo entry; no live budget consumed | NO |
   | Other resolver-level error (e.g. `SteamDTCachedPriceResolverError`) | propagates by identity | NO |

3. **Cache backend / codec / adapter exceptions** are NOT live candidates. Phase 14A-R1 explicitly forbids silently reinterpreting a backend/codec/contract error as a `MISS` because doing so would erase the operational signal a Redis failure or codec corruption is sending. `PriceCacheBackendError(RuntimeError)` and `PriceCacheCodecError(ValueError)` propagate by identity from the resolver (zero `try`/`except` in `steamdt_cached_price_resolver.py`).
4. **Cache write after live success**: OUT OF SCOPE for initial Phase 14C. No scanner writeback occurs. The existing manual refresh stack (`scripts/steamdt_refresh_integration.py`) remains the only writer. A future separately authorized phase may add scanner writeback and must then define opt-in config, write-failure semantics, write counters, and whether live success survives write failure.
5. **Cache selection rerun**: on every cache hit (including `FRESH + SELECTED`), the session MUST rerun the caller-supplied strict BUFF adapter against the stored candidates. The adapter is the strict BUFF behavior described in task group 4.
6. **No platform filter at write time**: the cache stores the full ordered list of normalized SteamDT platform candidates per item, in provider response order. Selection between BUFF and any other platform happens at READ time via the strict BUFF adapter.

Deliverable: the FRESH_ONLY policy table above.

### 6. Freeze live-resolution semantics

For each outcome of a NEW LIVE SteamDT attempt, Phase 14B / 14C must behave as follows.

| Outcome | Memo entry | Counter updates | Recipe consequence |
|---|---|---|---|
| `PriceLookupResult.quotes[name]` present (strict BUFF quote via live provider) | memo SUCCESS | `live_attempted += 1`, `live_succeeded += 1` | valuation may complete for that name |
| `PriceLookupResult.missing[name]` present (with corresponding `errors` entry) — i.e. live provider caught ordinary `SteamDTBuffPriceSelectionError` or other `Exception` and recorded the name as missing | memo TERMINAL FAILURE with reason | `live_attempted += 1`, `live_failed += 1` | run-reuse failure for the rest of the run; no second live attempt this run |
| `MemoryError` from `get_prices` (bare `raise` at `steamdt_buff_price_provider.py:52-53`) | propagation by identity | the session may not be able to increment counters because the live call raised before returning | recipe is dropped; never swallowed |
| Other `BaseException` subclass (`CancelledError`, `KeyboardInterrupt`, `SystemExit`, `GeneratorExit`) | propagation by identity | the session may not be able to increment counters | recipe is dropped; never swallowed |
| Cache backend / codec / adapter exception during `prepare` (Phase 14C) | propagates by identity from the cache-read seam | NOT counted as live attempt; NOT counted as live demand | recipe is dropped or run aborts (the orchestrator decides) |
| `STEAMDT_BUFF_PRICE_LOOKUP_FAILED` identity guard (live returned a quote with the wrong name) | memo TERMINAL FAILURE | `live_attempted += 1`, `live_failed += 1` | run-reuse failure |

Target invariant: **at most one SteamDT live attempt per exact name per run**. Phase 14A-R1 explicitly forbids adding persistent negative caching unless a future separately authorized Phase 14E does so. Phase 14A-R1 also explicitly forbids "best-effort" cache write backends or "best-effort" codec error swallowing.

### 7. Freeze the budget algorithm (Phase 14B/C atomic preflight) and counter contract (Option A finalized)

`max_valuation_requests_per_run` is redefined as the count of NEW LIVE SteamDT provider demand / attempts within the run, exclusive of run-reuse hits and `FRESH + SELECTED` cache hits. The atomic preflight algorithm is exactly:

1. Derive current recipe unique output names in first-seen order.
2. **Stage A: `prepare_output_prices(names)`** runs without any live SteamDT calls.
   - For 14B: consult the run memo; classify `memo_successes`, `memo_terminal_failures`, `live_demand_names`.
   - For 14C: consult the run memo first; for still-unresolved names, perform `FRESH_ONLY` cache reads via `SteamDTCachedPriceResolver.resolve(name, read_policy=PriceCacheReadPolicy.FRESH_ONLY, selection_config=strict_buff_adapter_config)` in first-seen order. Classify `cache_hits_fresh_selected`, `cache_terminal_selection_failures`, `cache_misses_or_refresh_candidates` (live-refresh candidates). Backend / codec / adapter exceptions propagate by identity.
3. Compute `live_demand = len(live_demand_names)` (14B) or `len(cache_misses_or_refresh_candidates)` (14C).
4. **Before any live call**, atomically compare in the orchestrator:
   - If `valuation_live_used + live_demand > max_valuation_requests_per_run`: build a blocked evaluation; set `valuation_requests_blocked += requested_count`, `live_atomically_blocked += live_demand`, `live_demand += live_demand`; issue **ZERO** live SteamDT calls for that recipe (Stage B is NEVER called).
5. Else: `valuation_live_used += live_demand`; `valuation_requests_attempted += requested_count`; call `resolve_prepared(plan)`. Each `live provider call` (for 14B, the per-name `SteamDTBuffPriceProvider.get_price(name)` calls; for 14C, the per-name `SteamDTPriceRefreshService.refresh_one(name)` calls inside the existing refresh path) charges `live_attempted += 1` the moment the call is actually attempted, even if it later fails. `live_demand += live_demand` regardless of whether Stage B actually executes.
6. **Counter invariants for COMPLETED runs** (where `ScannerRunResult` is materialized):

```text
run_reuse_hits
= run_reuse_successes + run_reuse_failures

live_demand
= live_attempted + live_atomically_blocked

live_attempted
= live_succeeded + live_failed
```

   No arithmetic equality is defined between the legacy `valuation_requests_attempted` counter and the new Phase 14 counters. They model different things (legacy = ADMITTED recipe structural demand; Phase 14 = NEW LIVE SteamDT demand).

7. Legacy semantics preserved exactly:
   - `valuation_requests_attempted` is incremented by `requested_count` only for an ADMITTED recipe (atomic preflight passed). A blocked recipe does NOT increment `attempted`.
   - `valuation_requests_succeeded` is incremented by `resolved_count` (`len(PriceLookupResult.quotes)`) for an admitted recipe.
   - `valuation_requests_failed` is incremented by `failed_count` (`max(0, requested_count - resolved_count)`) for an admitted recipe.
   - `valuation_requests_blocked` is incremented by `requested_count` for a blocked recipe.
8. If the run aborts with `MemoryError` / uncatchable `BaseException` / cache-fatal error, no `ScannerRunResult` exists, so the completed-run invariants need not describe partial execution.
9. The preflight MUST remain single-threaded inside one `run_once()` call. No concurrent recipes, no background tasks.

Deliverable: the algorithm above.

### 8. Freeze counter names and meanings

| Counter | Type | Meaning |
|---|---|---|
| `valuation_requests_attempted` | `int` (legacy preserved) | Sum of `requested_count` for ADMITTED recipes only. |
| `valuation_requests_succeeded` | `int` (legacy preserved) | Sum of `len(PriceLookupResult.quotes)` for ADMITTED recipes. |
| `valuation_requests_failed` | `int` (legacy preserved) | Sum of `max(0, requested_count - resolved_count)` for ADMITTED recipes. |
| `valuation_requests_blocked` | `int` (legacy preserved) | Sum of `requested_count` for BLOCKED recipes. |
| `run_reuse_hits` | `int` (new) | Names resolved by the run memo within the run. |
| `run_reuse_successes` | `int` (new) | Subset of `run_reuse_hits` that are memo SUCCESSES. |
| `run_reuse_failures` | `int` (new) | Subset of `run_reuse_hits` that are memo TERMINAL FAILURES. |
| `cache_hits_fresh_selected` | `int` (new, Phase 14C) | Names resolved via `FRESH + SELECTED` (strict BUFF) cache hit. |
| `cache_misses` | `int` (new, Phase 14C) | Names returning `MISS` (`state=None, hit=False`) from the cache. |
| `cache_policy_blocked` | `int` (new, Phase 14C) | Names returning `STALE / STALE_GRACE / POLICY_BLOCKED` under FRESH_ONLY. |
| `cache_expired` | `int` (new, Phase 14C) | Names returning EXPIRED. |
| `cache_selection_failures` | `int` (new, Phase 14C) | Names returning `FRESH + SELECTION_FAILURE` (terminal). |
| `live_demand` | `int` (new) | Total NEW LIVE names classified by `prepare`, INCLUDING later-blocked demand. |
| `live_attempted` | `int` (new) | Live SteamDT calls actually issued. |
| `live_succeeded` | `int` (new) | Live SteamDT calls whose `PriceLookupResult.quotes` includes the requested name. |
| `live_failed` | `int` (new) | Live SteamDT calls whose `PriceLookupResult.missing` includes the requested name. |
| `live_atomically_blocked` | `int` (new) | Live demand that the atomic preflight refused (subset of `live_demand`). |

No arithmetic equality between legacy and Phase 14 counters is defined or implied.

Deliverable: the counter table above.

### 9. Freeze TTL / config ownership

1. NO scanner fresh_ttl numeric default is frozen in Phase 14A-R1.
2. The 5-minute value in `scripts/steamdt_refresh_integration.py:59` (`INTEGRATION_POLICY = PriceCachePolicy(fresh_ttl=timedelta(minutes=5))`) is **historical manual-script precedent only**, not a scanner default.
3. `PriceCachePolicy` shape: `fresh_ttl` required (`> timedelta(0)`); `stale_ttl` and `stale_grace_ttl` default to `timedelta(0)`. The existing integration policy is effectively 5-minute fresh, zero stale, zero grace — entries jump from FRESH to EXPIRED at the 5-minute mark; `ALLOW_STALE` and `ALLOW_STALE_GRACE` are unreachable under it.
4. The existing `STEAMDT_PRICE_CACHE_BACKEND` (`app/config.py:77`, default `"inmemory"`) and `STEAMDT_PRICE_CACHE_REDIS_NAMESPACE` (`app/config.py:78`, default `"steamdt-price-cache-v1"`) remain the env-driven knobs.
5. Future scanner-side `PriceCachePolicy` config will live in a new `PriceCachePolicyConfig` Pydantic DTO colocated with `LiveScanSettings` in `scripts/run_live_scan_once.py`, exposed in `.env.example` as a single derived knob (e.g. `STEAMDT_PRICE_CACHE_FRESH_TTL_SECONDS`), with identical semantics for `InMemoryPriceCache` and `RedisPriceCache`. **The numeric default is chosen and documented at Phase 14C implementation time, NOT frozen in 14A-R1.**
6. Cache keys / values / TTL must be identical in semantic behavior between the InMemory and Redis backends. Redis is optional; the default one-shot CLI continues to work without Redis.

Deliverable: the TTL ownership rules above.

### 10. Freeze backend composition

1. The future scanner-owned session MUST work with `InMemoryPriceCache` without Redis.
2. The future scanner-owned session MUST preserve existing Redis compatibility via the existing `create_steamdt_price_cache_runtime` factory.
3. The future scanner-owned session MUST NOT add background refresh workers, scheduler behavior, periodic tasks, or daemon threads.
4. The future scanner-owned session MUST NOT require Redis for the default one-shot CLI.
5. The future scanner-owned session MUST compose the cache via `create_steamdt_price_cache_runtime` (`app/services/price_cache_factory.py:159`) so that `STEAMDT_PRICE_CACHE_BACKEND` semantics remain centralized.
6. Invalid cache configuration MUST fail before any live SteamDT work. The factory's existing composition-error types (`SteamDTPriceCacheCompositionError`, `SteamDTPriceCacheConstructionCleanupError`, `SteamDTPriceCacheRuntimeCloseError`, `SteamDTPriceCacheContextExitError`) are the canonical failure surface.

### 11. Freeze the implementation sequence (14B / 14C / 14D)

**14B — Run-scoped exact-name reuse (no persistent cache yet)**

1. Introduce the scanner-owned `RunScopedValuationSession` boundary outside `valuation_service.py` and `live_recipe_valuation.py`. The session holds the run memo only.
2. Implement the two-stage contract: `prepare_output_prices(names)` (memo-only, zero live calls) and `resolve_prepared(plan)` (calls existing strict live provider).
3. The session calls the existing strict live provider path (`SteamDTBuffPriceProvider.get_prices`) with no cache lookup and no cache write.
4. Run-reuse hits (success and terminal failure) reduce live demand.
5. The legacy `valuation_requests_attempted / succeeded / failed / blocked` semantics are preserved. The new discriminators (`run_reuse_hits`, `run_reuse_successes`, `run_reuse_failures`, `live_demand`, `live_attempted`, `live_succeeded`, `live_failed`, `live_atomically_blocked`) are added additively.
6. **Validation — cross-recipe reuse (no persistent cache):**
   - Recipe1 demands `A, B, C, D, E, F, G, H, I, J`. Recipe2 demands `A, B, C, D, E, F, G, H, I, K`.
   - Distinct names across both recipes = 11.
   - `live_demand == 11`, `live_attempted == 11`, `recipes_fully_valued` depends on quote availability but `live_attempted` does not.
   - Recipe2 memo hits = 9 (`A..I`), so `run_reuse_hits == 9`, `run_reuse_successes == 9` if `A..I` all succeeded live for Recipe1, `run_reuse_failures == 0`.
   - `run_reuse_hits != 0` (this corrects the R1 audit's earlier wording that implied zero hits in 14B).
7. **Validation — failure reuse:**
   - Recipe1 demands `X, Y`. Recipe2 demands `X, Y, Z`.
   - `X` succeeds live for Recipe1 → memo SUCCESS.
   - `Y` is recorded in `PriceLookupResult.missing` for Recipe1 (live provider caught ordinary `Exception`/`SteamDTBuffPriceSelectionError`) → memo TERMINAL FAILURE.
   - `Z` is a new live demand.
   - Recipe2: `X` is memo SUCCESS (no live call); `Y` is memo TERMINAL FAILURE (no live retry); `Z` triggers one new live attempt.
   - Recipe2 is incomplete because `Y` failed; no metrics, no risk, no opportunity.
   - Counter invariants:
     - `live_demand == 2` (one for `Y` in Recipe1; one for `Z` in Recipe2 — `X` is memo SUCCESS, never enters `live_demand`);
     - `live_attempted == 2` (both entered Stage B);
     - `live_succeeded == 1` (`X`), `live_failed == 1` (`Y`);
     - `run_reuse_hits == 2` (`X` SUCCESS, `Y` TERMINAL FAILURE for Recipe2);
     - `run_reuse_successes == 1`, `run_reuse_failures == 1`.

**14C — Phase 12D cache integration (READ only)**

1. Add `SteamDTCachedPriceResolver` lookup (Phase 12D3B) ahead of the live provider path with `PriceCacheReadPolicy.FRESH_ONLY`. Inject the strict BUFF adapter at the session level (do NOT modify `SteamDTCachedPriceResolver`).
2. Add `SteamDTPriceRefreshService.refresh_one` for live-refresh candidates (Phase 12D4A).
3. Selector rerun on cache hits uses the strict BUFF adapter (not the resolver's default cross-platform selector).
4. Existing refresh / read semantics preserved.
5. InMemory works without Redis; Redis optional explicit backend.
6. No stale valuation (FRESH_ONLY).
7. No scheduler.
8. Cache backend / codec / adapter exceptions propagate by identity from the cache-read seam; no silent reinterpretation.
9. **No scanner writeback occurs in initial 14C**. The existing manual refresh stack remains the writer. No write-failure runtime test is required for initial 14C.

**14D — CLI + scale / live validation**

1. Wire runtime to `scripts/run_live_scan_once.py`. Necessary config only; one-shot behavior preserved.
2. Overlap-heavy scale test proves fewer provider calls (recipe1 A..J, recipe2 shares A..I + K → 11 distinct names → with all-fresh cache → 0 live calls; with 9 fresh + 1 miss → 1 live call; with 1 live failure cached as terminal → 0 live retry same run).
3. Bounded live validation under explicit authorization; no risk threshold changes; no cap inflation merely to make live validation pass.
4. CLI defaults remain offline-safe; live and integration paths remain opt-in.

### 12. Documentation checkpoints (this PR)

1. `specs/2026-08-29-scanner-valuation-integration-design-freeze/{requirements,plan,validation}.md` (this PR, revised by R1).
2. Append new decision IDs to `docs/ai-context/DECISION_LOG.md`: the six D- IDs from 14A (`D-CACHE-002..004`, `D-BUDGET-001`, `D-ACCOUNTING-001`, `D-PHASE14A-COMPLETE`) and the new `D-PHASE14A-R1-COHERENCE` decision.
3. Pointer surfaces (`CLAUDE.md`, `PROJECT_CONTEXT.md`, `DEVELOPMENT_HANDOFF.md`, `ARCHITECTURE_STATE.md`, `specs/roadmap.md`) — updated only where the pointer semantics have changed; Phase 14A-R1 is a design coherence correction, not a status advance.

### 13. Validation (this PR)

Run before commit:

```text
git diff --check
git diff --name-only
git diff --name-only e98cd97b78476864e35c93f364309a443759cde6 -- app tests scripts .github pyproject.toml
   (must be empty — no production code or test or script or config change)
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 -m pytest
```

Acceptance gates are detailed in `validation.md`.
