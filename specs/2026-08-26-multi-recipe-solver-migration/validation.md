# Phase 13T — Multi-Recipe Solver Migration Design / Protected-Core Audit Validation

## Validation strategy

Phase 13T uses static audit gates only. It does not run the application, make network requests, modify runtime/test code, or claim that the future enumerator is implemented.

## Gate 1 — Repository baseline

Run and require:

```bash
git branch --show-current
git rev-parse HEAD
git rev-parse @{u}
git rev-list --left-right --count HEAD...@{u}
git status --short
```

Expected baseline:

```text
branch:   feature/steamdt-cache-rate-limit
HEAD:     d161ec43d47644751f874e85f796889506f0051a
upstream: d161ec43d47644751f874e85f796889506f0051a
ahead/behind: 0 0
```

Before design files are created, only these local research files may appear:

```text
?? research/identity_revalidation/data/modest_serhat.json
?? research/identity_revalidation/data/timofey_ivanenko.json
```

After design files are created, the only additional entries may be the three untracked Phase 13T documents.

## Gate 2 — Spec-trilogy integrity

The directory must contain exactly:

```text
specs/2026-08-26-multi-recipe-solver-migration/requirements.md
specs/2026-08-26-multi-recipe-solver-migration/plan.md
specs/2026-08-26-multi-recipe-solver-migration/validation.md
```

All three files must agree on:

- design/audit-only status;
- Protected Core unchanged in Phase 13T;
- future Protected Core migration required;
- Option B as the sole recommendation;
- exact legacy baseline **state** explored first and called a candidate only after successful engine validation;
- legacy API and new enumerator `1/1` equivalence for both valid and rejected baseline states;
- larger-budget continuation to radius-one states after a rejected baseline;
- canonical original listing identity `(source, goods_id, listing_id)`;
- permutation/projection-invariant recipe key;
- cross-candidate listing reuse allowed;
- greedy-first radius-one substitution search;
- default limits `max_recipe_candidates_returned=2` and `max_candidate_states_explored=256`;
- hard maxima `max_recipe_candidates_returned=6` and `max_candidate_states_explored=1,024`;
- bounded generation rather than exhaustive generation plus truncation;
- scanner-domain collection/Souvenir compatibility separated from historical core rules;
- one aggregate scanner composition budget across StatTrak buckets with exact quotient/remainder candidate quotas and reserved-baseline state quotas;
- returned-depth global interleaving of successful normal/StatTrak sequences;
- duplicate eligible `(source, goods_id, listing_id)` failure in the new API before search, with legacy behavior unchanged;
- zero price/EV/ROI/risk dependence in enumeration;
- run-level exact-name cache absent and out of scope;
- no implementation, network, stage, commit, or push.

## Gate 3 — Traceability of current contract

Verify every core assertion against these exact sources:

### Solver and engine

- Config and DTOs: `app/services/recipe_solver.py:15-124`.
- Legacy call chain: `app/services/recipe_solver.py:127-241`.
- One first-ten slice and singleton return: `app/services/recipe_solver.py:144-199`.
- Eligibility/input construction: `app/services/recipe_solver.py:275-337`.
- Sort: `app/services/recipe_solver.py:341-352`.
- Collection retained-input cap: `app/services/recipe_solver.py:356-376`.
- Engine legality: `app/services/tradeup_engine.py:107-134`.
- Probability, float, merge, and output ordering: `app/services/tradeup_engine.py:65-103,138-163`.
- Metadata/output pool: `app/services/metadata_service.py:54-107`.

### Scanner boundary

- Current output eligibility and StatTrak buckets: `app/services/scanner_recipe_composition.py:34-111`.
- Original listing facts preserved in legacy conversion: `app/services/scanner_recipe_composition.py:255-273`.
- Exact per-selection rehydration: `app/services/scanner_recipe_composition.py:275-312`.
- Duplicate listing protections: `app/services/scanner_recipe_composition.py:133-157`, `app/services/scanner_orchestrator.py:378-382`.
- Multi-selection valuation loop and request budget: `app/services/scanner_orchestrator.py:383-512`.
- Per-recipe output-name dedupe: `app/services/scanner_orchestrator.py:596-605`.

### Alternate callers and compatibility

- Disjoint SteamApis live construction: `app/services/live_recipe_construction.py:71-101,105-182`.
- Disjoint live valuation result: `app/services/live_recipe_valuation.py:133-165,168-230`.
- Deterministic one-recipe SteamDT fixture: `app/services/steamdt_buff_live_recipe_fixture.py:88-105,232-333`.

Any contradiction between source and design blocks Phase 13T completion.

## Gate 4 — Ceiling proof

The audit must explicitly classify the user’s A–F alternatives:

```text
A. Greedily consume exactly 10 once: YES
B. Select one optimal-looking subset: NO
C. Explicit first-valid break: NO (no enumeration loop exists)
D. Mutate/consume a working pool: NO
E. Structurally return one selection per invocation: YES
F. Combination: A + E, via straight-line singleton control flow
```

Evidence must include the one slice, one engine call, and literal one-element return. Merely citing the Phase 13S observed count is insufficient.

## Gate 5 — Candidate identity decisions

The trilogy and final report must explicitly answer:

```text
permutation duplicates: SAME
same composition / different listing IDs: DIFFERENT
one listing changed: DIFFERENT
projection duplicates: SAME
```

Acceptance:

- no deduplication on market name, collection, price, float, or current recipe hash;
- key is based on original facts;
- selected order is retained separately from identity;
- candidate-owned/provenance facts survive every composition boundary.

## Gate 6 — Combination arithmetic

Recalculate locally with Python standard library only:

```bash
python -c "import math; print([math.comb(n, 10) for n in (10, 20, 30, 50, 94, 100)])"
```

Require exactly:

```text
1
184756
30045015
10272278170
9041256841903
17310309456440
```

No web lookup is needed or permitted.

## Gate 7 — API and bounded-search design

The proposed API must contain no implementation but must include exact types for:

- `RecipeEnumerationConfig`;
- `RecipeEnumerationDiagnostics`, including `engine_rejected_states` and `baseline_state_rejected`;
- `RecipeEnumerationResult`;
- `enumerate_recipe_selections(...)`;
- unchanged `construct_recipe_selections(...)` legacy API and an explicit `1/1` equivalence requirement for eligible unique-offer inputs;

Acceptance:

1. Candidate and state limits are distinct.
2. Hard maxima are explicit.
3. The baseline state is always explored first and becomes the first returned candidate only when valid.
4. Under strict `1/1`, a valid or rejected baseline exactly matches the legacy API result.
5. With larger state budget, baseline rejection is recorded and does not prevent later radius-one exploration.
6. Radius-one state order is total and deterministic.
7. Rejected states occupy explored-state budget but no candidate slot; successful selections preserve exploration order.
8. Candidate-key duplicate suppression occurs before the engine call and is counted exactly.
9. Every unique state is validated by existing engine math.
10. Exploration stops at generation time; cap flags use known remaining-state cardinality rather than an extra probe.
11. Limit exhaustion is normal bounded completion.
12. Unexpected failures and `MemoryError` propagate under existing contracts.
13. Search does not import valuation/network/financial ranking concerns.

## Gate 8 — Integration impact completeness

The impact table must cover at least:

```text
recipe_solver.py
tradeup_engine.py
scanner_recipe_composition.py
scanner_orchestrator.py
valuation_service.py
live_recipe_construction.py
live_recipe_valuation.py
steamdt_buff_live_recipe_fixture.py
ev_service.py
risk_filter.py
run_live_scan_once.py
```

For each, record symbol, current assumption, required migration, and Protected Core status.

Acceptance:

- old disjoint SteamApis DTOs are not silently redefined as overlapping alternatives;
- scanner composition rehydrates every candidate;
- orchestrator remains valuation-budget owner;
- caching remains a separate concern;
- EV/risk/float/probability modules remain unchanged.

## Gate 9 — Aggregate bucket-budget arithmetic

For active buckets in existing order and aggregate budgets `C` and `S`, recompute:

```text
P = min(active_bucket_count, C)
candidate_quota[i] = C // P + (i < C % P)
state_quota[i] = 1 + (S-P) // P + (i < (S-P) % P)
```

Require:

```text
C=6, B=2 → candidate 3/3
C=5, B=2 → candidate 3/2
C=2, B=2 → candidate 1/1
C=1, B=2 → candidate normal 1 / StatTrak 0

C=6, S=256, P=2 → states 128/128
C=5, S=255, P=2 → states 128/127
C=2, S=3,   P=2 → states 2/1
C=1, S=256, P=1 → states normal 256 / StatTrak 0
```

Acceptance:

- only first `P` active buckets participate;
- every participant receives at least one baseline state;
- each state quota is at least its candidate quota;
- quota sums do not exceed aggregates and actual usage may be smaller;
- no quota stealing, second pass, or financial feedback;
- global returned order places successful baseline candidates at structural depth 0 and successful alternatives at depth 1 onward, using baseline rejection diagnostics so a first returned alternative is not misclassified as a baseline.

## Gate 10 — Duplicate exact offer boundary

For the new enumerator only, require:

- canonical key is exactly `(source, goods_id, listing_id)`;
- duplicate eligible canonical key raises exact `ValueError("duplicate recipe offer identity")` after eligibility but before sorting/capping/search;
- no silent deduplication and no duplicate key in any returned candidate;
- same textual `listing_id` with genuinely different source or goods ID is not a duplicate unless the full tuple matches;
- legacy `construct_recipe_selections(...)` behavior remains unchanged.

## Gate 11 — Future test matrix completeness

The future Phase 13T-1 through 13T-4 matrix must cover:

- exact legacy result under `1/1` limits for both valid and engine-rejected baseline states;
- larger-budget continuation and later valid alternative after baseline rejection;
- multiple deterministic candidates from one bucket;
- permutation dedupe;
- different listing IDs preserved;
- one-listing difference preserved;
- duplicate eligible `RecipeListingKey` fails closed in the new API before search;
- same textual listing ID under different source/goods identity follows the full canonical tuple;
- every returned candidate has exactly ten distinct canonical offer keys;
- explicit cross-candidate listing reuse;
- no duplicate listing within one candidate;
- no StatTrak mixing;
- current normal/Souvenir composition;
- exact projection rehydration for every candidate;
- mixed collections and unchanged probabilities;
- unchanged float validation/math;
- candidate hard limit;
- state hard limit;
- deterministic ordered results and diagnostics;
- same input producing value-identical output;
- `MemoryError` identity;
- 10/30/50/94/100/100+ pool sizes;
- no exhaustive combination materialization;
- one aggregate normal/StatTrak budget with exact fair-split quotas and no redistribution;
- returned-depth interleaving of successful bucket sequences;
- cumulative valuation budget and no partial lookup.

Historical one-result tests must be classified as either unchanged (exact-ten and legacy API) or generalized/supplemented (larger pools/new API). Historical regression tests must not be weakened.

## Gate 12 — Structural scale proof

A future implementation’s primary scale proof must be structural, not wall-clock based:

1. guarded lazy state iterator fails at state-bound + 1;
2. exact diagnostics never exceed candidate/state limits;
3. no materialization of all combinations;
4. retained candidate/state/reference counts have explicit finite bounds;
5. sentinel `MemoryError` propagates by identity;
6. observed 94-input and 100+ cases run under the hard bound.

Phase 13T only documents these requirements; it does not add or run their future tests.

The existing `tests/test_synthetic_scanner_scale_validation.py` remains a candidate/enrichment seam regression, not proof of recipe-solver enumeration scale. Do not weaken it or claim otherwise.

## Gate 13 — Documentation-only diff

Run:

```bash
git diff --check
git status --short
git diff --name-only
git ls-files --others --exclude-standard
```

Acceptance:

- `git diff --check` succeeds;
- tracked diff is empty because all three design files are new/untracked;
- no path under `app/`, `scripts/`, `tests/`, `docs/ai-context/`, or the roadmap is modified;
- the only untracked paths are the three design files plus the two pre-existing local research JSONs;
- the two research JSONs remain untouched and excluded.

Expected application-code diff:

```text
NONE
```

Expected test-code diff:

```text
NONE
```

Expected AI-context diff:

```text
NONE
```

## Gate 14 — No external activity and safety

Report exactly:

```text
BUFF requests: 0
SteamDT requests: 0
Other web/API requests: 0
```

Verify no:

- scheduler/daemon/background loop;
- automatic purchase, order, trade, login, or reservation;
- Cookie/session/credential acquisition;
- browser automation, CAPTCHA/risk-control bypass, proxy/UA rotation, or evasion;
- marketplace/database/Redis/Discord write;
- secret/config/environment modification;
- no live validation in design-only Phase 13T (the future 13T-4 live gate remains separately authorized);
- stage, commit, amend, merge, tag, or push.

## Final acceptance checklist

- [ ] Repository baseline verified before audit.
- [ ] Architecture and complete call path read.
- [ ] Current ceiling proven from code.
- [ ] Domain legality separated from greedy heuristic.
- [ ] Canonical identity and reuse semantics frozen.
- [ ] Combination counts exact.
- [ ] Option A/B/C compared; Option B chosen.
- [ ] Radius-one bounded V1 specified precisely.
- [ ] Default and hard limits explicit.
- [ ] Deterministic order explicit.
- [ ] Baseline state/result distinction and rejected-baseline continuation explicit.
- [ ] Exact candidate/state fair split and returned-depth composition order explicit.
- [ ] New-API duplicate canonical offer failure and unchanged legacy behavior explicit.
- [ ] `max=1` legacy equivalence required.
- [ ] Float/probability/current Souvenir behavior preserved.
- [ ] StatTrak and aggregate budget ownership explicit.
- [ ] Run-level price-cache audit says `NO` and stays separate.
- [ ] Diagnostics and failure semantics measurable.
- [ ] Integration impact table complete.
- [ ] Future tests and scale proof complete.
- [ ] Design staging is audit-adjusted Phase 13T-1 through 13T-4.
- [ ] Exactly three design files created.
- [ ] No application/script/test/AI-context/roadmap diff.
- [ ] Zero network activity.
- [ ] Nothing staged, committed, or pushed.

If any item fails, final status is `PHASE_13T_BLOCKED`. Otherwise final status is `MULTI_RECIPE_MIGRATION_DESIGN_COMPLETE` with:

```text
Protected Core migration required: YES
```
