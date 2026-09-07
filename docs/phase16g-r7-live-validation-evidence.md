# Phase 16G-R7 Live Validation Evidence

## Status

`PHASE16G_R7_LIVE_VALIDATED`

## Authoritative pre-live checkpoint

- Branch: `feature/recipe-first-steamdt-live-validation`
- Commit F: `ce546730e4a34bf53e3973e5a30508361f51355e`
- Commit subject: `harden phase16g prelive identity and dispatch accounting`
- CI workflow: `CI`
- CI run: `34083045096`
- CI event/status/conclusion: `push` / `completed` / `success`
- CI pytest: `3698 passed, 23 skipped, 2 warnings in 58.65s`
- Case path (outside Git):
  `C:\Users\lijie\AppData\Local\Temp\cs2-phase16g\phase16g_case.json`
- Case SHA-256:
  `266bbd0f4df64bd947c4d081a0b978d51a03a221691c2e2acc8987fe890f5e68`

## Family and frozen plan

- Family key: `45bfd0f0d3e7405588acdcf7`
- Family hash:
  `45bfd0f0d3e7405588acdcf742d980577eed4963382c2fde31632fc43db52516`
- Input: Classified / normal / The Phoenix Collection x10
- Static feasibility: `feasible`
- Result schema: v2
- Frozen prescreen count: 9
- Frozen caps: BUFF 1 / SteamDT batch 1 / SteamDT singles 2 /
  total SteamDT 3

## One consumed live attempt

The operator executed one separately authorized attempt. No automatic retry,
pagination, polling, or fallback occurred.

- Classification: `validated`
- Result path (outside Git):
  `C:\Users\lijie\AppData\Local\Temp\cs2-phase16g\phase16g_result.json`
- Result SHA-256:
  `9a0aa4ac2572018af65af3692f4f9db1e374efa2c7ad41723eaea11289a8f17e`
- Archive path (outside Git):
  `C:\Users\lijie\AppData\Local\Temp\cs2-phase16g\archive\phase16g_commitF_validated_result.json`
- Archived bytes are byte-identical to the result artifact.

### Phases

1. prescreen: `ok`; selected=9, missing=0, failures=0
2. BUFF page: `dispatched`; listings=10, compatible=10, incompatible=0
3. concrete search: `ok`; selections=1, states_explored=1,
   unique_candidates_returned=1
4. final valuation: `ok`; NEW-LIVE=2, missing=0, errors=0

### Request state

- SteamDT batch attempted/dispatched: 1 / 1
- BUFF attempted/dispatched: 1 / 1
- SteamDT singles attempted/dispatched: 2 / 2
- Total SteamDT dispatched: 3

`dispatched` means the external request dispatch started.

### Prescreen evidence

| Exact market name | BUFF sell CNY | sellCount | updateTime |
|---|---:|---:|---:|
| AK-47 \| Redline (Field-Tested) | 184.5 | 7946 | 1788755427 |
| AUG \| Chameleon (Factory New) | 558.64 | 117 | 1788755423 |
| AUG \| Chameleon (Minimal Wear) | 555.0 | 75 | 1788755423 |
| AUG \| Chameleon (Field-Tested) | 524.49 | 24 | 1788755422 |
| AUG \| Chameleon (Well-Worn) | 520.0 | 3 | 1788755391 |
| AUG \| Chameleon (Battle-Scarred) | 550.0 | 1 | 1788755390 |
| AWP \| Asiimov (Field-Tested) | 730.0 | 1660 | 1788755425 |
| AWP \| Asiimov (Well-Worn) | 568.99 | 276 | 1788755424 |
| AWP \| Asiimov (Battle-Scarred) | 505.77 | 500 | 1788755424 |

All entries have source `steamdt:buff-prescreen`. These approximate
prescreen prices were not reused as final quotes.

### BUFF acquisition evidence

- goods_id: `33960`
- exact name: `AK-47 | Redline (Field-Tested)`
- listings / candidate accepted / metadata resolved: 10 / 10 / 10
- family-compatible / incompatible enriched inputs: 10 / 0

### Real concrete search and structural rows

Search diagnostics: eligible=10, retained=10, states explored=1,
raw candidates found=1, unique candidates returned=1, duplicates
suppressed=0; no candidate or exploration limit reached.

| Exact output | Probability | Output float | Wear |
|---|---:|---:|---|
| AUG \| Chameleon (Field-Tested) | 0.5 | 0.20962120840946835 | Field-Tested |
| AWP \| Asiimov (Battle-Scarred) | 0.5 | 0.523778781791528 | Battle-Scarred |

Probability sum is 1.0. Output names are unique and both are members of
the successful nine-name prescreen set.

### Strict final valuation

| Exact output | Final BUFF sell CNY | Source | EV contribution CNY |
|---|---:|---|---:|
| AUG \| Chameleon (Field-Tested) | 524.49 | steamdt:buff | 262.245 |
| AWP \| Asiimov (Battle-Scarred) | 505.77 | steamdt:buff | 252.885 |

Final NEW-LIVE names and final quote names exactly equal the concrete
output names. Missing and errors are empty. Pre/post valuation values
for market name, probability, output float, and output wear are exactly
equal; `structural_fields_preserved=true`. Only the valuation fields
changed.

## Boundary

This validates the bounded recipe-first SteamDT prescreen + real
family-constrained concrete search + strict final SteamDT-BUFF valuation
interface. It does not claim the recipe is economically attractive or
risk-approved. Production recipe-first remains OFF; goods-first remains
the production path. No Discord, Redis, PostgreSQL mutation, scheduler,
auto-buy, auto-trade, or Phase 15C campaign was used.
