# Phase 13A Step 2M-A2 — Plan

## 1. Freeze the provider composition contract

- Keep `get_steamdt_market_data()` and `select_buff_output_price()` as the only market-data and BUFF-selection authorities.
- Adapt the selected gross sell price into the existing `PriceQuote` / `PriceLookupResult` models with fixed source `steamdt:buff` and `raw=None`.
- Preserve the existing SteamDT batch input semantics: strip, drop blank names, and stable-deduplicate by first canonical occurrence.
- Define deterministic per-item failure ordering and safe error strings.

## 2. Add fake-only tests

- Pin the provider public API, async method signatures, existing generic result types, source, Decimal precision, and key/name alignment.
- Cover single success/failure, exact A1 policy reuse, no bid/platform fallback, batch canonicalization, sequential calls, middle-item failure isolation, and process-control propagation.
- Add static boundaries proving no concrete client/network, env/key, retry/task/concurrency, SteamApis, cache/Redis, valuation/EV/ROI/risk, fee, purchase/listing, scheduler, or runtime wiring.

## 3. Implement the standalone provider

- Inject only the existing narrow `SteamDTMarketDataClient` and borrow it.
- Compose aggregate fetch → A1 selector → generic quote for single lookups.
- Process canonical unique batch names sequentially through that same single-item path.
- Produce no quote for failures; append aligned missing/error entries and continue ordinary failures.
- Preserve process-control failures without returning partial results.

## 4. Document the A2 seam

- Add a concise section to `docs/STEAMDT_API_NOTES.md` covering fixed provenance, project CNY interpretation, batch semantics, safe failures, and the offline/unwired boundary.

## 5. Validate and audit offline

- Run all required focused suites, full pytest, Ruff, Mypy, and whitespace checks.
- Audit exactly six approved paths and record observed results in `validation.md`.
- Leave changes unstaged and uncommitted; do not push, run live smokes, wire valuation runtime, or start Step 2M-A3.
