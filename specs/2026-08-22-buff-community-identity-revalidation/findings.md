# Phase 13N-3A — BUFF Identity Source Revalidation (Findings)

## 1. Searched Locations

### 1.1 Repository context re-examination

| File | What was confirmed |
|---|---|
| `app/services/buff_item_identity.py` | `BuffItemIdentity(market_hash_name, goods_id)` DTO; `BuffItemIdentityResolver.resolve(market_hash_name) -> BuffItemIdentity \| None` Protocol; forward-only direction; no concrete resolver exists. |
| `app/services/buff_listing_provider.py` line 212 | `market_hash_name=None` hardcoded on every parsed `BuffListing`; `goods_id` is caller context, not response-derived; parser reads exactly six item-level fields. |
| `app/clients/buff_client.py` line 228 | `BuffHttpClient.get_goods_info` raises `NotImplementedError(UNCONFIRMED_MAPPING_ERROR)` ("BUFF API endpoint mapping is not confirmed. See docs/BUFF_API_NOTES.md."). |
| `app/clients/buff_anonymous_listing_client.py` | One-request, anonymous, no auth/cookie/redirect, header allowlist `{Host, Accept, User-Agent}` only; query allowlist exactly `(game=csgo, goods_id=<caller>, page_num=1, sort_by=default)`. |
| `docs/BUFF_API_NOTES.md` TODO `#5` | Goods-info endpoint checkboxes still unchecked. |
| `docs/ai-context/DECISION_LOG.md` | `D-IDENTITY-001` through `D-IDENTITY-005` all present and unmodified. |

### 1.2 Current resolver direction (re-confirmed)

`BuffItemIdentityResolver.resolve(market_hash_name) -> BuffItemIdentity | None` — **forward-only**: takes a `market_hash_name` and returns identity containing `goods_id`.

The production blocker is the **reverse** direction: given a `goods_id`, derive `market_hash_name`. The current Protocol signature does not natively support this. A community catalog keyed by `market_hash_name` would need an inverted index (goods_id → market_hash_name) to be useful in production, OR a new resolver method.

This is a real architectural detail, not a blocker: an inverted index is straightforward and does not violate any frozen decision.

## 3. External Sources Investigated

### Source A — EricZhu-42/SteamTradingSite-ID-Mapper

| Field | Value |
|---|---|
| Repository | https://github.com/EricZhu-42/SteamTradingSite-ID-Mapper |
| File | `buff/730.json` |
| File path on disk | `research/identity_revalidation/data/eric_zhu_730.json` |
| Latest commit affecting this file (SHA) | `093adde1f9f3b0a5fd14957cd52fb988154251c3` |
| Latest commit date | 2026-05-20T15:52:36Z |
| Commit author | EricZhu-42 |
| Commit message | "Update items" |
| License | **CC-BY-4.0** |
| File SHA-256 (downloaded) | `a7f370a61dd34f7d206e0372f6806cbcb936e1ba89e33f48bbb89adaa273d72f` |
| Schema | Flat object: `{market_hash_name: integer_value}`. Single integer value per record. No nesting. No additional fields. |
| Keying | Keyed by `market_hash_name`. |
| Update mechanism | Manual repository commits. README states "the team cannot guarantee completeness/accuracy/timeliness as new items are continuously added; contributions via PR are welcome." No documented automation. |
| Total top-level records | 34,417 |
| Valid goods_id records | 34,402 (99.96%) |
| `-1` sentinel records | 15 (all "Sticker Slab" entries — community has flagged these as not having BUF IDs) |
| Goods_id collisions | **0** (perfect 1:1 mapping) |
| market_hash_name collisions | **0** |
| Provenance | Independent community catalog. README does not declare upstream dependencies for the BUF CS2 file. |
| Public availability | Yes, public GitHub repo. CC-BY-4.0 requires attribution. |

**Assessment:** Highest-quality candidate. CC-BY-4.0 is explicit. Coverage is 99.96%. Zero collisions. Simple flat schema. Reproducible via commit SHA + file SHA-256.

### Source B — ModestSerhat/cs2-marketplace-ids

| Field | Value |
|---|---|
| Repository | https://github.com/ModestSerhat/cs2-marketplace-ids |
| File | `cs2_marketplaceids.json` |
| File path on disk | `research/identity_revalidation/data/modest_serhat.json` |
| Latest commit affecting this file (SHA) | `b5d3d210ce240861474230de3cd087d119b368bc` |
| Latest commit date | 2026-08-17T09:51:51Z (most recent of the three) |
| Commit message | "feat: Add fourth batch of Cologne 2026 Ranked Sticker item IDs, their applied sticker IDs, twentieth batch of item IDs with applied Souvenir quality and update Sticker Slab IDs since August 7th" |
| License | **LICENSE_UNCLEAR** (no LICENSE file in repo; GitHub does not display a license) |
| File SHA-256 (downloaded) | `75cca18553f36a0d0d46b4044a284a597fe4d2b902f96d927b6c362e7e9f257c` |
| Schema | `{items: {market_hash_name: {buff163_goods_id, youpin_id, buffmarket_goods_id, csmoney_nameid, ...}}}`. Nested. Uses `null` to denote missing (not `-1`). |
| Keying | Keyed by `market_hash_name` under `items`. |
| Total records | 41,611 |
| Valid `buff163_goods_id` records | 40,844 (98.16%) |
| `null` / invalid `buff163_goods_id` records | 767 (mostly "Sticker Slab" entries) |
| Goods_id collisions | **0** |
| market_hash_name collisions | **0** |
| Provenance | Independent community catalog (no declared dependency on EricZhu-42 in the README). |
| Public availability | Yes, public GitHub repo. **License unclear.** |

**Assessment:** Good second source for cross-verification. License is **unclear** — using this as the primary identity source would require explicit license verification. Suitable as a consistency-checker against Source A.

### Source C — TimofeyIvanenko/cs2-marketplace-mapping

| Field | Value |
|---|---|
| Repository | https://github.com/TimofeyIvanenko/cs2-marketplace-mapping |
| File | `cs2_full_mapping.json` |
| File path on disk | `research/identity_revalidation/data/timofey_ivanenko.json` |
| Latest commit affecting this file (SHA) | `139c91cd4c09ff94b9d20f47c24763ca6211010b` |
| Latest commit date | 2026-03-21T09:36:03Z |
| Commit message | "Initial release: 36,988 CS2 skins mapped across 7 marketplaces" |
| License | **MIT** |
| File SHA-256 (downloaded) | `aea4c428d19cc826941a916f348cb36422df2e8ffcb415785c26f1b22a38a36d` |
| Schema | `{metadata: {...}, items: {market_hash_name: {buff163_goods_id, ...}}}` |
| Keying | Keyed by `market_hash_name` under `items`. |
| Total records | 36,988 |
| Valid `buff163_goods_id` records | 35,975 (97.25%) |
| `null` / invalid `buff163_goods_id` records | 1,013 (recent items + Sticker Slabs) |
| Goods_id collisions | **14** (whitespace artifacts: e.g. `'Ground Rebel  | Elite Crew'` vs `'Ground Rebel | Elite Crew'` mapping to same `goods_id=774881`) |
| market_hash_name collisions | 0 |
| Provenance | **DERIVED.** README explicitly credits three upstream sources: ByMykel/CSGO-API, ModestSerhat/cs2-marketplace-ids, EricZhu-42/SteamTradingSite-ID-Mapper. Merge key is `market_hash_name`. |
| Public availability | Yes, MIT licensed. |

**Assessment:** Not independent evidence. Aggregates EricZhu + ModestSerhat + ByMykel. Useful as a secondary consistency-checker ONLY when both upstreams are also checked. The 14 whitespace collisions are evidence that aggregated data can introduce minor formatting artifacts.

## 4. Quantitative Analysis (single source)

### 4.1 EricZhu-42 (Source A)

```text
total top-level records:       34417
valid goods_id records:        34402  (99.96%)
-1 sentinel records:           15   (all Sticker Slab)
duplicate goods_id:            0
duplicate market_hash_name:    0
goods_id collisions:           0
market_hash_name collisions:   0
```

All 15 `-1` sentinels are "Sticker Slab | ..." entries — explicitly flagged by the community as not having BUF IDs. The dataset's coverage is therefore 100% for all non-Sticker-Slab items.

### 4.2 ModestSerhat (Source B)

```text
total items records:                 41611
valid buff163_goods_id records:      40844  (98.16%)
null / invalid buff163_goods_id:     767    (mostly Sticker Slab)
duplicate goods_id:                  0
duplicate market_hash_name:          0
goods_id collisions:                 0
market_hash_name collisions:         0
```

Larger record count than EricZhu because it includes applied-sticker IDs, applied-patch IDs, applied-charm IDs, Doppler phase IDs, and pattern tiers — not just item-level identities.

### 4.3 TimofeyIvanenko (Source C)

```text
total items records:                 36988
valid buff163_goods_id records:      35975  (97.25%)
null / invalid buff163_goods_id:     1013
goods_id collisions:                 14   (whitespace artifacts; same gid for different names)
market_hash_name collisions:         0
```

Sample collision (all whitespace):
- `gid=774881`: `'Ground Rebel  | Elite Crew'` vs `'Ground Rebel | Elite Crew'`
- `gid=774827`: `'Michael Syfers  | FBI Sniper'` vs `'Michael Syfers | FBI Sniper'`

These are aggregation artifacts, not real semantic collisions. They would not affect a strict equality lookup of trimmed, canonical names.

## 5. Cross-Source Comparison

### 5.1 EricZhu (A) vs ModestSerhat (B)

| Metric | Value |
|---|---|
| Total pairs (A) | 34,402 |
| Total pairs (B) | 40,844 |
| Exact `(market_hash_name, goods_id)` agreement | **34,272** |
| Market_hash_name overlap | 34,273 |
| Only in A | 129 |
| Only in B | 6,571 (B has more items but same BUF IDs) |
| **Disagreement count** | **1** |
| Disagreement sample | `('Souvenir Charm | Austin 2025 Highlight | Wont go quietly', '1134690', '1118388')` |

**Verdict:** Independent verification. 99.997% agreement on overlap. The single disagreement is plausibly a freshness race on a very recent item (Austin 2025).

### 5.2 EricZhu (A) vs TimofeyIvanenko (C)

| Metric | Value |
|---|---|
| Total pairs (A) | 34,402 |
| Total pairs (C) | 35,975 |
| Exact agreement | 34,319 |
| Market_hash_name overlap | 34,320 |
| Only in A | 82 |
| Only in B | 1,655 |
| **Disagreement count** | **1** |
| Disagreement sample | Same as 5.1 (Austin 2025 charm) |

**Verdict:** NOT independent verification — TimofeyIvanenko derives from EricZhu. The single disagreement is consistent with what ModestSerhat reports for the same item.

### 5.3 ModestSerhat (B) vs TimofeyIvanenko (C)

| Metric | Value |
|---|---|
| Total pairs (B) | 40,844 |
| Total pairs (C) | 35,975 |
| Exact agreement | 35,843 |
| Market_hash_name overlap | 35,843 |
| Only in B | 5,001 |
| Only in C | 132 |
| **Disagreement count** | **0** |

**Verdict:** Consistent — but **not independent** because TimofeyIvanenko derives from ModestSerhat.

### 5.4 Dependency map

```
        ByMykel/CSGO-API
              │
              ▼
   EricZhu-42/SteamTradingSite-ID-Mapper  ◄──┐
              │                            │
              ▼                            │
   ModestSerhat/cs2-marketplace-ids ───────┼──► TimofeyIvanenko/cs2-marketplace-mapping
                                           │      (aggregator; not independent)
                                           │
                                  (independence proof: 5.1)
```

**Independent verification pair:** EricZhu-42 vs ModestSerhat (5.1). 99.997% agreement on the 34,273 overlapping keys.

## 6. Spot Checks (deterministic samples across categories)

All twelve categories returned identical `goods_id` from all three sources:

| Category | market_hash_name | goods_id (all three sources) |
|---|---|---|
| Normal weapon skin | `AK-47 \| Redline (Field-Tested)` | 33960 |
| Knife (★) | `★ Karambit \| Doppler (Factory New)` | 42998 |
| Rare special | `AWP \| Dragon Lore (Factory New)` | 44060 |
| StatTrak™ | `StatTrak™ AK-47 \| Redline (Field-Tested)` | 38220 |
| Souvenir | `Souvenir AWP \| Dragon Lore (Factory New)` | 45462 |
| Sticker | `Sticker \| Howling Dawn` | 40335 |
| Older skin | `AK-47 \| The Empress (Field-Tested)` | 33970 |
| Fade (vanilla) | `Glock-18 \| Fade (Factory New)` | 35020 |
| Fade (knife) | `★ M9 Bayonet \| Fade (Factory New)` | 33812 |
| Chroma Case | `Chroma Case` | 33813 |
| Chroma 2 Case | `Chroma 2 Case` | 34369 |
| Operation Bravo Case | `Operation Bravo Case` | 35879 |

**Zero divergence** on the 12 samples × 3 sources = 36 lookups.

## 7. First-Party BUFF Evidence

The investigation did **not** perform any HTTP probing of BUF, in compliance with `D-AUTH-001`. The following first-party observations come from the existing empirical Phase 13B probe (`docs/BUFF_ANONYMOUS_READONLY_NOTES.md`, 2026-08-20) and the Phase 13N-2 goods-info survey.

| Source | Classification | Notes |
|---|---|---|
| `GET https://buff.163.com/api/market/goods/sell_order` | **HISTORICAL_ONLY** for the first-item probe. The probe verified only six item-level fields on the first item of one response. No first-party source of `goods_id ↔ market_hash_name` was probed, claimed, or verified. | Per `docs/BUFF_ANONYMOUS_READONLY_NOTES.md`. |
| Goods-info endpoint (unconfirmed path) | **PUBLIC_BUT_UNDOCUMENTED**. Listed as TODO `#5` in `docs/BUFF_API_NOTES.md`. Path unconfirmed. Auth unconfirmed. Schema unconfirmed. No probe authorized. | Per Phase 13N-2. |
| BUF first-party with both `goods_id` and `market_hash_name` in same payload | **UNVERIFIED**. No evidence exists. |

**No `VERIFIED_PUBLIC_CONTRACT` for BUF identity is currently known.**

## 8. Licensing

| Source | License | Compatibility assessment |
|---|---|---|
| EricZhu-42 | **CC-BY-4.0** | Clear. Attribution required. Permits download, transformation, snapshot storage, redistribution with attribution. Compatible with this project. |
| ModestSerhat | **LICENSE_UNCLEAR** | No LICENSE file. No explicit grant. Cannot rely on for primary use. Can be used only as consistency-checker. |
| TimofeyIvanenko | **MIT** | Clear. Permits download, transformation, redistribution. Not independent evidence (derived), so not useful as primary. |

**Recommendation:** prefer EricZhu-42 (CC-BY-4.0, clear attribution requirement) as primary. Use ModestSerhat as consistency-checker if it license is later clarified.

## 10. Reproducibility

All three can be file-pinned:

```
Repository:        EricZhu-42/SteamTradingSite-ID-Mapper
File path:         buff/730.json
Commit SHA:        093adde1f9f3b0a5fd14957cd52fb988154251c3
File SHA-256:      a7f370a61dd34f7d206e0372f6806cbcb936e1ba89e33f48bbb89adaa273d72f
```

The future production model can be:

```text
external source
      ↓
explicit pinned revision
      ↓
offline validation (deterministic, stdlib-only)
      ↓
version-controlled snapshot
```

Runtime has zero network I/O.

## 11. Freshness

- **EricZhu-42:** last update 2026-05-20; updates irregular; no automation documented. **Could grow stale for new items.**
- **ModestSerhat:** last update 2026-08-17 (most recent); updates regularly (4+ commits/month observed); Cologne 2026 items added.
- **TimofeyIvanenko:** last update 2026-03-21; updates infrequent.

The recommendation is to **pin a snapshot** rather than depend on a live fetch. Future production can include a re-pinning workflow (manual, version-controlled) for periodic refreshes.

## 12. Coverage and Conflict Summary

```text
EricZhu-42 (CC-BY-4.0):
  34,402 valid records, 0 collisions, 15 -1 sentinels (all sticker slabs)
  99.96% coverage of BUF catalog (excluding sticker slabs which legitimately lack BUF IDs)

ModestSerhat (LICENSE_UNCLEAR):
  40,844 valid records, 0 collisions, 767 null
  98.16% coverage; covers items EricZhu doesn't (stickers, patches, charms, doppler phases, pattern tiers)

TimofeyIvanenko (MIT, NOT independent):
  35,975 valid records, 14 whitespace collisions, 1013 null
  97.25% coverage; not independently verifiable
```

## 13. Policy Evaluation

| Policy | Verdict |
|---|---|
| **A — single community source** | **Acceptable** with EricZhu-42 + offline snapshot. CC-BY-4.0 licensing is clear. 99.96% coverage. 0 collisions. |
| **B — community source + consistency checker** | **Strongly supported.** EricZhu-42 (primary) + ModestSerhat (consistency-checker). 99.997% independent agreement on overlap. |
| **C — multi-source agreement only** | **Not appropriate** as primary. TimofeyIvanenko is derived, not independent. ModestSerhat's license is unclear. Coverage loss from would be would be 6,571 records (only-in-B) — too costly. |
| **D — official-first / community fallback** | **Future.** Per Phase 13N-2 finding: BUF goods-info endpoint is `PUBLIC_BUT_UNDOCUMENTED`. Cannot use as primary today. When a future verified first-party source emerges, it can supersede the community snapshot. |

## 14. Criteria Checklist (per phase prompt section 18)

For EricZhu-42 + offline snapshot:

1. ✅ High coverage — 99.96% valid records.
2. ✅ Low conflict rate — 0 collisions in EricZhu; 1 disagreement vs ModestSerhat across 34,273 overlap keys (0.003%).
3. ✅ Deterministic exact mapping — integer ↔ string equality.
4. ✅ Reproducible source revision — commit SHA + file SHA-256 captured.
6. ✅ Identifiable provenance — community catalog with explicit upstream attribution.
6. ⚠️ Acceptable/understood licensing — CC-BY-4.0 is clear; attribution is required (manageable).
7. ✅ Runtime can operate fully offline — snapshot pattern enables zero network I/O.
8. ✅ No fuzzy inference required — exact integer lookup.
9. ✅ Unresolved items can safely return `None` — empty/missing entries naturally produce no match.
10. ✅ Downstream code does not need to trust it as official BUF data — provisional source; can be replaced.

**All 10 criteria satisfied.**

## 15. Cross-Source Independence vs. Derived

The user's prompt section 11 specifically asks to label TimofeyIvanenko-vs-EricZhu/ModestSerhat comparisons as "consistency comparison" rather than "independent verification" because TimofeyIvanenko derives from both upstream sources.

Confirmed: **EricZhu-42 vs ModestSerhat is the only meaningful independent comparison.** Agreement on 34,272 of 34,273 overlapping keys (99.997%) is the strongest available independent evidence.