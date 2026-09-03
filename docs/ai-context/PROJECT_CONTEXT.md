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
Current phase:                              PHASE_15B_POLICY_FREEZE_COMPLETE

Latest Phase 15 checkpoints:                Phase 15A df621d4
                                            192 designed replays /
                                            439 structural census records /
                                            CI run 33325598811 SUCCESS
                                            Phase 15B: default 5 unchanged,
                                            hard max 60 unchanged,
                                            representative snapshot gate required

Post-Phase-13T AI-context synchronization
baseline:                                    bb09068
                                            sync AI context after Phase 13T
                                            (full SHA bb090686407032b915172eaed2424bf2dd41a9a3)

Post-R0-C canonical main:                   9cfaf36
                                            sync docs after R0-C repository consolidation
                                            (full SHA 9cfaf36db028661075a495587ac32e51256fffe8)
                                            parents:
                                              24ece8582d1b3cb1b72322afc15de94b652a8bcc (old main)
                                              3aa44e9364268308d0fbb4c0532f4a910f4f85e8 (consolidation)
                                            tree:   7a39d28f2654cdf3b4eb98c8123227de64db5e34
                                            (post-R0-C main; ancestor of current canonical main P2;
                                             retained for historical reference)

Post-R0-C docs checkpoint:                 b13201b
                                            sync docs after R0-C docs checkpoint
                                            (full SHA b13201bdff4f2323a82d4da3560add25365e5695)
                                            (PR #2 `Sync documentation after R0-C consolidation`)

Current canonical main (P3):               24c95c029f583d5cc0b0a67986e48c06d0ef7957
                                            parents: {328269112f229faf3fce4cf0be4b9c7875582b65,
                                                       6964cc4ff25cd4ad72fe65f92f40a5ce70a4a268}
                                            tree:   608d3e473072afb0d97aadf46ea0be8b1f55ca26
                                            CI workflow blob 02d0ce81d3704d9bc9c513df9b474855ffeae703
                                            preserved unchanged since R0-A
                                            (canonical main advanced to P3 by the R0-D
                                             completion documentation checkpoint PR #3;
                                             P2 = 328269112f229faf3fce4cf0be4b9c7875582b65
                                             is now an ancestor of P3; retained as
                                             historical reference)

Post-Phase-14A design-freeze baseline:    e98cd97
                                            freeze scanner valuation integration design
Phase 14A-R1 coherence correction:       bb056e5
                                            tighten scanner valuation integration design
Phase 14B checkpoint:                    c7031b61c3c44640ffd76165946809f7383f5d0c
                                            add run-scoped scanner valuation reuse
Phase 14C checkpoint:                    current feature-branch HEAD
                                            add scanner fresh-only price cache reads
                                            (verify via `git rev-parse HEAD`)

Historical DEV tip (pre-R0-C development line): 4c2f1ef6cd850985e71f041601ae58489abe947b
                                            sync docs after minimum CI validation

R0-D cleanup deletion summary (executed in R0-D2-TER):
  removed remote branches:
    docs/r0c-completion-checkpoint
    repo/main-consolidation
    feature/steamdt-cache-rate-limit
    feature/steamdt-data-source
  removed named local branches:
    docs/r0c-completion-checkpoint
    repo/main-consolidation
    feature/steamdt-cache-rate-limit
    feature/steamdt-data-source
    feature/buff-tradeup-scanner
  removed generated local branches (305):
    worktree-agent-a*  (all 305; ancestor of P2; 0 unique commits)
  removed linked Claude agent worktrees (305):
    D:/CS/.claude/worktrees/agent-*
  deleted session-local dirt (305, before worktree removal):
    .claude/settings.local.json  (one per agent worktree)
  preserved local-only tag (target unchanged):
    v1-dry-run-baseline -> 32ab47c5b66a0f331457e69f1515e5e9bb2a37e1
  method: `git worktree remove` (no --force), `git branch -d` (no -D);
    no commits, no tracked file changes, no main push, no force,
    no `git fetch --prune` / `git remote prune` / `git worktree prune`,
    no settings changes, no history rewrite, no unique history lost.
  remaining linked worktrees after cleanup: D:/CS root only.
  remaining local branches after cleanup: main only.
  remaining remote branches after cleanup: main only.

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
- **R0-C — Main History Consolidation:** **COMPLETE**. PR #1 (`Reconcile main history with current project lineage`) merged using `Create a merge commit`. Final canonical `main` tip is `9cfaf36db028661075a495587ac32e51256fffe8` with parents `{24ece8582d1b3cb1b72322afc15de94b652a8bcc, 3aa44e9364268308d0fbb4c0532f4a910f4f85e8}`; tree `7a39d28f2654cdf3b4eb98c8123227de64db5e34`; CI workflow blob `02d0ce81d3704d9bc9c513df9b474855ffeae703`. DEV tip `4c2f1ef6cd850985e71f041601ae58489abe947b` is an ancestor. Final-main push CI: workflow `CI`, run `33173529766`, conclusion `success`.
- **R0-D — Branch / Repository Cleanup:** **COMPLETE**. PR #3 (`R0-D completion documentation checkpoint`) merged using `Create a merge commit`. Final canonical `main` tip is `24c95c029f583d5cc0b0a67986e48c06d0ef7957` (P3) with parents `{328269112f229faf3fce4cf0be4b9c7875582b65 (P2), 6964cc4ff25cd4ad72fe65f92f40a5ce70a4a268 (R0-D3 docs commit)}`; tree `608d3e473072afb0d97aadf46ea0be8b1f55ca26`; CI workflow blob `02d0ce81d3704d9bc9c513df9b474855ffeae703` preserved unchanged since R0-A. Final-main push CI: workflow `CI`, run `33240760167`, event `push`, branch `main`, head SHA `24c95c0…`, conclusion `success`. Cleanup execution summary is captured in the dedicated block above (305 worktrees + 305 generated branches + 5 named local branches + 4 named remote branches removed; `v1-dry-run-baseline` preserved; no unique history lost).

- **Phase:** `PHASE15B_POLICY_FREEZE_COMPLETE`. Phase 15A offline measurement remains authoritative structural/designed-replay evidence (`192` observations, `439` census records, fixed `2 / 256`; checkpoint `df621d4`, CI run `33325598811` SUCCESS). Phase 15B freezes a no-change policy: `NO_PRODUCTION_DEFAULT_CHANGE_PENDING_REPRESENTATIVE_SNAPSHOT` (default remains `5`) and `HARD_MAX_60_REVIEW_DEFERRED` (hard max remains `60`). Designed replay shares are not production probabilities. Artifact: `research/valuation_budget_calibration/POLICY_DECISION.md`. No production, test, script, workflow, CLI, budget, or atomic-semantics change; representative read-only listing-snapshot calibration is required before any numeric policy change.
- **Phase 14 canonical baseline:** Phase 14A / 14A-R1 / 14B / 14C / 14D merged onto canonical main via PR #4. Phase 14 docs checkpoint PR #5 merged at main `215c91c46a6d95de793649a87bccceb3a24a42d3`; main push CI run `33321890478` SUCCESS.
- **Latest completed phases:**
  - **Phase 14C — Phase12D FRESH_ONLY cache READ integration** — optional scanner-owned `ScannerCachedBuffPriceResolver` injection; the wrapper internally fixes the existing raw resolver to `select_scanner_cached_buff_price`, so generic cross-platform selection cannot enter the public scanner composition path. Each fresh run session performs deterministic memo → sequential FRESH_ONLY cache → live classification. New cached selector delegates strict authority to `select_buff_output_price`. Selected outcomes independently require `lookup.state == FRESH`; strict selection failures retain their stable reason across same-run memo reuse; MISS/EXPIRED/POLICY_BLOCKED become NEW LIVE; typed backend/codec/adapter/resolver errors propagate. Cache-derived memo survives atomic blocks, unresolved blocked names are re-read, Stage B performs live-only resolution and no persistent writes. Snapshot TTL policy remains writer-owned; CLI composition and scanner write-after-live remain unimplemented. `D-CACHE-001` remains Active until Phase 14D runtime composition. Full validation: `3413 passed, 23 skipped, 1 warning`; ruff/mypy pass.
  - **Phase 14B — Run-scoped exact-name valuation reuse** — scanner-owned `app/services/scanner_valuation_session.py`; fresh session inside every `LiveScannerOrchestrator.run_once()`; immutable session-bound two-stage plans; atomic NEW-LIVE cap; exact success/failure reuse; no same-name retry or cross-run memo; existing `ValuationService` formula reused. Baseline full validation: 3382 passed, 23 skipped, 1 warning.
  - **Phase 14A — Scanner Valuation Integration Design Freeze** — design only; `specs/2026-08-29-scanner-valuation-integration-design-freeze/{requirements,plan,validation}.md`; branch `feature/scanner-valuation-integration`; doc-only commit `freeze scanner valuation integration design`. Six new decision IDs appended: `D-CACHE-002` (run-scoped exact-name reuse is the only Phase 14 seam), `D-CACHE-003` (initial scanner cache policy is `FRESH_ONLY`), `D-BUDGET-001` (atomic live-demand preflight; `max_valuation_requests_per_run` now means NEW LIVE SteamDT provider demand, not structural recipe demand), `D-CACHE-004` (failure reuse within a run; no automatic same-name retry), `D-ACCOUNTING-001` (additive counter migration; Option A preferred), `D-PHASE14A-COMPLETE` (design freeze closed). The frozen design preserves every Phase 13T contract (`D-ENUM-001..004`, `D-CACHE-001` remains `Active`) and the future 14B / 14C / 14D implementation sequence is documented in the trilogy. **No production code touched.** `D-CACHE-001` remains `Active` (the runtime cache is still not implemented); Phase 14A only freezes the design.
  - **Phase 14A-R1 — Design Coherence Correction** — docs only; corrected internal contradictions in the Phase 14A prose before any 14B implementation. New decision ID: `D-PHASE14A-R1-COHERENCE` records nine sub-corrections: (1) `select_steamdt_price_quote` is generic cross-platform and CANNOT be configured strict BUFF-only — strict BUFF adapter must be composed at the session level via reuse/adaption of `select_buff_output_price`; (2) two-stage prepare/execute session contract (Stage A `prepare_output_prices(names)` issues ZERO live calls; Stage B `resolve_prepared(plan)` only after atomic-cap admission); (3) cache backend/codec/adapter errors propagate by identity and are NOT live candidates; (4) `SteamDTBuffPriceProvider.get_prices` converts ordinary failures to `PriceLookupResult.missing/errors` (only `MemoryError` and uncatchable `BaseException` propagate by identity); (5) counter contract finalized under Option A — legacy semantics preserved exactly, no arithmetic equality between legacy and Phase 14 counters; (6) 14B reuse test corrected (Recipe2 memo hits = 9, not 0); (7) NO scanner fresh_ttl numeric default frozen — 5-minute value in `scripts/steamdt_refresh_integration.py:59` is historical precedent only; (8) initial Phase 14C is READ-only (no scanner writeback; existing manual refresh stack remains the writer); (9) `D-CACHE-001` remains Active until Phase 14B / 14C land and are verified. **No production code touched.**
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
- **Run-level exact-name valuation and cache-read status:** **IMPLEMENTED at scanner service/session boundary** (Phase 14B + 14C). Each `run_once()` gets a fresh memo. Optional injected Phase12D resolver reads only FRESH data and reruns strict BUFF selection; cache failures/misses follow the frozen classifications. `max_valuation_requests_per_run` counts NEW LIVE demand after memo/cache. `D-CACHE-001` remains Active because default `run_live_scan_once.py` composition is still **NOT IMPLEMENTED** (Phase 14D). Scanner write-after-live remains **NOT IMPLEMENTED**.
- **Auto-universe scanner status:** **STRUCTURAL ALLOCATION IMPLEMENTED / COHORT-DEPTH LIVE VERIFIED** (Phase 13S; Phase 13R preserved). The pure offline planner now separates exact catalog eligibility from explicit allocation. `BREADTH` remains the default and preserves Phase 13R collection round-robin ordering. Opt-in `COHORT_DEPTH` ranks collection-local allocation cohorts `(collection_name, input rarity, StatTrak)` by descending eligible catalog capacity then lexical key, allocates a configurable target of three cohorts by capacity-aware fair rounds (`10 -> 4/3/3`), and deterministically interleaves normal/Souvenir identities within each cohort. The legal recipe bucket remains broader `(rarity, StatTrak)`; collections may mix and Souvenir is not a cohort-key field under the May-2026 rule. Catalog capacity is not liquidity or live availability. No price/EV/ROI/risk/network dependence exists in planning. Hard cap remains 10; preview remains no-network; manual mode is unchanged when auto options are omitted.
- **Metadata status:** pinned local ByMykel catalog snapshot (`data/metadata/skin_metadata_v1.json`, commit `8a785962...`, MIT, raw SHA-256 `7aeb9582...`); exact-name local O(1) resolver, zero runtime metadata network I/O.
- **Working tree:** Phase 15A checkpoint `df621d4` is pushed on `feature/valuation-budget-calibration`; Phase 15B adds only policy/current-state documentation before its own checkpoint. The only unrelated working-tree entries are the two protected untracked research JSONs, which remain untouched. Canonical `main` remains `215c91c46a6d95de793649a87bccceb3a24a42d3`. Verify live via Git.

> Prefer `git status` and `git log --oneline -n 20` over this snapshot.
---

## Phase 16A Recipe-first Pre-screen Architecture Design Freeze (2026-08-31)

- **Phase pointer:** `PHASE_16A_DESIGN_FREEZE_COMPLETE` on `feature/recipe-first-prescreen-design` from CURRENT `origin/main`.
- **Scope:** docs/spec/AI-context only. No production code change. No PR/merge.
- **Frozen target architecture:**
  `pinned CS2 metadata + pinned BUFF identity -> RecipeFamilyGenerator -> static structural/output geometry -> static float feasibility -> SteamDT batch pre-screen -> coarse/scenario economics -> deterministic ranking/Top-N -> TargetedBuffScanPlanner -> existing BUFF anonymous listing ingestion -> existing identity/intrinsic/enrichment -> family-constrained concrete recipe search -> existing strict final SteamDT-BUFF valuation -> existing EV/risk -> opportunity report`.
- **Frozen V1 project bounds (NOT external API limits):** `MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3`, `TOP_RANKED_FAMILIES = 2`, `MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10`, `PRESCREEN_BATCH_CHUNK_SIZE = 10` (internal project transport chunk; NOT a confirmed SteamDT limit).
- **Offline evidence:** `data/metadata/skin_metadata_v1.json` (sha256 `55e4d446a5343e1932f24b9069090431f87b0c750d2cb4c091947ec2411dc421`, accepted 16868) and `data/identity/buff_identity_v1.json` (sha256 `e3aab46d570869e0b6866eac44b26bca7492ea7c2c54669e74b2b4feeec506ac`, accepted 34402). State count formula `sum_{k=1..K} C(C, k) * C(9, k-1)` over the eight productive strata yields ~477 (K=1), ~143k (K=2), and ~14M (K=3) total family states.
- **Implementation stages (NOT in 16A; freeze only):** 16B RecipeFamily domain; 16C static float feasibility + SteamDT batch pre-screen; 16D coarse economics + ranking + TargetedBuffScanPlan; 16E family-constrained concrete solver integration + orchestrator composition behind explicit opt-in (production default OFF); 16F ONE bounded live read-only validation.
- **Phase 15C-3:** DEFERRED until recipe-first production discovery is implemented and bounded-live validated. Phase 15C-1/2/2B preserved on `feature/representative-snapshot-calibration` and referenced, not modified. Production default remains `5`; hard max remains `60`. Phase 15 evidence is NOT deleted or rewritten.
- **Decisions:** `D-RECIPE-FIRST-001`, `D-PRESCREEN-VALUATION-001`, `D-PRESCREEN-FLOAT-001`, `D-TARGETED-BUFF-001`, `D-PHASE15C3-DEFER-001`.

---

## Phase 16A-R1 Recipe-first Pre-screen Design Coherence Correction (2026-08-31)

- **Phase pointer:** `PHASE_16A_R1_DESIGN_COHERENCE_CORRECTED` on `feature/recipe-first-prescreen-design` from CURRENT `origin/main`.
- **Scope:** docs/spec/AI-context only. No production code change. No PR/merge.
- **Three material ambiguities corrected:**
  1. Souvenir is NOT a `RecipeFamily` structural identity axis (StatTrak IS). Normal/Souvenir inputs may coexist; concrete provenance retained through the existing temporary `souvenir=False` solver projection + exact rehydration seam. `souvenir_inclusion` is removed from `RecipeFamily` fields, canonical bytes, `family_hash`, duplicate key, and enumeration key.
  2. Top-N ranking does NOT multiply live BUFF request budget. Exactly ONE family is active for one live targeted BUFF scan per run. Family #2 is allowed only as a fallback BEFORE any BUFF page request starts. Once any BUFF page request starts, family switching in that run is forbidden. Total BUFF page requests per run is `<= MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10`.
  3. ~14M K=3 theoretical family states are analytic evidence, NOT an eager-materialization requirement. `RecipeFamilyGenerator` MUST support lazy deterministic iteration by stratum, analytic counting without materializing all family objects, and streaming / top-K ranking without retaining all family DTOs simultaneously. SteamDT pre-screen transport MUST deduplicate exact `market_hash_name`s before issuing any batch call.
- **Frozen V1 project bounds (NOT external API limits):**
  - `MAX_DISTINCT_COLLECTIONS_PER_FAMILY = 3`
  - `TOP_RANKED_FAMILIES = 2` (ranking signal only)
  - `MAX_TARGETED_BUFF_GOODS_IDS_PER_RUN = 10` (PROJECT safety bound; one active family per run)
  - `PRESCREEN_BATCH_CHUNK_SIZE = 10` (internal project transport chunk; NOT a confirmed SteamDT limit)
- **Decisions appended:** `D-RECIPE-FIRST-SOUVENIR-IDENTITY-001`, `D-TARGETED-BUFF-BUDGET-001`, `D-RECIPE-FIRST-ENUMERATION-001`.
- **Next authorized phase:** Phase 16B RecipeFamily domain + lazy deterministic generator + structural geometry (OFFLINE ONLY, production diff empty).

---

## Phase 16A-R2 Output Identity / Wear Geometry Coherence Correction (2026-08-31)

- **Phase pointer:** `PHASE_16A_R2_OUTPUT_IDENTITY_GEOMETRY_CORRECTED` on `feature/recipe-first-prescreen-design` from CURRENT `origin/main`.
- **Scope:** docs/spec/AI-context only. No production code change. No PR/merge.
- **Audit finding:** The pinned metadata snapshot expands one underlying CS2 finish into typically 5 canonical non-Souvenir wear-qualified `market_hash_name` rows. The 6-tuple `(collection_name, rarity, stattrak, name, weapon, paint_index)` is collision-free against the pinned snapshot: 16868 wear rows -> 2148 distinct finish keys. 3 finishes have a single canonical non-Souvenir wear row; 2145 have multiple (1791 have all 5 wear bands). `min_float` / `max_float` are consistent across all variants of one finish. The current production `tradeup_engine.calculate_tradeup_results` operates on `OutputCandidate.market_hash_name` and treats each wear row as a separate probability bucket. This is recorded as `D-TRADEUP-WEAR-ROW-MIGRATION-001`.
- **Three corrections applied:**
  1. Two distinct output identities are frozen: `StructuralOutputFinish` (finish-level, used for collection output pool membership, trade-up structural probability, family geometry, and finish-level duplicate suppression) and exact market valuation identity (canonical non-Souvenir `market_hash_name` resolved fail-closed from pinned finish + wear metadata after output float is determined).
  2. `RecipeFamily.represented_outputs` is replaced with `represented_output_finishes` (finish-level). The structural probability primitive counts unique eligible output finishes per family collection and aggregates to `per-finish probability = (collection_count / 10) / unique_finish_count_in_collection`. The probability sum over `represented_output_finishes` MUST equal 1.
  3. The 6-tuple finish key is frozen as collision-free. The wear map (canonical non-Souvenir only) is deterministic per finish. Souvenir wear rows never appear in the canonical non-Souvenir output wear map.
- **Decisions appended:** `D-RECIPE-FIRST-OUTPUT-IDENTITY-001`, `D-RECIPE-FIRST-PROBABILITY-001`, `D-OUTPUT-WEAR-MAPPING-001`, `D-TRADEUP-WEAR-ROW-MIGRATION-001`.
- **Next authorized phase:** Phase 16B RecipeFamily + Structural Finish Index + Lazy Generator + Finish-Level Geometry (OFFLINE ONLY, production diff empty, no production refactor of `tradeup_engine.py`).

---

## Phase 16A-R3 Eligibility Evidence Reconciliation (2026-09-01)

Authoritative Phase 16B pinned counts under exact identity + valid next-rarity output-finish gates: C=`38/44/86/44/76/44/63/44`; K<=3 family counts=`310061/485342/3717221/485342/2556526/485342/1447236/485342`; total=`9,972,412`. Earlier metadata-only counts and the written 13,947,034 total are superseded historical evidence. No production code change.

---

## Phase 16B Structural Core Complete (2026-09-01)

`PHASE_16B_RECIPE_FAMILY_GEOMETRY_COMPLETE` on `feature/recipe-first-family-geometry`. Offline-only `StructuralOutputFinishIndex`, `RecipeFamily`, exact eligibility, analytic counts, lazy deterministic generation, and finish-level exact-Fraction geometry implemented. Pinned evidence: 16868 wear rows, 2148 finishes, C=`38/44/86/44/76/44/63/44`, K<=3 total `9,972,412`. Production scanner and wear-row migration unchanged. Next: separately authorized Phase 16C.

---

## Phase 16C Static Float + Batch Pre-Screen Complete (2026-09-01)

`PHASE_16C_STATIC_FLOAT_BATCH_PRESCREEN_COMPLETE` on `feature/recipe-first-float-prescreen`: exact interval-union/Minkowski static reachability and strict SteamDT batch BUFF pre-screen implemented as isolated pre-production primitives. Full suite 3516 passed / 23 skipped / 1 warning. Production final valuation/scanner/cache/budget and `D-TRADEUP-WEAR-ROW-MIGRATION-001` unchanged.

---

## Phase 16D Economics + Ranking + Targeted Plan Complete (2026-09-01)

`PHASE_16D_ECONOMICS_RANKING_TARGETED_PLAN_COMPLETE` on `feature/recipe-first-economics-ranking`: immutable strict-BUFF price evidence; exact per-input identity/float evidence; Decimal/Fraction optimistic/base/conservative economics; deterministic seven-key streaming Top-2; and exact <=10 targeted goods plan with one active family. `update_time` is opaque diagnostics, never chronological ranking authority. Exact static reachability is a gate/structured evidence, not a threshold-margin scalar. Offline/pre-production only; scanner remains goods-first; final valuation and `D-TRADEUP-WEAR-ROW-MIGRATION-001` unchanged. Next: separately authorized Phase 16E.

---

## Phase 16E Family-Constrained Concrete Search + Opt-In Orchestrator (2026-09-01)

`PHASE_16E_FAMILY_CONCRETE_OPTIN_ORCHESTRATOR_COMPLETE` on `feature/recipe-first-concrete-orchestrator`: dedicated family-count-preserving bounded enumerator reusing `RecipeEnumerationConfig(2,256)`; new `ConcreteFamilyTradeupResults` from Phase 16B finish geometry + canonical float/wear helpers bypassing the legacy wear-row probability bug; offline opt-in `RecipeFirstScannerOrchestrator` that reuses existing identity/intrinsic/enrichment, `RunScopedValuationSession`, strict SteamDT-BUFF valuation, `OpportunityMetrics`, and `RiskFilterConfig` unchanged. `enabled=False` by default; no current production caller imports the new modules. Goods-first scanner, final valuation path, defaults 5/60, enumeration 2/256, and `D-TRADEUP-WEAR-ROW-MIGRATION-001` remain unchanged. Next: separately authorized Phase 16F.

## Phase 16F — One bounded read-only recipe-first BUFF interface validation

Validated the recipe-first acquisition interface against the anonymous
BUFF sell-order endpoint under a `1 <= hard_request_count <= 10`
hard bound and 2-second sequential pacing. Classification was
`validated` from one live attempt; no SteamDT, Discord, Redis,
PostgreSQL, scheduler, or Phase 15C campaign work was issued.
The recipe-first production switch remains OFF. The legacy
goods-first scanner continues to be the production path.
