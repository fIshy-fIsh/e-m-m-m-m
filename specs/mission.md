# CS2 BUFF Trade-up Opportunity Scanner — Mission

## Purpose

Build a backend-first system that continuously discovers CS2 trade-up opportunities from BUFF marketplace listings, evaluates each opportunity against the canonical trade-up rules and a SteamDT-based output valuation, and surfaces only opportunities that satisfy explicit quality thresholds. The V1 long-term product goal is continuous, unattended operation with human-readable alerting.

## Problem Statement

Manual trade-up opportunity discovery is slow, inconsistent, and error-prone. Traders need a system that can:

- observe BUFF listings continuously,
- normalize fragmented market and metadata inputs,
- compute realistic trade-up outcomes and downside,
- surface only opportunities that meet explicit quality thresholds.

## Target Outcome for V1

V1 should deliver a scanner that:

1. fetches candidate BUFF material listings through the anonymous read-only sell-order path,
2. resolves listing identity through a pinned offline community catalog using exact fail-closed matching,
3. maps listings to canonical CS2 metadata (collection, rarity, float range) needed for trade-up computation,
4. computes the bounded multi-recipe enumeration over the candidate pool (default 2 candidates / 256 states, hard bounds 1..6 candidates / 1..1024 states with `states >= candidates`),
5. computes output pool, output probabilities, output float ranges, EV, ROI, worst-case loss, and profit probability for each bounded candidate,
6. values outputs through the strict SteamDT-BUFF aggregate sell price path (no fallback, no bid substitution, no metadata-zero reuse),
7. filters weak opportunities using configurable risk rules,
8. emits structured opportunity reports for human review,
9. does **not** place purchases or automate account actions.

The current production scanner is a **manual one-shot CLI**. Continuous scheduling, Discord opportunity delivery, and database persistence are **not** part of the current production capability and are documented under "Deferred" in `specs/roadmap.md`.

## Product Principles

- **Read-only market interaction in V1**: observe and analyze, do not trade.
- **Exact identity binding**: pinned offline community catalog only; no derived / inferred identity.
- **Deterministic calculations**: every alert must be explainable from stored inputs and formulas.
- **No fallback valuation**: a missing or unusable BUFF aggregate sell price fails the affected output; there is no second-platform substitute, no bid substitution, and no metadata-zero reuse.
- **No probability renormalization**: solver-computed probabilities are the source of truth.
- **Operational safety**: no captcha bypass, no anti-risk-control evasion, no browser automation for purchases, no non-official evasion techniques.
- **Traceability**: every opportunity should be reproducible from persisted market snapshots and metadata versions.
- **Configurable quality bar**: thresholds should be adjustable without code rewrites.

## Primary Users

- quantitative CS2 skin traders,
- operator of a private scanning service,
- future automation layer maintainers who need clean domain boundaries.

## V1 In Scope

- BUFF anonymous market material listing ingestion through the documented anonymous read-only sell-order path
- pinned offline community-catalog identity resolution (exact fail-closed)
- CS2 metadata matching and normalization
- bounded multi-recipe enumeration (default 2 candidates / 256 states)
- trade-up probability and economics engine
- strict SteamDT-BUFF output valuation (exact, case-sensitive, single-platform)
- risk filter / opportunity scoring
- manual one-shot CLI scanning
- observability and retry handling sufficient for unattended read-only operation

## Explicitly Out of Scope for V1

- automatic buying
- automatic trading
- automatic login flows
- cookie extraction
- captcha bypass
- BUFF risk-control bypass
- browser-simulated purchasing
- non-official anti-detection or evasion techniques
- portfolio management or capital allocation automation
- invented BUFF endpoints, signatures, request parameters, or response field mappings
- fallback valuation (second-platform substitute, bid substitution, metadata-zero reuse)
- probability renormalization

## Success Criteria

The project is successful when it can run the bounded multi-recipe one-shot scanner, reproduce trade-up analyses from live BUFF listings and SteamDT-BUFF aggregate sell prices, and notify only opportunities that satisfy defined EV and risk thresholds without performing any market action.

The current scanner satisfies this criterion in its manual one-shot form. Continuous scheduling and real Discord delivery are roadmap items, not current capabilities.

Phase 16A freezes a recipe-first pre-screen discovery architecture that preserves the V1 read-only / strict BUFF valuation / no-fallback contracts and reuses the mature downstream calculation/safety stack. Implementation of the new production path (Phases 16B–16F) is separately gated; no representative campaign runs under the new path until Phase 16F passes.