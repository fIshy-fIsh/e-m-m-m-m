# Phase 17C-R1 Collection-Scope Discovery Budget Repair Evidence

## Status

`PHASE17C_R1_COLLECTION_SCOPED_DISCOVERY_BUDGET_REPAIRED`

This repair round is offline only. No market HTTP, no live CLI, no Phase16G live
execution, no production-default change, no Phase15C campaign work.

## Authority

- Phase17C commit: `d8dafa9215bfb78dfcb78fd990ed30f899892ae9`
- Phase17C CI: run `34251076086` — SUCCESS
- Phase17C exact CI pytest: `3766 passed, 23 skipped, 2 warnings in 50.84s`
- Phase17D-A pre-live freeze blocked because the coordinator applied
  `collection_allowlist` AFTER family state visitation, causing the
  one-state budget to be consumed by an out-of-scope family
  (`Limited Edition Item`, key
  `40a60d49838d4fe7a70126ec`, hash
  `40a60d49838d4fe7a70126ec4bf5e5bb29cea5d9ea00cc6327c49066e343288f`)
  before reaching the configured `The Phoenix Collection`.

## Implemented semantics

```text
pinned catalogs
  -> RecipeFamilyGenerator.from_catalogs(rarity, stattrak, ...)
  -> .with_collection_allowlist(exact_collection_allowlist)
       -> new RecipeFamilyGenerator whose RecipeFamilyStratum.eligible_collections
          is the exact sorted intersection of the unrestricted stratum and the allowlist
  -> iter_families() walks only in-scope families
  -> max_family_states_considered counts ONLY in-scope generated states
```

- Empty allowlist returns the unrestricted generator unchanged.
- Exact case-sensitive canonical names only; no alias, casefold, trim.
- New `RecipeFirstGenerator.with_collection_allowlist` is pure, offline, and
  backward-compatible.
- Coordinator constructor requires in-scope collections to be in the
  pinned metadata catalog; unknown collection names remain fail-closed.

## Counters

After the repair:

- `families_visited` = in-scope generated family states actually considered.
- `families_infeasible` = visited in-scope states failing static feasibility.
- `families_contract_failed` = visited in-scope states failing structural
  downstream checks (wrong family type, identity mismatch, etc.).
- `families_ranked_retained` = in-scope feasible candidates.

No hidden separate unbounded family traversal counter.

## Phoenix one-state structural prerequisite

Configured scope:

```text
input rarity:           Classified
StatTrak mode:           normal
collection allowlist:    The Phoenix Collection
max_family_states:      1
```

Offline pure result:

```text
families_visited:         1
infeasible:               0
contract_failed:          0
unique first/only family:
  collection_counts:    (("The Phoenix Collection", 10),)
  family_key:           45bfd0f0d3e7405588acdcf7
  family_hash:          45bfd0f0d3e7405588acdcf742d980577eed4963382c2fde31632fc43db52516
```

The structural prerequisite now holds. The Phase17D pre-live freeze remains
pending and is NOT marked frozen or live-validated here.

## Regression evidence

New focused tests:

- `test_phoenix_one_state_is_first_and_only_visited_in_scope`
- `test_empty_allowlist_preserves_unrestricted_first_family_and_identity`
- `test_multi_collection_allowlist_constrains_before_iteration`
- `test_multi_collection_state_cap_counts_only_in_scope_states`
- `test_unknown_allowlist_collection_remains_fail_closed`
- `test_allowlist_is_exact_case_sensitive_and_never_trimmed`
- `test_constraining_generator_does_not_iterate_family_states`
- `test_validation_bound_remains_exactly_one`

Phase17C scenario that previously relied on disjoint allowlist was rewritten
to assert zero in-scope states (Consumer Grade × Phoenix Collection) instead of
the old out-of-scope state behavior.

## Quality gates

- `git diff --check`: clean
- `ruff check .`: passed
- `mypy app`: passed, 105 source files
- Full pytest: `3774 passed, 23 skipped, 2 warnings in 151.36s`

## Goods-first unchanged

Phase17A-frozen blobs remain exact:

- `app/services/scanner_orchestrator.py`:
  `06bb4fe5654c72bc3540904f6982c1e0672f276d`
- `scripts/run_live_scan_once.py`:
  `e0f8773fe4b9a81c96a3b23877a07c60a6dfc871`

## Boundary

- SteamDT HTTP during repair: `0`
- BUFF HTTP during repair: `0`
- Production recipe-first default remains OFF
- Goods-first remains the production path
- Phase15C remains NOT STARTED
- Phase17D pre-live case is NOT FROZEN; it must be re-run from the repaired CI-green commit
- Phase17D live remains NOT STARTED
- No PR, no merge, no amend, no rebase, no force push
