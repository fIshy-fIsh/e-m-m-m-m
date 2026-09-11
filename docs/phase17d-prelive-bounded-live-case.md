# Phase 17D-A-R1 Pre-live Bounded Live Case Evidence

## Status

`PHASE17D_A_R1_PRELIVE_CASE_FROZEN`

This round is PRE-LIVE ONLY. No SteamDT/BUFF/market HTTP request was issued.

## Repaired authority

- Repository: `fIshy-fIsh/e-m-m-m-m`
- Phase17C-R1 commit: `e2ffe97443a54e329242d0e5147d1be1898ab537`
- Phase17C-R1 CI: run `34349207729` — SUCCESS
- Phase17C-R1 exact CI pytest: `3774 passed, 23 skipped, 2 warnings in 63.67s`

The previous Phase17D-A attempt was blocked because `collection_allowlist` was applied after family-state visitation, causing the one-state budget to be consumed by an out-of-scope family. Phase17C-R1 repaired the semantics.

## Reconfirmed structural precondition

Configured scope:

```text
input rarity:        Classified
StatTrak mode:        normal
collection allowlist: The Phoenix Collection
max_family_states:   1
```

Offline pure result:

```text
families_visited:   1
infeasible:         0
contract_failed:    0
first/only in-scope family:
  collection_counts: (("The Phoenix Collection", 10),)
  family_key:        45bfd0f0d3e7405588acdcf7
  family_hash:       45bfd0f0d3e7405588acdcf742d980577eed4963382c2fde31632fc43db52516
```

The Phase17D validation bound was NOT widened.

## CLI scope audit

The actual recipe-first CLI (`scripts/run_recipe_first_scan_once.py`) accepts exactly the following flags:

```text
--enable-recipe-first
--preview
--identity-snapshot
--metadata-snapshot
--input-rarity
--stattrak-mode
--collection
--max-targeted-buff-goods-ids
--max-final-valuation-requests
--max-recipe-candidates-returned
--max-candidate-states-explored
--max-family-states-considered
--max-prescreen-names
--max-prescreen-batch-dispatches
--cache-backend
--output-format
--artifact-dir
```

No additional harness was added; Phase17D live must use this same CLI.

## Recomputed prescreen shape

Using the actual repaired runtime on the frozen Phoenix state:

```text
logical_names_before_dedupe: 19
unique_names:                19
batch_chunks:                 2
```

Exact unique names (19):

```text
AK-47 | Redline (Battle-Scarred)
AK-47 | Redline (Field-Tested)
AK-47 | Redline (Minimal Wear)
AK-47 | Redline (Well-Worn)
Nova | Antique (Factory New)
Nova | Antique (Field-Tested)
Nova | Antique (Minimal Wear)
P90 | Trigon (Battle-Scarred)
P90 | Trigon (Field-Tested)
P90 | Trigon (Minimal Wear)
P90 | Trigon (Well-Worn)
AUG | Chameleon (Factory New)
AUG | Chameleon (Minimal Wear)
AUG | Chameleon (Field-Tested)
AUG | Chameleon (Well-Worn)
AUG | Chameleon (Battle-Scarred)
AWP | Asiimov (Field-Tested)
AWP | Asiimov (Well-Worn)
AWP | Asiimov (Battle-Scarred)
```

All fit within `max_prescreen_names = 20` and `max_prescreen_batch_dispatches = 2`.

## Frozen request bounds (Phase17D validation bounds)

- `max_family_states_considered = 1`
- `max_prescreen_names = 20`
- `max_prescreen_batch_dispatches = 2`
- `max_targeted_buff_goods_ids = 10`
- `max_final_new_live = 2`
- `total_market_dispatch_upper_bound = 14`

Interpreted as at most `2 prescreen batch + 10 BUFF goods-page + 2 final SteamDT NEW-LIVE`.

These are validation bounds, not production defaults.

## Concrete-search bounds

- `--max-recipe-candidates-returned = 1`
- `--max-candidate-states-explored = 256`

Smallest values already live-validated by Phase16G and Phase17C; not increased without offline evidence.

## Cache / final contract

- `--cache-backend inmemory`
- no Redis
- no scanner cache writeback
- fresh `RunScopedValuationSession`
- strict final source `steamdt:buff`
- no prescreen substitution
- final `NEW-LIVE` cap = 2
- exact-name dedupe active

## Frozen structural scope and identity

- Collection: `The Phoenix Collection`
- Input rarity: `Classified`
- StatTrak mode: `normal`
- Expected family key: `45bfd0f0d3e7405588acdcf7`
- Expected family hash: `45bfd0f0d3e7405588acdcf742d980577eed4963382c2fde31632fc43db52516`

Snapshot digests:

- `data/identity/buff_identity_v1.json`:
  `e3aab46d570869e0b6866eac44b26bca7492ea7c2c54669e74b2b4feeec506ac`
- `data/metadata/skin_metadata_v1.json`:
  `55e4d446a5343e1932f24b9069090431f87b0c750d2cb4c091947ec2411dc421`

## Future live environment contract

- `STEAMDT_API_KEY` must be present in operator shell; never persisted.
- `STEAMDT_DRY_RUN=false` for future authorized live run.
- Use repository-default SteamDT base URL.
- Credentials remain environment-owned only.
- BUFF remains anonymous read-only.

## Safe artifact policy

- Artifact directory OUTSIDE Git: e.g. `<temp>/cs2-phase17d/`.
- Exact result filename (current CLI constant): `phase17b_result.json`.
- Required post-run SHA-256 and safety audit.
- Artifact must exclude credentials, auth headers, cookies, raw provider
  payloads, seller/account data, listing IDs, asset IDs, webhooks, raw
  exception strings.

## Terminal acceptance policy

```text
A VALIDATED_COMPLETE_RESULT
B VALIDATED_NO_OPPORTUNITY
C INCONCLUSIVE_PROVIDER
D CONTRACT_FAILURE
```

Only A/B count as successful live-path validation. C/D do NOT authorize
automatic retry. No claim of economic attractiveness is made from A/B.

## Frozen future CLI command (do NOT execute now)

The exact future live CLI command is built only from real flags; it must
inherit `STEAMDT_API_KEY` from the operator environment and never carry
the key as a literal:

```bash
STEAMDT_DRY_RUN=false \
./.venv/Scripts/python.exe \
  scripts/run_recipe_first_scan_once.py \
  --enable-recipe-first \
  --input-rarity Classified \
  --stattrak-mode normal \
  --collection "The Phoenix Collection" \
  --max-family-states-considered 1 \
  --max-prescreen-names 20 \
  --max-prescreen-batch-dispatches 2 \
  --max-targeted-buff-goods-ids 10 \
  --max-final-valuation-requests 2 \
  --max-recipe-candidates-returned 1 \
  --max-candidate-states-explored 256 \
  --cache-backend inmemory \
  --output-format json \
  --artifact-dir <temp>/cs2-phase17d
```

Where `<temp>` resolves to the host temporary directory.

## Pre-live tests

New file `tests/test_phase17d_prelive_case.py` proves the exact structural
precondition offline and exercises the actual CLI parser, frozen bounds,
snapshot digests, external artifact path, no Phase16G harness import, no
retry/pagination/polling path, and unchanged Phase17A goods-first blobs.

## Phase17C-R1 reference evidence

Authoritative record of the repair:

[phase17c-r1-collection-scope-budget-repair-evidence.md](phase17c-r1-collection-scope-budget-repair-evidence.md)

## Phase15C

`NOT_STARTED`.

## Production recipe-first default

`OFF`. Goods-first remains the production path.

## Live executed

`NO`. This round is pre-live only and did not contact any market endpoint.

## Status token

`PHASE17D_LIVE_NOT_EXECUTED`
