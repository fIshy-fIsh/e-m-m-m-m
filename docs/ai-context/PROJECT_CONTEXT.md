# PROJECT_CONTEXT.md

## Project Overview

- **Project:** CS2 Trade-up Opportunity Scanner (backend-first).
- **Repository:** https://github.com/fIshy-fIsh/e-m-m-m-m
- **Goal:** Automatically discover CS2 skin trade-up opportunities and alert a human, who performs any transaction manually.
- **Core flow:** market data → candidate discovery → trade-up simulation → EV → ROI/risk filtering → alert.
- **Long-term goal:** evolve from a theoretical opportunity scanner into a **listing-level verified** opportunity scanner.

### What this project does NOT do (hard constraints)

- No automatic purchasing / auto-buy.
- No automatic login.
- No Cookie scraping/extraction.
- No CAPTCHA bypass.
- No BUFF risk-control bypass.
- No browser automation for purchasing.
- No proxy rotation or User-Agent rotation.
- No SteamApis account automation beyond the read-only documented offer stream (currently paused/unverified).
- No invented BUFF endpoints, signatures, parameters, or field mappings.

V1 scope: scanning, normalization, calculation, filtering, Discord notification. No trade execution.

## Current Strategy

Two-source incremental route:

- **Phase A — SteamDT aggregate market data** (active): multi-market price visibility + output valuation.
- **Phase B — BUFF anonymous read-only listing source** (active): concrete input listing discovery.

SteamDT is used for **output valuation / cross-market reference / ranking**, never as a real input listing source (it has no concrete listing, seller, purchase URL, or exact per-listing float).

BUFF anonymous sell-order is the emerging **input listing source**, gated, read-only, anonymous, one-request, fail-closed.

The missing bridge `market_hash_name ↔ BUFF goods_id` has **no verified source yet** and remains an unresolved abstraction (Phase 13D-0).

## Technology Stack

- Python 3.12 target (validation runs on 3.13 locally).
- FastAPI (health-only currently).
- PostgreSQL, Redis (provisioned; not wired into the BUFF/SteamDT valuation seam yet).
- SQLAlchemy 2.0, Alembic, Pydantic.
- httpx (async HTTP; owned clients with strict request contract).
- APScheduler (mock BUFF pipeline only).
- pytest, ruff, mypy.
- Docker Compose (DRY_RUN=true enforced).
- Discord webhook (optional/manual alert channel). V1 is notification-only; Discord is never part of the trade execution pipeline.

## AI Working Rules (mandatory, ordered)

1. Read `PROJECT_CONTEXT.md`, then `ARCHITECTURE_STATE.md`, then `DECISION_LOG.md`, then `DEVELOPMENT_HANDOFF.md`.
2. Check `git status` and current branch/HEAD before any edit.
3. Do **not** modify Protected Core (see `ARCHITECTURE_STATE.md`) without an explicit migration plan and user approval.
4. Never treat an aggregate price as a concrete listing price.
5. Never treat a synthetic fixture as real market data.
6. Never add a live API path without a disabled-by-default, one-request schema smoke first.
7. Never invent endpoints/signatures/parameters/fields; record uncertainty as TODO in `docs/BUFF_API_NOTES.md`.
8. All secrets come from `.env`; never print secrets/tokens/webhook URLs; never hardcode credentials.
9. Any core calculation (trade-up, float, EV, probability, ROI, risk) requires unit tests before commit.
10. Normalize provider fields before they enter engine/service; keep raw provider shapes out of core domain.
11. Add/update these AI context files after every significant phase.

## Current Git State (verify live; authoritative snapshot)

- **Branch:** `feature/steamdt-cache-rate-limit`
- **HEAD:** `2a8a1e8bb23aa0e51ad9ebb73ac50a662a951e4f` — `harden buff listing provider anonymous contract`
- **Uncommitted:** Phase 13D-0 identity contract is staged in the working tree but **not yet committed** (see DEVELOPMENT_HANDOFF).

> Prefer `git status` and `git log --oneline -n 20` over this snapshot.
