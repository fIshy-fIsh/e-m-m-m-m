# Phase 13M-0 — Production Scanner Orchestration Architecture Review (Requirements)

## Goal

Define — through repository-only evidence — how a future production scanner orchestration layer would compose the frozen canonical seams, schedule its work, and own its caches. No code, no scheduler, no scanner, no BUFF calls, no modification to existing modules.

## Functional Requirements

### FR-1 — Scanner orchestration boundary

- FR-1.1 The orchestrator MUST be a new standalone module at `app/services/scanner_orchestration.py`. It MUST NOT extend `market_scan_service` or any existing service.
- FR-1.2 The orchestrator MUST expose a single entrypoint `ScannerOrchestrator` with one method `run_once()` returning a structured result.
- FR-1.3 `run_once()` MUST compose the four frozen seams in this exact order, with no inlining:
  1. `BuffListingProvider` → `Sequence[BuffListing]`
  2. `BuffListingCandidateAdapter` → `Sequence[TradeUpInputCandidate | CandidateAdapterRejection]`
  3. `TradeUpInputEnricher` → `Sequence[TradeUpEnrichedInput | TradeUpEnrichmentRejection]`
  4. `trade_up_engine` → `Sequence[OpportunityResult]`
- FR-1.4 The orchestrator MUST NOT import any external API client (BUFF, SteamDT, SteamApis) directly. All input MUST arrive through `BuffListingProvider`.
- FR-1.5 The orchestrator MUST read configuration from a single frozen `ScannerOrchestratorConfig` dataclass. No module may read environment variables directly.
- FR-1.6 The orchestrator MUST emit structured logs and counters at each lifecycle stage. Logs MUST NOT contain secrets, tokens, cookies, or webhook URLs.
- FR-1.7 The orchestrator MUST NOT perform any purchase, login, bidding, or write to BUFF / SteamDT / SteamApis.

### FR-2 — Periodic scheduling model

- FR-2.1 Scheduling MUST be periodic. The default interval MUST be configurable via `ScannerOrchestratorConfig`.
- FR-2.2 The scheduler adapter MUST be the only place `APScheduler` is referenced in the orchestrator. The orchestrator itself MUST NOT import `APScheduler`.
- FR-2.3 The scheduler adapter MUST be swappable for tests: a no-op scheduler, an in-process scheduler, and the production `APScheduler` adapter MUST all satisfy the same protocol.
- FR-2.4 Manual trigger MUST be exposed as a callable (not an HTTP endpoint). The orchestrator MUST expose `run_once()` directly so ops/debug can invoke it.
- FR-2.5 Event-driven ingestion MUST be out of scope. No Kafka, Redis Streams, WebSocket subscription, or push-channel integration is part of this design.

### FR-3 — Per-cache module ownership

- FR-3.1 Each cache MUST live in its own module. The four modules are:
  - `app/services/listing_cache.py`
  - `app/services/metadata_cache.py`
  - `app/services/valuation_cache.py`
  - `app/services/identity_cache.py`
- FR-3.2 Each cache MUST expose a single protocol-typed accessor. The orchestrator MUST consume caches only through that protocol.
- FR-3.3 Each cache MUST own its own key namespace, TTL, invalidation rule, and observability surface. Cross-cache coordination MUST be by orchestrator message, not shared state.
- FR-3.4 Cache modules MUST NOT import each other. Cache-to-cache coupling is forbidden.
- FR-3.5 `identity_cache` MUST be consulted only when a verified identity source exists. Until then it MUST remain unimplemented or stubbed with `None`-returning accessors.
- FR-3.6 Cache MISS MUST fall through to the underlying provider. Cache HIT MUST NOT bypass the underlying provider's own validation.

### FR-4 — Opportunity lifecycle

- FR-4.1 The lifecycle MUST consist of exactly five stages, in order:
  1. **Listing observed** — `BuffListingProvider`.
  2. **Candidate conversion** — `BuffListingCandidateAdapter`.
  3. **Enrichment** — `TradeUpInputEnricher`.
  4. **Trade-up evaluation** — `trade_up_engine`.
  5. **Opportunity result** — orchestrator emit step.
- FR-4.2 Each stage MUST be owned by exactly one module. Cross-stage leakage is forbidden.
- FR-4.3 Each stage MUST emit a typed result with `kept` and `rejected` partitions in input order, mirroring the candidate adapter and enrichment contracts.
- FR-4.4 The final opportunity result MUST be a typed DTO. The orchestrator MUST NOT invent a return shape on top of `OpportunityResult`.

### FR-5 — Failure handling

- FR-5.1 **Provider failure** — owned by `BuffListingProvider` and its underlying client. Surface: typed exception. Orchestrator MUST catch, log, and increment a counter. No fallback to a different source.
- FR-5.2 **Enrichment rejection** — owned by `TradeUpInputEnricher`. Surface: `TradeUpEnrichmentRejection` already typed. Orchestrator MUST log and continue.
- FR-5.3 **Valuation failure** — owned by the existing valuation service. Surface: typed exception. Orchestrator MUST log and continue. No silent zeroing.
- FR-5.4 **Stale data** — owned by each cache module via TTL. Orchestrator MUST NOT override a cache's freshness decision.
- FR-5.5 The orchestrator MUST NOT introduce retry-with-backoff logic. Retry posture is owned by the underlying clients.
- FR-5.6 The orchestrator MUST distinguish "no opportunity" (legitimate empty result) from "system failure" (exception) in its return shape.

### FR-6 — Frozen contracts preserved

- FR-6.1 `BuffItemIdentity` / `BuffItemIdentityResolver` MUST remain unchanged.
- FR-6.2 `BuffListing` MUST remain unchanged.
- FR-6.3 `TradeUpInputCandidate` MUST remain unchanged.
- FR-6.4 `TradeUpInputEnricher` and its rejection vocabulary MUST remain unchanged.
- FR-6.5 `BuffListingCandidateAdapter` and its rejection vocabulary MUST remain unchanged.

## Non-Functional Requirements

- NFR-1 Repository-only evidence. Every architectural claim MUST trace to a file path already committed to the repository. No external documentation is cited.
- NFR-2 No code changes. The phase produces no `app/` or `tests/` modifications.
- NFR-3 Decision-record honesty. The plan must explicitly state which alternatives were rejected and why.
- NFR-4 Reopen prevention. The spec must list which subsequent decisions would force a reopen (verified identity source, intrinsic flag source on `BuffListing`, etc.).
- NFR-5 Frozen contracts (FR-6) MUST be cross-checked against the plan and validation files.

## Out of Scope (frozen here)

- No scanner implementation.
- No scheduler implementation.
- No BUFF endpoint.
- No identity resolver implementation.
- No database schema.
- No webhook.
- No Discord alert dispatch.
- No purchase logic.
- No manual trigger HTTP endpoint.
- No event-driven ingestion.
- No cache implementation.
- No orchestration module code in this phase.
- No modification to existing identity / candidate / enrichment / adapter / engine modules.
- No production wiring of any kind.

## Acceptance

This review passes if:

- The spec trilogy files are present at `specs/2026-08-22-production-scanner-orchestration-review/`.
- The plan, requirements, and validation files agree on the B / periodic / per-cache choices.
- All FR-* and NFR-* requirements are met.
- No commit is performed unless separately requested.