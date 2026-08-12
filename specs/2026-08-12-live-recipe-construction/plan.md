# Phase 13A Step 2E — Plan

1. Freeze the offline construction and provenance contracts, including the confirmed solver identity gap, exact public DTOs, deterministic ordering, failure behavior, scope, and exclusions.
2. Add a source-agnostic `ConstructedRecipeSelection` and `construct_recipe_selections()` as the single authoritative construction path; retain exact `construct_recipes()` and `solve_recipes()` compatibility.
3. Add synchronous `construct_live_recipes()` composition from one immutable snapshot through Step 2D classification and exact-mode bucket construction.
4. Map solver-selected listing IDs back through the same bucket's explicit eligible bindings to ten ordered source offer IDs; fail closed on incomplete or ambiguous provenance.
5. Add focused solver compatibility and synthetic multi-collection live integration tests, including identical-economics listings and pool purchase-link joins.
6. Update only README and SteamApis market-data notes with the new offline/non-production boundary.
7. Run focused/full tests, Ruff, Mypy, three offline dry-runs, whitespace and exact-scope audits; record observed results and stop before Step 2F without commit or push.
