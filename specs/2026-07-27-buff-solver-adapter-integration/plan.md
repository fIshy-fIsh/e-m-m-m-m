# Phase 12E4C — Plan

1. Reuse the existing offline qualification runner and exact run result without repeating fixture parsing, facts lookup, eligibility, or qualification.
2. Add a strict frozen two-field integration result and one public async runner that adapts only `QUALIFIED` results once each in source order.
3. Promote the existing safe BUFF candidate market-name renderer with no behavior change and reuse it in both manual commands.
4. Add a sibling direct/module CLI with atomic safe output and exit codes 0, 1, 2, and 130.
5. Add focused tests for filtering, ordering, duplicates, counts, fail-closed behavior, output safety, entrypoints, and runtime isolation.
6. Document the offline integration boundary, explicit exclusions, and lack of production readiness.
7. Run all requested focused/full validation, manual CLI checks, dry-runs, and exact scope audits without committing or pushing.
