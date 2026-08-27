# PROJECT_CONTEXT.md

## Project Overview

- **Project:** CS2 Trade-up Opportunity Scanner (backend-first).
- **Repository:** https://github.com/fIshy-fIsh/e-m-m-m-m
- **Goal:** Automatically discover CS2 skin trade-up opportunities and alert a human, who performs any transaction manually.
- **Core flow:** market data → candidate discovery → bounded multi-recipe enumeration → trade-up simulation → EV → ROI/risk filtering → alert.
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

BUFF anonymous sell-order is the current **input listing source**, gated, read-only, anonymous, one-request, fail-closed.

The bridge `market_hash_name ↔ BUFF goods_id` is the **provisional community catalog** (`D-IDENTITY-006`) wired into the runtime by `D-IDENTITY-007`. The community-catalog resolver (`BuffCommunityIdentityResolver`) is read at composition time only.

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

## Git / Phase Baselines

```text
Current phase:                              PHASE_13T_COMPLETE

Latest production / test checkpoint:        9288794
                                            add bounded multi-recipe scale validation
                                            (full SHA 92887947e0e1808f1bc23258cf53adb10a0036ee)

Post-Phase-13T AI-context synchronization
baseline:                                    bb09068
                                            sync AI context after Phase 13T
                                            (full SHA bb090686407032b915172eaed2424bf2dd41a9a3)

Live repository HEAD / branch / working tree:
  MUST be verified from Git at task entry.
  Do not infer current HEAD from this document.
  Use:
    git rev-parse HEAD
    git rev-parse @{u}
    git rev-list --left-right --count HEAD...@{u}
    git status --short
```

## Repository Governance

- **R0-A — Public Documentation Synchronization:** **COMPLETE**.
- **R0-B — Minimum CI:** **COMPLETE**. Implementation checkpoint `7a6349e` (`add minimum GitHub Actions CI`). `.github/workflows/ci.yml` runs on `push` and `pull_request` with `contents: read`, `ubuntu-latest`, Python 3.12, `python -m pip install -e ".[dev]"`, `ruff check .`, `mypy app`, and `pytest`.
- **Remote validation:** GitHub Actions workflow `CI`, job `quality`, run `33098999757` completed successfully for checkpoint `7a6349e`. Local validation also passed: ruff, mypy, and pytest (`3336 passed, 23 skipped, 1 warning`).
- **Safety:** default CI is offline-safe and requires no real secrets. Live / integration paths remain opt-in and environment-gated; default CI performs no live BUFF, SteamDT, Redis, or Discord operation.
- **R0-C — Main History Consolidation:** **NOT STARTED**. `origin/main` remains a separate initial history; no merge has been performed.
- **R0-D — Branch / Repository Cleanup:** **NOT STARTED**. No branch cleanup has been performed.

- **Phase:** `PHASE_13T_COMPLETE`. Phase 13T-1 through 13T-4A are committed and pushed (latest commit `9288794`); Phase 13T-4B is a live-only validation performed against that commit and intentionally produced no commit and no repository artifact.
- **Latest completed phases:**
  - **Phase 13T-4B** — `LIVE_VALIDATION_PASSED_NO_COMPLETE_VALUATION` (live-only validation; no commit, no repository artifact; performed against `9288794`). One bounded live `--auto-universe --allocation cohort-depth --target-cohorts 3` run selected 10 goods IDs across three cohorts; 10/10 BUFF pages succeeded; 95 listings → 95 enriched InputItems; real bounded composition returned 2 real recipe candidates; under effective `max_valuation_requests_per_run=5` the two recipes required 10 + 20 unique output names and were atomically blocked before any SteamDT HTTP/provider request; 0 fully valued, 0 risk evaluated, 0 opportunities. SteamDT live mode configured: YES. SteamDT HTTP/provider requests issued during Phase 13T-4B: 0. Frozen contracts held.
  - **Phase 13T-4A** — Offline bounded multi-recipe scale validation committed at `9288794` (`tests/test_multi_recipe_scanner_scale_validation.py`): 10 goods / 100 InputItems / theoretical 901 radius-one states / 2 returned / 2 explored; real composition → real engine → real ValuationService → real metrics → real risk; exact-cap=20 → 2 fully valued; one-below=19 → 1 fully valued + 1 atomically blocked; two-bucket aggregate allocation `1 / 1` candidates and `128 / 128` states; 1/1 legacy compatibility verified; determinism verified.
  - **Phase 13T-3B** — CLI enumeration wiring committed at `33675ee`. Adds `--max-recipe-candidates-returned` and `--max-candidate-states-explored`; `argparse int → RecipeEnumerationConfig → LiveScannerOrchestrator`. Domain validation authority remains `RecipeEnumerationConfig`.
  - **Phase 13T-3A** — Orchestrator bounded enumeration integration committed at `ac26e9b`. `LiveScannerOrchestrator.run_once` now consumes `enumerate_scanner_recipe_selections(…)`; accepts `enumeration_config: RecipeEnumerationConfig | None = None` (default `2 / 256`).
  - **Phase 13T-2** — Scanner composition enumeration adapter committed at `74332e7`. Adds `enumerate_scanner_recipe_selections(…)`, `ScannerRecipeCompositionDiagnostics`, `ScannerRecipeBucketDiagnostics`. Aggregate candidate/state budget split across `min(active_count, C)` participating buckets; no redistribution; no second pass; exact candidate-owned `InputItem` rehydration after temporary `souvenir=False` solver projection; projected inputs never escape.
  - **Phase 13T-1** — Protected Core bounded recipe enumerator committed at `4a6b85c`. Adds `RecipeEnumerationConfig`, `RecipeEnumerationDiagnostics`, `RecipeEnumerationResult`, `enumerate_recipe_selections(…)`. Defaults `2 / 256`; hard bounds `1..6` candidates, `1..1024` states with `states >= candidates`; baseline first (`P0..P9`) then deterministic radius-one substitutions ordered by `(r-d, r, d, RecipeSelectionKey)`; no exhaustive combinations; no beam search; no financial ranking. Canonical offer identity `(source, goods_id, listing_id)`; cross-candidate listing reuse allowed; duplicate canonical offer identity fails closed before sort/cap/search.
  - **Phase 13T Design Freeze** — design only at `010d8cc` (specs trilogy).
  - **Phase 13S** — structural coverage allocation + recipe-depth universe (`COHORT_DEPTH` opt-in; BREADTH default preserved; target 3 cohorts at 10/3 → `4/3/3`).
  - **Phase 13R** — bounded automatic market universe builder (round-robin across collections; 10 BUFF pages, 71 listings, 1 recipe, 10 SteamDT lookups, `RiskDecision.passed=False`).
  - **Phase 13P-5** — post-semantics fully live opportunity-path verification (`LIVE_OPPORTUNITY_PATH_VERIFIED`).
  - **Phase 13P-4** — current Trade Up Contract intrinsic semantics correction (IMPLEMENTED offline; May 21, 2026 Souvenir rule; normal/Souvenir inputs may coexist, standard outputs canonical non-Souvenir, StatTrak separate; Protected Core unchanged).
  - **Phase 13P-3** — SteamDT live price-provider diagnosis (`ROOT_CAUSE_CONFIRMED`; CLI `base_url` transport fix).
  - **Phase 13P-1** — Live SteamDT valuation verification gate + cumulative request guard (atomic fail-closed semantics, `max_valuation_requests_per_run ∈ [1, 60]`, default 5).
  - **Phase 13P** — Live read-only one-shot opportunity scanner MVP (manual `run_once`, bounded goods-id allowlist, pinned local metadata catalog, existing solver/SteamDT valuation/EV/risk composition; no scheduler/no writes).
  - **Phase 13O-1A**, **Phase 13O-1**, **Phase 13O** — Intrinsic-flag canonical-name classifier, binding separation, three-state representation.
  - **Phase 13N-3C** / **Phase 13N-3B** / **Phase 13N-3A** — Identity binding + community catalog snapshot.
  - **Phase 13M-0** / **Phase 13L-0** — Production orchestration and identity-bridge architecture reviews (committed `a70b0e6`, design only).
  - **Phase 13I-3** — Trade-up input enrichment boundary (canonical `TradeUpInputCandidate + metadata → InputItem` seam).
- **Identity status:** **PROVISIONAL** under `D-IDENTITY-006` — community catalog (EricZhu-42) implemented as version-pinned offline source. Resolver exists (13N-3B). Identity binding between `BuffListingProvider` and `BuffListingCandidateAdapter` exists (13N-3C) and is **identity-only** (Phase 13O-1 removed the intrinsic-flag kwargs). The candidate adapter itself still does NOT resolve identity.
- **Intrinsic-flag status:** **THREE-STATE INPUT FACTS / CURRENT NORMAL-OUTPUT RULE** under `D-INTRINSIC-001`, `D-INTRINSIC-002`, and `D-TRADEUP-001` (Phase 13P-4). Candidate-owned `stattrak` / `souvenir` remain exact input facts. Effective May 21, 2026, normal and Souvenir inputs may coexist in the standard Trade Up Contract path; selected Souvenir inputs keep their true provenance facts but the resulting output is canonical non-Souvenir (`souvenir=False`). StatTrak is independent and remains homogeneous/mode-matched. `app/services/scanner_recipe_composition.py` enforces output eligibility by selecting canonical metadata records, never by stripping a name prefix.
- **Bounded multi-recipe status:** **IMPLEMENTED / CURRENT PRODUCTION PIPELINE**. Phase 13T-1 adds the additive bounded enumeration API in `recipe_solver.py` while preserving `construct_recipe_selections` exactly for legacy callers. Phase 13T-2 wraps it in `enumerate_scanner_recipe_selections` with rehydration. Phase 13T-3A wires it into `LiveScannerOrchestrator.run_once`. Phase 13T-3B exposes bounded knobs on the CLI. Phase 13T-4A validates the real end-to-end pipeline offline. Phase 13T-4B validates it live. Candidate identity is `(source, goods_id, listing_id)`. Default `2 / 256`. Cross-candidate listing reuse is allowed.
- **Run-level SteamDT output-price cache status:** **NOT IMPLEMENTED**. Same exact output name in separate recipe valuation calls is a separate logical request today. Classified as a known deferred optimization (separately authorized future phase); must not be promoted to a current feature.
- **Auto-universe scanner status:** **STRUCTURAL ALLOCATION IMPLEMENTED / COHORT-DEPTH LIVE VERIFIED** (Phase 13S; Phase 13R preserved). The pure offline planner now separates exact catalog eligibility from explicit allocation. `BREADTH` remains the default and preserves Phase 13R collection round-robin ordering. Opt-in `COHORT_DEPTH` ranks collection-local allocation cohorts `(collection_name, input rarity, StatTrak)` by descending eligible catalog capacity then lexical key, allocates a configurable target of three cohorts by capacity-aware fair rounds (`10 -> 4/3/3`), and deterministically interleaves normal/Souvenir identities within each cohort. The legal recipe bucket remains broader `(rarity, StatTrak)`; collections may mix and Souvenir is not a cohort-key field under the May-2026 rule. Catalog capacity is not liquidity or live availability. No price/EV/ROI/risk/network dependence exists in planning. Hard cap remains 10; preview remains no-network; manual mode is unchanged when auto options are omitted.
- **Metadata status:** pinned local ByMykel catalog snapshot (`data/metadata/skin_metadata_v1.json`, commit `8a785962...`, MIT, raw SHA-256 `7aeb9582...`); exact-name local O(1) resolver, zero runtime metadata network I/O.
- **Working tree:** contains only the two pre-existing excluded research JSON files (`research/identity_revalidation/data/modest_serhat.json`, `research/identity_revalidation/data/timofey_ivanenko.json`). All Phase 13T-1 through 13T-4A work is committed and pushed at `9288794`.

> Prefer `git status` and `git log --oneline -n 20` over this snapshot.