# Phase 13M-0 — Production Scanner Orchestration Architecture Review (Plan)

## Status

- Design-only research phase. No code, no scanner, no scheduler, no BUFF calls, no modifications to existing modules.
- Date: 2026-08-22.
- Branch: `feature/steamdt-cache-rate-limit`.
- Anchors: `D-IDENTITY-003`, `D-ENRICH-001`, `D-ADAPTER-004`, `D-VALIDATION-001`, `D-MIGRATION-002`, Phase 13D-0 / 13E-0 / 13I-3 / 13K-1 / 13L-0.

## Decisions Locked In This Review (from intake and Q&A)

1. **Scanner orchestration boundary:** **B — new standalone orchestration module** (`app/services/scanner_orchestration.py`). The frozen canonical path is composed by a thin coordinator that wires the four frozen seams and never reaches back into them.
2. **Scheduling model:** **Periodic scan** — a single recurring tick with a configurable interval. Manual trigger is explicitly deferred; event-driven ingestion is explicitly out of scope for V1.
3. **Cache ownership:** **Per-cache module ownership.** Listing, metadata, valuation, and identity each own their own module, keyspace, TTL, invalidation, and observability. Cross-cache coordination is by message, not shared state.
4. **Next implementation phase:** **none.** The spec recommends no follow-on implementation phase. Production wiring remains blocked on a verified identity bridge (`D-IDENTITY-003`).

## Review Scope

The review covers five design-only surfaces. It does not introduce code, does not invent endpoints, does not assume any live wiring, and does not modify any existing module.

1. Scanner orchestration boundary.
2. Scheduling model.
3. Cache ownership.
4. Opportunity lifecycle.
5. Failure handling.

## Research Findings

### F-1 — Frozen canonical path

The repository has reached a stable four-seam composition:

```
BuffListingProvider
        |
        v
BuffListingCandidateAdapter
        |
        v
TradeUpInputCandidate
        |
        v
TradeUpInputEnrichment
        |
        v
InputItem
        |
        v
trade-up engine
        |
        v
EV / ROI / Risk
```

Frozen decisions:

- `D-ADAPTER-004` — adapter must route through enrichment.
- `D-ENRICH-001` — canonical candidate → `InputItem` seam.
- `D-VALIDATION-001` — synthetic validation protects the seam.
- `D-MIGRATION-002` — intrinsic flags must survive the adapter.
- `D-IDENTITY-003` — no verified identity source; resolver stays abstract.

There is **no** production scanner orchestration module today. `market_scan_service` exists but is unrelated to the canonical seam composition.

### F-2 — Existing scheduler surface

`APScheduler` is in the dependency surface but is wired only to a mock BUFF pipeline. No production scanner job exists. No scheduler entrypoint exists for the canonical seam. `Docker Compose` ships with `DRY_RUN=true`; production scheduling is not yet a target.

### F-3 — Existing cache surface

No application-level cache layer exists for the canonical seam today. PostgreSQL and Redis are provisioned but not wired into the BUFF/SteamDT/SteamApis valuation seam. `market_scan_service` does not own a cache.

### F-4 — Existing opportunity lifecycle

Today, no opportunity lifecycle exists. Phase 12 trades were synthetic fixtures only. There is no notion of "listing observed → opportunity result" beyond a one-shot synthesis path. The lifecycle design here is the *future* shape, not a current module.

### F-5 — Failure handling posture

External API clients already carry `timeout`, `retry`, `rate limit`, error classification, and response validation (per project rule). Failure handling design here specifies the *orchestration-level* responsibilities on top of those primitives.

## Architecture Decision

### Scanner orchestration boundary — B (new orchestration module)

`app/services/scanner_orchestration.py` is a thin coordinator. It owns:

- A single `ScannerOrchestrator` entrypoint with a `run_once()` method.
- Composition of the four frozen seams by dependency injection (no global state).
- Lifecycle hooks for observability, metrics, and structured logging (no secrets).
- Configuration surface read from a single `ScannerOrchestratorConfig` frozen dataclass.
- A periodic scheduler adapter (the only reference to `APScheduler`) that calls `run_once()` on a configured interval.

It does **not** own:

- BUFF endpoint construction.
- Identity derivation.
- SteamApis WebSocket subscription.
- SteamDT request policy.
- The four frozen seams themselves.
- Any cache.
- Any database write.

### Scheduling model — periodic scan

A single recurring tick driven by `APScheduler`. Interval is configurable; default is the documented BUFF rate-limit posture. Manual trigger is exposed only as a function (not an HTTP endpoint) for ops/debug. Event-driven ingestion is out of scope.

### Cache ownership — per-cache module ownership

Four cache modules, each with a single responsibility:

- `app/services/listing_cache.py` — BuffListing observation cache. Key: `(source, goods_id, listing_id)`. TTL: configurable. Invalidation: time-based.
- `app/services/metadata_cache.py` — `TradeUpInputMetadata` cache. Key: `market_hash_name`. TTL: configurable, longer than listing TTL. Invalidation: time-based.
- `app/services/valuation_cache.py` — output valuation cache. Key: `output_market_hash_name + collection + rarity`. TTL: configurable, shorter than metadata TTL. Invalidation: time-based.
- `app/services/identity_cache.py` — `BuffItemIdentity` cache (only consulted when a verified source exists). Key: `market_hash_name`. TTL: configurable. Invalidation: time-based.

Each module exposes a single protocol-typed accessor used by the orchestrator and the candidate adapter. Cache modules never import each other; cross-cache coordination is by orchestrator message, not shared state.

### Opportunity lifecycle

Five stages, each owned by exactly one module:

1. **Listing observed** — `BuffListingProvider` (or its successor). Output: `Sequence[BuffListing]`.
2. **Candidate conversion** — `BuffListingCandidateAdapter`. Output: `Sequence[TradeUpInputCandidate | CandidateAdapterRejection]`.
3. **Enrichment** — `TradeUpInputEnricher` (`D-ENRICH-001`). Output: `Sequence[TradeUpEnrichedInput | TradeUpEnrichmentRejection]`.
4. **Trade-up evaluation** — `trade_up_engine` (existing). Output: `Sequence[OpportunityResult]`.
5. **Opportunity result** — owned by the orchestrator's emit step. Output: structured log + (future) alert dispatch. No purchase, no auto-buy.

### Failure handling

Four categories, each owned by exactly one module:

- **Provider failure** — owned by the `BuffListingProvider` and its underlying client. Surface: typed exception. Orchestrator catches and routes to a structured log + metric. No fallback to a different source.
- **Enrichment rejection** — owned by `TradeUpInputEnricher`. Surface: `TradeUpEnrichmentRejection` (already typed). Orchestrator logs and continues.
- **Valuation failure** — owned by the existing valuation service. Surface: typed exception. Orchestrator logs and continues. No silent zeroing.
- **Stale data** — owned by each cache module via TTL. Orchestrator never overrides a cache's freshness decision; stale data is a cache concern, not an orchestrator concern.

No retry with backoff inside the orchestrator; the underlying clients already own their retry posture.

## Rejected Alternatives

### Boundary alternatives

- **A. Extend `market_scan_service`** — rejected. `market_scan_service` is unrelated to the canonical four-seam composition; tangling orchestration into it would couple concerns and force future migration of unrelated functionality.
- **C. Provider-driven pipeline runner** — rejected. Collapses two distinct abstractions (orchestration and pipeline composition) into one, blurring the boundary between "who runs the pipeline" and "how the pipeline is composed". A future pipeline runner can be added; orchestration remains separate.

### Scheduling alternatives

- **Event-driven ingestion** — rejected. No event source exists; no verified push channel for BUFF or SteamApis; introducing event-driven design would require inventing a source. Out of scope.
- **Manual trigger only** — rejected. The project explicitly aims at a 24h unattended scanner; a manual trigger alone defeats that goal. The orchestration module still exposes a manual `run_once()` callable, but the primary mode is periodic.

### Cache ownership alternatives

- **Central cache registry** — rejected. A single cache module would leak cross-concern invalidation rules and force every cache to share a key namespace. This contradicts the frozen seam-per-concern pattern.
- **Lazy / just-in-time caches** — rejected. Lazy creation defers but does not solve ownership; it produces an inconsistent cache layer where some caches have a module and others have inline dictionaries. Either commit to per-cache modules from day one, or defer the entire cache layer.

## Future Implementation Order

The recommended order assumes `D-IDENTITY-003` becomes unblocked at some point. Until then, none of these are actionable.

1. **Pre-implementation gate.** Verify identity bridge (Source D manual offline mapping under strict constraints, or Source A BUF native metadata under independent verification).
2. **Cache layer** — `metadata_cache`, `valuation_cache`, `listing_cache`, `identity_cache`. Each is independently testable and stands alone without the orchestrator.
3. **Orchestrator skeleton** — `ScannerOrchestrator.run_once()` with the four-seam composition, no scheduler.
4. **Periodic scheduler adapter** — wires `APScheduler` to `run_once()`.
5. **Observability** — structured logs, counters for each lifecycle stage, counters per failure category.
6. **Synthetic end-to-end** — same path as production but with synthetic `BuffListingProvider`; gates against `D-VALIDATION-001`.
7. **Live integration smoke** — gated, one-request, anonymous, schema-only. Not a commit gate.

Each step is independent and gated by tests. No step assumes later steps exist.

## Remaining Blockers

- **Primary:** verified `market_hash_name ↔ BUFF goods_id` source (`D-IDENTITY-003`). The orchestration module is a coordinator over seams; without identity, the enrichment seam rejects every candidate and the orchestrator runs an empty cycle.
- **Secondary:** intrinsic flag source on `BuffListing` (`D-MIGRATION-002`). The adapter currently hard-codes `stattrak=False`, `souvenir=False`. Before any production wiring, `BuffListing` (or its successor) must expose the flags.
- **Tertiary:** no production scanner orchestration today. The orchestration module is design only; no implementation exists. This phase does not create it.

## Out of Scope (frozen here)

- No scanner implementation.
- No scheduler implementation.
- No BUFF endpoint.
- No identity resolver implementation.
- No database schema.
- No webhook.
- No purchase logic.
- No modification to existing identity / candidate / enrichment / adapter modules.
- No cache implementation.
- No orchestration module code in this phase.

## Critical Files

Add (this design phase, no implementation):

- `specs/2026-08-22-production-scanner-orchestration-review/plan.md`
- `specs/2026-08-22-production-scanner-orchestration-review/requirements.md`
- `specs/2026-08-22-production-scanner-orchestration-review/validation.md`

No other path may change in this phase.

## Verification

```bash
git diff --check
git diff --name-only
git status --short
```

Acceptance requires:

- `git diff --check` clean.
- `git status --short` shows only the three new spec files.
- No `app/`, `tests/`, or Protected Core path modified.
- No commit unless separately requested.