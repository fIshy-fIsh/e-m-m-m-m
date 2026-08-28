# Phase 12D5C Plan

1. Create a standalone CLI with fake/live modes and strict validation.
2. Reuse shared safe-output helpers while preserving the existing snapshot smoke.
3. Compose the existing planner, executor, source, refresh service, in-memory cache, and cached resolver.
4. Keep fake mode deterministic and fully offline.
5. Double-gate live mode and reuse the existing SteamDT runtime, limiter, retry, parser, and single-item source.
6. Produce a complete ordered allowlisted summary with defined exit codes and cancellation cleanup.
7. Add focused integration, entrypoint, safety, ownership, and boundary tests.
8. Update the environment example and SteamDT documentation without claiming production readiness.
9. Run the complete offline validation matrix and both manual fake commands; do not run live mode.
