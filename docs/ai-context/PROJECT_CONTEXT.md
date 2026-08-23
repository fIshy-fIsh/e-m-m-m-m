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
- **HEAD:** `481dafb63661ad7165bd023fa9a35d82b21bf4310` — `add identity and orchestration architecture reviews`
- **Latest completed phases:**
  - **Phase 13O-1A** — Intrinsic classifier correctness audit (IMPLEMENTED; counts and terminology corrected; per-page resolver invocation; new tests for matrix invariants).
  - **Phase 13O-1** — Intrinsic-flag canonical-name classifier + binding separation (IMPLEMENTED; `app/services/buff_intrinsic_flag_resolver.py` provides the pure exact-canonical-string-prefix classifier; `app/services/buff_intrinsic_flag_listing_provider.py` provides the separate composition layer; identity-binding layer restored to identity-only).
  - **Phase 13O** — Intrinsic-flag three-state representation (IMPLEMENTED; `bool | None = None` for `stattrak` / `souvenir` at the candidate boundary; `INTRINSIC_FLAG_UNRESOLVED` enrichment rejection; `INTRINSIC_FLAG_INVALID` adapter rejection).
  - **Phase 13N-3C** — BUF listing identity binding (IMPLEMENTED; identity-only).
  - **Phase 13N-3B** — Offline BUFF identity snapshot + bidirectional resolver (IMPLEMENTED).
  - **Phase 13N-3A** — BUF community catalog identity revalidation.
  - **Phase 13M-0** — production scanner orchestration architecture review (committed `a70b0e6`, design only).
  - **Phase 13L-0** — identity bridge architecture review (committed `a70b0e6`, design only; new decision `D-IDENTITY-003`).
  - **Phase 13N-1** — BUF anonymous response field inventory (committed; decision `D-IDENTITY-004`).
  - **Phase 13N-2** — BUF goods-info endpoint survey (committed; decision `D-IDENTITY-005`).
  - **Phase 13K-3** — BuffListing candidate adapter boundary commit (`5d19096`).
  - **Phase 13K-1** — synthetic BuffListing candidate adapter implementation (`5d19096`).
  - **Phase 13J-1** — synthetic scanner-scale validation implementation (`1549248`).
  - **Phase 13I-3** — trade-up input enrichment boundary (`f34f25f`).
- **Identity status:** **PROVISIONAL** under `D-IDENTITY-006` — community catalog (EricZhu-42) implemented as version-pinned offline source. Resolver exists (13N-3B). Identity binding between `BuffListingProvider` and `BuffListingCandidateAdapter` exists (13N-3C) and is **identity-only** (Phase 13O-1 removed the intrinsic-flag kwargs). The candidate adapter itself still does NOT resolve identity.
- **Intrinsic-flag status:** **THREE-STATE** under `D-INTRINSIC-001` (Phase 13O); **canonical-name classifier** under `D-INTRINSIC-002` (Phase 13O-1). The classifier establishes `True` / `False` for every well-formed canonical name using the exact-byte prefix rule (`'StatTrak™ '` and `'Souvenir '`). `None` is reserved for unresolved identity or unknown-source resolvers. The classifier is pure: no HTTP, no filesystem mutation, no BUFF / SteamDT / SteamApis / Redis / DB / Discord.
- **Working tree:** contains Phase 13O-1 implementation (canonical-name classifier + binding separation + AI context updates) on top of Phase 13O (intrinsic-flag wrapper module + 3-state representation), 13N-3C (binding layer), 13N-3B (resolver/snapshot/builder), and 13N-3A (spec trilogy and research artifacts).

> Prefer `git status` and `git log --oneline -n 20` over this snapshot.
