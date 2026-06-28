# CS2 BUFF Trade-up Opportunity Scanner — Mission

## Purpose
Build a backend-first system that continuously scans BUFF marketplace listings for CS2 trade-up input materials, enriches them with CS2 collection and float metadata, computes trade-up economics and risk, filters low-quality opportunities, and sends actionable alerts to Discord.

## Problem Statement
Manual trade-up opportunity discovery is slow, inconsistent, and error-prone. Traders need a system that can:
- monitor BUFF listings continuously,
- normalize fragmented market and metadata inputs,
- compute realistic trade-up outcomes and downside,
- surface only opportunities that meet explicit quality thresholds.

## Target Outcome for V1
V1 should deliver an always-on scanner that:
1. fetches candidate BUFF material listings on a recurring schedule,
2. stores price, float, goods identifiers, and listing context,
3. maps listings to CS2 metadata needed for trade-up computation,
4. computes output pool, output probabilities, output float ranges, EV, ROI, worst-case loss, and profit probability,
5. filters weak opportunities using configurable risk rules,
6. sends Discord Webhook alerts for high-quality opportunities,
7. does **not** place purchases or automate account actions.

## Product Principles
- **Read-only market interaction in V1**: observe and analyze, do not trade.
- **Deterministic calculations**: every alert must be explainable from stored inputs and formulas.
- **Operational safety**: no captcha bypass, anti-risk-control evasion, or browser automation for purchases.
- **Traceability**: every opportunity should be reproducible from persisted market snapshots and metadata versions.
- **Configurable quality bar**: thresholds should be adjustable without code rewrites.

## Primary Users
- quantitative CS2 skin traders,
- operator of a private scanning service,
- future automation layer maintainers who need clean domain boundaries.

## V1 In Scope
- BUFF market material scanning
- CS2 metadata matching and normalization
- trade-up probability and economics engine
- risk filter / opportunity scoring
- Discord Webhook alerting
- 24h scheduled operation
- observability and retry handling sufficient for unattended operation

## Explicitly Out of Scope for V1
- automatic buying
- automatic login flows
- cookie extraction
- captcha bypass
- BUFF risk-control bypass
- browser-simulated purchasing
- non-official anti-detection or evasion techniques
- portfolio management or capital allocation automation

## Success Criteria
The project is successful when it can run continuously, produce reproducible trade-up analyses from live BUFF listings, and notify only opportunities that satisfy defined EV and risk thresholds without performing any market action.