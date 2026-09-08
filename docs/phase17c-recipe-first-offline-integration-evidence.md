# Phase 17C — Recipe-first Runtime Offline Integration Evidence

## Authority and scope

- Base authority: Phase17B-R1 commit
  `d1ac3a2e9fc9012441c3337904f391ab612094ac`.
- Branch: `feature/recipe-first-runtime-offline-integration`.
- Scope: offline integration only. No SteamDT/BUFF/network-cache HTTP,
  Phase16G execute, scheduler, Discord, PostgreSQL mutation, auto-buy, or
  auto-trade.
- Production recipe-first remains OFF; goods-first remains unchanged.

## Actual path exercised

The real `scripts/run_recipe_first_scan_once.py` public `main()` path is
exercised for no-enable and preview cases. Full scenarios use the real
`RecipeFirstRuntimeCoordinator` with pinned metadata/identity snapshots and
fake/injected external market seams:

```text
bounded lazy family discovery
  -> structural finish geometry
  -> exact static float feasibility
  -> strict BUFF-only batch pre-screen resolver
  -> immutable pre-screen price book
  -> Decimal/Fraction coarse economics
  -> deterministic streaming Top-2
  -> targeted BUFF decision / pre-dispatch fallback state
  -> ExistingRecipeFirstAcquisitionPipeline
  -> family-constrained concrete search
  -> RunScopedValuationSession
  -> FRESH_ONLY cache classification / atomic NEW-LIVE
  -> ValuationService -> EV -> RiskFilter
  -> immutable operator report -> human/JSON
```

## Scenario matrix

| Scenario | Expected terminal / evidence |
|---|---|
| Missing explicit enable | `CONFIGURATION_BLOCKED`, exit 3, zero factories |
| Preview | `SUCCESS_PREVIEW`, exit 0, zero SteamDT/BUFF/cache network clients |
| Complete opportunity | `SUCCESS_OPPORTUNITIES_FOUND`, exact metrics/risk copied from downstream |
| Complete risk reject | `RISK_FILTER_REJECTED`, expected-no-opportunity group |
| No concrete selection | `NO_CONCRETE_SELECTION` |
| Strict prescreen selection failure | `PRESCREEN_INCOMPLETE`, zero BUFF |
| BUFF inputs insufficient | `BUFF_ACQUISITION_INSUFFICIENT` |
| Identity/intrinsic/metadata contradiction | `IDENTITY_INTRINSIC_METADATA_CONTRACT_FAILURE` |
| Final price incomplete | `FINAL_VALUATION_INCOMPLETE`, no metrics/risk/opportunity |
| Final one-over NEW-LIVE cap | `VALUATION_REQUEST_BUDGET_BLOCKED`, zero final provider dispatch |
| Batch fake-provider failure | `EXTERNAL_PROVIDER_FAILURE`, dispatch start consumed |
| BUFF fake-provider failure | `EXTERNAL_PROVIDER_FAILURE`, family remains locked |
| Post-lock contract failure | contract terminal, no fallback |
| Internal impossible invariant | `INTERNAL_CONTRACT_FAILURE` |
| Pre-BUFF family #2 fallback | exactly one transition, family #2 active, no recursive/third fallback |
| Post-BUFF fallback attempt | contract failure |
| Fresh FRESH_ONLY hit | cache hit, zero NEW-LIVE for cached exact name |
| Cache miss | NEW-LIVE |
| Expired | NEW-LIVE, expired counter |
| Policy-blocked stale | NEW-LIVE, policy-blocked counter |
| Cache selection failure | terminal cache selection evidence; no same-name live fallback |
| Cache backend/codec failure | infrastructure/provider terminal, no family fallback |
| Deterministic repeated fixture | byte-identical JSON after run-id/time normalization only |
| Goods-first | authoritative blobs unchanged |

## Authoritative deterministic fixture evidence

Designed Phoenix/Classified/normal fixture:

- family hash:
  `45bfd0f0d3e7405588acdcf742d980577eed4963382c2fde31632fc43db52516`.
- family states visited: 1
- feasible: 1
- infeasible: 0
- contract-failed: 0
- prescreen logical names before dedupe: 19
- unique prescreen names: 19
- chunks planned/admitted/dispatched: 2 / 2 / 2
- chunks atomically blocked: 0
- ranked retained: 1 (separate three-family fixture proves Top-2)
- targeted BUFF goods: 10
- concrete search states/selections: 1 / 1
- concrete exact outputs:
  - `AUG | Chameleon (Field-Tested)`
  - `AWP | Asiimov (Battle-Scarred)`
- final FRESH_ONLY/cache/live classification is recorded in report counters
- terminal: `SUCCESS_OPPORTUNITIES_FOUND` under intentionally permissive
  fixture risk thresholds
- approximate elapsed runtime of the authoritative deterministic
  fixture build is ~0.20 seconds in this environment; no portable memory
  high-water is recorded
- no production distribution or policy claim is made

The fixture has input cost CNY 1860, gross output EV CNY 1000, fee-adjusted
expected profit CNY -885.0000, and still passes only because the fixture's
risk threshold is intentionally permissive. This is structural integration
evidence, not an economically attractive opportunity claim.

## Determinism

Two identical normalized fixtures produce identical serialized report JSON
after normalizing only `run_id` (currently constant 1); family ordering,
active/fallback identity, targeted goods order, concrete outputs, prices,
probabilities, counters, terminal codes, and risk values are not normalized.

## Fallback / lock

- Ranking retains at most two families.
- Only one active family is passed downstream.
- Family #2 may replace #1 once before any BUFF dispatch starts.
- Actual raw BUFF `get_listings` entry increments dispatch-start and locks
  the family.
- After lock, provider or contract failures cannot return to ranking or
  fallback.
- No third family and no recursive fallback.

## Prescreen / final separation

- Prescreen names are exact input names plus reachable exact output names.
- All prescreen names/chunks are admitted atomically before dispatch.
- Strict batch resolver accepts one exact `platform == "BUFF"` positive sell
  record only; no bid or second-platform substitution.
- Pre-screen quotes enter only `PreScreenPriceBook` / coarse economics /
  ranking / targeted planning.
- Final exact names come from `selection.concrete_outcomes`.
- Final valuation independently passes FRESH_ONLY cache/session/strict final
  provider. Numerically equal prices still traverse independent seams.
- Missing final price is never replaced by pre-screen evidence.
- Scanner performs no cache writes.

## Final NEW-LIVE atomicity

- Exact-name prepare dedupes.
- Same exact output is requested live once per run.
- Required == remaining cap is admitted by existing session/orchestrator
  semantics.
- Required > remaining cap blocks the entire output set before final provider
  dispatch.
- Goods-first default 5 / hard 60 remains unchanged.

## Goods-first evidence

Phase17A-frozen blobs remain authoritative:

- `app/services/scanner_orchestrator.py`:
  `06bb4fe5654c72bc3540904f6982c1e0672f276d`
- `scripts/run_live_scan_once.py`:
  `e0f8773fe4b9a81c96a3b23877a07c60a6dfc871`

## Proposed Phase17D validation bounds

Every value below is a `PHASE17D_PROPOSED_VALIDATION_BOUND`, not a production
default or policy change:

- `PHASE17D_PROPOSED_VALIDATION_BOUND.max_family_states_considered = 1`
- `PHASE17D_PROPOSED_VALIDATION_BOUND.max_prescreen_names = 20`
- `PHASE17D_PROPOSED_VALIDATION_BOUND.max_prescreen_batch_dispatches = 2`
- `PHASE17D_PROPOSED_VALIDATION_BOUND.max_targeted_buff_goods_ids = 10`
- `PHASE17D_PROPOSED_VALIDATION_BOUND.max_final_new_live = 2`
- `PHASE17D_PROPOSED_VALIDATION_BOUND.total_market_dispatch_upper_bound = 14`
  (2 SteamDT batch + 10 BUFF pages + 2 SteamDT final exact-name calls)
- one operator attempt only
- actual `scripts/run_recipe_first_scan_once.py` CLI only
- zero retry / pagination / polling
- no family switch after first BUFF dispatch start

Phase17D live is NOT STARTED and requires separate explicit authorization.
Phase15C remains NOT STARTED.
