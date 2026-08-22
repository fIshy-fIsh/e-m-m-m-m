# Phase 13I-0 — Trade-up Metadata Enrichment Boundary Review — Validation

## How to know this review is complete

This is a design-only review phase. The success criteria are:

- `plan.md`, `requirements.md`, and `validation.md` exist under
  `specs/2026-08-22-trade-up-metadata-enrichment-boundary-review/`.
- No production code file is modified.
- `TradeUpInputCandidate` is not widened beyond `stattrak` and
  `souvenir` in this phase. No code is added to it.
- `InputItem` and the trade-up engine remain untouched.
- No metadata provider is added.
- No BUFF / SteamDT / SteamApis wiring is added.
- The existing `trade_up_pipeline.py` (synthetic adapter) is preserved.
- All review-time commands below pass.

## Commands to run

```bash
git diff --check
git status --short
git diff --stat
py -3.13 -m pytest -q
py -3.13 -m ruff check .
py -3.13 -m mypy app
```

## Expected outcome

- The only working-tree changes are the three new spec files plus this
  validation file. Everything else is `git status --short`-empty.
- `py -3.13 -m pytest -q` reports the same `passed / skipped / warning`
  counts as before this phase (no new tests are added; this is
  design-only).
- `py -3.13 -m ruff check .` reports zero violations.
- `py -3.13 -m mypy app` reports no issues.
- `git diff --check` reports no whitespace problems.

## Observed outcome

Recorded at the end of the phase:

```text
git status --short: (no production-code changes; only spec/ files)
pytest: 2848 passed, 23 skipped, 1 warning  (unchanged)
ruff: 0 violations
mypy app: no issues
git diff --check: passed
```

## Sign-off checklist

- [ ] `plan.md` present, lists the inspected sources verbatim.
- [ ] `requirements.md` answers all four task-brief questions:
  - [ ] Which fields are required by `InputItem`?
  - [ ] Which fields belong to A/B/C?
  - [ ] Should `TradeUpInputCandidate` be expanded or remain minimal?
  - [ ] How should `stattrak / souvenir / collection / rarity` be
        supplied in future?
- [ ] Architecture decision recorded with rationale.
- [ ] Limitations recorded (no live provider, candidate not widened
  beyond two flags, identity unchanged, no engine modification).
- [ ] Files-changed list is docs/spec only.