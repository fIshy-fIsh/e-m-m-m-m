# Phase 13A Step 2A — SteamApis Offer Domain + Strict Parser Validation

## Focused validation

```bash
py -3.13 -m pytest tests/test_steamapis_listing.py
```

Acceptance:

- Public enum/model/API vocabulary and exact fields are locked.
- Valid subscribed/error/Added/Updated messages produce the exact immutable result kind.
- Added/Updated and changed economics preserve the source ID for one purchase link; different links differ.
- CNY, float, sticker wear, and timestamps preserve documented precision/units.
- Other source/game and missing/null CNY/float produce stable ignored outcomes.
- Malformed envelopes, event types, values, timestamps, stickers, JSON, and duplicate keys fail closed.
- Repr/error/chaining expose no provider data, raw content, server text, or secret-shaped values.
- The module contains no network, client, environment, task/thread, runtime, BUFF, SteamDT, Redis, metadata, solver, or pipeline integration.

## Full repository validation

```bash
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
```

All commands must pass without changing an existing public production contract.

## Existing offline dry-runs

```bash
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
```

Acceptance:

- Existing pipeline, valuation, recipe, risk, alert, and scheduler behavior remains unchanged.
- No dry-run imports or executes the new parser unless explicitly added in a later phase.
- No command connects SteamApis, BUFF, SteamDT, or Redis and no real alert or purchase action occurs.

## Scope and whitespace

```bash
git diff --check
git diff --name-status
git diff --stat
git status --short
```

Exactly seven repository paths may change:

```text
app/services/steamapis_listing.py
tests/test_steamapis_listing.py
docs/STEAMAPIS_MARKET_DATA_NOTES.md
README.md
specs/2026-08-11-steamapis-listing-domain/plan.md
specs/2026-08-11-steamapis-listing-domain/requirements.md
specs/2026-08-11-steamapis-listing-domain/validation.md
```

Confirm no modification to `pyproject.toml`, `.env.example`, config, clients, `CandidateListing`, scanner, solver, trade-up/EV/risk, SteamDT, Redis/cache, metadata, Phase 12 BUFF modules, pipeline, scheduler, FastAPI, Discord, Docker/database, fixtures, roadmap, or deployment files. Report Windows LF-to-CRLF warnings if observed without rewriting valid line endings.

## Source and safety audit

Verify and report:

- official documentation was re-verified from the three official pages through read-only HTTP retrieval, with no third-party source;
- no SteamApis request or WebSocket connection;
- no BUFF request/authentication/login/Cookie activity;
- no SteamDT request;
- no Redis connection;
- no dependency installation;
- no secret or provider raw payload retained/logged;
- no URL parsing or fabricated BUFF/SteamApis marketplace identity;
- no removal semantics;
- no metadata classification, CandidateListing adapter, live pool, solver, valuation, risk, pipeline, scheduler, alert, browser, or purchase action;
- no commit or push;
- no Step 2B work.

## Suggested commit message

```text
add steamapis listing domain parser
```

Do not create that commit or push until separately authorized.
