# Phase 13I-1 — Metadata Provider Contract Audit — Validation

## How to know this audit is complete

Audit-only phase. Success criteria:

- `plan.md`, `requirements.md`, `validation.md` exist under
  `specs/2026-08-22-trade-up-metadata-provider-contract-audit/`.
- No production code is modified.
- `SkinMetadata`, `CollectionMetadata`, `OutputCandidateBuildResult`,
  `RarityOrder`, `InputItem`, `OutputCandidate`, `TradeupResult`,
  `MetadataProvider`, `LocalJsonMetadataProvider`,
  `ByMykelMetadataProvider`, `normalize_skin`, `normalize_skins`,
  `SkinMetadataCatalog`, `LiveSolverBucketKey`,
  `classify_steamapis_snapshot`, `TradeUpInputCandidate`,
  `TradeUpInputMetadata`, `TradeUpInputMetadataResolver`,
  `InMemoryTradeUpInputMetadataResolver`, `candidates_to_input_items`,
  and `recipe_solver` are all untouched.
- All review-time commands below pass.

## Commands to run

```bash
git status --short
git diff --stat
git diff --check
py -3.13 -m pytest -q
py -3.13 -m ruff check .
py -3.13 -m mypy app
```

## Expected outcome

- `git status --short` shows only the new spec directory; no
  application code is modified.
- `git diff --stat` is empty.
- `git diff --check` passes.
- `py -3.13 -m pytest -q` reports the same numbers as before this
  phase (no new tests; audit-only).
- `py -3.13 -m ruff check .` reports zero violations.
- `py -3.13 -m mypy app` reports no issues.

## Observed outcome

Recorded at the end of the phase:

```text
git status --short: (no production-code changes; only spec/ files)
git diff --stat: (empty)
git diff --check: passed
pytest: 2848 passed, 23 skipped, 1 warning  (unchanged from 13I-0)
ruff: 0 violations
mypy app: no issues
```

## Sign-off checklist

- [ ] `plan.md` present, lists inspected sources verbatim with line numbers.
- [ ] `requirements.md` answers all five task-brief questions:
  - [ ] Required metadata fields for `InputItem`?
  - [ ] Existing metadata fields available today?
  - [ ] Missing fields?
  - [ ] Whether current metadata layer needs a future extension?
  - [ ] Recommended future enrichment contract?
- [ ] Decision recorded: metadata layer does not need a new field or
  shape; only the candidate side grows two intrinsic-item flags.
- [ ] Files-changed list is docs/spec only.
- [ ] Limitations recorded (audit-only, candidate not yet widened,
  solver still reads metadata-side flags, packaging of future
  enrichment module not decided).