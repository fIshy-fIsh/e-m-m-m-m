# Phase 17A — Recipe-first Runtime Integration Design Freeze

## Requirements

## 1. Status and authority

This is a docs/design-only freeze for
`PHASE_17A_RECIPE_FIRST_RUNTIME_INTEGRATION_DESIGN_FREEZE`.

Current completed phase: `PHASE_16G_R7_LIVE_VALIDATED`.

Validated authority:

- pre-live Commit F:
  `ce546730e4a34bf53e3973e5a30508361f51355e`
- case SHA-256:
  `266bbd0f4df64bd947c4d081a0b978d51a03a221691c2e2acc8987fe890f5e68`
- result SHA-256:
  `9a0aa4ac2572018af65af3692f4f9db1e374efa2c7ad41723eaea11289a8f17e`
- completion commit:
  `940127ff4d8f7d6a55aba4128670c059acd7e731`
- completion CI run `34085292093`: SUCCESS;
  `3698 passed, 23 skipped, 2 warnings in 46.29s`

Phase 16G validated interface/path correctness under one bounded live
attempt. It did not prove profitability or risk acceptance. No further
Phase 16G live run is authorized.

## 2. Problem

The mature production one-shot scanner is goods-first. The implemented
recipe-first stack exists behind an explicit disabled-by-default
orchestrator and has bounded-live validation evidence, but there is no
operator-facing runtime that composes the complete front half:

```text
family discovery
  -> static geometry and float feasibility
  -> batch prescreen
  -> coarse economics and deterministic ranking
  -> one active family / targeted BUFF plan
```

with the mature downstream half:

```text
targeted acquisition
  -> exact identity/intrinsic/metadata enrichment
  -> family-constrained concrete search
  -> strict final valuation
  -> existing EV/ROI/risk
  -> report
```

Phase 17A freezes that integration boundary before implementation.

## 3. Goals

1. Freeze a separate explicit operator-facing recipe-first one-shot CLI:
   `scripts/run_recipe_first_scan_once.py`.
2. Replace the discovery brain in front of the mature downstream stack;
   do not rewrite the mature downstream stack.
3. Compose existing Phase 16B–16E authorities rather than reimplementing
   family, float, probability, valuation, EV, or risk math.
4. Keep goods-first behavior and `scripts/run_live_scan_once.py`
   unchanged by default.
5. Keep recipe-first disabled unless explicitly invoked and enabled.
6. Define deterministic one-active-family and fallback-before-BUFF state.
7. Define independent SteamDT prescreen, BUFF acquisition, and final
   valuation budgets and fail-closed accounting.
8. Reuse the existing strict `FRESH_ONLY` persistent cache-read seam for
   final valuation only; no persistent writes.
9. Define stable terminal classifications and operator report fields.
10. Define staged Phase 17B/C/D/E/F gates.

## 4. Non-goals

- No runtime implementation in Phase 17A.
- No modification to application, script, test, provider, dependency, CI,
  or workflow code.
- No market HTTP, smoke, retry, pagination, polling, or fallback execution.
- No scheduler, daemon, Discord delivery, Redis requirement, PostgreSQL
  persistence, or scanner write-after-live.
- No automatic buying, trading, login, cookie collection, CAPTCHA bypass,
  BUFF risk-control bypass, or browser purchase automation.
- No production-default change.
- No Phase 15C representative campaign execution.
- No migration of the legacy goods-first wear-row cardinality behavior;
  `D-TRADEUP-WEAR-ROW-MIGRATION-001` remains deferred.
- No reuse of Phase 16G's tiny validation caps as inferred production
  defaults.
- No new external endpoint, signature, request field, or response mapping.

## 5. Production boundaries

- The production default remains the existing goods-first one-shot path.
- Recipe-first is a separate explicit opt-in CLI through at least Phase 17D.
- No default cutover is authorized before Phase 17E.
- The new CLI is one-shot, read-only, and exits after one terminal report.
- It cannot be called by APScheduler or a background loop in V1.
- Docker/Linux is future operations infrastructure, not a requirement for
  the current Windows/Python one-shot development path.
- `D-TRADEUP-WEAR-ROW-MIGRATION-001` remains deferred because the
  recipe-first concrete path already uses finish-level structural geometry
  rather than the legacy wear-row builder.

## 6. Operator UX and CLI requirements

The Phase 17B entrypoint MUST be separate:

```text
python scripts/run_recipe_first_scan_once.py <explicit options>
```

The exact flag spelling is an implementation detail for Phase 17B, but
these semantics are frozen:

- invocation itself selects recipe-first mode;
- an additional explicit enable value must be true for market I/O;
- default/no enable refuses pre-network;
- one run only; no interval/repeat option;
- `--preview` (or equivalently named command) performs family discovery,
  static feasibility, batch-request planning, deterministic ranking, and
  targeted-plan rendering without constructing live providers or making
  any market request;
- human summary is default; additive `--json` is allowed;
- user-facing output must identify recipe-first mode and never imply the
  goods-first default changed;
- secrets must come from existing settings/environment ownership and must
  never appear in arguments, output, reports, or exceptions;
- exact snapshot paths may be configurable using existing CLI patterns;
  defaults remain the pinned repository snapshots;
- invalid config and impossible combinations fail before market clients.

## 7. Runtime composition requirements

The operator runtime MUST compose:

```text
PinnedSkinMetadataResolver.skins
  + BuffCommunityIdentityResolver
    -> structural finish index
    -> lazy deterministic RecipeFamily discovery
    -> exact RecipeFamilyGeometry
    -> exact static float feasibility
    -> strict SteamDT BUFF-only batch prescreen
    -> immutable prescreen price book
    -> exact Fraction/Decimal prescreen economics
    -> deterministic streaming Top-2 ranking
    -> TargetedBuffScanDecision
    -> exactly one active family
    -> ExistingRecipeFirstAcquisitionPipeline
    -> RecipeFirstScannerOrchestrator
         -> search_family_constrained_recipes
         -> RunScopedValuationSession
         -> ValuationService
         -> calculate_opportunity_metrics
         -> evaluate_opportunity
    -> RecipeFirstOperatorRunReport
```

Existing ownership boundaries are mandatory. The Phase 16G runner is
live-validation evidence only and MUST NOT become production composition.

## 8. One-active-family / fallback requirements

- Ranking may retain at most the existing `TOP_RANKED_FAMILIES = 2`.
- Only one family is active for BUFF acquisition in a run.
- Family #2 may replace family #1 only while `buff_dispatch_started == 0`.
- A pre-BUFF fallback reason must be explicit and limited to expected
  plan-preparation conditions (for example: no resolved targeted goods,
  static-plan contract incomplete, or explicit operator policy). It may
  not hide an internal contract failure.
- Once any BUFF request dispatch starts, family identity is immutable for
  the rest of the run, including after transport or parsing failure.
- `fallback_family_calls` and selected/fallback keys are reported.
- No recursive fallback and no third family.

## 9. Cache and final valuation requirements

- Final valuation uses a fresh `RunScopedValuationSession` per run.
- The session receives the existing `ScannerCachedBuffPriceResolver`,
  fixed to `FRESH_ONLY` and the strict BUFF selector.
- Default cache backend follows the existing one-shot CLI composition:
  in-memory; Redis remains explicit/optional and is never required.
- Cache is read-only from the scanner: no write-after-live, refresh, TTL
  override, or scheduler is added.
- Run memo ordering remains memo -> FRESH_ONLY cache -> NEW LIVE.
- Atomic admission applies only to NEW LIVE exact-name demand.
- Prescreen batch prices never seed the session memo/cache and never
  substitute for final exact prices.
- A complete final valuation still requires exact-name strict BUFF prices;
  no bid, second platform, lowest-platform, stale-cache, or metadata-zero
  fallback.

## 10. Budget requirements

Budget ownership is separate:

### A. SteamDT prescreen

- Logical names come from exact family feasibility/prescreen planning.
- Existing internal `PRESCREEN_BATCH_CHUNK_SIZE = 10` is a project
  transport chunk, not a confirmed provider limit.
- Request count is derived from deterministic chunks and must be admitted
  before any batch dispatch.
- No hidden retry. Attempts, dispatch starts, successes, missing names,
  terminal selection failures, and transport errors are distinct evidence.
- A Phase 17 runtime cap/config is required, but its production default is
  not frozen in 17A. Phase 17C measurement must establish a safe value.

### B. BUFF acquisition

- Existing hard project cap remains
  `MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10`, matching the production
  goods-first hard cap `LiveScannerOrchestrator.HARD_MAX_GOODS_IDS = 10`.
- Active plan `hard_request_count` is the exact admitted logical demand.
- Each goods ID is fetched page 1/default sort only through the existing
  anonymous read-only path.
- Attempt and dispatch-start counters are charged before provider completion.
- No retry/pagination. No family switch after first dispatch start.
- A lower configurable per-run limit may be added in Phase 17B, but 17A
  does not change the hard cap or choose a new default without evidence.

### C. Final exact SteamDT valuation

- Existing hard limit remains `1..60`; current goods-first CLI default is 5.
- Recipe-first Phase 17B may expose an independently named configuration,
  but 17A freezes no numeric increase or new default. Initial implementation
  should inherit the conservative existing default 5 unless Phase 17C
  evidence justifies a separate decision.
- Run-scoped memo/FRESH_ONLY reads reduce NEW LIVE demand before atomic
  admission. A recipe is either admitted entirely or blocked entirely;
  no partial valuation.
- Logical demand, cache results, real provider dispatch starts, successes,
  failures, and atomically blocked names remain separately observable.
- No same-name NEW LIVE request is duplicated within one run.

Phase 16G caps 1 / 1 / 2 / 3 remain evidence-harness caps only.

## 11. Terminal classification requirements

The future CLI returns one terminal class from three operator-level groups.

### Successful execution (`exit 0`)

- `SUCCESS_OPPORTUNITIES_FOUND`: run completed; one or more opportunities
  passed risk.
- `SUCCESS_NO_QUALIFYING_OPPORTUNITY`: complete evaluations existed, but
  none passed; include risk rejects separately.
- `SUCCESS_PREVIEW`: deterministic zero-market-I/O preview completed.

### Expected bounded no-opportunity (`exit 0`)

- `NO_CONCRETE_SELECTION`: acquisition completed but no bounded concrete
  selection existed.
- `RISK_FILTER_REJECTED`: complete valuation but every evaluation failed
  risk. This may be a subtype/count within
  `SUCCESS_NO_QUALIFYING_OPPORTUNITY`; JSON must retain the exact reason.

### Incomplete/infrastructure (`exit 2`)

- `PRESCREEN_INCOMPLETE`
- `BUFF_ACQUISITION_INSUFFICIENT`
- `FINAL_VALUATION_INCOMPLETE`
- `VALUATION_REQUEST_BUDGET_BLOCKED`
- `EXTERNAL_PROVIDER_FAILURE`

### Contract/configuration (`exit 3`)

- `CONFIGURATION_BLOCKED`
- `IDENTITY_INTRINSIC_METADATA_CONTRACT_FAILURE`
- `INTERNAL_CONTRACT_FAILURE`

Expected no-opportunity outcomes must not be reported as infrastructure
failures. Provider failures must not be hidden as no opportunity. Contract
bugs must not trigger family fallback or be relabeled as provider failure.
Keyboard/system cancellation semantics remain normal process interruption.

## 12. Opportunity report requirements

Define an immutable service-layer `RecipeFirstOperatorRunReport` (name may
change in Phase 17B, semantics may not) separate from provider DTOs and CLI
serialization. Minimum fields:

- run ID, timestamps, terminal class, incompleteness flags;
- selected family key/hash, rarity, StatTrak mode, collection counts;
- ranked-family summary with deterministic rank/economics/gate reasons;
- active/fallback family keys and fallback-used/reason;
- targeted input exact names and goods IDs; requested/succeeded/failed page
  counts;
- concrete 10-input summary: exact names, collection counts, float/cost
  aggregates, intrinsic mode; no seller/account details and no listing IDs in
  normal output;
- exact output names, probabilities, output floats/wears;
- final exact prices and source;
- total input cost, gross/net EV, expected profit, ROI, profit probability,
  worst-case loss and percentage;
- risk decision and stable rejection reasons;
- prescreen/BUFF/final logical, attempted, dispatch-start, success, failure,
  cache-hit, reuse, and blocked counters;
- incomplete/missing identities and provider error classes using bounded safe
  codes only.

Human and JSON renderers consume this DTO. They do not recompute math or
expose credentials, raw provider payloads, seller/account data, cookies,
auth headers, webhook values, or unnecessary listing identifiers.

## 13. Failure and determinism requirements

- Exact names remain case-sensitive and fail closed.
- Family generation, geometry, feasibility, ranking, plan allocation,
  concrete search, output ordering, and report serialization are deterministic
  for identical snapshots and normalized provider fakes.
- Internal contract exceptions stop the run; no hidden fallback.
- A provider transport/API failure reports its phase and safe class; no raw
  response or credential content.
- No retry unless a future separately reviewed client policy explicitly owns
  it. Phase 17B/C add none.
- A request dispatch start consumes the relevant budget even when transport,
  parsing, policy selection, or identity validation later fails.

## 14. Phase 15C relationship

The 14-day representative campaign remains deferred and not started in
Phase 17A/B/C.

After Phase 17D validates the actual operator-facing runtime, Phase 17F
reopens measurement as a controlled side-by-side comparison of recipe-first
and goods-first. The two arms must use matched observation windows and
pinned policy/snapshot versions, but independent request budgets, caches,
run state, and artifacts. Results may compare coverage, valuation demand,
provider dispatch, complete evaluations, and opportunity/risk outcomes;
they may not treat designed replay frequencies as production probabilities.

## 15. Acceptance for Phase 17A

- All four dated design-freeze files exist and are internally consistent.
- Current-state docs point to Phase 16G-R7 as completed and Phase 17A as the
  next/active docs-only phase.
- Historical Phase 15/16 evidence remains intact.
- No runtime/test/provider/dependency/workflow file changes.
- No SteamDT or BUFF request.
- Exactly one docs/design commit is pushed on the new branch.
