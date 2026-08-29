# Phase 14A — Scanner Valuation Integration Design Freeze — Validation

## Validation strategy

Phase 14A is a **design freeze**. Validation here means: confirm the design is consistent with the actual code, the audit summary in `requirements.md` is correct, the frozen contracts in `plan.md` are coherent and complete, the existing pre-Phase-14 test matrix is preserved unchanged, and the proposed future test matrix is sufficient for the 14B / 14C / 14D phases that will follow.

Phase 14A does NOT:

- run the application;
- make any network request;
- modify production code;
- weaken, skip, or mark-xfail any pre-existing test;
- run any opt-in live / integration path;
- claim Phase 14B / 14C / 14D are implemented.

## Gate 1 — Repository baseline

Run and require:

```text
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git worktree list
git status --short
git tag --list v1-dry-run-baseline
```

Expected baseline at Phase 14A entry:

```text
branch:          feature/scanner-valuation-integration
HEAD:            24c95c029f583d5cc0b0a67986e48c06d0ef7957
origin/main:     24c95c029f583d5cc0b0a67986e48c06d0ef7957
ahead/behind:    0 0
worktrees:       D:/CS at 24c95c0 (main) only
status --short:  ?? research/identity_revalidation/data/modest_serhat.json
                 ?? research/identity_revalidation/data/timofey_ivanenko.json
v1-dry-run-baseline -> 32ab47c5b66a0f331457e69f1515e5e9bb2a37e1  (local-only; preserved)
```

If `origin/main` is anything other than `24c95c0…`, stop with `PHASE14A_BASELINE_MOVED`.

If `git status --short` shows anything other than the two protected research JSONs (before any design file is created), stop with `PHASE14A_LOCAL_STATE_BLOCKED`.

## Gate 2 — Spec-trilogy integrity

The directory must contain exactly three new files:

```text
specs/2026-08-29-scanner-valuation-integration-design-freeze/requirements.md
specs/2026-08-29-scanner-valuation-integration-design-freeze/plan.md
specs/2026-08-29-scanner-valuation-integration-design-freeze/validation.md
```

All three files must agree on:

- date `2026-08-29`;
- branch `feature/scanner-valuation-integration`;
- baseline `24c95c029f583d5cc0b0a67986e48c06d0ef7957`;
- design-freeze-only status (no application code, no Protected Core edit, no live request, no scheduler, no commits to `main`);
- preservation of `D-CACHE-001` as `Active` (cache still not implemented at runtime);
- preservation of every frozen contract `D-ENUM-001..004`, `D-SCANNER-001`, `D-VALIDATION-001`, `D-MEMORY-001`, `D-ADAPTER-003`, `D-ADAPTER-004`;
- no invented BUFF / SteamDT / Redis / Discord / cache endpoint, signature, parameter, or field mapping;
- no fallback valuation, no bid substitution, no metadata-zero reuse, no probability renormalization, no risk-threshold weakening;
- no renaming, retagging, force-updating, or pushing of `v1-dry-run-baseline`;
- the two protected research JSONs remain untouched and un-staged.

`git diff --check` must report no whitespace or conflict markers.

## Gate 3 — Production code byte-identity

`git diff --name-only 24c95c029f583d5cc0b0a67986e48c06d0ef7957 -- 'app/**' 'tests/**' 'scripts/**' 'pyproject.toml' 'requirements*.txt'` must report no files.

Specifically, the following files MUST be byte-identical to `24c95c0…`:

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
- `app/services/steamdt_cached_price_resolver.py`
- `app/services/steamdt_price_snapshot_source.py`
- `app/services/steamdt_price_refresh_service.py`
- `app/services/steamdt_refresh_planner.py`
- `app/services/steamdt_refresh_executor.py`
- `scripts/run_live_scan_once.py`
- `scripts/steamdt_refresh_integration.py`
- `tests/test_scanner_orchestrator.py`
- `tests/test_multi_recipe_scanner_scale_validation.py`
- `tests/test_synthetic_scanner_scale_validation.py`
- `tests/test_run_live_scan_once.py`
- `tests/test_valuation_service.py`
- `tests/test_steamdt_buff_price_provider.py`
- `tests/test_price_cache.py`
- `tests/test_price_cache_factory.py`
- `tests/test_steamdt_cached_price_resolver.py`
- `tests/test_steamdt_price_refresh_service.py`
- `tests/test_steamdt_price_snapshot_source.py`
- `tests/test_steamdt_refresh_planner.py`
- `tests/test_steamdt_refresh_executor.py`
- `tests/test_redis_price_cache.py`
- `tests/test_redis_price_cache_integration.py`

Any non-empty `git diff` against these files at Phase 14A commit time = `PHASE14A_COMMIT_SCOPE_FAILED`.

## Gate 4 — Static checks

Run, with the repository-established Windows equivalent only if needed:

```text
git diff --check
python -m ruff check .
python -m mypy app
python -m pytest
```

Expected:

- `git diff --check`: clean (exit 0).
- `python -m ruff check .`: passes (exit 0); no new warnings or errors.
- `python -m mypy app`: passes (exit 0); no new warnings or errors.
- `python -m pytest`: passes the **default suite**, which is offline-safe. The default suite must NOT be weakened.

Explicitly do NOT run:

- opt-in live BUFF tests (gated by env vars; default off);
- opt-in live SteamDT tests (gated by env vars; default off);
- real Redis integration tests (gated by `STEAMDT_RUN_REDIS_INTEGRATION_TESTS=true`; default off).

Any failure = `PHASE14A_VALIDATION_FAILED`.

## Gate 5 — Pre-Phase-14 test matrix preservation

The following pre-existing test files must NOT be modified, skipped, xfailed, marked `@pytest.mark.skip`, or have any assertion removed / weakened:

- `tests/test_synthetic_scanner_scale_validation.py`
- `tests/test_multi_recipe_scanner_scale_validation.py`

Their pass / fail outcome against `24c95c0…` MUST match exactly before and after the Phase 14A commit. They are the canonical regression gates for any future scanner-side change. Phase 14A explicitly forbids weakening them to make the design-freeze PR pass.

## Gate 6 — Counter / accounting migration contract (for 14B)

The 14B implementation PR must demonstrate that the additive counters preserve the legacy semantics for every pre-existing test that touches `ScannerRunStageCounters`. The following pre-Phase-14 tests are the contract surface:

- `tests/test_scanner_orchestrator.py::test_scanner_orchestrator_bounded_multi_recipe` (and any sibling tests that assert on `valuation_requests_attempted / succeeded / failed / blocked`).
- `tests/test_multi_recipe_scanner_scale_validation.py::test_exact_cap_full_valuation` and `::test_one_below_cap_atomic_block` and `::test_two_bucket_aggregate_allocation` and `::test_legacy_compat_1_1_equivalence`.
- `tests/test_synthetic_scanner_scale_validation.py` (any test that asserts on the legacy counters).

After 14B lands, those tests must pass unchanged, except possibly for additive assertions on the new counters. If any legacy counter semantics are silently overloaded (Option A ambiguity), Phase 14A explicitly requires escalation to Option B (explicit semantics migration with full test / doc migration). Option B is not implemented in 14A; the choice is made at the start of 14B.

## Gate 7 — Design coherence

The design must be coherent against the existing audit facts. The validation check is:

1. The `RunScopedValuationSession` boundary does NOT depend on `BuffCommunityIdentityResolver` or any other identity resolver. It receives canonical `output_market_hash_name` strings.
2. The atomic preflight algorithm (`plan.md` task group 6) is single-threaded inside one `run_once()`. It does NOT introduce background tasks, schedulers, daemons, or concurrent recipe evaluation.
3. `FRESH_ONLY` is the only initial policy. `ALLOW_STALE`, `ALLOW_STALE_GRACE`, and any future policy that consumes stale data are NOT enabled in 14B or 14C.
4. The cache backend / codec exception contract is explicit fail-closed. The design does NOT silently reinterpret `PriceCacheBackendError` or `PriceCacheCodecError` as `MISS`.
5. `MemoryError` propagates by identity. The design does NOT add any `try/except MemoryError` block in the new session.
6. The "at most one live SteamDT attempt per exact name per run" invariant holds under every defined outcome in `plan.md` task group 5.
7. No partial valuation. Any missing / failed / blocked / invalid exact-name resolution yields `valuation_completed=False`, no metrics, no risk, no opportunity. The design does NOT drop outputs, renormalize probabilities, zero-fill, stale-fill, or substitute another platform.
8. Bounded multi-recipe ordering is preserved. `LiveScannerOrchestrator.run_once` continues to iterate `composition.selections` in structural order; counter updates and cache lookups happen inside the per-recipe `_evaluate_selection` boundary.
9. The legacy `live_recipe_valuation.py` and `valuation_service.py` APIs are NOT modified by Phase 14A. Any future 14B / 14C / 14D modification to them is explicit and reviewed.
10. The 14B / 14C / 14D sequence in `plan.md` task group 10 is internally consistent. 14B is the smallest safe step (run memo + additive counters; no persistent cache). 14C layers Phase 12D cache. 14D wires CLI + scale/live validation.

Any coherence failure = `PHASE14A_DESIGN_UNRESOLVED`.

## Gate 8 — Documentation pointer consistency

The pointer surfaces must remain mutually consistent. After the Phase 14A commit:

- `CLAUDE.md` "当前阶段指针" block: R0-D = COMPLETE; Phase 14A = IN PROGRESS — DESIGN FREEZE (no code); canonical `main` = `24c95c0…`.
- `docs/ai-context/PROJECT_CONTEXT.md` "Git / Phase Baselines" + "Latest completed phases": pointers advanced to `PHASE_14A_COMPLETE` for the design-freeze sub-phase; R0-D = COMPLETE.
- `docs/ai-context/DEVELOPMENT_HANDOFF.md` "Current Git State" + "Completed Milestones" + "Next Action": R0-D = COMPLETE; Phase 14A = latest completed design-freeze sub-phase; 14B = PROPOSED / NOT AUTHORIZED.
- `docs/ai-context/ARCHITECTURE_STATE.md`: minimal note that any future Phase 14 implementation must touch Protected Core under explicit authorization; `RunScopedValuationSession` design is the only sanctioned seam.
- `docs/ai-context/DECISION_LOG.md`: append `D-CACHE-002` (run-scope exact-name reuse), `D-CACHE-003` (FRESH_ONLY initial policy), `D-BUDGET-001` (atomic live-demand preflight), `D-CACHE-004` (failure reuse within run), `D-ACCOUNTING-001` (additive counter migration; legacy preserved), `D-PHASE14A-COMPLETE` (design freeze closed).
- `specs/roadmap.md`: Phase 14A = IN PROGRESS — DESIGN FREEZE (no code); R0-D = COMPLETE; six "not implemented" capability lines (live scanner cache integration; run-level cross-recipe exact-price reuse) still say "NOT IMPLEMENTED".
- All six public surfaces that say "run-level cross-recipe exact-price reuse = NOT IMPLEMENTED" still say so (README.md, docs/SPEC.md, docs/ARCHITECTURE.md, PROJECT_CONTEXT.md, DEVELOPMENT_HANDOFF.md, DECISION_LOG.md).

Any surface that says "implemented" for Phase 14B / 14C / 14D is a `PHASE14A_AUDIT_CONTRACT_CONFLICT`.

## Future test matrix (must be written in Phase 14B / 14C / 14D, NOT in 14A)

The 14A design freeze does not write any of these tests. They are listed here as the canonical contract that 14B / 14C / 14D must satisfy.

### A. Cross-recipe reuse (14B)

Recipe1 demands `A, B, C, D, E, F, G, H, I, J`. Recipe2 shares `A..I` plus a new name `K`. No persistent cache. Expected: `live_attempted == 11` for 11 distinct output names across 2 recipes; `run_reuse_hits == 0` (no run memo hits yet); `live_atomically_blocked == 0`.

### B. Exact-cap (14B)

`valuation_live_used = 9` already consumed by prior recipes; recipe2 demands exactly 1 new live name; remaining live budget = 1. Expected: recipe2 evaluated, `live_attempted += 1`, no block. Same scenario with remaining live budget = 0-equivalent (i.e. cap already exhausted by prior recipes): recipe2 atomically blocked before any SteamDT call, `live_atomically_blocked += 1`.

### C. All fresh persistent cache (14C)

Cache is pre-populated with `FRESH + SELECTED` for every output name demanded by every recipe. Expected: `live_attempted == 0`; strict selector reruns; valuation completes only if every output name's selector run produced a strict quote; otherwise the recipe is incomplete with no partial valuation.

### D. Mixed (14C)

9 fresh-cache hits + 1 cache miss. Expected: `cache_hits_fresh_selected == 9`; `cache_misses == 1`; `live_attempted == 1`; valuation may complete for the recipe.

### E. Stale under FRESH_ONLY (14C)

Cache returns `STALE / STALE_GRACE / POLICY_BLOCKED` for an output name. Expected: stale value NOT used; `live_attempted += 1` for that name; if the remaining live budget is 0, the recipe is atomically blocked before any SteamDT call.

### F. Fresh cache selection failure (14C)

Cache returns `FRESH + SELECTION_FAILURE` for an output name. Expected: terminal same-run failure; no fallback; no second-platform substitute; no bid substitution; no metadata-zero reuse; if a later recipe demands the same exact name, no duplicate same-run live request.

### G. Live failure reuse (14B and 14C)

Exact name `X` fails once live. A later recipe demanding `X` causes no second live request in the same run. `run_reuse_failures` records the propagated failure.

### H. Invalid / mismatched quote (14C)

Cached candidates include a row whose `platform != "BUFF"`. Expected: selector rejects it; `FRESH + SELECTION_FAILURE` outcome; no live fallback; no second-platform substitute.

### I. Cache backend failure (14C)

Redis raises a non-`PriceCacheCodecError` exception during `cache.get()`. Expected: `PriceCacheBackendError` propagated by identity; no silent reinterpretation as `MISS`; the recipe's valuation is incomplete and the error is observable.

### J. Cache write failure (14C)

Cache write after live success raises `PriceCacheBackendError` (Redis down). Expected: live success stands; the cache write is skipped; no silent reinterpretation of the live success as failure; the quote is returned and valuation may complete.

### K. MemoryError propagation (14B and 14C)

A `MemoryError` raised mid-live-call propagates by identity from the session to the orchestrator; no swallow, no reclassification as a normal failure, no partial valuation.

### L. Deep-pool regression (14B and 14C)

The existing `tests/test_multi_recipe_scanner_scale_validation.py` deep-pool fixture (10 goods / 100 InputItems / 901 theoretical radius-one states / 2 returned / 2 explored) remains green. Existing bounded enumeration / exact rehydration / Souvenir projection / deterministic order remain intact. Extend, never weaken.

### M. Strict fail-closed valuation (14B and 14C)

No partial EV / risk; no probability renormalization; no zero-filling; no risk-threshold changes. Every test in `tests/test_synthetic_scanner_scale_validation.py` and `tests/test_multi_recipe_scanner_scale_validation.py` continues to assert the same risk thresholds and EV math.

### N. CLI (14D)

The default one-shot CLI does NOT require Redis. Live and integration paths remain opt-in. Invalid cache configuration fails before any live SteamDT work. `--universe-preview` continues to perform zero network calls. No hidden background work.

## Stop / status mapping

| Status | Meaning |
|---|---|
| `PHASE14A_COMPLETE` | All gates pass; design frozen; branch pushed. |
| `PHASE14A_BASELINE_MOVED` | `origin/main` is not `24c95c0…`. |
| `PHASE14A_LOCAL_STATE_BLOCKED` | Unexpected local state exists beyond the two protected research JSONs. |
| `PHASE14A_BRANCH_COLLISION` | `feature/scanner-valuation-integration` already exists at a non-clean reusable state. |
| `PHASE14A_SCOPE_ALREADY_IMPLEMENTED` | Code audit shows the seam is already implemented. |
| `PHASE14A_AUDIT_CONTRACT_CONFLICT` | Pointer surfaces disagree or a surface prematurely says "implemented" for 14B / 14C / 14D. |
| `PHASE14A_DESIGN_UNRESOLVED` | Design fails one of Gate 7's coherence checks. |
| `PHASE14A_VALIDATION_FAILED` | Ruff / mypy / pytest / `git diff --check` fails against the unchanged baseline. |
| `PHASE14A_COMMIT_SCOPE_FAILED` | `git diff --name-only` shows any production `.py` file changed. |
| `PHASE14A_PUSH_FAILED` | `git push -u origin feature/scanner-valuation-integration` fails. |

If the audit finds that the scanner path already imports any Phase 12D cache module or already memoizes exact names across recipes, stop with `PHASE14A_SCOPE_ALREADY_IMPLEMENTED`.

## Acceptance criteria (summary)

Phase 14A closes only when ALL of the following hold simultaneously:

1. Spec trilogy created under `specs/2026-08-29-scanner-valuation-integration-design-freeze/`.
2. `git diff --check` clean.
3. `ruff check .`, `mypy app`, `pytest` all pass locally with no weakening of pre-existing tests.
4. `git diff --name-only` shows that NO production `.py` file was modified; only docs and the three spec files.
5. The protected research JSONs (`research/identity_revalidation/data/modest_serhat.json`, `research/identity_revalidation/data/timofey_ivanenko.json`) are NOT staged.
6. New D- IDs appended to `docs/ai-context/DECISION_LOG.md` covering run reuse, FRESH_ONLY, atomic live-demand preflight, failure reuse, accounting, and 14A completion.
7. Pointer surfaces (`CLAUDE.md`, `PROJECT_CONTEXT.md`, `DEVELOPMENT_HANDOFF.md`, `ARCHITECTURE_STATE.md`, `specs/roadmap.md`) updated consistently.
8. The six public surfaces that say "run-level cross-recipe exact-price reuse = NOT IMPLEMENTED" continue to say so.
9. The `v1-dry-run-baseline` tag is preserved at `32ab47c5b66a0f331457e69f1515e5e9bb2a37e1` and remains local-only.
10. `git push -u origin feature/scanner-valuation-integration` succeeds.
11. After push: `git rev-parse HEAD == git rev-parse @{u}`, `ahead/behind 0 0`, `main` is unchanged, the protected research JSONs remain untouched.
12. No PR, no merge, no force-push.
