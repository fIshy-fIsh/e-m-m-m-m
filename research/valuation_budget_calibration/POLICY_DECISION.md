# Phase 15B — Valuation Budget Policy Decision / Freeze

**Decision date:** 2026-08-30

**Production default:** `UNCHANGED`

**Hard maximum:** `UNCHANGED`

**Default-policy status:** `NO_PRODUCTION_DEFAULT_CHANGE_PENDING_REPRESENTATIVE_SNAPSHOT`

**Hard-max status:** `HARD_MAX_60_REVIEW_DEFERRED`

## 1. Phase 15A evidence reviewed

Phase 15A measured `run_unique_output_names`: the number of distinct exact
`output_market_hash_name` values across the ordered recipe candidates returned
by the current default scanner composition (`2 candidates / 256 states`). With
an empty persistent cache and a fresh run memo, this is theoretical NEW-LIVE
exact-name demand when every required output price must be fetched successfully.
It is not the legacy logical `valuation_requests_attempted` counter.

The reviewed evidence contains:

- 192 deterministic designed-replay observations;
- 439 structural-census records;
- repository-pinned normalized identity and metadata snapshots;
- current cohort-depth universe allocation;
- real scanner recipe composition, recipe solver, and trade-up output
  construction;
- deterministic synthetic price/float orderings that are explicitly not market
  samples.

Independent calculation from `results.json` confirms the R-7 designed-replay
summary:

| min | P25 | P50 | P75 | P90 | P95 | max |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 20 | 29.5 | 45 | 75 | 95 | 95 |

The designed-corpus threshold counts are:

| Reference threshold | Designed observations at or below threshold |
|---:|---:|
| 5 | 5 / 192 |
| 10 | 25 / 192 |
| 15 | 47 / 192 |
| 20 | 61 / 192 |
| 30 | 108 / 192 |
| 60 | 162 / 192 |

These counts describe only the designed replay corpus. They are not estimates
of production-run coverage or probability.

Structural evidence confirms:

- constructible 1–3 cohort maximum: 120 exact names;
- current default cohort-depth-universe maximum: 95 exact names.

## 2. What the evidence establishes

Phase 15A establishes that:

- exact output-name demand can be measured reproducibly under the current
  structural contracts;
- the current default cohort-depth universe and default bounded enumeration can
  produce structurally valid cases requiring more than 5 NEW-LIVE exact names;
- the current production default of 5 is conservative relative to the
  structural search space;
- structurally valid current-default-universe cases can require as many as 95
  exact names;
- therefore the hard maximum of 60 intentionally cannot admit every
  structurally possible current-default-universe case;
- the existing exact-name, run-memo, strict composition, and atomic NEW-LIVE
  semantics give a stable target for later representative measurement.

## 3. What the evidence does not establish

`PHASE15A_REPRESENTATIVENESS_LIMITATION` remains controlling.

Phase 15A does not establish:

- production-run probabilities or expected production workload;
- live listing availability, liquidity, or market frequency;
- how often any rarity, StatTrak mode, collection mixture, output cardinality,
  or threshold occurs in production;
- that the designed-corpus threshold shares transfer to real runs;
- that 5 is statistically incorrect as a production default;
- that 60 should be raised as a hard maximum;
- an acceptable change to the external-call safety envelope.

In particular, `162 / 192` at threshold 60 is not evidence that 60 covers any
specific share of real production runs.

## 4. Production-default decision

**Decision: `UNCHANGED`.**

**Status: `NO_PRODUCTION_DEFAULT_CHANGE_PENDING_REPRESENTATIVE_SNAPSHOT`.**

The production default `max_valuation_requests_per_run = 5` remains unchanged.
Phase 15A demonstrates structural cases above 5, but a production-default
change requires representative evidence about expected production workload.
No such representative sampling evidence exists in the reviewed authority.
Designed structural coverage cannot authorize a numeric production default.

This decision does not claim that 5 is statistically optimal. It records only
that the evidence required to change it is missing.

## 5. Hard-maximum decision

**Decision: `UNCHANGED`.**

**Status: `HARD_MAX_60_REVIEW_DEFERRED`.**

The hard maximum remains 60. Phase 15A proves that the current default universe
can be structurally valid at 95 exact names, so 60 cannot admit every
structurally possible case. That fact alone does not justify raising the hard
maximum. A higher hard maximum expands the external-call safety envelope and
requires separate explicit authorization, representative workload evidence,
and an operational safety review.

## 6. Why no numeric policy change is authorized

Phase 15A establishes structural demand and designed scenario coverage, not
production-frequency demand. The replay corpus was deliberately constructed to
exercise single-, two-, and three-cohort compositions, reuse patterns,
rarities, and intrinsic modes. Its observations are not a random, stratified,
or otherwise representative sample of production runs.

Changing either the default or hard maximum from these observations would turn
coverage design into an unsupported production-frequency claim. Therefore no
numeric production policy change is authorized from Phase 15A alone.

## 7. Minimum representative snapshot requirements

A future calibration intended to support numeric production policy must use
read-only, policy-compliant listing snapshots with at least:

1. timestamped snapshots;
2. a declared sampling window and sampling frame;
3. a documented goods-id universe selection method;
4. exact goods-id-to-market-hash-name identity binding;
5. listing price;
6. float / `paintwear`;
7. intrinsic mode, including StatTrak and Souvenir facts;
8. input rarity;
9. collection;
10. enough observations across time to avoid one-point-in-time bias;
11. documented missingness, rejection, and failed-acquisition reasons;
12. reproducible replay through the unchanged cohort-depth universe builder,
    default `2 / 256` enumeration, strict scanner composition, and exact
    NEW-LIVE name accounting.

Collection must remain read-only. It must not invent BUFF endpoints,
signatures, parameters, or response fields; it must use only separately
confirmed and authorized interfaces. It must not add auto-buy, auto-trade,
login, cookie collection, CAPTCHA/risk-control bypass, browser purchasing, or
marketplace writes.

## 8. Explicit next-phase gate

Before any numeric default or hard-maximum change:

- representative read-only listing-snapshot calibration must be separately
  specified and authorized;
- its sampling frame, collection boundary, retention/redaction policy, and
  missing-data semantics must be reviewed;
- its output must distinguish observed production-frequency evidence from
  structural possibility;
- any hard-maximum change must receive a separate external-call safety-envelope
  review and explicit implementation authorization.

Until that gate is satisfied:

- production default: unchanged at 5;
- hard maximum: unchanged at 60;
- CLI semantics: unchanged;
- atomic NEW-LIVE admission: unchanged;
- cohort-depth universe builder: unchanged;
- default bounded enumeration: unchanged at `2 / 256`;
- strict scanner composition: unchanged;
- no production code change is authorized.
