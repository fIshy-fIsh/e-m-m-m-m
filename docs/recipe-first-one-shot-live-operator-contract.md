# Recipe-first One-shot Live Operator Contract

Contract ID: `recipe-first-one-shot-live-operator-contract-v1`

This compact contract applies to future separately authorized recipe-first
SteamDT live cases.

## Authorization and case binding

- Live execution requires explicit authorization bound to an exact canonical
  case SHA-256 and repository commit.
- A secret file is not authorization.
- Current branch/HEAD/upstream/tracked-clean state and manifest SHA must match
  before any secret access or child launch.
- Manifest `child_argv` is the single source of the exact child command.
- The launcher child must remain `scripts/run_recipe_first_scan_once.py`; no
  second scanner path or live harness.

## Secret handoff

- Secret path is derived from case SHA, never accepted as operator input:
  `C:\Users\lijie\AppData\Local\Temp\cs2-secret-handoff\steamdt_<first16-of-case-sha>.once`.
- The file contains only the one-shot key and remains outside Git/repo/chat/
  argv/docs/artifacts/settings/history.
- Preflight may report only `secret_handoff_ready=true/false`; never secret
  value, length, hash, prefix, suffix, or derived metadata.
- Secret is read into memory, injected only as child `STEAMDT_API_KEY`, and
  unlinked before child spawn. `STEAMDT_DRY_RUN=false` is child-only.
- If unlink fails, no spawn occurs and authorization is not consumed.
- No claim of secure physical erasure is made; the operation is unlink/remove.

## One-shot consumption

- At most one child launch per case.
- Authorization remains unconsumed until `subprocess.Popen` successfully
  returns a process handle.
- Once Popen succeeds, authorization is consumed regardless of return code,
  provider failure, contract failure, incomplete result, or no opportunity.
- Per-case launch-state lives outside Git. Any existing reserved/consumed state
  hard-blocks another launch. Successful Popen records `CONSUMED`.
- No automatic retry, second invocation, repair-then-rerun, pagination, or
  polling.
- `live_attempted` is a runtime final-valuation counter and never replaces the
  separate operator invocation count.

## Child process and output

- Launch with argv list and `shell=False`; never include the key in argv.
- Never log or serialize child environment.
- Capture the exact Popen return code. Do not infer or rewrite it.
- Redact the secret from captured stdout/stderr before output.
- Parent/wrapper secret references are removed where practical after spawn.

## Safety and evidence

- No provider mutation, account action, auto-buy, or auto-trade.
- Inspect only sanitized output and safe artifacts after the child exits.
- Evidence uses explicit classes:
  - `OBSERVED`
  - `DERIVED_FROM_CODE`
  - `NOT_OBSERVED`
- Artifact audit rejects secret/auth/cookie/raw provider/seller/account/listing/
  asset/webhook/raw-sensitive-exception content.
- Append-only errata is allowed; history rewriting is not.
- Exact CI pytest text is reported only when directly observable; otherwise
  `NOT_OBSERVABLE`.
- Production recipe-first remains OFF unless a separate cutover decision is
  authorized.
