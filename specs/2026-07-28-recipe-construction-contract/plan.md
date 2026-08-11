# Phase 12E4D0 — Recipe Construction Contract Plan

1. Add a public immutable `ConstructedRecipe` model in `app/services/recipe_solver.py` with exactly ordered input, trade-up-result, and paint-seed tuples plus derived input cost.
2. Extract the existing pre-EV solver logic into `construct_recipes()` while preserving eligibility, sorting, limiting, selection, output-pool, engine, cardinality, and exception semantics.
3. Refactor `solve_recipes()` to call construction once, then calculate metrics and risk once per construction and return the unchanged `RecipeCandidate` contract.
4. Update focused solver tests for construction-only behavior, result invariants, deterministic ordering, control-flow propagation, and evaluated-wrapper compatibility.
5. Document the construction/evaluation boundary in README without wiring the pending BUFF recipe integration or changing runtime callers.
6. Run focused and full regression checks, three existing dry-runs, and exact six-path scope/security audits; leave the work uncommitted and unpushed.
