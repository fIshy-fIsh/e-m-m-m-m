# Phase 13I-0 — Trade-up Metadata Enrichment Boundary Review — Plan

## Goal

Determine the stable metadata boundary required between `TradeUpInputCandidate`
and the existing `InputItem` / trade-up engine. This is a design review only.

## Constraints (from the task brief)

- Design review only. No implementation.
- Do not add a metadata provider.
- Do not modify `InputItem`.
- Do not modify the trade-up engine.
- Do not connect BUFF / SteamDT / SteamApis.

## Approach

1. Survey the four files the task brief asks us to inspect.
2. Tabulate which fields each side requires and supplies today.
3. Propose the recommended boundary under three headings: `A` (candidate),
   `B` (metadata enrichment layer), `C` (identity layer).
4. State the architecture decision and its rationale.
5. Document limitations, TODOs, and what the next phase (`13I-1`) would do.

## Sources inspected

- [app/services/trade_up_input_candidate.py](app/services/trade_up_input_candidate.py) — `TradeUpInputCandidate`.
- [app/services/tradeup_engine.py](app/services/tradeup_engine.py) — `InputItem`,
  `OutputCandidate`, `TradeupResult`, `calculate_tradeup_results`.
- [app/services/recipe_solver.py](app/services/recipe_solver.py) —
  `RecipeSolverConfig`, `ConstructedRecipe`, `ConstructedRecipeSelection`,
  `RecipeCandidate`, `solve_recipes`, `value_live_recipes`, `build_recipe_hash`.
- [app/services/metadata_models.py](app/services/metadata_models.py) —
  `SkinMetadata`, `CollectionMetadata`, `OutputCandidateBuildResult`,
  `RarityOrder`.
- [app/services/trade_up_pipeline.py](app/services/trade_up_pipeline.py) —
  synthetic metadata adapter from 13H-0.
- [app/services/buff_item_identity.py](app/services/buff_item_identity.py) —
  `BuffItemIdentity`, `BuffItemIdentityResolver`.
- [app/services/buff_listing.py](app/services/buff_listing.py) and
  [app/services/buff_listing_provider.py](app/services/buff_listing_provider.py) —
  BUFF side.
- [app/services/market_scan_service.py](app/services/market_scan_service.py) —
  `CandidateListing` (existing in-app candidate model).

## Tasks

- T1. Field table: `InputItem` ↔ candidate ↔ metadata ↔ identity.
- T2. Boundary recommendation per the three AskUserQuestion answers.
- T3. Architecture decision and rationale.
- T4. Limitations and what must NOT be inferred.
- T5. Next-phase sketch (without writing it as implementation).