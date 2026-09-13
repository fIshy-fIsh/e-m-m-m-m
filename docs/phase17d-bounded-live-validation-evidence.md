# Phase17D — Bounded Live Validation Evidence

## Status

`PHASE17D_ACTUAL_CLI_BOUNDED_LIVE_INCONCLUSIVE_PROVIDER`

## Authorization

- Authorized case SHA-256:
  `b707cf3f986283486a31fda936d9bb8b91c1d73f35b46f62c1dd20819dead21c`
- Pre-live authority commit: `3824dae8c259d2e48cc8900cd8ae07899e7f09fc`
  (`freeze phase17d bounded live recipe-first case`)
- Branch: `feature/recipe-first-runtime-bounded-live-validation-r1`
- Operator live invocation count: exactly 1
- Authorization consumed: YES
- Actual CLI invoked: operator-facing
  `scripts/run_recipe_first_scan_once.py`
- Second live invocation: NO

## Outcome

- process completion: phase17b_execute: complete (process exit code 0)
- terminal_group: `incomplete_or_provider`
- terminal_code: `EXTERNAL_PROVIDER_FAILURE`
- acceptance class: `C INCONCLUSIVE_PROVIDER`
- safe_error_codes: `['PRESCREEN_PROVIDER_FAILURE']`
- incompleteness_flags: `['EXTERNAL_PROVIDER_FAILURE']`
- market_io_executed: yes (one operator invocation only)

Observed phases:

1. `discovery`: ok
   - visited=1 feasible=1 infeasible=0 contract_failed=0
2. `prescreen`: failed
   - dispatches=2 transport_errors=1

Observed prescreen quotes (10 exact names):

- AK-47 | Redline (Battle-Scarred)
- AK-47 | Redline (Field-Tested)
- AK-47 | Redline (Minimal Wear)
- AK-47 | Redline (Well-Worn)
- Nova | Antique (Factory New)
- Nova | Antique (Field-Tested)
- Nova | Antique (Minimal Wear)
- P90 | Trigon (Battle-Scarred)
- P90 | Trigon (Field-Tested)
- P90 | Trigon (Minimal Wear)

Observed prescreen missing (9 exact names):

- P90 | Trigon (Well-Worn)
- AUG | Chameleon (Factory New)
- AUG | Chameleon (Minimal Wear)
- AUG | Chameleon (Field-Tested)
- AUG | Chameleon (Well-Worn)
- AUG | Chameleon (Battle-Scarred)
- AWP | Asiimov (Field-Tested)
- AWP | Asiimov (Well-Worn)
- AWP | Asiimov (Battle-Scarred)

## Structural family scope (one in-scope family)

- collection: The Phoenix Collection
- input rarity: Classified
- StatTrak CLI spelling: normal
- family key: 45bfd0f0d3e7405588acdcf7
- family hash: 45bfd0f0d3e7405588acdcf742d980577eed4963382c2fde31632fc43db52516

## Discovery

- families_visited: 1
- families_infeasible: 0
- families_contract_failed: 0
- families_ranked_retained: 0 (incomplete downstream)

## Prescreen

- logical_requested: 19
- unique_after_dedupe: 19
- attempted: 19
- dispatch_started: 2
- succeeded: 10
- missing: 9
- terminal_selection_failures: 0
- transport_error_count: 1
- atomic block: 0

## BUFF and final / EV / risk

- buff_attempted: 0
- buff_dispatch_started: 0
- buff_succeeded: 0
- buff_provider_failure: 0
- live_demand: 0
- live_attempted: 0
- live_succeeded: 0
- live_failed: 0
- evaluations_total: 0
- evaluations_budget_blocked: 0
- opportunities_found: 0
- fallback_family_used: false

## Market request accounting (single observation)

| Provider | Type | Dispatch starts |
|---|---|---|
| SteamDT batch | prescreen | 2 |
| SteamDT single | final NEW-LIVE | 0 |
| BUFF | targeted page | 0 |
| **Total observed** | | **2** |

Frozen caps held:

- family states: 1 ≤ 1
- prescreen batches: 2 ≤ 2
- BUFF targeted: 0 ≤ 10
- final NEW-LIVE: 0 ≤ 2
- total market dispatch starts: 2 ≤ 14

## Resource and process policy

- retried live invocation: 0
- paginated: 0
- polled: 0
- second CLI invocation: 0
- recursive fallback: 0
- post-BUFF family switch: 0
- auto-buy / auto-trade: 0
- raw Traceback string in artifact: False

## Result artifact

- Path: `C:\Users\lijie\AppData\Local\Temp\cs2-phase17d\phase17b_result.json`
- Size: 4204 bytes
- SHA-256: `14bd3f2d13610bda49ef195cb2b9bd589b6cc8f62128ef3722ec2ce922726b77`
- Safety audit result: PASS
  - API keys / secrets: none observed
  - Authorization headers / cookies: none observed
  - raw provider payloads: none observed
  - seller / account identifiers: none observed
  - listing IDs / asset IDs: none observed
  - webhook values: none observed
  - raw sensitive exception text: none observed
  - the full artifact was not pasted into this document

## Case binding (unchanged)

- Case path: `C:\Users\lijie\AppData\Local\Temp\cs2-phase17d\phase17d_case.json`
- Case SHA-256 (recomputed from current bytes):
  `b707cf3f986283486a31fda936d9bb8b91c1d73f35b46f62c1dd20819dead21c`
- Case repository_commit_oid: `3824dae8c259d2e48cc8900cd8ae07899e7f09fc`
- The case file was not modified by this round.

## Snapshot digests (recomputed for this evidence)

- `data/identity/buff_identity_v1.json`:
  `e3aab46d570869e0b6866eac44b26bca7492ea7c2c54669e74b2b4feeec506ac`
- `data/metadata/skin_metadata_v1.json`:
  `55e4d446a5343e1932f24b9069090431f87b0c750d2cb4c091947ec2411dc421`

## Acceptance classification rationale

Per the frozen Phase17D acceptance policy this run classifies as:

```text
C INCONCLUSIVE_PROVIDER
```

because the actual CLI launched, market I/O executed, discovery completed
correctly, both allowed prescreen batch dispatches were used, one prescreen
transport error occurred, the prescreen was incomplete, and the ranking/BUFF
concrete/final valuation/EV/risk stages did not run. No contract or budget
violation is shown by the observed counters, so this is not `D`. The success
classes `A` and `B` do not apply because the final valuation was never reached.

## Production state

- Recipe-first production default: `OFF`
- Goods-first path: unchanged (blob identities still
  `06bb4fe5654c72bc3540904f6982c1e0672f276d` and
  `e0f8773fe4b9a81c96a3b23877a07c60a6dfc871`)
- Phase15C representative campaign: `NOT_STARTED`

## Profitability / economic-attractiveness

No claim of economic attractiveness is made. Phase17D is a bounded live
interface and path-correctness validation only. The prescreen transport
failure prevented any final quote, so there is no resolved EV / ROI / risk
result to interpret.

## Phase17D live-status tokens

```text
PHASE17D_ACTUAL_CLI_BOUNDED_LIVE_INCONCLUSIVE_PROVIDER
```
