# Phase17D-R1 Prescreen Provider-Failure Offline Diagnosis

## Authority

- Evidence commit: `40af94b7b7c48dd866d2d4fab79f0aefb53be1ad`
- Pre-live authority: `3824dae8c259d2e48cc8900cd8ae07899e7f09fc`
- Authorized case SHA-256:
  `b707cf3f986283486a31fda936d9bb8b91c1d73f35b46f62c1dd20819dead21c`
- Result artifact SHA-256:
  `14bd3f2d13610bda49ef195cb2b9bd589b6cc8f62128ef3722ec2ce922726b77`
- Phase17D classification: `C INCONCLUSIVE_PROVIDER`

## Failure boundary

`OBSERVED`:

- one operator live invocation; authorization consumed
- discovery succeeded for one family
- 19 logical / 19 unique exact prescreen names
- two batch dispatch starts
- 10 selected exact names
- 9 missing exact names
- one prescreen transport error
- terminal group/code:
  `incomplete_or_provider / EXTERNAL_PROVIDER_FAILURE`
- safe code: `PRESCREEN_PROVIDER_FAILURE`
- zero BUFF dispatch, zero final NEW-LIVE, zero evaluations, zero opportunities
- no second live invocation

`DERIVED_FROM_CODE`:

1. `SteamDTBatchPreScreenResolver.prescreen` normalizes/deduplicates names and
   chunks them by `PRESCREEN_BATCH_CHUNK_SIZE = 10`, producing chunks of
   10 and 9.
2. `_BudgetedBatchTransport.get_price_batch_with_selection` increments
   `dispatch_started` before calling the injected SteamDT transport and
   enforces the admitted cap of 2.
3. For each chunk, `SteamDTBatchPreScreenResolver.prescreen` catches ordinary
   transport/parsing exceptions, records `type(exc).__name__`, marks the
   whole failing chunk missing, and continues without retrying it.
4. Therefore a successful first chunk plus a failing second chunk produces
   selected=10, missing=9, transport_errors=1, dispatches=2.
5. `RecipeFirstRuntimeCoordinator.run_once` sees non-empty
   `result.diagnostics.transport_errors`, appends the failed prescreen phase,
   emits safe code `PRESCREEN_PROVIDER_FAILURE`, classifies
   `EXTERNAL_PROVIDER_FAILURE`, and returns before price-book/ranking/BUFF/
   concrete/final/EV/risk stages.
6. The frozen terminal-group mapping derives expected process exit code 2;
   the actual shell exit code was not observed.

`NOT_OBSERVED`:

- specific provider cause (timeout, DNS, rate limit, HTTP status, malformed
  payload, provider outage, local socket failure, or any other subtype)
- raw provider response
- raw exception text
- shell exit code

No provider root cause is inferred beyond the observed safe class
`PRESCREEN_PROVIDER_FAILURE`.

## Responsible code

- `app/services/steamdt_batch_prescreen.py`
  - `_normalise_names`
  - `_chunks`
  - `SteamDTBatchPreScreenResolver.prescreen`
- `app/services/recipe_first_runtime_coordinator.py`
  - `_BudgetedBatchTransport.get_price_batch_with_selection`
  - `RecipeFirstRuntimeCoordinator._run_prescreen`
  - `RecipeFirstRuntimeCoordinator.run_once`
  - `_prescreen_summary`
  - `_report`

## Offline reproduction

`tests/test_phase17d_r1_prescreen_provider_failure.py` uses an in-memory fake:

- one frozen Phoenix family
- 19 exact prescreen names
- first batch returns strict BUFF quotes for 10 exact names
- second batch raises an ordinary transport exception
- resulting terminal/counters exactly match the Phase17D boundary:
  2 dispatch starts, 10 selected, 9 missing, 1 transport error, zero BUFF,
  zero final valuation, zero evaluations/opportunities, no fallback

The focused reproduction passes with zero external HTTP.

## Diagnosis classification

`EXPECTED_FAIL_CLOSED_PROVIDER_FAILURE`

The runtime behavior matches the frozen failure contract. No deterministic
runtime defect was identified in the safely observable path:

- request budget was enforced
- the failing chunk was marked incomplete
- no retry occurred
- no prescreen evidence was reused as final valuation
- BUFF and downstream stages were not entered
- a safe provider terminal was emitted

## New live-case recommendation

A new separately frozen and explicitly authorized live case may be technically
justified if the operator wants additional provider-interface evidence. That is
not a retry under this consumed authorization and must have a new case SHA,
new pre-live authority, explicit authorization, and the one-shot secret-handoff
standard. This diagnosis alone grants no live authorization.

## Network and safety

- SteamDT HTTP during diagnosis: 0
- BUFF HTTP during diagnosis: 0
- secret access during diagnosis: 0
- original evidence file unchanged
- runtime/provider/CLI source unchanged
- Phase17D authorization remains consumed and closed
- production recipe-first default remains OFF
- Phase15C remains NOT_STARTED
