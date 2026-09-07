# Phase 17A — Recipe-first Runtime Integration Design Freeze

## Design

## 1. Design decision

Phase 17A freezes a **separate recipe-first one-shot CLI**:

```text
scripts/run_recipe_first_scan_once.py
```

It does not add a mode, flag, or subcommand to
`scripts/run_live_scan_once.py`.

Rationale:

- preserves the goods-first production entrypoint and defaults;
- isolates config, failure state, and reports during the first integration;
- makes accidental cutover harder;
- permits explicit goods-first vs recipe-first comparison;
- keeps unit/integration tests small and deterministic;
- avoids branching the already mature goods-first composition;
- still permits reuse of settings/cache/client construction helpers by
  extracting neutral helpers later if Phase 17B proves that necessary.

The separate script is not a second implementation of downstream logic. It is
an operator composition root over existing services.

## 2. Code audit and actual authority map

The requested audit names `recipe_first_economics.py` and
`recipe_first_ranking.py`; neither file exists. Actual authorities are:

| Concern | Existing authority | Phase 17 use |
|---|---|---|
| Family identity/generation | `app/services/recipe_family.py` | Reuse lazy deterministic generation and `build_recipe_family` |
| Finish identity | `app/services/structural_output_finish.py` | Build from pinned `SkinMetadata` |
| Geometry | `app/services/recipe_family_geometry.py` | Reuse exact finish-level `Fraction` probabilities |
| Float feasibility | `app/services/static_float_feasibility.py` | Reuse exact interval-union/reachable wear evidence |
| Batch prescreen | `app/services/steamdt_batch_prescreen.py` | Reuse strict BUFF-only selection and chunking |
| Prescreen price book | `app/services/prescreen_price_book.py` | Reuse immutable exact-name input/output evidence |
| Prescreen economics | `app/services/recipe_family_prescreen_economics.py` | Reuse Decimal/Fraction optimistic/base/conservative scenarios |
| Ranking | `app/services/recipe_family_ranking.py` | Reuse deterministic streaming Top-2 |
| Targeted plan | `app/services/targeted_buff_scan_plan.py` | Reuse exact identity mapping, active/fallback decision, hard cap 10 |
| BUFF transport/parser | `app/clients/buff_anonymous_listing_client.py`, `app/services/buff_listing_provider.py` | Reuse anonymous page-1/default-sort read-only path |
| Acquisition/enrichment | `app/services/recipe_first_acquisition.py` | Reuse identity/intrinsic/candidate/metadata composition |
| Concrete results | `app/services/family_concrete_tradeup_results.py` | Reuse finish-level outputs, canonical float/wear mapping |
| Concrete search | `app/services/family_constrained_concrete_search.py` | Reuse family-quota-preserving bounded search |
| Recipe-first downstream orchestration | `app/services/recipe_first_scanner_orchestrator.py` | Reuse targeted acquisition through EV/risk; enabled explicitly |
| Final session | `app/services/scanner_valuation_session.py` | Reuse memo/FRESH_ONLY/atomic NEW-LIVE admission |
| Final strict valuation | `app/services/steamdt_buff_price_provider.py`, `app/services/valuation_service.py` | Reuse exact BUFF sell path and valuation-only field replacement |
| Existing cache seam | `app/services/scanner_cached_buff_price_resolver.py`, `app/services/price_cache_factory.py` | Reuse strict FRESH_ONLY reads; no writes |
| EV/risk | `app/services/ev_service.py`, `app/services/risk_filter.py` | Reuse unchanged |
| Goods-first production | `app/services/scanner_orchestrator.py`, `scripts/run_live_scan_once.py` | Preserve unchanged/default |
| Phase 16G evidence harness | `app/services/recipe_first_steamdt_live_runner.py`, `scripts/run_live_recipe_first_steamdt_validation.py` | Evidence only; never import into production runtime |

Relevant tests already cover:

- recipe-first prescreen integration:
  `tests/test_recipe_first_prescreen_offline_integration.py`;
- targeted planner/ranking/economics modules;
- acquisition and recipe-first orchestrator:
  `tests/test_recipe_first_acquisition.py`,
  `tests/test_recipe_first_scanner_orchestrator.py`;
- family-constrained search and concrete results;
- run-scoped valuation/cache/atomic budget:
  `tests/test_scanner_valuation_session.py`;
- goods-first production and CLI:
  `tests/test_scanner_orchestrator.py`, `tests/test_run_live_scan_once.py`;
- Phase 16G real internal path with external seams faked and bounded-live
  artifact evidence.

## 3. Component diagram

```text
┌─────────────────────────────────────────────────────────────────────┐
│ scripts/run_recipe_first_scan_once.py                              │
│ one-shot composition root; explicit recipe-first + enable gate     │
└──────────────┬──────────────────────────────────────────────────────┘
               │ pinned snapshots + validated runtime config
               v
┌───────────────────────┐     ┌──────────────────────────────────────┐
│ RecipeFamily discovery│────>│ StructuralOutputFinishIndex          │
│ (lazy/streaming)       │     │ + RecipeFamilyGeometry              │
└──────────────┬────────┘     └──────────────────────────────────────┘
               │ family + geometry
               v
┌─────────────────────────────────────────────────────────────────────┐
│ StaticFloatFeasibility -> exact wear names -> batch request plan    │
└──────────────┬──────────────────────────────────────────────────────┘
               │ one or more admitted deterministic chunks
               v
┌─────────────────────────────────────────────────────────────────────┐
│ SteamDTBatchPreScreenResolver -> PrescreenPriceBook                 │
│ approximate strict-BUFF evidence only; never final valuation        │
└──────────────┬──────────────────────────────────────────────────────┘
               │
               v
┌─────────────────────────────────────────────────────────────────────┐
│ RecipeFamilyPreScreenEconomics -> deterministic Top-2 ranking       │
│ -> TargetedBuffScanDecision (one active; fallback candidate only)   │
└──────────────┬──────────────────────────────────────────────────────┘
               │ pre-BUFF state machine
               v
┌─────────────────────────────────────────────────────────────────────┐
│ RecipeFirstScannerOrchestrator (enabled=True only in explicit CLI)  │
│ ExistingRecipeFirstAcquisitionPipeline                              │
│ -> search_family_constrained_recipes                                │
│ -> fresh RunScopedValuationSession                                  │
│    memo -> FRESH_ONLY cache -> atomic NEW LIVE                      │
│ -> ValuationService -> EV -> risk                                   │
└──────────────┬──────────────────────────────────────────────────────┘
               │
               v
┌─────────────────────────────────────────────────────────────────────┐
│ RecipeFirstOperatorRunReport -> human summary or JSON               │
└─────────────────────────────────────────────────────────────────────┘
```

## 4. Front-half ownership

Phase 17B needs a new runtime composition service above the current
`RecipeFirstScannerOrchestrator`. The concrete name is not frozen; suggested
name: `RecipeFirstRuntimeCoordinator`.

It owns only:

1. invocation/config validation;
2. family discovery stream and bounded candidate admission;
3. static geometry/feasibility;
4. batch prescreen planning/admission;
5. prescreen economics/ranking;
6. active/fallback pre-BUFF state;
7. invoking the existing downstream orchestrator once;
8. translating service results into one operator report.

It MUST NOT own or copy:

- float/probability/trade-up math;
- listing parsing/normalization;
- family-constrained concrete search;
- final price selection;
- valuation field replacement;
- EV/ROI/profit probability/worst-case math;
- risk policy evaluation.

## 5. Runtime state machine and fallback

```text
CONFIG_VALIDATED
  -> FAMILY_DISCOVERY_COMPLETE
  -> PRESCREEN_PLAN_ADMITTED
  -> PRESCREEN_COMPLETE
  -> RANKING_COMPLETE
  -> ACTIVE_PLAN_PREPARED
      ├─ expected pre-BUFF unusable active plan
      │    and fallback candidate exists
      │    and buff_dispatch_started == 0
      │       -> FALLBACK_SELECTED -> ACTIVE_PLAN_PREPARED
      └─ otherwise
           -> BUFF_LOCKED
                -> ACQUISITION_COMPLETE
                -> CONCRETE_SEARCH_COMPLETE
                -> FINAL_VALUATION_COMPLETE
                -> RISK_COMPLETE
                -> REPORTED
```

State invariants:

- `buff_dispatch_started` is monotonic.
- `active_family_key` may change at most once and only before
  `BUFF_LOCKED`.
- A contract failure transitions directly to terminal contract failure.
- Provider failure after BUFF lock cannot transition back to ranking or
  fallback.
- The downstream orchestrator receives one exact `TargetedBuffScanDecision`,
  family, and matching geometry.

The existing `RecipeFirstScannerOrchestrator` deliberately never activates
fallback. Therefore the coordinator resolves pre-BUFF fallback first, then
passes one active plan to the orchestrator. This preserves the orchestrator's
single-family contract.

## 6. Discovery and ranking boundary

A production one-shot cannot materialize the full K<=3 family space. Family
generation remains lazy and deterministic. Phase 17B/C must define an explicit
bounded discovery input/window using existing project structures; no eager
~9.97M-state list.

Phase 17A does not freeze a new numerical family-enumeration budget. Phase 17C
must measure:

- families visited;
- families statically feasible/infeasible;
- exact prescreen names before/after dedupe;
- batch chunks admitted/blocked;
- ranked families retained;
- elapsed offline computation and memory high-water evidence.

Any Phase 17B placeholder default must be conservative, explicit, bounded,
and not presented as an evidence-based production optimum.

Ranking remains the existing seven-key deterministic streaming Top-2 authority.
SteamDT `update_time` stays opaque diagnostics and is not parsed/ranked as
freshness.

## 7. Prescreen vs final valuation

```text
PRESCREEN
  purpose: approximate ranking/pruning
  source: strict BUFF record selected from batch response
  DTO: SteamDTBatchPreScreenQuote / PrescreenPriceBook
  may create OpportunityMetrics? NO
  may run RiskFilterConfig? NO
  may seed final memo/cache? NO
  missing/unusable identity: fail/incomplete ranking evidence

FINAL
  purpose: exact valuation of actual concrete output names
  source: FRESH_ONLY strict cache read, then strict live SteamDT-BUFF
  DTO: PriceQuote -> ValuationService -> TradeupResult
  may create OpportunityMetrics? YES, after complete valuation
  may run RiskFilterConfig? YES
  missing/unusable identity: valuation incomplete, no opportunity
```

No prescreen price is accepted because it equals a later final price; it must
cross the final authority independently.

## 8. Cache ownership

Chosen contract: existing scanner-owned `FRESH_ONLY` persistent read seam.

- The CLI creates a cache runtime using the existing factory composition.
- In-memory is default; Redis is explicit and optional.
- The scanner receives only `ScannerCachedBuffPriceResolver`.
- The session alone decides memo/cache/NEW-LIVE classification.
- Cache-selected records rerun the strict BUFF selector.
- No scanner writeback and no prescreen-to-cache write.
- Cache backend/codec errors are infrastructure failures; they do not silently
  become live candidates unless the existing frozen contract explicitly says
  MISS/EXPIRED/POLICY_BLOCKED.

## 9. Budget ownership and accounting

A proposed Phase 17 service-level `RecipeFirstRuntimeBudgets` DTO owns distinct
fields; the name is not frozen, separation is:

```text
max_family_states_considered          # new; undecided until 17C
max_prescreen_names                   # new; undecided until 17C
max_prescreen_batch_dispatches        # new; undecided until 17C
max_targeted_buff_goods_ids           # <= existing hard 10
max_concrete_candidates_returned      # reuse RecipeEnumerationConfig
max_concrete_states_explored          # reuse RecipeEnumerationConfig
max_final_new_live_names              # existing range 1..60; default 5 unchanged
```

Counters are phase-local and aggregate into the report:

- logical requested;
- unique after dedupe;
- cache/memo classification where applicable;
- attempted;
- provider dispatch started;
- succeeded;
- missing/selection failed/transport failed;
- atomically blocked.

A provider dispatch started consumes budget even if response, parsing,
selection, or identity validation fails. There is no automatic retry in the
Phase 17B/C composition.

## 10. Config contract

Suggested future DTOs (field semantics frozen, names may be refined):

```python
@dataclass(frozen=True, kw_only=True)
class RecipeFirstRuntimeConfig:
    enabled: bool = False
    preview: bool = False
    stattrak_modes: tuple[StatTrakMode, ...]
    input_rarities: tuple[str, ...]
    collection_allowlist: tuple[str, ...]
    max_targeted_buff_goods_ids: int
    max_final_valuation_requests: int
    enumeration_config: RecipeEnumerationConfig
    cache_backend: str
    output_format: Literal["human", "json"]

@dataclass(frozen=True, kw_only=True)
class RecipeFirstDiscoveryBudget:
    max_family_states_considered: int
    max_prescreen_names: int
    max_prescreen_batch_dispatches: int
```

The first DTO reuses existing validated bounds. The second requires Phase 17C
measurement before any numeric policy claim. Settings continue to own secrets;
CLI arguments do not accept credentials.

## 11. Terminal model

Service terminal DTO:

```text
RecipeFirstRuntimeTerminalGroup:
  success
  expected_no_opportunity
  incomplete_or_provider
  contract_or_configuration

RecipeFirstRuntimeTerminalCode:
  SUCCESS_OPPORTUNITIES_FOUND
  SUCCESS_NO_QUALIFYING_OPPORTUNITY
  SUCCESS_PREVIEW
  NO_CONCRETE_SELECTION
  RISK_FILTER_REJECTED
  PRESCREEN_INCOMPLETE
  BUFF_ACQUISITION_INSUFFICIENT
  FINAL_VALUATION_INCOMPLETE
  VALUATION_REQUEST_BUDGET_BLOCKED
  EXTERNAL_PROVIDER_FAILURE
  CONFIGURATION_BLOCKED
  IDENTITY_INTRINSIC_METADATA_CONTRACT_FAILURE
  INTERNAL_CONTRACT_FAILURE
```

The report carries phase and stable bounded reasons. Human rendering can group
codes; JSON keeps the exact code. Exit policy: success/expected-no-opportunity
0, incomplete/provider 2, contract/config 3. Process interruption is not
translated.

## 12. Report DTO boundary

The new report wraps existing immutable evidence rather than exposing raw
provider DTOs. It contains:

```text
mode / run ID / timestamps / terminal group+code
snapshots/config/budget identity (non-secret)
ranked families and scenario economics
active/fallback decision and state transition
selected family identity
active targeted goods exact names/IDs
aggregate acquisition and provenance-safe concrete input summary
concrete outputs and structural fields
final exact quotes and sources
OpportunityMetrics
RiskDecision / rejection reason
phase-local and aggregate request counters
incompleteness flags / safe error codes
```

Normal operator output omits listing IDs and asset IDs. A future explicit audit
artifact may retain normalized provenance only under a separately frozen data
policy; Phase 17A does not authorize it.

## 13. CLI composition details

The new script should mirror mature patterns from `run_live_scan_once.py`:

- `argparse` for explicit bounded structural options;
- `pydantic-settings` for environment-owned secrets/risk/cache policy;
- validate all config before constructing clients;
- `AsyncExitStack` for HTTP/cache resources;
- pinned identity and metadata resolvers;
- explicit strict `SteamDTBuffPriceProvider` and
  `ScannerCachedBuffPriceResolver`;
- one coroutine invocation and deterministic close;
- human/JSON renderers over service result only.

Do not import Phase 16G runner/case/script. Phase 16G's validated facts become
acceptance criteria for the real runtime, not production dependencies.

## 14. Migration compatibility

- `scripts/run_live_scan_once.py` remains the production/default entrypoint.
- `LiveScannerOrchestrator` remains unchanged.
- New recipe-first CLI is explicit and default-disabled.
- `RecipeFirstScannerOrchestrator.config.enabled=False` remains its service
  default; only validated new CLI composition passes `enabled=True`.
- The goods-first default valuation budget remains 5 and hard max 60.
- The legacy wear-row path remains isolated to goods-first and deferred under
  `D-TRADEUP-WEAR-ROW-MIGRATION-001`.
- No API, scheduler, Discord, Redis requirement, or database migration.
- Current Windows/Python one-shot invocation is sufficient for Phase 17B–D;
  Docker/Linux packaging is deferred operations work.

## 15. Phase 15C re-entry design

After Phase 17D only, Phase 17F uses a controlled side-by-side design:

```text
same observation windows + pinned snapshots/policy versions
  ├─ goods-first one-shot arm (independent budgets/cache/run artifacts)
  └─ recipe-first one-shot arm (independent budgets/cache/run artifacts)
```

Compare structural coverage, requested/unique/cache/live names, BUFF pages,
provider dispatch, complete evaluations, risk outcomes, and reportable
opportunities. Do not share state or let one arm consume the other's budget.
No campaign starts in Phase 17A/B/C/D.

## 16. Security and observability

- No credentials, cookies, auth headers, raw upstream payloads, seller/account
  details, or webhook values in reports/logs.
- Safe provider failures include phase, provider class, and stable reason code;
  raw exception payloads are excluded from normal output.
- Request counters mean dispatch start, not quote success.
- No auto-buy/trade/login/browser action exists in the component graph.
