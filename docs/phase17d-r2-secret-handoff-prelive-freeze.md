# Phase17D-R2 Secret-handoff Pre-live Freeze

## Status

`PHASE17D_R2_PRELIVE_FREEZE_REPOSITORY_AUTHORITY`

This round is PRE-LIVE ONLY. No SteamDT/BUFF HTTP, no secret access, no child
launch, no Phase16G harness, no production-default change.

## Base authority and lineage

- Base diagnosis commit: `4fba0556a8088b84073c2a725fbc4492307bc29a`
- Base diagnosis:
  `PHASE17D_R1_OFFLINE_PROVIDER_FAILURE_DIAGNOSED_EXPECTED_FAIL_CLOSED`
- Prior Phase17D authorization remains consumed and closed forever.
- New R2 authorization granted: NO.

## Generic launcher

- Launcher: `scripts/run_recipe_first_authorized_once.py`
- Operator contract:
  `docs/recipe-first-one-shot-live-operator-contract.md`
- Child scanner: `scripts/run_recipe_first_scan_once.py` only.
- Inputs: `--case-file`, `--expected-case-sha256`, optional
  `--preflight-only`.
- Popen uses argv list and `shell=False`; exact child return code is captured.
- Authorization consumption occurs only after Popen returns a process handle.
- Secret file is derived from case SHA prefix and cannot be overridden via CLI.
- Secret is unlinked before spawn and is never persisted in argv/evidence/Git.
- Per-case outside-Git launch-state uses exclusive reservation and consumed
  marker semantics to hard-block a second launch.
- `--preflight-only` reads no secret and spawns no child.

## Frozen R2 structural and budget contract

Same Phoenix scope as the repaired authority:

- collection: The Phoenix Collection
- rarity: Classified
- StatTrak mode: normal
- family key: `45bfd0f0d3e7405588acdcf7`
- family hash:
  `45bfd0f0d3e7405588acdcf742d980577eed4963382c2fde31632fc43db52516`

Validation bounds (not production defaults):

- family states: 1
- prescreen names: 20
- prescreen batch dispatches: 2
- targeted BUFF goods/pages: 10
- final NEW-LIVE: 2
- recipe candidates: 1
- concrete states: 256
- cache: inmemory
- output: json
- artifact dir:
  `C:/Users/lijie/AppData/Local/Temp/cs2-phase17d-r2`

## Snapshot authority

- `data/identity/buff_identity_v1.json`:
  `e3aab46d570869e0b6866eac44b26bca7492ea7c2c54669e74b2b4feeec506ac`
- `data/metadata/skin_metadata_v1.json`:
  `55e4d446a5343e1932f24b9069090431f87b0c750d2cb4c091947ec2411dc421`

## External case lifecycle

The canonical external case is intentionally created only after this repository
commit is pushed and CI succeeds. It binds the exact authority commit and
contains the exact child argv JSON array. Its expected location is:

`C:\Users\lijie\AppData\Local\Temp\cs2-phase17d-r2\phase17d_r2_case.json`

The launcher will then run `--preflight-only` with the exact case SHA. This
preflight requires no secret, spawns no child, and performs no provider HTTP.

## Safety boundary

- Provider HTTP: 0
- Secret access: 0
- Child launches: 0
- Production recipe-first: OFF
- Goods-first: unchanged
- Phase15C: NOT_STARTED
- No live authorization is requested or granted by this round.
