# Phase 12E4B0 — Validation

Run:

```bash
py -3.13 -m pytest tests/test_buff_listing.py
py -3.13 -m pytest tests/test_buff_listing_parser.py
py -3.13 -m pytest tests/test_buff_listing_facts.py
py -3.13 -m pytest tests/test_buff_listing_eligibility.py
py -3.13 -m pytest tests/test_buff_listing_qualification.py
py -3.13 -m pytest tests/test_buff_listing_qualification_integration.py
py -3.13 -m pytest tests/test_buff_listing.py tests/test_buff_listing_parser.py tests/test_buff_listing_facts.py tests/test_buff_listing_eligibility.py tests/test_buff_listing_qualification.py tests/test_buff_listing_qualification_integration.py
py -3.13 -m pytest
py -3.13 -m ruff check .
py -3.13 -m mypy app
py -3.13 scripts/run_mock_pipeline.py
py -3.13 scripts/run_scheduler_once.py
py -3.13 scripts/docker_smoke_test.py
py -3.13 -m scripts.buff_listing_qualification_integration
py -3.13 scripts/buff_listing_qualification_integration.py
py -3.13 -m scripts.buff_listing_qualification_integration --listings-fixture tests/fixtures/buff/qualification_listings_v1.json --facts-fixture tests/fixtures/buff/qualification_facts_v1.json
py -3.13 scripts/buff_listing_qualification_integration.py --listings-fixture tests/fixtures/buff/qualification_listings_v1.json --facts-fixture tests/fixtures/buff/qualification_facts_v1.json
git diff --check
```

Acceptance requires:

1. Observation and candidate accept omitted/`None` goods ID and normalize valid supplied strings.
2. Blank/whitespace-only and non-string goods IDs fail with fixed safe validation.
3. Normalization, eligibility, and qualification snapshots preserve populated and legacy-null goods IDs.
4. V1 remains strict, rejects `goods_id`, and parses unchanged fixtures as `None`.
5. V2 requires a valid goods ID and preserves all pre-existing parser semantics.
6. Existing v1 fixtures are byte-unchanged and both new v2 fixtures are project-owned synthetic data.
7. Facts implementation and identity remain listing ID plus market name only.
8. Eligibility reasons and all three qualification statuses are unchanged.
9. Default integration uses v2 listings plus v1 facts and returns ordered outcomes `qualified`, `rejected`, `qualified`, `missing_facts` with counts `4/2/1/1`.
10. Explicit v1 integration also exits 0 with identical business outcomes and `goods_id=None` candidates.
11. No goods ID appears in command output; embedded goods ID in a market name triggers complete redaction.
12. Full tests, Ruff, Mypy, and all three existing dry-runs pass.
13. No BUFF or SteamDT request occurs and Redis is not used.
14. No solver or new integration path executes; pipeline and scheduler behavior remain unchanged.
15. Diff scope contains only approved files; protected modules, API notes, roadmap, and existing fixtures remain unchanged.
16. `git diff --check` reports no actual whitespace errors.
17. Nothing is committed or pushed.
