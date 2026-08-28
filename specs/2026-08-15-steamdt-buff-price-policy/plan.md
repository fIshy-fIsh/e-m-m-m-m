# Phase 13A Step 2M-A1 — Plan

## 1. Freeze the offline policy contract

- Treat exact, case-sensitive provider platform text `"BUFF"` as the only eligible record.
- Select only a positive finite gross `sell_price_cny` under the project-approved CNY interpretation.
- Ignore bidding fields completely because aggregate bid data does not prove that an output meets possible special order conditions.
- Fix fail-closed reason codes and their precedence for missing, duplicate, missing-price, non-finite, non-positive, and malformed input cases.

## 2. Add focused tests first

- Pin the public API, immutable result shape, exception contract, and reason vocabulary.
- Cover exact platform matching, gross sell-price preservation, ignored bids, no fallback, duplicate and missing behavior, opaque metadata preservation, input detachment, and malformed relevant values.
- Add static boundary checks for no networking, SteamApis, provider/PriceQuote, valuation/EV/ROI/risk, fee, cache/Redis, scheduler, live-smoke, or bid-field access.

## 3. Implement the pure BUFF selector

- Add one synchronous service module consuming `SteamDTMarketDataResult`.
- Return a detached `SteamDTBuffOutputPrice` containing the market name, exact `"BUFF"` platform, gross sell price, sell count, opaque platform item ID, and opaque update time.
- Raise one fixed-message `SteamDTBuffPriceSelectionError` carrying a stable `SteamDTBuffPriceSelectionReason` on every fail-closed path.
- Do not change the SteamDT client, aggregate service, generic selector/provider, `PriceQuote`, or valuation services.

## 4. Record the policy boundary

- Add a concise Step 2M-A1 section to `docs/STEAMDT_API_NOTES.md`.
- Distinguish the project CNY interpretation from an official provider guarantee.
- State that this is aggregate gross sell-price selection, not executable proceeds or runtime valuation wiring.

## 5. Validate and audit offline

- Run focused policy, aggregate market-data, and price-provider tests.
- Run full pytest, Ruff, Mypy, and `git diff --check`.
- Audit the exact six-path scope and confirm no protected file changed.
- Record observed results in `validation.md`.
- Leave all work unstaged and uncommitted; do not push, run a live smoke, or start Step 2M-A2.
