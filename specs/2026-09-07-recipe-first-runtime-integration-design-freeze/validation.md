# Phase 17A — Recipe-first Runtime Integration Design Freeze

## Validation

## 1. Phase 17A docs-only validation

Required checks:

```text
git diff --check
stale current-state consistency search
git diff --name-only 940127ff...HEAD
git status --short
```

Pass conditions:

- top-level roadmap and AI-context current phase no longer claim Phase15B;
- current completed authority is Phase16G-R7;
- next/active docs-only authority is Phase17A;
- no new Phase16G live authorization is implied;
- history sections retain Phase15/16 facts;
- changed paths are docs/spec/current-context only;
- no `app/**`, `scripts/**`, `tests/**`, dependency, data, or workflow change;
- protected untracked JSONs remain untouched;
- no `.env` or credentials accessed;
- SteamDT HTTP = 0; BUFF HTTP = 0.

Repository convention still permits full offline quality gates on docs-only
changes. If run, record ruff/mypy/pytest exactly.

## 2. Phase 17B unit matrix (future, zero network)

### Entrypoint/config

- no enable flag -> `CONFIGURATION_BLOCKED`, no client construction;
- explicit enable + invalid secrets/config -> fail before provider construction;
- preview -> `SUCCESS_PREVIEW`, zero SteamDT/BUFF/provider construction;
- one-shot exits after one report; no loop/scheduler path;
- human and JSON render the same service DTO;
- existing `scripts/run_live_scan_once.py` behavior/defaults unchanged;
- no Phase16G harness import.

### Family/discovery

- identical pinned inputs produce identical family order/hash/geometry;
- discovery respects explicit state bound without eager full-space materialization;
- unsupported rarity/mode/collection fails before prescreen;
- geometry hash/finish identity/probability sum mismatch fails closed;
- exact float feasibility prunes impossible family without market I/O;
- opaque SteamDT `update_time` is not parsed or ranked.

### Prescreen

- exact-name dedupe is stable and ordered;
- deterministic chunking uses existing chunk size 10;
- batch budget admitted before first dispatch;
- missing/unusable/duplicate strict BUFF records are terminal prescreen evidence;
- no bid/second-platform/lowest-platform fallback;
- dispatch-start charged on transport/parsing/selection failure;
- prescreen quote never enters final memo/cache/provider result.

### Ranking/planning/fallback

- economics use exact Decimal/Fraction authorities;
- streaming rank is deterministic and returns <=2;
- one active family only;
- family #2 may be selected only before BUFF dispatch starts;
- after one BUFF dispatch start, every fallback attempt is contract failure;
- contract bug never triggers fallback;
- no third family or recursive fallback;
- exact identity failure has stable terminal class;
- targeted goods IDs remain <=10.

### Final downstream

- real `RecipeFirstScannerOrchestrator` receives one active decision;
- real acquisition/enrichment/concrete search/session/valuation/EV/risk is used;
- concrete enumeration bounds obey `RecipeEnumerationConfig`;
- FRESH_ONLY exact-name cache hit avoids NEW LIVE demand;
- miss/expired/policy-blocked classifications follow existing contracts;
- duplicate output exact names issue no duplicate NEW LIVE call;
- final request set admitted atomically; one-over cap dispatches zero;
- structural output name/probability/float/wear unchanged after valuation;
- final missing price creates no metrics/risk/opportunity;
- risk reject is expected no-opportunity, not provider/contract failure.

### Report/safety

- selected/ranked family, targeted goods, input summary, concrete outputs,
  final quotes, EV/ROI/profit probability/worst-case/risk, counters and flags
  are present;
- report values equal existing service DTOs; no recomputation;
- no API key, Authorization, cookie, raw payload, seller/account, webhook,
  secret, listing ID, or asset ID in normal output;
- safe error codes do not contain raw upstream exception text.

## 3. Phase 17C offline end-to-end acceptance (future)

Run the actual future CLI with external market seams faked. Required scenarios:

1. Preview success, zero providers.
2. Full opportunity passes risk.
3. Full complete evaluation rejected by risk.
4. No concrete selection.
5. Prescreen incomplete.
6. BUFF acquisition insufficient.
7. Identity/intrinsic/metadata contract failure.
8. Final valuation incomplete.
9. Final NEW-LIVE atomic budget block.
10. SteamDT batch provider failure.
11. BUFF provider failure before/after lock.
12. Final SteamDT provider failure.
13. Internal invariant failure.
14. Pre-BUFF family #2 fallback success.
15. Attempted fallback after BUFF dispatch -> contract failure.
16. FRESH_ONLY cache selected/miss/expired/policy-blocked/selection-failure.
17. Deterministic repeat with byte-identical JSON after normalizing run ID/time.
18. Goods-first regression suite unchanged.

Record exact logical/attempted/dispatch-start/success/failure/blocked counters by
phase. Prove no path exceeds configured/hard caps.

## 4. Future Phase 17D bounded-live acceptance

Phase 17D requires a separately approved live spec. At minimum freeze before
execution:

- exact pre-live Git commit and CI success;
- exact pinned identity/metadata snapshot digests;
- exact CLI arguments/config identity excluding secrets;
- discovery and prescreen bounds derived from Phase17C evidence;
- BUFF hard cap <=10;
- final NEW-LIVE cap <=60 and explicit value;
- no retry/pagination/polling;
- safe result artifact path/schema/digest policy;
- operator manual execution command and no-auto-rerun rule.

The one run is accepted only if the **actual operator-facing recipe-first CLI**
(not Phase16G harness) proves:

1. runtime mode/enablement and repository identity;
2. deterministic discovery/feasibility/ranking evidence;
3. exact one-active-family/fallback state;
4. bounded targeted BUFF acquisition and normalized input facts;
5. real family-constrained concrete selection;
6. exact structural outputs and preserved fields;
7. final strict BUFF valuation with no prescreen substitution;
8. existing EV/ROI/profit probability/worst-case/risk result;
9. complete operator report and correct terminal/exit code;
10. all dispatch-start counters and caps;
11. no secret/raw/seller/account/listing/asset leakage;
12. production goods-first/default remained unchanged.

A provider/incomplete/contract failure does not become validated and does not
authorize a retry.

## 5. Evidence required before Phase 17E default decision

- Phase17B implementation CI green;
- Phase17C full offline matrix and measurement artifact;
- Phase17D actual-runtime bounded-live result and exact CI;
- comparison against goods-first default behavior;
- rollback plan and config/default diff;
- explicit decision record choosing goods-first, recipe-first, or dual-mode.

No default cutover from interface validation alone.

## 6. Evidence required before Phase 17F/Phase15C re-entry

- runtime architecture stable after Phase17E decision;
- side-by-side protocol frozen;
- matched windows and pinned snapshots/policies;
- independent per-arm budgets/cache/run state/artifacts;
- safe request-frequency and rate-limit review;
- campaign stop rules and operational monitoring;
- separately authorized 14-day execution.

## 7. Success token

```text
PHASE17A_RECIPE_FIRST_RUNTIME_INTEGRATION_DESIGN_FROZEN
```
