# Phase 13A Step 2J — Plan

1. Freeze the current-pool construction API, post-TTL snapshot count, completeness invariant, and fixed safe error.
2. Implement one synchronous pool snapshot followed by one call to the existing Step 2E construction authority.
3. Add compact contract, current-state, TTL/no-rollback, failure, determinism, and real offline integration tests.
4. Document the independent evaluate-current-state boundary and its separation from WebSocket/session and valuation lifecycles.
5. Run focused regressions, full quality gates, offline dry-runs, and exact-scope/security audits.
6. Leave work unstaged, uncommitted, and unpushed; do not resume Step 2G or begin Step 2K.
