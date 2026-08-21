# Phase 13G-0 — Identity Source Decision Review — Validation

## Commands

```bash
git diff --check
git diff --name-only
git status --short
```

No Python test execution is required. This phase is a decision review.

## Acceptance

- One of A, B, C, D is selected with evidence and rejected alternatives are defended.
- No candidate source is approved for live wiring.
- The forward direction is the only verified resolver surface; reverse direction remains a future spec-only addition.
- No new endpoint, mapping, resolver backend, or production wiring is added.
- All existing modules — `BuffItemIdentity`, `BuffItemIdentityResolver`, `BuffListing`, `TradeUpInputCandidate`, the anonymous BUFF client/provider/smokes, Phase 12 BUFF, SteamDT, SteamApis, metadata, scanner, solver, trade-up engine, EV/ROI/risk, valuation, pipeline, scheduler, config, dependencies — remain unchanged.

## Observed results

Pending implementation and offline validation.
