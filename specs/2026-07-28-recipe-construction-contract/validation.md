# Phase 12E4D0 — Recipe Construction Contract Validation

## Focused regression

```bash
py -3.13 -m pytest tests/test_recipe_solver.py
py -3.13 -m pytest tests/test_pipeline_service.py
py -3.13 -m pytest tests/test_ev_service.py
py -3.13 -m pytest tests/test_risk_filter.py
```

Acceptance:

- Construction returns the exact immutable public type with ordered tuples and derived cost.
- Construction executes metadata matching, selection, output-pool construction, and trade-up geometry but no EV/ROI/profit metrics or risk evaluation.
- Empty-result and exception behavior match the previous solver construction block.
- `solve_recipes()` delegates once, evaluates each construction once, and retains its exact signature, return shape, `RecipeCandidate`, ordering, hash, metrics, risk, and failure behavior.
- Pipeline tests pass unchanged.

## Full repository validation

```bash
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
```

All commands must pass. Core trade-up, EV, probability, and risk behavior remains covered by existing tests.

## Existing dry-runs

```bash
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
```

Acceptance:

- Existing recipe count and evaluated `RecipeCandidate` output remain unchanged.
- Metrics, risk, valuation replacement, hash, alerts, and scheduler aggregates remain unchanged.
- The dry-runs do not import or invoke a Phase 12E4D BUFF recipe integration because none is created.

## Scope and whitespace

```bash
git diff --check
git diff --name-status
git diff --stat
git status --short
```

Exactly six repository paths may be changed:

```text
app/services/recipe_solver.py
README.md
tests/test_recipe_solver.py
specs/2026-07-28-recipe-construction-contract/plan.md
specs/2026-07-28-recipe-construction-contract/requirements.md
specs/2026-07-28-recipe-construction-contract/validation.md
```

Confirm no change to protected application modules, callers, fixtures, roadmap, BUFF integrations, clients, cache, config, environment, Docker/database, Discord, or deployment files. Report Windows LF-to-CRLF warnings if observed, but do not rewrite line endings when no actual whitespace error exists.

## Safety and external activity

Verify and report:

- no BUFF request or authentication activity;
- no SteamDT request;
- no Redis connection;
- no network or external valuation provider call;
- no alert sent by the new construction API;
- no automatic purchase, login, Cookie, crawler, captcha, or risk-control bypass behavior;
- no hardcoded secret or endpoint;
- no commit or push;
- no Phase 12E4D implementation or next-phase work.

## Suggested commit message

```text
separate recipe construction from evaluation
```

Do not create that commit until separately authorized.
