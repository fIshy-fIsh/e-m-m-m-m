# Phase 13A Step 2M-A1 — Requirements

## Scope

Implement one synchronous, offline policy:

```text
SteamDTMarketDataResult
→ exact platform == "BUFF"
→ positive finite gross sell_price_cny
→ SteamDTBuffOutputPrice
```

This step does not perform live recipe valuation, EV, ROI, risk evaluation, fee calculation, caching, scheduling, networking, or runtime composition.

## Provider and currency interpretation

- `"BUFF"` is the exact, case-sensitive provider platform literal approved for this project policy.
- Do not trim, case-fold, normalize, alias, translate, or substring-match provider platform text.
- The project treats SteamDT `sell_price_cny` as CNY/RMB; this is a project-approved interpretation, not a claim that current SteamDT documentation explicitly guarantees the currency.
- The selected price is a platform-level aggregate gross sell price. It is not an exact executable listing price, guaranteed realized price, buy order, recent sale, or special-condition order.

## Public API

`app/services/steamdt_buff_price_policy.py` must export exactly:

- `SteamDTBuffPriceSelectionReason`
- `SteamDTBuffPriceSelectionError`
- `SteamDTBuffOutputPrice`
- `select_buff_output_price`

`SteamDTBuffOutputPrice` must be frozen, keyword-only, and repr-suppressed, with these fields in order:

1. `market_hash_name: str`
2. `platform: str`
3. `sell_price_cny: Decimal`
4. `sell_count: int | None`
5. `platform_item_id: str | None`
6. `update_time: int | str | None`

It retains no source quote, raw response, bid, fee, net price, listing, URL, or mutable trace object.

## Stable failure contract

`SteamDTBuffPriceSelectionError` must be a `RuntimeError` with one fixed, non-sensitive message and an exact `SteamDTBuffPriceSelectionReason` property.

Reasons and values:

- `INVALID_MARKET_DATA = "invalid_market_data"`
- `BUFF_RECORD_MISSING = "buff_record_missing"`
- `DUPLICATE_BUFF_RECORDS = "duplicate_buff_records"`
- `BUFF_SELL_PRICE_MISSING = "buff_sell_price_missing"`
- `BUFF_SELL_PRICE_NON_FINITE = "buff_sell_price_non_finite"`
- `BUFF_SELL_PRICE_NON_POSITIVE = "buff_sell_price_non_positive"`

Reason precedence:

1. malformed relevant aggregate structure or field → `invalid_market_data`;
2. zero exact `"BUFF"` records → `buff_record_missing`;
3. more than one exact `"BUFF"` record → `duplicate_buff_records`, before inspecting duplicate economics;
4. unique BUFF sell price is `None` → `buff_sell_price_missing`;
5. unique BUFF sell price is not an exact `Decimal` → `invalid_market_data`;
6. NaN or infinity → `buff_sell_price_non_finite`;
7. finite value `<= 0` → `buff_sell_price_non_positive`.

Errors must not include market names, platform item IDs, prices, timestamps, raw values, or nested exception messages. `MemoryError` and other non-`Exception` process-control values must propagate.

## Exact platform selection

Only `platform == "BUFF"` is eligible. These and all other values are not matches:

- `"buff"`
- `"Buff"`
- `"BUFF163"`
- `"网易BUFF"`
- `" BUFF "`

No exact BUFF record fails closed. There is no fallback to STEAM, YOUPIN, C5, HALOSKINS, or any other platform.

Multiple exact BUFF records fail closed. The policy must not choose first, minimum, maximum, newest, or most liquid.

## Sell-price policy

For the unique exact BUFF record, `sell_price_cny` must be:

- an exact `Decimal`;
- finite;
- greater than zero.

Preserve the Decimal value, precision, and exponent exactly. Do not convert through float, round, quantize, apply exchange rates, calculate fees, or calculate net proceeds.

## Bidding-price exclusion

The selector must not read, validate, compare, copy, return, or fall back to:

- `bidding_price_cny`
- `bidding_count`

This remains true when a bid is greater than the sell price or when the sell price is missing or unusable. Aggregate bid data may represent a special-condition order whose requirements are not present in the response, so it cannot be treated as unconditional output value.

## Retained opaque fields

For the unique selected BUFF record:

- `sell_count` is `None` or an exact nonnegative `int`; zero is valid and no liquidity minimum is imposed;
- `platform_item_id` is `None` or an exact `str`, preserved without parsing or listing semantics;
- `update_time` is `None`, an exact non-bool `int`, or an exact `str`, preserved without freshness, unit, or timezone assumptions;
- `market_hash_name` remains an exact nonblank string without surrounding whitespace;
- `platform` remains exactly `"BUFF"`.

Construct a fresh detached output. Do not mutate or retain the input aggregate, quote, tuple, or raw mapping.

## Offline test acceptance

At minimum cover:

1. one exact BUFF record succeeds;
2. other platforms plus one BUFF selects BUFF;
3. positive BUFF sell price is preserved exactly;
4. a higher BUFF bid does not replace sell price;
5. bid-only BUFF with missing sell price fails closed;
6. zero BUFF sell price fails closed;
7. negative BUFF sell price fails closed, including tampered input;
8. no BUFF fails closed;
9. `"buff"` alone fails closed;
10. `"BUFF163"` alone fails closed;
11. `" BUFF "` alone fails closed;
12. duplicate exact BUFF records fail closed;
13. STEAM/YOUPIN/C5 never serve as fallback;
14. sell count is preserved;
15. platform item ID is preserved;
16. update time is preserved;
17. input is not mutated and output is detached;
18. no network path exists;
19. no SteamApis dependency exists;
20. no `PriceQuote` dependency exists;
21. no valuation, EV, ROI, or risk path exists;
22. no bid fallback or bid-field access exists.

Also pin the public signature, field order, immutable/repr behavior, exact reasons, fixed redacted error text, nonfinite values, invalid relevant types, zero count, missing ancillary values, and deterministic repeated calls.

## Allowed files

- New: `app/services/steamdt_buff_price_policy.py`
- New: `tests/test_steamdt_buff_price_policy.py`
- New: `specs/2026-08-15-steamdt-buff-price-policy/plan.md`
- New: `specs/2026-08-15-steamdt-buff-price-policy/requirements.md`
- New: `specs/2026-08-15-steamdt-buff-price-policy/validation.md`
- Modified: `docs/STEAMDT_API_NOTES.md`

No other file may change.

## Exclusions

Do not modify or wire:

- `app/clients/steamdt_client.py`;
- `app/services/steamdt_market_data.py`;
- SteamDT generic selection/provider or `PriceQuote`;
- valuation, live recipe valuation, EV, ROI, risk, or recipe solving;
- SteamDT cache, Redis, rate limiters, refresh, scheduler, or smoke scripts;
- SteamApis, direct BUFF integration, Discord, FastAPI, Docker, or database code;
- configuration or environment files.

Do not make network requests, run a live smoke, commit, push, or start Step 2M-A2.
