# Phase 17A — Recipe-first Runtime Integration Design Freeze

## Plan

This plan is staged and gated. No phase inherits live authorization from a
prior phase.

## Task group 1 — Phase 17A current-state sync and design freeze

1. Correct only top-level stale current-position/current-working-line fields.
2. Preserve all historical Phase 15/16 evidence.
3. Record Phase 16G-R7 as the completed interface/path authority, with no
   profitability/risk claim and no new live authorization.
4. Freeze the separate recipe-first one-shot CLI strategy.
5. Freeze front-half coordinator vs mature downstream ownership.
6. Freeze FRESH_ONLY final cache reads, no writes.
7. Freeze independent request-budget accounting and terminal/report contracts.
8. Freeze Phase 17B/C/D/E/F gates and side-by-side Phase 15C re-entry.

Do not proceed until:

- requirements/design/plan/validation agree;
- docs-only diff is proven;
- no stale top-level Phase15B current pointer remains;
- no market request occurred;
- the design branch has one docs/design commit with CI success if triggered.

## Task group 2 — Phase 17B opt-in one-shot runtime composition

Scope: implementation, **zero market network in tests**.

1. Add `scripts/run_recipe_first_scan_once.py` as a separate composition root.
2. Add immutable runtime config/budget/terminal/report DTOs.
3. Add a coordinator for family discovery -> feasibility -> prescreen planning
   -> economics/ranking -> active/fallback state -> downstream invocation.
4. Reuse pinned resolvers, strict batch resolver, ranking/planning authorities,
   `RecipeFirstScannerOrchestrator`, strict final provider, FRESH_ONLY resolver,
   existing EV/risk, and resource ownership helpers.
5. Keep service and CLI defaults disabled/read-only/one-shot.
6. Add preview mode that proves no client/provider construction.
7. Add human/JSON rendering without recomputation or sensitive fields.
8. Preserve goods-first script/service byte behavior unless an unavoidable
   neutral helper extraction is separately reviewed and proven equivalent.

Do not proceed to Phase 17C until:

- no production caller automatically invokes the new CLI;
- default-disabled and preview zero-network tests pass;
- goods-first regression suite is byte/behavior equivalent;
- no Phase 16G harness is imported by runtime;
- all new config invalidity fails before provider construction;
- no numeric policy increase is introduced.

## Task group 3 — Phase 17C offline end-to-end integration

Scope: real internal composition, external market seams faked, **zero market
network**.

Test the complete path:

```text
lazy family generation
  -> geometry
  -> static feasibility
  -> batch prescreen
  -> prescreen price book/economics
  -> deterministic ranking
  -> targeted active/fallback decision
  -> acquisition/enrichment
  -> concrete search
  -> memo/FRESH_ONLY/NEW-LIVE valuation
  -> EV/risk
  -> human/JSON report
```

Required evidence:

1. Determinism across repeated normalized fixtures.
2. Family discovery CPU/memory/state counters.
3. Prescreen name/chunk/request cardinality distributions.
4. Top-2 and one-active-family ordering.
5. Fallback allowed before BUFF and impossible after BUFF dispatch start.
6. BUFF hard cap <=10 and page-1/default-sort only.
7. Exact-name FRESH_ONLY reuse and atomic final NEW-LIVE admission.
8. No prescreen price in final memo/quotes.
9. Complete terminal classification matrix.
10. Structural-field preservation and exact EV/risk reuse.
11. Human/JSON report parity and secret/raw/provenance-safety guards.
12. Existing goods-first tests unchanged and green.

Do not proceed to Phase 17D until:

- family/prescreen production defaults have an evidence-backed proposal;
- all failure and budget boundaries are covered offline;
- request dispatch-start accounting is proven;
- the actual CLI path is exercised offline, not just services;
- the exact bounded-live case and budgets are frozen outside Git;
- CI for the pre-live checkpoint is exact green;
- a separate Phase 17D live authorization is granted.

## Task group 4 — Phase 17D one bounded live operator run

Scope: one separately authorized, read-only, operator-facing runtime attempt.

1. Use the actual `scripts/run_recipe_first_scan_once.py`; no special live
   validation harness.
2. Freeze commit/case/config identities and numeric request caps first.
3. Execute one attempt only.
4. Treat any external dispatch start as consuming authorization.
5. No retry, pagination, polling, or post-BUFF family fallback.
6. Persist only a redacted safe result/evidence artifact outside Git.
7. Independently audit identity, budgets, concrete structure, final strict
   prices, EV/risk/report consistency, and sensitive-field exclusion.

Do not proceed to Phase 17E until:

- the actual operator entrypoint reaches a terminal result under all frozen
  budgets;
- any failure is classified without hiding contract/provider distinctions;
- no production default changed during validation;
- evidence and exact CI are durable.

A failed/incomplete Phase 17D does not authorize an automatic rerun.

## Task group 5 — Phase 17E default/cutover decision

Scope: policy/design decision, not automatic implementation.

Inputs:

- Phase 17C offline measurement;
- Phase 17D actual-runtime live evidence;
- goods-first baseline behavior;
- operational/failure/budget evidence.

Allowed outcomes:

1. Keep goods-first default and recipe-first explicit.
2. Make recipe-first default in a separately approved implementation.
3. Maintain explicit dual-mode indefinitely.

No default switch occurs merely because Phase 17D validates. A cutover needs a
separate decision record, migration/rollback plan, tests, and authorization.

## Task group 6 — Phase 17F representative measurement / Phase 15C re-entry

Only after the runtime architecture is stable:

1. Freeze a controlled side-by-side protocol.
2. Run goods-first and recipe-first in matched windows with independent
   budgets, cache/run state, and artifacts.
3. Measure structural coverage, provider demand, complete evaluations,
   risk rejections, and reportable opportunities.
4. Revisit default 5 / hard 60 and any new prescreen/family budget only from
   representative evidence.
5. Do not infer production probabilities from designed replay observations.

Do not start the 14-day campaign in Phase 17A/B/C/D/E.

## Rollback/default-off guarantees

- Deleting/not invoking the new script leaves the existing production path
  intact.
- `RecipeFirstScannerConfig.enabled=False` remains the service default.
- No scheduler or background caller is introduced.
- Phase 17B can be reverted independently without changing goods-first.
- Phase 17D evidence cannot trigger a default change.
- Redis remains optional; in-memory cache remains usable.
- No scanner persistent write path is introduced.
- `D-TRADEUP-WEAR-ROW-MIGRATION-001` remains deferred.
