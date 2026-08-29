# Phase 14A — Scanner Valuation Integration Design Freeze — Validation

## Validation strategy

Phase 14A (revised under Phase 14A-R1 design coherence correction) is a **design freeze**. Validation here means: confirm the design is consistent with the actual code, the audit summary in `requirements.md` is correct, the frozen contracts in `plan.md` are coherent and complete, the existing pre-Phase-14 test matrix is preserved unchanged, and the proposed future test matrix is sufficient for the 14B / 14C / 14D phases that will follow.

Phase 14A-R1 does NOT:

- run the application;
- make any network request;
- modify production code;
- weaken, skip, or mark-xfail any pre-existing test;
- run any opt-in live / integration path;
- claim Phase 14B / 14C / 14D are implemented;
- modify `SteamDTCachedPriceResolver`, `SteamDTBuffPriceProvider`, `ValuationService`, `LiveScannerOrchestrator`, or any Phase 12D cache module.

## Gate 1 — Repository baseline

Run and require:

```text
git branch --show-current
git rev-parse HEAD
git rev-parse origin/feature/scanner-valuation-integration
git rev-list --left-right --count HEAD...origin/feature/scanner-valuation-integration
git rev-parse origin/main
git worktree list
git status --short
git tag --list v1-dry-run-baseline
```

Expected baseline at Phase 14A-R1 entry:

```text
local branch:                    feature/scanner-valuation-integration
local HEAD:                      e98cd97b78476864e35c93f364309a443759cde6  (the R1-pre commit)
upstream:                        e98cd97b78476864e35c93f364309a443759cde6
ahead/behind:                    0 0
origin/main:                     24c95c029f583d5cc0b0a67986e48c06d0ef7957
worktrees:                       D:/CS at 24c95c0 (main) only
status --short:                  ?? research/identity_revalidation/data/modest_serhat.json
                                 ?? research/identity_revalidation/data/timofey_ivanenko.json
v1-dry-run-baseline:             32ab47c5b66a0f331457e69f1515e5e9bb2a37e1  (local-only; preserved)
```

If any of the above fails, stop with `PHASE14A_R1_LOCAL_STATE_BLOCKED`.

## Gate 2 — Spec-trilogy integrity

The directory must contain exactly three files:

```text
specs/2026-08-29-scanner-valuation-integration-design-freeze/requirements.md
specs/2026-08-29-scanner-valuation-integration-design-freeze/plan.md
specs/2026-08-29-scanner-valuation-integration-design-freeze/validation.md
```

All three files must agree on:

- date `2026-08-29` (initial design freeze; revised under R1);
- branch `feature/scanner-valuation-integration`;
- baseline `24c95c029f583d5cc0b0a67986e48c06d0ef7957`;
- design-freeze-only status (no application code, no Protected Core edit, no live request, no scheduler, no commits to `main`);
- preservation of `D-CACHE-001` as `Active` (cache still not implemented at runtime);
- preservation of every frozen contract `D-ENUM-001..004`, `D-CACHE-001..004`, `D-BUDGET-001`, `D-ACCOUNTING-001`, `D-SCANNER-001`, `D-VALIDATION-001`, `D-MEMORY-001`, `D-ADAPTER-003`, `D-ADAPTER-004`;
- no invented BUFF / SteamDT / Redis / Discord / cache endpoint, signature, parameter, or field mapping;
- no fallback valuation, no bid substitution, no metadata-zero reuse, no probability renormalization, no risk-threshold weakening;
- no renaming, retagging, force-updating, or pushing of `v1-dry-run-baseline`;
- the two protected research JSONs remain untouched and un-staged.

`git diff --check` must report no whitespace or conflict markers.

## Gate 3 — Production code byte-identity (extended for R1)

`git diff --name-only e98cd97b78476864e35c93f364309a443759cde6 -- app tests scripts .github pyproject.toml` MUST report no files.

This blocks production code changes more aggressively than R0/R1's normal Gate 3 because R1 is purely a docs/spec/decision-log correction. Any non-empty output here = `PHASE14A_R1_CODE_SCOPE_FAILED`.

Specifically, the following files MUST be byte-identical to `e98cd97…`:

- `app/services/valuation_service.py`
- `app/services/live_recipe_valuation.py`
- `app/services/steamdt_buff_price_provider.py`
- `app/services/steamdt_buff_price_policy.py`
- `app/services/steamdt_market_data.py`
- `app/clients/steamdt_client.py`
- `app/services/scanner_orchestrator.py`
- `app/services/scanner_recipe_composition.py`
- `app/services/recipe_solver.py`
- `app/services/price_cache.py`
- `app/services/price_cache_codec.py`
- `app/services/redis_price_cache.py`
- `app/services/price_cache_factory.py`
- `app/services/steamdt_price_cache_adapter.py`
- **`app/services/steamdt_cached_price_resolver.py`** — explicitly NOT modified by R1 (R1 freezes the strict-BUFF adapter at the session level, not the resolver level)
- `app/services/steamdt_price_snapshot_source.py`
- `app/services/steamdt_price_refresh_service.py`
- `app/services/steamdt_refresh_planner.py`
- `app/services/steamdt_refresh_executor.py`
- **`app/clients/steamdt_price_selection.py`** — explicitly NOT modified by R1 (Phase 14A-R1 does not modify `select_steamdt_price_quote`; the strict-BUFF behavior is in `select_buff_output_price`)
- `scripts/run_live_scan_once.py`
- `scripts/steamdt_refresh_integration.py`
- all `tests/test_*.py`

## Gate 4 — Static checks

Run:

```text
git diff --check
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 -m pytest
```

Expected:

- `git diff --check`: clean (exit 0).
- `py -3.13 -m ruff check .`: passes (exit 0); no new warnings or errors.
- `py -3.13 -m mypy app`: passes (exit 0); no new warnings or errors.
- `py -3.13 -m pytest`: passes the **default suite**, which is offline-safe. The default suite must NOT be weakened. Expected existing baseline: `3336 passed, 23 skipped, 1 warning` unless independently explained.

Explicitly do NOT run:

- opt-in live BUFF tests (gated by env vars; default off);
- opt-in live SteamDT tests (gated by env vars; default off);
- real Redis integration tests (gated by `STEAMDT_RUN_REDIS_INTEGRATION_TESTS=true`; default off).

Any failure = `PHASE14A_R1_VALIDATION_FAILED`.

## Gate 5 — Pre-Phase-14 test matrix preservation

The following pre-existing test files must NOT be modified, skipped, xfailed, marked `@pytest.mark.skip`, or have any assertion removed / weakened:

- `tests/test_synthetic_scanner_scale_validation.py`
- `tests/test_multi_recipe_scanner_scale_validation.py`

Their pass / fail outcome against `e98cd97…` MUST match exactly before and after the Phase 14A-R1 commit. They are the canonical regression gates for any future scanner-side change. Phase 14A-R1 explicitly forbids weakening them to make the design-coherence PR pass.

## Gate 6 — Counter / accounting migration contract (for 14B)

The 14B implementation PR must demonstrate that the additive counters preserve the legacy semantics for every pre-existing test that touches `ScannerRunStageCounters`. The following pre-Phase-14 tests are the contract surface:

- `tests/test_scanner_orchestrator.py::test_scanner_orchestrator_bounded_multi_recipe` (and any sibling tests that assert on `valuation_requests_attempted / succeeded / failed / blocked`).
- `tests/test_multi_recipe_scanner_scale_validation.py::test_exact_cap_full_valuation` and `::test_one_below_cap_atomic_block` and `::test_two_bucket_aggregate_allocation` and `::test_legacy_compat_1_1_equivalence`.
- `tests/test_synthetic_scanner_scale_validation.py` (any test that asserts on the legacy counters).

After 14B lands, those tests must pass unchanged, except possibly for additive assertions on the new discriminators. The completed-run invariants are:

```text
run_reuse_hits  ==  run_reuse_successes + run_reuse_failures
live_demand     ==  live_attempted + live_atomically_blocked
live_attempted  ==  live_succeeded + live_failed
```

No arithmetic equality between legacy `valuation_requests_attempted` and any Phase 14 counter is defined or implied. Phase 14A-R1 explicitly forbids silently reinterpreting legacy counter semantics.

## Gate 7 — Design coherence

The design must be coherent against the existing audit facts. The validation check is:

1. The `RunScopedValuationSession` boundary does NOT depend on `BuffCommunityIdentityResolver` or any other identity resolver. It receives canonical `output_market_hash_name` strings.
2. The session exposes a two-stage contract: `prepare_output_prices(names)` issues ZERO live SteamDT calls; `resolve_prepared(plan)` may issue live calls only after orchestrator admission. The session is single-threaded inside one `run_once()`.
3. The atomic preflight algorithm holds `live_demand` from the prepared plan. If `valuation_live_used + live_demand > max_valuation_requests_per_run`, the entire recipe is blocked and `resolve_prepared` is NEVER called.
4. `FRESH_ONLY` is the only initial policy. `ALLOW_STALE`, `ALLOW_STALE_GRACE`, and any future policy that consumes stale data are NOT enabled in 14B or 14C.
5. The strict-BUFF cache-selection adapter behaviorally equivalent to `select_buff_output_price` is composed at the session level. The adapter:
   - exact `BUFF` platform, exactly one BUFF record, positive finite sell price;
   - never bid, never another platform, never `fallback_to_lowest_positive`;
   - propagates `SteamDTBuffPriceSelectionError` as terminal cache-selection failure.
   `SteamDTCachedPriceResolver` and `select_steamdt_price_quote` are NOT modified; the strict BUFF behavior lives in the session-level adapter.
6. The cache backend / codec / adapter exception contract is explicit fail-closed. The design does NOT silently reinterpret `PriceCacheBackendError`, `PriceCacheCodecError`, or `SteamDTPriceCacheAdapterError` as `MISS`. None of these are live candidates; none consume live budget; none are memo entries.
7. `MemoryError` propagates by identity. The design does NOT add any `try/except MemoryError` block in the new session. Other uncatchable `BaseException` subclasses (`CancelledError`, `KeyboardInterrupt`, `SystemExit`, `GeneratorExit`) also propagate by identity.
8. The live provider returns `PriceLookupResult` with `quotes`, `missing`, `errors`. Names in `quotes` are memo SUCCESSES. Names in `missing` (with corresponding `errors` entries) are memo TERMINAL FAILURES. Identity-mismatch quotes (`quote.market_hash_name != market_hash_name`) are recorded as `missing`.
9. The "at most one SteamDT live attempt per exact name per run" invariant holds under every defined outcome in `plan.md` task group 6.
10. No partial valuation. Any missing / failed / blocked / invalid exact-name resolution yields `valuation_completed=False`, no metrics, no risk, no opportunity. The design does NOT drop outputs, renormalize probabilities, zero-fill, stale-fill, or substitute another platform.
11. Bounded multi-recipe ordering is preserved. `LiveScannerOrchestrator.run_once` continues to iterate `composition.selections` in structural order; counter updates and cache lookups happen inside the per-recipe `_evaluate_selection` boundary.
12. The legacy `live_recipe_valuation.py` and `valuation_service.py` APIs are NOT modified by Phase 14A-R1. Any future 14B / 14C / 14D modification to them is explicit and reviewed.
13. No scanner fresh_ttl numeric default is frozen in Phase 14A-R1. The 5-minute value in `scripts/steamdt_refresh_integration.py:59` is historical manual-script precedent only; the Phase 14C scanner TTL is chosen and documented at implementation authorization.
14. Initial Phase 14C is scanner cache READ integration only. Automatic scanner write-after-live is OUT OF SCOPE; the existing manual refresh stack remains the writer; no write-failure runtime test is required.
15. `D-CACHE-001` remains `Active` after R1. Phase 14B (run-scope reuse) and Phase 14C (Phase 12D scanner cache integration) are the phases that, when they land and are verified, reclassify `D-CACHE-001` from `Active` to `Implemented`.
16. The 14B / 14C / 14D sequence in `plan.md` task group 11 is internally consistent. 14B is the smallest safe step (run memo + additive counters; no persistent cache). 14C layers Phase 12D cache with strict-BUFF selection. 14D wires CLI + scale/live validation.

Any coherence failure = `PHASE14A_R1_DESIGN_UNRESOLVED`.

## Gate 8 — Documentation pointer consistency

The pointer surfaces must remain mutually consistent. After the Phase 14A-R1 commit:

- `CLAUDE.md` "当前阶段指针" block: R0-A / R0-B / R0-C / R0-C docs checkpoint / R0-D = COMPLETE; Phase 14A = COMPLETE (design freeze; revised by R1); canonical `main` = `24c95c0…`; Phase 14A-R1 coherence correction recorded.
- `docs/ai-context/PROJECT_CONTEXT.md` "Git / Phase Baselines" + "Latest completed phases": pointers remain at `PHASE_14A_COMPLETE` for the design-freeze sub-phase; R0-D = COMPLETE; `D-PHASE14A-R1-COHERENCE` referenced.
- `docs/ai-context/DEVELOPMENT_HANDOFF.md` "Current Git State" + "Completed Milestones" + "Next Action": Phase 14A-R1 = latest design-coherence correction sub-phase; 14B = PROPOSED / NOT AUTHORIZED UNTIL R1 REVIEW.
- `docs/ai-context/ARCHITECTURE_STATE.md`: minimal note that any future Phase 14 implementation must touch Protected Core under explicit authorization; `RunScopedValuationSession` design is the only sanctioned seam; `SteamDTCachedPriceResolver` is NOT modified in R1; strict-BUFF behavior is composed at the session level via an adapter.
- `docs/ai-context/DECISION_LOG.md`: append `D-PHASE14A-R1-COHERENCE` (design coherence correction; nine recorded sub-corrections; `D-CACHE-001` remains `Active`; 14B / 14C reclassify only when verified).
- `specs/roadmap.md`: Phase 14A = IN PROGRESS — DESIGN FREEZE; six "not implemented" capability lines (live scanner cache integration; run-level cross-recipe exact-price reuse) still say "NOT IMPLEMENTED".
- All six public surfaces that say "run-level cross-recipe exact-price reuse = NOT IMPLEMENTED" still say so (README.md, docs/SPEC.md, docs/ARCHITECTURE.md, PROJECT_CONTEXT.md, DEVELOPMENT_HANDOFF.md, DECISION_LOG.md).

Any surface that says "implemented" for Phase 14B / 14C / 14D is a `PHASE14A_R1_AUDIT_CONTRACT_CONFLICT`.

## Future test matrix (must be written in Phase 14B / 14C / 14D, NOT in 14A-R1)

The 14A-R1 design freeze does not write any of these tests. They are listed here as the canonical contract that 14B / 14C / 14D must satisfy.

### A. Cross-recipe reuse (14B)

Recipe1 demands `A, B, C, D, E, F, G, H, I, J`. Recipe2 shares `A, B, C, D, E, F, G, H, I` plus a new name `K`. No persistent cache. Expected:

- `distinct names across both recipes = 11` (the set `{A..K}`, not 20).
- `live_demand == 11` (sum of `requested_count` for admitted recipes; here both admitted under sufficient cap).
- `live_attempted == 11` (each distinct name issued exactly one live SteamDT call across both recipes).
- For Recipe2: memo hits = 9 (`A..I` from Recipe1's live success); `run_reuse_hits == 9`, `run_reuse_successes == 9` (assuming `A..I` all succeeded), `run_reuse_failures == 0`.
- Counter invariants:
  - `run_reuse_hits == run_reuse_successes + run_reuse_failures` → `9 == 9 + 0` ✓.
  - `live_demand == live_attempted + live_atomically_blocked` → `11 == 11 + 0` ✓.
  - `live_attempted == live_succeeded + live_failed` (depends on whether all `A..K` resolved; counter invariants hold even if some failed).
- Recipe2's `K` triggers exactly one new live attempt; no second live attempt for `A..I`.

### B. Failure reuse (14B)

Recipe1 demands `X, Y`. Recipe2 demands `X, Y, Z`. Expected:

- `X` succeeds live for Recipe1 → memo SUCCESS.
- `Y` is recorded in `PriceLookupResult.missing` for Recipe1 (live provider caught ordinary `Exception`/`SteamDTBuffPriceSelectionError`) → memo TERMINAL FAILURE.
- `Z` is a new live demand.
- Recipe2: `X` is memo SUCCESS (no live call); `Y` is memo TERMINAL FAILURE (no live retry); `Z` triggers one new live attempt.
- Recipe2 is incomplete because `Y` failed; no metrics, no risk, no opportunity.
- Counter invariants:
  - `live_demand == 2` (one for `Y` in Recipe1; one for `Z` in Recipe2).
  - `live_attempted == 2` (both entered Stage B).
  - `live_succeeded == 1` (for `X`); `live_failed == 1` (for `Y`).
  - `run_reuse_hits == 2` (`X` SUCCESS, `Y` TERMINAL FAILURE for Recipe2).
  - `run_reuse_successes == 1`; `run_reuse_failures == 1`.

### C. All fresh persistent cache (14C)

Cache is pre-populated with `FRESH + SELECTED` (strict BUFF) for every output name demanded by every recipe. Expected: `live_demand == 0`; `live_attempted == 0`; strict BUFF adapter reruns; valuation completes only if every output name's strict BUFF adapter run produced a strict quote; otherwise the recipe is incomplete with no partial valuation.

### D. Mixed (14C)

9 fresh-cache hits + 1 cache miss. Expected: `cache_hits_fresh_selected == 9`; `cache_misses == 1`; `live_demand == 1`; `live_attempted == 1`; valuation may complete for the recipe.

### E. Stale under FRESH_ONLY (14C)

Cache returns `STALE / STALE_GRACE / POLICY_BLOCKED` for an output name. Expected: stale value NOT used; the name is in `cache_policy_blocked`; if `live_demand > remaining_budget`, the recipe is atomically blocked before any SteamDT call.

### F. Fresh cache strict-BUFF selection failure (14C)

Cache returns `FRESH + SELECTION_FAILURE` (strict BUFF adapter rejected the cached candidates — duplicate BUFF, non-positive sell price, no BUFF record). Expected: terminal same-run failure; no fallback; no second-platform substitute; no bid substitution; no metadata-zero reuse; if a later recipe demands the same exact name, no duplicate same-run live request.

### G. Live failure reuse (14B and 14C)

Exact name `X` fails once live (recorded in `PriceLookupResult.missing`). A later recipe demanding `X` causes no second live request in the same run. `run_reuse_failures` records the propagated failure.

### H. Invalid / mismatched quote (14C and 14B)

Cached candidates include a row whose `platform != "BUFF"`. Expected: strict BUFF adapter rejects it; `FRESH + SELECTION_FAILURE` outcome; no live fallback; no second-platform substitute.

### I. Cache backend failure (14C)

Redis raises a non-`PriceCacheCodecError` exception during `cache.get()`. Expected: `PriceCacheBackendError` propagates by identity from the resolver; NOT silently reinterpreted as `MISS`; NOT a live candidate; NOT a memo entry; no live budget consumed. The recipe's prepare or evaluate aborts with the typed error visible to the orchestrator.

### J. Cache codec failure (14C)

Stored Redis hash is corrupt. Expected: `PriceCacheCodecError` propagates by identity from the resolver; NOT silently reinterpreted as `MISS`; same fail-closed semantics as `I`.

### K. Cache adapter failure (14C)

`SteamDTPriceCacheAdapterError` raised during candidate normalization. Expected: propagates by identity from the cache-read seam; NOT a `MISS`; same fail-closed semantics as `I`.

### L. Cache write failure (NOT REQUIRED for initial 14C)

Initial Phase 14C is READ-only. No scanner writeback occurs. The existing manual refresh stack remains the writer. **No cache-write-failure runtime test is required for initial 14C** because scanner writeback does not occur. A future separately authorized phase may add scanner writeback and must then define write-failure semantics.

### M. MemoryError propagation (14B and 14C)

A `MemoryError` raised mid-live-call (from `SteamDTBuffPriceProvider.get_price` bare `raise` at `steamdt_buff_price_provider.py:52-53`) propagates by identity from the session to the orchestrator; no swallow, no reclassification as a normal failure, no partial valuation.

### N. Other BaseException propagation (14B and 14C)

`asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit`, `GeneratorExit` raised from `SteamDTBuffPriceProvider.get_price` propagate by identity because the provider's catch chain stops at `except Exception`. The session must NOT swallow them.

### O. Deep-pool regression (14B and 14C)

The existing `tests/test_multi_recipe_scanner_scale_validation.py` deep-pool fixture (10 goods / 100 InputItems / 901 theoretical radius-one states / 2 returned / 2 explored) remains green. Existing bounded enumeration / exact rehydration / Souvenir projection / deterministic order remain intact. Extend, never weaken.

### P. Strict fail-closed valuation (14B and 14C)

No partial EV / risk; no probability renormalization; no zero-filling; no risk-threshold changes. Every test in `tests/test_synthetic_scanner_scale_validation.py` and `tests/test_multi_recipe_scanner_scale_validation.py` continues to assert the same risk thresholds and EV math.

### Q. CLI (14D)

The default one-shot CLI does NOT require Redis. Live and integration paths remain opt-in. Invalid cache configuration fails before any live SteamDT work. `--universe-preview` continues to perform zero network calls. No hidden background work.

## Stop / status mapping

| Status | Meaning |
|---|---|
| `PHASE14A_R1_COMPLETE` | All gates pass; design corrected; branch pushed. |
| `PHASE14A_R1_LOCAL_STATE_BLOCKED` | Unexpected local state exists beyond the two protected research JSONs. |
| `PHASE14A_R1_BASELINE_MOVED` | `origin/main` or `origin/feature/scanner-valuation-integration` differs from expected. |
| `PHASE14A_R1_DESIGN_UNRESOLVED` | Design fails one of Gate 7's coherence checks. |
| `PHASE14A_R1_VALIDATION_FAILED` | Ruff / mypy / pytest / `git diff --check` fails against the unchanged baseline. |
| `PHASE14A_R1_CODE_SCOPE_FAILED` | `git diff --name-only e98cd97... -- app tests scripts .github pyproject.toml` is non-empty. |
| `PHASE14A_R1_AUDIT_CONTRACT_CONFLICT` | Pointer surfaces disagree or a surface prematurely says "implemented" for 14B / 14C / 14D. |
| `PHASE14A_R1_PUSH_FAILED` | `git push origin feature/scanner-valuation-integration` fails. |

## Acceptance criteria (summary)

Phase 14A-R1 closes only when ALL of the following hold simultaneously:

1. Spec trilogy updated under `specs/2026-08-29-scanner-valuation-integration-design-freeze/`.
2. `git diff --check` clean.
3. `ruff check .`, `mypy app`, `pytest` all pass locally with no weakening of pre-existing tests.
4. `git diff --name-only` shows that NO production `.py`, NO test, NO script, NO config file was modified; only docs and the three spec files.
5. `git diff --name-only e98cd97... -- app tests scripts .github pyproject.toml` is empty.
6. The protected research JSONs (`research/identity_revalidation/data/modest_serhat.json`, `research/identity_revalidation/data/timofey_ivanenko.json`) are NOT staged.
7. New `D-PHASE14A-R1-COHERENCE` decision appended to `docs/ai-context/DECISION_LOG.md` covering the nine R1 sub-corrections.
8. Pointer surfaces (`CLAUDE.md`, `PROJECT_CONTEXT.md`, `DEVELOPMENT_HANDOFF.md`, `ARCHITECTURE_STATE.md`, `specs/roadmap.md`) remain mutually consistent (R1 is not a status advance; pointers stay at Phase 14A / COMPLETE).
9. The six public surfaces that say "run-level cross-recipe exact-price reuse = NOT IMPLEMENTED" continue to say so.
10. The `v1-dry-run-baseline` tag is preserved at `32ab47c5b66a0f331457e69f1515e5e9bb2a37e1` and remains local-only.
11. `git push origin feature/scanner-valuation-integration` succeeds.
12. After push: `git rev-parse HEAD == git rev-parse @{u}`, `ahead/behind 0 0`, `main` is unchanged at `24c95c029f583d5cc0b0a67986e48c06d0ef7957`, the protected research JSONs remain untouched.
13. No PR, no merge, no force-push.
