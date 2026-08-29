# Phase 14A — Scanner Valuation Integration Design Freeze — Plan

## Status

- **Design freeze only.** No application code, test code, Protected Core edit, live request, scheduler, market execution, login, Cookie, browser automation, risk-control bypass, mass scraping, or invented BUFF / SteamDT endpoint.
- **Date:** 2026-08-29.
- **Branch:** `feature/scanner-valuation-integration`.
- **Baseline:** `24c95c029f583d5cc0b0a67986e48c06d0ef7957` (post-R0-D canonical main after PR #3 merge). Upstream and local synchronized at `0 0`.
- **Recommended architecture:** Option C — scanner-owned run-scoped valuation session boundary, narrow additive seam, no global cache manager. The future class / API name is not frozen; choose the narrowest compatible interface after the 14B implementation begins.
- **Recommended implementation sequence:** 14B (run-scoped exact-name reuse, current strict live provider path only, no persistent cache yet) → 14C (Phase 12D cache integration, `FRESH_ONLY`, selector rerun, no scheduler) → 14D (CLI + scale/live validation).

## Numbered task groups

### 1. Confirm current scanner valuation path and audit boundary

1. Lock the current scanner valuation chain as recorded in `requirements.md` — `LiveScannerOrchestrator.run_once` → per-recipe `_unique_output_names` → atomic preflight → `_evaluate_selection` → `ValuationService.value_tradeup_results` → `self.price_provider.get_prices` → `SteamDTBuffPriceProvider.get_prices`.
2. Lock the atomic preflight as the ONLY mutator of `valuation_requests_used` (`app/services/scanner_orchestrator.py:439`), and document the line that blocks an entire recipe before any provider call (`app/services/scanner_orchestrator.py:417-428`).
3. Lock the absence of any Phase 12D cache import in the scanner-to-price chain (verified by grep).
4. Lock the absence of any run-scope memoization across recipe valuation calls (`SteamDTBuffPriceProvider.get_prices` only dedupes within ONE call).
5. Lock the existing `LiveRecipeEvaluation`, `ScannerRunStageCounters`, and `ScannerRunDiagnostics` shape as the surface that future counters must extend.
6. Treat the existing `live_recipe_valuation.py` and `valuation_service.py` as Protected Core. Any cross-recipe reuse requires explicit migration authorization under the existing Protected-Core rules.

Deliverable: the verified audit summary above (preserved in `requirements.md`).

### 2. Freeze the seam: scanner-owned run-scoped valuation session

1. Introduce a scanner-owned `RunScopedValuationSession` boundary that lives **outside** `valuation_service.py` and `live_recipe_valuation.py`. The session owns:
   - the run-scoped exact-name memo (success / terminal failure);
   - the call into `SteamDTCachedPriceResolver` (Phase 14C onward);
   - the call into `SteamDTPriceRefreshService.refresh_one` for NEW LIVE demand (Phase 14C onward);
   - the accounting counter updates (additive migration; see task group 6).
2. The session exposes ONE method to the orchestrator: `resolve_output_prices(output_market_hash_names) -> SessionResolutionResult` returning per-name statuses, a typed `live_demand_increment`, and a typed `live_outcome_increment`. The orchestrator continues to do the atomic preflight using the `live_demand_increment` BEFORE issuing the session call.
3. The session does NOT resolve BUFF listing identity. It does NOT alter recipe enumeration. It does NOT cache-cross-reference with `BuffCommunityIdentityResolver` or any other identity resolver.
4. The session never observes raw provider fields; it only observes the existing strict `SteamDTBuffOutputPrice` shape returned by `SteamDTBuffPriceProvider`.
5. The session never weakens the strict BUFF selector; the existing `SteamDTBuffPriceSelection` is the only allowed selection path. Cached and live paths both go through it.

Deliverable: a frozen seam contract. Class / function names are not frozen; this task group freezes the contract only.

### 3. Freeze exact-name reuse semantics

1. **Run-level reuse key** is the canonical `output_market_hash_name` string itself — byte-exact, no fuzzy matching, no case folding, no aliases, no `goods_id` substitution, no `platformItemId` substitution.
2. Current canonicalization is the Steam community market canonical name (e.g. `M4A1-S | Knight (Factory New)`) used by `TradeupResult` / `OutputCandidate.market_hash_name` throughout the engine path. Phase 14A does not introduce a hidden normalization layer; it reuses the existing canonical form.
3. The canonical form is the value the orchestrator already passes into `ValuationService.value_tradeup_results` via `recipe.tradeup_results`. Phase 14 implementation must consume the same canonical form.
4. Cache key (`PriceCacheKey.market_hash_name`) is the same canonical form. The deterministic sha256 digest in `PriceCacheKey` already normalizes `currency` to uppercase and rejects non-`CNY` currencies.
5. **Run-scoped memo** behavior within one `run_once()`:
   - Successful exact-name resolution is reused (no second cache lookup, no second provider call).
   - Terminal exact-name failure (live lookup/selection failure, fresh-cache selection failure) is reused as failure; no automatic same-name retry.
   - Missing / stale / stale-grace / expired / policy-blocked exact names are NOT terminal if live refresh is allowed and the live budget has room; they are candidates for live refresh.
6. The memo dies at end of `run_once()`. It is NOT persisted. It is NOT shared across `run_once()` calls. It is NOT a second persistent cache.
7. No persistent negative caching in Phase 14B or 14C. A negative outcome in the run memo is reused only within that run.

Deliverable: the exact-name reuse contract above.

### 4. Freeze FRESH_ONLY persistent-cache policy (Phase 14C onward)

1. Initial scanner integration uses **`PriceCacheReadPolicy.FRESH_ONLY`**.
2. **FRESH + SELECTED**: usable cache hit. Zero live-provider budget. Valuation completes for that name subject to selection strictness.
3. **FRESH + SELECTION_FAILURE**: terminal same-run failure. Reused within the run. No immediate live retry. No second-platform fallback. No bid substitution. No metadata-zero reuse. Phase 14A explicitly forbids adding a "live fallback on FRESH + SELECTION_FAILURE" path because the selector is the strict BUFF selector and the cached candidates are already the full provider response; re-running the live path on the same name would either re-discover the same failure or silently swallow it.
4. **MISS / EXPIRED / STALE / STALE_GRACE / POLICY_BLOCKED under FRESH_ONLY**: live refresh candidate if budget allows. Not usable as a quote without a successful live attempt.
5. **Cache backend / codec exception** (`PriceCacheBackendError`, `PriceCacheCodecError`, `SteamDTPriceCacheAdapterError`, `SteamDTCachedPriceResolutionStatus.BACKEND_ERROR`, `SteamDTCachedPriceResolutionStatus.CODEC_ERROR`): explicit fail-closed. The session propagates the typed error by identity. Phase 14A explicitly forbids silently reinterpreting a backend / codec error as a normal `MISS` because doing so would erase the operational signal a Redis failure or a codec corruption is sending.
6. **Cache write after live success**: Phase 14C keeps cache writes OFF by default (consistent with the existing manual-only refresh path). Future implementation may add an opt-in `STEAMDT_PRICE_CACHE_WRITE_AFTER_LIVE` setting; that decision is not made in Phase 14A.
7. **Cache selection rerun**: on every cache hit (including `FRESH + SELECTED`), the session MUST rerun the caller-supplied selector against the stored candidates. The selector's identity and `SteamDTPriceSelectionConfig` MUST come from the existing project configuration (no new selector is added).
8. **No platform filter at write time**: the cache stores the full ordered list of normalized SteamDT platform candidates per item, in provider response order. Selection between BUFF and any other platform happens at READ time via the existing strict selector.

Deliverable: the FRESH_ONLY policy table above.

### 5. Freeze live-resolution semantics

For each outcome of a NEW LIVE SteamDT attempt, Phase 14B / 14C must behave as follows.

| Outcome | Memo entry | Budget charge | Recipe consequence |
|---|---|---|---|
| Live success (strict BUFF sell price resolved) | success | `live_attempted += 1`, `live_succeeded += 1` | valuation may complete for that name |
| Transport / API failure (`PriceCacheBackendError`, `SteamDTClientError`, `SteamDTTransportError`, HTTP 4xx / 5xx, `errorCode=4005`, parser / Decimal failure) | terminal failure | `live_attempted += 1`, `live_failed += 1` | run-reuse failure; no second live attempt this run |
| Parsed response but BUFF selection failure (`buff_sell_price_non_positive` / no `BUFF` row / non-positive finite sell price) | terminal failure | `live_attempted += 1`, `live_failed += 1` | run-reuse failure; no second live attempt this run |
| Cache backend exception after live success | the live success stands; the cache write is skipped | `live_attempted += 1`, `live_succeeded += 1`; **no cache write** | valuation may complete for that name; no silent reinterpretation of failure |
| `MemoryError` | propagation by identity | `live_attempted += 1` if it occurs mid-call | recipe is dropped from the run; never swallowed |
| Cancellation / other `BaseException` | propagation by identity | `live_attempted += 1` if it occurs mid-call | recipe is dropped from the run; never swallowed |

Target invariant: **at most one SteamDT live attempt per exact name per run**. Phase 14A explicitly forbids adding persistent negative caching unless a future separately authorized Phase 14E does so. Phase 14A also explicitly forbids "best-effort" cache write backends or "best-effort" codec error swallowing.

### 6. Freeze the budget algorithm (Phase 14B/C atomic preflight)

`max_valuation_requests_per_run` is redefined as the count of NEW LIVE SteamDT provider demand / attempts within the run, exclusive of run-reuse hits and `FRESH + SELECTED` cache hits. The atomic preflight algorithm is exactly:

1. Derive current recipe unique output names in first-seen order.
2. Consult the run memo. Mark memoed-success / memoed-failure names as already resolved; they consume ZERO live-provider budget.
3. For the still-unresolved subset, perform `FRESH_ONLY` cache preflight via `SteamDTCachedPriceResolver.resolve(..., read_policy=PriceCacheReadPolicy.FRESH_ONLY, selection_config=...)`.
   - Names returning `FRESH + SELECTED` are now resolved and consume ZERO live-provider budget.
   - Names returning `FRESH + SELECTION_FAILURE` are now memoed as terminal failure and consume ZERO live-provider budget.
   - Names returning `MISS / EXPIRED / STALE / STALE_GRACE / POLICY_BLOCKED / BACKEND_ERROR / CODEC_ERROR` are live-refresh candidates below.
   - Backend / codec exceptions propagate by identity at this stage; they are NOT silently re-interpreted as `MISS`.
4. Compute `live_demand = count(live_refresh_candidate_names)`.
5. **Before any live call**, atomically compare:
   - If `valuation_live_used + live_demand > max_valuation_requests_per_run`: build a blocked evaluation; set `valuation_requests_blocked += requested_count`, `live_atomically_blocked += live_demand`; issue **ZERO** live SteamDT calls for that recipe.
6. Else: `valuation_live_used += live_demand`; perform live resolution over the live-refresh candidates in first-seen order; each `refresh_one` call charges the budget the moment the live call is actually attempted, even if the call later fails.
7. A live attempt that succeeds updates the run memo for that name. A live attempt that fails (transport / API / selection) updates the run memo for that name as a terminal failure.
8. Run-reuse hits and `FRESH + SELECTED` cache hits NEVER consume the live budget.
9. Any incomplete recipe yields `valuation_completed=False`, no metrics, no risk, no opportunity. Never drop outputs, never renormalize probabilities, never substitute a previous recipe's metrics, never zero-fill, never stale-fill.

The preflight MUST remain single-threaded inside one `run_once()` call. No concurrent recipes, no background tasks.

Deliverable: the algorithm above.

### 7. Freeze accounting / counter contract (Option A preferred)

Phase 14A prefers **Option A — additive counters** that preserve the legacy `valuation_requests_attempted / succeeded / failed / blocked` semantics. Option B (explicit semantics migration with all tests/docs migrated) is the fallback if Option A surfaces ambiguity during 14B implementation.

**Option A — additive counters**:

| Counter | Type | Meaning |
|---|---|---|
| `valuation_requests_attempted` | `int` (legacy) | Sum of unique output names charged against `valuation_requests_used` — preserved as the legacy Phase13T structural demand. |
| `valuation_requests_succeeded` | `int` (legacy) | Names resolved into a quote via any path (run-reuse hit / cache hit / live success). Preserved for backward compatibility. |
| `valuation_requests_failed` | `int` (legacy) | Names missing or errored. Preserved for backward compatibility. |
| `valuation_requests_blocked` | `int` (legacy) | Names that the atomic preflight refused. Preserved for backward compatibility. |
| `run_reuse_hits` | `int` (new) | Names resolved by the run memo within the run. |
| `cache_hits_fresh_selected` | `int` (new) | Names resolved via `FRESH + SELECTED` cache hit. |
| `cache_misses` | `int` (new) | Names returning `MISS` from the cache. |
| `cache_policy_blocked` | `int` (new) | Names returning `STALE / STALE_GRACE / POLICY_BLOCKED` under FRESH_ONLY. |
| `cache_expired` | `int` (new) | Names returning `EXPIRED`. |
| `cache_selection_failures` | `int` (new) | Names returning `FRESH + SELECTION_FAILURE` (terminal). |
| `live_demand` | `int` (new) | Names classified as live-refresh candidates by the atomic preflight. |
| `live_attempted` | `int` (new) | Live SteamDT refresh calls actually issued. |
| `live_succeeded` | `int` (new) | Live SteamDT refresh calls that produced a strict quote. |
| `live_failed` | `int` (new) | Live SteamDT refresh calls that failed (transport / API / selection). |
| `live_atomically_blocked` | `int` (new) | Live demand that the atomic preflight refused (subset of `valuation_requests_blocked`). |

Invariant:
- `valuation_requests_attempted == run_reuse_hits + cache_hits_fresh_selected + live_demand + live_atomically_blocked + cache_selection_failures` (within each recipe, after memo + cache preflight).
- `live_demand >= live_attempted` (only recipes that pass the atomic preflight actually issue live calls).
- `live_attempted == live_succeeded + live_failed`.
- `valuation_requests_blocked >= live_atomically_blocked` (a recipe can be blocked for other reasons, including missing inputs).

Display vs processing order: structural composition order determines valuation order and counter update order; final opportunity display ordering by `expected_profit_cny desc, roi desc` does not affect counter update order.

**Option B — explicit semantics migration** (fallback only): rename legacy counters to `structural_unique_output_demand`, `resolved_total`, `resolved_failed`, `blocked_total`; migrate every existing test in `tests/test_scanner_orchestrator.py`, `tests/test_multi_recipe_scanner_scale_validation.py`, `tests/test_run_live_scan_once.py` to the new names; do not silently overload ambiguous names.

Phase 14A does NOT pick between Option A and Option B at freeze time. The choice is made at the start of 14B based on the surface-area of test/doc migration observed during the implementation PR.

### 8. Freeze TTL / config ownership

1. No env-driven TTL is invented in Phase 14A.
2. The existing `STEAMDT_PRICE_CACHE_BACKEND` (`app/config.py:77`, default `"inmemory"`) and `STEAMDT_PRICE_CACHE_REDIS_NAMESPACE` (`app/config.py:78`, default `"steamdt-price-cache-v1"`) remain the env-driven knobs.
3. Future scanner-side `PriceCachePolicy` config will live in a new `PriceCachePolicyConfig` Pydantic DTO colocated with `LiveScanSettings` in `scripts/run_live_scan_once.py`, exposed in `.env.example` as a single derived knob (e.g. `STEAMDT_PRICE_CACHE_FRESH_TTL_SECONDS`), with identical semantics for `InMemoryPriceCache` and `RedisPriceCache`. The TTL default is `5 minutes` (matching the existing integration script convention); the choice is documented at implementation time, NOT frozen here.
4. Cache write after live success is OFF by default. An opt-in `STEAMDT_PRICE_CACHE_WRITE_AFTER_LIVE` setting may be added in a future separately authorized phase; not decided here.
5. Cache keys / values / TTL must be identical in semantic behavior between the InMemory and Redis backends. Redis is optional; the default one-shot CLI continues to work without Redis.

### 9. Freeze backend composition

1. The future scanner-owned session MUST work with `InMemoryPriceCache` without Redis.
2. The future scanner-owned session MUST preserve existing Redis compatibility via the existing `create_steamdt_price_cache_runtime` factory.
3. The future scanner-owned session MUST NOT add background refresh workers, scheduler behavior, periodic tasks, or daemon threads.
4. The future scanner-owned session MUST NOT require Redis for the default one-shot CLI.
5. The future scanner-owned session MUST compose the cache via `create_steamdt_price_cache_runtime` (`app/services/price_cache_factory.py:159`) so that `STEAMDT_PRICE_CACHE_BACKEND` semantics remain centralized.
6. Invalid cache configuration MUST fail before any live SteamDT work. The factory's existing composition-error types (`SteamDTPriceCacheCompositionError`, `SteamDTPriceCacheConstructionCleanupError`, `SteamDTPriceCacheRuntimeCloseError`, `SteamDTPriceCacheContextExitError`) are the canonical failure surface.

### 10. Freeze the implementation sequence (14B / 14C / 14D)

**14B — Run-scoped exact-name reuse (no persistent cache yet)**

1. Introduce the scanner-owned `RunScopedValuationSession` boundary outside `valuation_service.py` and `live_recipe_valuation.py`. The session holds the run memo only.
2. Wire the orchestrator's atomic preflight to charge `valuation_requests_used` against the new live-demand metric.
3. The session calls the existing strict live provider path (`SteamDTBuffPriceProvider.get_prices`) with no cache lookup and no cache write.
4. Run-reuse hits (success and terminal failure) reduce live demand.
5. The legacy `valuation_requests_attempted / succeeded / failed / blocked` semantics are preserved. The new discriminators (`run_reuse_hits`, `live_attempted`, `live_succeeded`, `live_failed`, `live_atomically_blocked`, `live_demand`) are added additively.
6. Validation: offline tests covering cross-recipe reuse (recipe1 A..J, recipe2 shares A..I + K → 11 distinct names → 11 live attempts without 14B's reuse layer; with 14B's reuse layer → still 11 because there is no persistent cache yet; the reduction comes from run-reuse of the in-run memo). Live call counter tests must show `live_attempted == 11` for 11 distinct output names across 2 recipes.

**14C — Phase 12D cache integration**

1. Add `SteamDTCachedPriceResolver` lookup (Phase 12D3B) ahead of the live provider path with `PriceCacheReadPolicy.FRESH_ONLY`.
2. Add `SteamDTPriceRefreshService.refresh_one` for live-refresh candidates (Phase 12D4A).
3. Selector rerun on cache hits (existing strict BUFF selector).
4. Existing refresh / write semantics preserved.
5. InMemory works without Redis; Redis optional explicit backend.
6. No stale valuation (FRESH_ONLY).
7. No scheduler.
8. Cache backend / codec exceptions propagate by identity; no silent reinterpretation.

**14D — CLI + scale / live validation**

1. Wire runtime to `scripts/run_live_scan_once.py`. Necessary config only; one-shot behavior preserved.
2. Overlap-heavy scale test proves fewer provider calls (recipe1 A..J, recipe2 shares A..I + K → 11 distinct names → with all-fresh cache → 0 live calls; with 9 fresh + 1 miss → 1 live call; with 1 live failure cached as terminal → 0 live retry same run).
3. Bounded live validation under explicit authorization; no risk threshold changes; no cap inflation merely to make live validation pass.
4. CLI defaults remain offline-safe; live and integration paths remain opt-in.

### 11. Documentation checkpoints (this PR)

1. `specs/2026-08-29-scanner-valuation-integration-design-freeze/{requirements,plan,validation}.md` (this PR).
2. Append new decision IDs to `docs/ai-context/DECISION_LOG.md` covering run reuse, FRESH_ONLY, live-budget atomic preflight, failure reuse, accounting, and 14A completion (preserving `D-CACHE-001` as historical Phase13T rule).
3. Update `docs/ai-context/PROJECT_CONTEXT.md` pointers and add the Phase 14A milestone bullet.
4. Update `docs/ai-context/DEVELOPMENT_HANDOFF.md` to record Phase 14A as the latest completed design-freeze phase and reorder Next Action.
5. Update `docs/ai-context/ARCHITECTURE_STATE.md` minimal note that any future Phase 14 implementation must touch `valuation_service.py` / `live_recipe_valuation.py` / `scanner_orchestrator.py` / `scanner_recipe_composition.py` under explicit migration authorization, and that the `RunScopedValuationSession` design is the only sanctioned seam.
6. Update `specs/roadmap.md`: Phase 14A = IN PROGRESS — DESIGN FREEZE (no code); six "not implemented" capability lines stay as they are; R0-D status correction to COMPLETE (post PR #3 merge).
7. Update `CLAUDE.md` minimal pointer correction: R0-D = COMPLETE; Phase 14A = IN PROGRESS — DESIGN FREEZE.

### 12. Validation (this PR)

Run before commit, with the default Windows-local equivalent of:

```text
git diff --check
python -m ruff check .
python -m mypy app
python -m pytest
git diff --name-only
```

Acceptance gates are detailed in `validation.md`.
