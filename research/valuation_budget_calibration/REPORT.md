# Phase 15A — Valuation Budget Calibration: Offline Measurement

**Status:** `offline_measurement_complete`

**Representativeness:** `PHASE15A_REPRESENTATIVENESS_LIMITATION`

**Policy:** `Phase 15B NOT STARTED / NOT AUTHORIZED`

## Measurement

`run_unique_output_names` is the count of distinct exact `output_market_hash_name` values across the ordered recipe candidates returned by the current default scanner composition (`2 / 256`).

With an empty persistent cache and a fresh run memo, run_unique_output_names equals theoretical NEW-LIVE exact-name demand when every required output price must be fetched successfully.

The replay corpus uses the repository-pinned normalized identity and metadata snapshots, current cohort-depth allocation, real scanner recipe composition, real recipe solver, and real trade-up output construction. Only listing price/float order is deterministic synthetic input.

Quantiles use R-7: sort `x[0..N-1]`, `h=(N-1)p`, then `q=x[floor(h)] + (h-floor(h)) * (x[ceil(h)]-x[floor(h)])`. All calculations use exact rational arithmetic.

Cross-recipe reuse ratio is `(sum(per-recipe unique counts) - run_unique_output_names) / sum(per-recipe unique counts)` (zero only for an empty denominator).

## Corpus

- Observations: **192**
- Structural census records: **439**
- Skipped rarity/mode cases: **2**
- Seeds: `11, 23, 37, 53`
- Ordering patterns: `single_cohort_high_reuse`, `single_to_two_incremental`, `mixed_two_high_reuse`, `two_cohort_rotation`, `mixed_three_high_reuse`, `mixed_three_rotation`

## Primary distribution (designed replay corpus)

| min | P25 | P50 | P75 | P90 | P95 | max |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 20 | 29.50 (59/2) | 45 | 75 | 95 | 95 |

## Reference-threshold coverage (analysis only, not policy)

| Threshold | Count | Share |
|---:|---:|---:|
| 5 | 5 / 192 | 2.60% |
| 10 | 25 / 192 | 13.02% |
| 15 | 47 / 192 | 24.47% |
| 20 | 61 / 192 | 31.77% |
| 30 | 108 / 192 | 56.25% |
| 60 | 162 / 192 | 84.37% |

## Structural census

- Overall constructible 1–3 cohort maximum: **120** (Consumer Grade, normal; The Ascent Collection, The Boreal Collection, The Radiant Collection).
- Current default cohort-depth-universe maximum: **95** (Consumer Grade, normal; The Boreal Collection, The Dust 2 Collection, The Lake Collection).

## Top maximum-cardinality replay cases

| Cardinality | Rarity | Mode | Pattern | Seed | Participating collections |
|---:|---|---|---|---:|---|
| 95 | Consumer Grade | normal | mixed_three_high_reuse | 11 | The Boreal Collection, The Dust 2 Collection, The Lake Collection |
| 95 | Consumer Grade | normal | mixed_three_high_reuse | 23 | The Boreal Collection, The Dust 2 Collection, The Lake Collection |
| 95 | Consumer Grade | normal | mixed_three_high_reuse | 37 | The Boreal Collection, The Dust 2 Collection, The Lake Collection |
| 95 | Consumer Grade | normal | mixed_three_high_reuse | 53 | The Boreal Collection, The Dust 2 Collection, The Lake Collection |
| 95 | Consumer Grade | normal | mixed_three_rotation | 11 | The Boreal Collection, The Dust 2 Collection, The Lake Collection |
| 95 | Consumer Grade | normal | mixed_three_rotation | 23 | The Boreal Collection, The Dust 2 Collection, The Lake Collection |
| 95 | Consumer Grade | normal | mixed_three_rotation | 37 | The Boreal Collection, The Dust 2 Collection, The Lake Collection |
| 95 | Consumer Grade | normal | mixed_three_rotation | 53 | The Boreal Collection, The Dust 2 Collection, The Lake Collection |
| 95 | Consumer Grade | normal | two_cohort_rotation | 11 | The Boreal Collection, The Dust 2 Collection, The Lake Collection |
| 95 | Consumer Grade | normal | two_cohort_rotation | 23 | The Boreal Collection, The Dust 2 Collection, The Lake Collection |

## Representativeness limitations

`PHASE15A_REPRESENTATIVENESS_LIMITATION`

- Pinned catalogs establish structural possibilities, not live listing availability, liquidity, or market frequency.
- Synthetic prices/floats only impose deterministic solver orderings; they are not sampled from BUFF or any market.
- The replay distribution is coverage evidence over designed scenarios, not a probability distribution of production runs.
- A market-frequency distribution requires timestamped, representative, policy-compliant listing snapshots with exact identity, price, float, StatTrak/Souvenir facts, sampling frame, and collection/rarity coverage.

The reported quantiles and threshold shares describe this designed offline replay corpus only. They must not be interpreted as expected production frequency. A defensible market-frequency distribution requires timestamped representative listing snapshots with a declared sampling frame and the exact identity/price/float/intrinsic facts.

## Policy boundary

Reference thresholds are analysis only. This phase changes no budget default, hard maximum, CLI semantics, atomic NEW-LIVE behavior, or production code. No final cap is recommended here.

**Phase 15B: NOT STARTED / NOT AUTHORIZED.**
