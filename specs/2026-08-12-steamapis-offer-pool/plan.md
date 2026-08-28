# Phase 13A Step 2C — Plan

1. Freeze the bounded offer-pool contract, exact seven-path scope, and explicit exclusions.
2. Implement a synchronous observation-owned pool with defensive ingest, injected UTC clock, lazy TTL expiry, deterministic capacity eviction, and immutable snapshots.
3. Add source-ID provenance lookups and one on-demand candidate projection path through the existing Step 2B adapter.
4. Add focused tests for update ordering, TTL, capacity, snapshot order, provenance, projection, redaction, and architecture isolation.
5. Document the local-state boundary, run all requested validation, audit scope and safety, then stop without commit, push, or Step 2D work.
