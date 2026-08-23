# Phase 13N-3A — BUFF Identity Source Revalidation (Validation)

## Validation Strategy

Two concentric rings. The first ring validates the spec trilogy itself; the second ring validates the repository state after the spec is written and AI context updates are applied.

The phase is research/evidence-only. No implementation. No production code changes.

---

## Ring 1 — Spec trilogy integrity

### R1.1 Spec files present

`specs/2026-08-22-buff-community-identity-revalidation/` must contain exactly `plan.md`, `findings.md`, `decision.md`, `validation.md`.

### R1.2 Recommendation is one of {BLOCKED, PROVISIONAL_COMMUNITY_CATALOG_ACCEPTABLE, MORE_EVIDENCE_REQUIRED}

`decision.md` must contain a section titled "Recommendation" that names exactly one of the three options.

### R1.3 Named candidate source

If the answer is `PROVISIONAL_COMMUNITY_CATALOG_ACCEPTABLE`, the recommendation must name a **specific** repository, file path, commit SHA, and file SHA-256.

### R1.4 All ten criteria are addressed

`findings.md` must contain a "Criteria Checklist" section addressing each of the ten items in section 18 of the phase prompt, with explicit ✓ / ⚠ / ✗ marking and rationale.

### R1.5 Independence analysis is explicit

`findings.md` must contain a "Dependency map" or equivalent that shows which sources are derived and which are independent. Agreement between derived and upstream sources must be labeled "consistency comparison" not "independent verification".

### R1.6 Licensing assessed for every source

`findings.md` must contain a "Licensing" section that reports the license of every candidate source and states what is unclear if any.

### R1.7 Cross-source numerical analysis

`findings.md` must contain quantitative cross-source metrics for at least the independent pair (EricZhu-42 vs ModestSerhat). Disagreement samples must be reported.

### R1.8 Spot-check across categories

`findings.md` must contain a "Spot Checks" section that exercises at least one normal weapon, one knife (★), one rare/special item, one StatTrak™, one Souvenir, one sticker, one older item, one knife Fade, and one or more cases.

### R1.9 Sentinel handling identified

`findings.md` must explicitly report the count of `-1` sentinels in EricZhu-42 and what they represent.

### R1.10 First-party BUF evidence classified

`findings.md` must contain a "First-Party BUF Evidence" section that classifies each candidate as one of {VERIFIED_PUBLIC_CONTRACT, PUBLIC_BUT_UNDOCUMENTED, AUTH_REQUIRED, HISTORICAL_ONLY, UNVERIFIED}.

### R1.11 `D-IDENTITY-006` proposed wording

If the recommendation is `PROVISIONAL_COMMUNITY_CATALOG_ACCEPTABLE`, `decision.md` must include a `D-IDENTITY-006` entry with full wording matching the repository's decision-log style.

### R1.12 Previous decisions explicitly preserved

`decision.md` must state that `D-IDENTITY-001` through `D-IDENTITY-005` are not modified and remain historically accurate.

### R1.13 Out-of-scope section

`decision.md` must enumerate the forbidden outcomes (concrete resolver implementation, project-tree mapping file in this phase, Protected Core modification, browser automation, cookie scraping, anti-bot bypass, runtime network I/O).

### R1.14 Recommended next phase section

`decision.md` must include a "Recommended Next Phase" section that describes Phase 13N-3B (offline snapshot builder + tests) without implementing it.

---

## Ring 2 — Repository state

### R2.1 `git diff --check` must be clean

No whitespace errors or merge conflicts.

### R2.2 `git status --short` scope

Must show only:

- The four new spec files under `specs/2026-08-22-buff-community-identity-revalidation/`
- Optional: research artifacts under `research/identity_revalidation/` (clearly non-production)
- Optional: AI context updates under `docs/ai-context/`

No `app/`, `tests/`, `scripts/` modifications.

### R2.3 No Protected Core file path appears in `git diff --name-only`

Protected Core (per `docs/ai-context/ARCHITECTURE_STATE.md`):

- `app/services/tradeup_engine.py`
- `app/services/valuation_service.py`
- `app/services/live_recipe_valuation.py`
- `app/services/ev_service.py`
- `app/services/risk_filter.py`
- `app/services/recipe_solver.py`
- `app/services/market_scan_service.py`
- Phase 12 BUF domain modules
- `app/clients/buff_client.py` (legacy skeleton)
- `app/services/buff_listing_provider.py`
- `app/clients/buff_anonymous_listing_client.py`
- SteamDT client/core, SteamApis modules, metadata providers.

### R2.4 `BuffItemIdentity` unchanged

Read `app/services/buff_item_identity.py`. Assert exactly `BuffItemIdentityValidationError`, `BuffItemIdentity`, `BuffItemIdentityResolver` are exported; assert forward-only `resolve(market_hash_name) -> BuffItemIdentity | None` signature is unchanged; assert no concrete resolver exists.

### R2.5 `BuffListing.market_hash_name` unchanged

Read `app/services/buff_listing_provider.py`. Assert `market_hash_name=None` is still hardcoded at the construction site.

### R2.6 `BuffHttpClient.get_goods_info` still raises `NotImplementedError`

Read `app/clients/buff_client.py`. Assert `BuffHttpClient.get_goods_info` still raises `NotImplementedError(UNCONFIRMED_MAPPING_ERROR)`.

### R2.7 `BuffListingCandidateAdapter` unchanged

Read `app/services/buff_listing_candidate_adapter.py`. Assert the rejection vocabulary is unchanged.

### R2.8 `TradeUpInputEnrichment` unchanged

Read `app/services/trade_up_input_enrichment.py`. Assert the rejection vocabulary is unchanged.

### R2.9 BUF API notes TODO #5 still unchecked

Read `docs/BUFF_API_NOTES.md`. Assert the goods-info endpoint checkboxes are still unchecked.

### R2.10 No new production resolver exists

`find . -path './app' -name '*.py' -newer <cutoff>` (or equivalent) must not contain any new resolver module.

### R2.11 Research artifacts do not import from `app/`

`grep -r 'from app' research/identity_revalidation/` must return zero results.

### R2.12 AI context updates reflect the decision

If the recommendation is `PROVISIONAL_COMMUNITY_CATALOG_ACCEPTABLE`:

- `docs/ai-context/DECISION_LOG.md` contains the new `D-IDENTITY-006` entry.
- `docs/ai-context/PROJECT_CONTEXT.md`, `ARCHITECTURE_STATE.md`, and `DEVELOPMENT_HANDOFF.md` mention identity source revalidated and implementation pending.

If the recommendation is `BLOCKED`, AI context files do not need updates.

---

## What Evidence is Accepted

- Repository file content (read directly from disk).
- Documentation (`docs/BUFF_API_NOTES.md`, `docs/BUFF_ANONYMOUS_READONLY_NOTES.md`, `docs/BUFF_LISTING_NOTES.md`, `docs/ai-context/DECISION_LOG.md`).
- Code analysis (source listings, grep results, frozen contracts).
- Existing empirical probe outcomes (`docs/BUFF_ANONYMOUS_READONLY_NOTES.md`, 2026-08-20).
- Public GitHub repositories and their raw JSON content.
- Public GitHub commit SHAs and dates via the GitHub API.
- Decision records (`D-IDENTITY-001` through `D-IDENTITY-005`, `D-AUTH-001`, `D-BUFF-001/002/003`).
- Analysis output from `research/identity_revalidation/scripts/analyze.py`.

## What Evidence is Rejected

- **Live BUF HTTP probes.** Per `D-AUTH-001` and `D-BUFF-001`, all live probes must be explicitly authorized, anonymous, one-request, no auth/cookie, gated by env flag. No authorization for a goods-info probe has been granted. Any claim about live BUF behavior is rejected.
- **Invented endpoints, signatures, parameters, fields.** Per `docs/BUFF_API_NOTES.md:107-118`.
- **Treating TimofeyIvanenko as independent evidence.** It is derived from EricZhu-42 + ModestSerhat + ByMykel. Agreement with EricZhu/ModestSerhat is "consistency comparison", not "independent verification".
- **Speculation about what a BUF endpoint returns.**
- **Browser automation, cookie scraping, anti-bot bypass.** All forbidden by CLAUDE.md standing rules.
- **Hardcoding secrets, tokens, webhook URLs.** Not present in this phase, but still forbidden.

## Why the Conclusion is Reliable

The recommendation `PROVISIONAL_COMMUNITY_CATALOG_ACCEPTABLE` (specifically for EricZhu-42) is reliable because:

1. **All 10 criteria from the phase prompt are met** (with one ⚠ on attribution, which is manageable).
2. **Cross-source independent agreement is 99.997%** (34,272 of 34,273 overlapping keys agree exactly).
3. **Internal source quality is high:** 0 collisions, deterministic exact mapping, fully reproducible.
4. **Licensing is clear:** CC-BY-4.0 is a permissive license with attribution only.
5. **Reproducibility is established:** commit SHA `093adde1f9f3b0a5fd14957cd52fb988154251c3` and file SHA-256 `a7f370a61dd34f7d206e0372f6806cbcb936e1ba89e33f48bbb89adaa273d72f` are both captured.
6. **The recommendation is bounded:** provisional, version-pinned, offline, attribution-preserving, fail-closed. Not a reversal of the prior decisions; an addition to them.
7. **Previous decisions are preserved:** `D-IDENTITY-001` through `D-IDENTITY-005` remain historically accurate and unmodified.
8. **Runtime is offline:** zero network I/O; refresh is manual and version-controlled.
9. **No fuzzy inference:** exact-string equality only.
10. **No protected module is modified** by this phase.

## Acceptance Checklist

- [ ] R1.1 spec files present
- [ ] R1.2 recommendation is one of the three
- [ ] R1.3 named candidate source (if applicable)
- [ ] R1.4 all ten criteria addressed
- [ ] R1.5 independence analysis explicit
- [ ] R1.6 licensing assessed for every source
- [ ] R1.7 cross-source numerical analysis
- [ ] R1.8 spot-check across categories
- [ ] R1.9 sentinel handling identified
- [ ] R1.10 first-party BUF evidence classified
- [ ] R1.11 `D-IDENTITY-006` proposed (if applicable)
- [ ] R1.12 previous decisions preserved
- [ ] R1.13 out-of-scope section present
- [ ] R1.14 recommended next phase section present
- [ ] R2.1 `git diff --check` clean
- [ ] R2.2 `git status --short` scope correct
- [ ] R2.3 no Protected Core diff
- [ ] R2.4 `BuffItemIdentity` unchanged
- [ ] R2.5 `BuffListing.market_hash_name` still `None`
- [ ] R2.6 `BuffHttpClient.get_goods_info` still raises `NotImplementedError`
- [ ] R2.7 `BuffListingCandidateAdapter` unchanged
- [ ] R2.8 `TradeUpInputEnrichment` unchanged
- [ ] R2.9 BUF API notes TODO #5 still unchecked
- [ ] R2.10 no new production resolver exists
- [ ] R2.11 research artifacts do not import from `app/`
- [ ] R2.12 AI context updates reflect decision

## Failure Handling

If any ring fails, the implementation phase MUST NOT commit. The failure must be reported with the failing assertion and the offending source location. Do not retry with relaxed thresholds; the design numbers and contract shapes are the contract.