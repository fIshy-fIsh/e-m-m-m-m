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
- **HEAD:** `8f78bb4a78dd98ae30f00c9b24a0f02eaf0219b6` — `add offline BUFF identity and intrinsic catalog resolution`
- **Latest completed phases:**
  - **Phase 13P-5** — post-semantics fully live opportunity-path validation (`LIVE_OPPORTUNITY_PATH_VERIFIED`; one real BUFF recipe obtained all required SteamDT BUFF sell prices, completed valuation/EV/ROI, and produced a real `RiskDecision`; it was rejected by the unchanged risk policy, so no opportunity passed).
  - **Phase 13P-4** — current Trade Up Contract intrinsic semantics correction (IMPLEMENTED offline; May 21, 2026 Souvenir rule; normal/Souvenir inputs may coexist, all standard outputs are canonical non-Souvenir records, StatTrak remains separate; Protected Core unchanged).
  - **Phase 13P-3** — SteamDT live price-provider diagnosis (ROOT_CAUSE_CONFIRMED; fixed missing `base_url` on the CLI-injected HTTPX client; post-fix four-name diagnostic resolved 3/4 real BUFF prices and isolated 1 `buff_sell_price_non_positive` selection failure).
  - **Phase 13P-1** — Live SteamDT valuation verification gate + request accounting (IMPLEMENTED offline; live valuation gate and cap verified).
  - **Phase 13P** — Live read-only one-shot opportunity scanner MVP (IMPLEMENTED; manual `run_once`, bounded goods-id allowlist, pinned local metadata catalog, existing solver/SteamDT valuation/EV/risk composition; no scheduler/no writes).
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
- **Intrinsic-flag status:** **THREE-STATE INPUT FACTS / CURRENT NORMAL-OUTPUT RULE** under `D-INTRINSIC-001`, `D-INTRINSIC-002`, and `D-TRADEUP-001` (Phase 13P-4). Candidate-owned `stattrak` / `souvenir` remain exact input facts. Effective May 21, 2026, normal and Souvenir inputs may coexist in the standard Trade Up Contract path; selected Souvenir inputs keep their true provenance facts but the resulting output is canonical non-Souvenir (`souvenir=False`). StatTrak is independent and remains homogeneous/mode-matched. `app/services/scanner_recipe_composition.py` enforces output eligibility by selecting canonical metadata records, never by stripping a name prefix.
- **Live one-shot scanner status:** **IMPLEMENTED / CURRENT SOUVENIR SEMANTICS** under `D-SCANNER-001` and `D-TRADEUP-001`. Manual only, one bounded run, sequential goods-id acquisition, run-wide enriched-input pool, existing risk policy, no scheduler/daemon/auto-buy/marketplace writes. Phase 13P-4 supplies a scanner-specific compatibility projection to unchanged Protected Core, admits mixed normal/Souvenir inputs, filters outputs to canonical non-Souvenir records with matching StatTrak mode, and restores exact candidate-owned InputItems before valuation/risk. The pinned Knight regression now requests only the two normal wear names.
- **Live valuation status:** **FULL READ-ONLY PATH VERIFIED** (Phase 13P-5). The Phase 13P-3 CLI `base_url` fix remains active. The post-13P-4 Knight scan requested only the two canonical normal Knight names; Factory New resolved while Minimal Wear failed the unchanged strict `buff_sell_price_non_positive` policy. A second bounded technical scan of goods ID `35458` used 10 real `MAC-10 | Urban DDPAT (Well-Worn)` BUFF listings, resolved both required `PP-Bizon | Carbon Fiber` SteamDT BUFF sell prices, completed valuation and EV/ROI, and produced `RiskDecision.passed=False` under unchanged thresholds. This satisfies the fully live opportunity-path criterion; zero opportunities passed. No scheduler, auto-buy, or marketplace writes.
- **Auto-universe scanner status:** **IMPLEMENTED / BOUNDED MULTI-GOODS LIVE SCAN VERIFIED** (Phase 13R). Pure offline deterministic planner joins the exact pinned identity + metadata catalogs (`BuffCommunityIdentityResolver.identities` × `PinnedSkinMetadataResolver.skins`) by exact `market_hash_name`, applies `is_current_standard_trade_up_output_eligible` and the existing rarity ordering, emits a bounded round-robin goods-id sequence (≤ `LiveScannerOrchestrator.HARD_MAX_GOODS_IDS = 10`), and feeds the existing one-shot scanner unchanged. CLI exposes `--auto-universe` with one input rarity, homogeneous StatTrak mode (`normal`/`stattrak`), include/exclude Souvenir, optional exact collection allowlist, `--max-goods-ids 1..10`, and `--universe-preview` (exits before any settings/client construction). Manual `--goods-id` path preserved byte-identically. No scheduler, no auto-buy, no marketplace writes.
- **Metadata status:** pinned local ByMykel catalog snapshot (`data/metadata/skin_metadata_v1.json`, commit `8a785962...`, MIT, raw SHA-256 `7aeb9582...`); exact-name local O(1) resolver, zero runtime metadata network I/O.
- **Working tree:** contains Phase 13P implementation on top of the pushed identity/intrinsic checkpoint. The two excluded raw research JSON files remain local/untracked.

> Prefer `git status` and `git log --oneline -n 20` over this snapshot.
