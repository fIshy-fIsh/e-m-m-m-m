# Phase17D Bounded Live Validation Evidence Errata

## Authority

- Original evidence commit:
  `40af94b7b7c48dd866d2d4fab79f0aefb53be1ad`
- Original evidence file:
  `docs/phase17d-bounded-live-validation-evidence.md`

## Correction

The original document includes this unsupported parenthetical:

```text
process completion: phase17b_execute: complete (process exit code 0)
```

The operator stdout did not attest a shell exit code.

Correct evidence classification:

- observed shell exit code: `NOT_OBSERVED`
- code-derived expected exit code for terminal group
  `incomplete_or_provider`: `2`

The code-derived value follows
`exit_code_for_terminal_group(RecipeFirstRuntimeTerminalGroup.INCOMPLETE_OR_PROVIDER)`.
It is not promoted to an observed shell fact.

## Unchanged evidence

This errata does not change:

- operator live invocation count: exactly 1
- authorization consumed: YES
- terminal group: `incomplete_or_provider`
- terminal code: `EXTERNAL_PROVIDER_FAILURE`
- acceptance class: `C INCONCLUSIVE_PROVIDER`
- request counters
- artifact SHA-256:
  `14bd3f2d13610bda49ef195cb2b9bd589b6cc8f62128ef3722ec2ce922726b77`
- authorized case SHA-256:
  `b707cf3f986283486a31fda936d9bb8b91c1d73f35b46f62c1dd20819dead21c`
- no-rerun status
- production recipe-first default OFF
- goods-first unchanged

The original evidence commit is preserved unchanged; this file is a separate
append-only correction.
