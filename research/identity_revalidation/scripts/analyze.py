"""Quantitative analysis of community BUF identity catalogs.

This is a one-off research script for Phase 13N-3A. It does not import
from app/ and does not modify production code. It only reads JSON files
under research/identity_revalidation/data/ and prints structured metrics.

Schema assumptions (must hold for the analysis to be valid):

  EricZhu-42/SteamTradingSite-ID-Mapper buff/730.json
    Flat object: {market_hash_name: integer_value}

  ModestSerhat/cs2-marketplace-ids cs2_marketplaceids.json
    Object with top-level "items" key:
      {"items": {market_hash_name: {"buff163_goods_id": int|None, ...}}}

  TimofeyIvanenko/cs2-marketplace-mapping cs2_full_mapping.json
    Object with top-level "items" key:
      {"items": {market_hash_name: {"buff163_goods_id": int|None, ...}}}

Per Phase 13N-3A rule: a BUF goods_id is "valid" iff it can be represented
as a canonical positive decimal string. Examples:
  33960, "33960" -> valid
  None, "", -1, "-1", 0, "0", "abc", "33960.0" -> invalid
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def is_valid_goods_id(value: object) -> bool:
    """Return True iff value can be a canonical positive decimal integer."""
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return False
        if not re.fullmatch(r"\d+", s):
            return False
        # No leading zeros except "0" itself, which we already rejected (must be > 0).
        if len(s) > 1 and s.startswith("0"):
            return False
        return int(s) > 0
    return False


def canonical_goods_id(value: object) -> str | None:
    """Return canonical decimal-string form if valid, else None."""
    if not is_valid_goods_id(value):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return None


def load_eric_zhu() -> dict[str, str]:
    """Return {market_hash_name: canonical_goods_id_str} for valid records."""
    path = DATA_DIR / "eric_zhu_730.json"
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("eric_zhu: expected top-level dict")
    out: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        cid = canonical_goods_id(value)
        if cid is None:
            continue
        out[key] = cid
    return out


def _load_items_wrapper(path: Path) -> dict[str, str]:
    """Return {market_hash_name: canonical_goods_id_str} from {items: {...}}."""
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: expected top-level dict")
    items = raw.get("items")
    if not isinstance(items, dict):
        raise ValueError(f"{path.name}: expected 'items' key as dict")
    out: dict[str, str] = {}
    for key, value in items.items():
        if not isinstance(key, str):
            continue
        if not isinstance(value, dict):
            continue
        cid = canonical_goods_id(value.get("buff163_goods_id"))
        if cid is None:
            continue
        out[key] = cid
    return out


def load_modest_serhat() -> dict[str, str]:
    return _load_items_wrapper(DATA_DIR / "modest_serhat.json")


def load_timofey_ivanenko() -> dict[str, str]:
    return _load_items_wrapper(DATA_DIR / "timofey_ivanenko.json")


def raw_counts_eric_zhu() -> tuple[int, int, int, list[str]]:
    """Return (total, valid, sentinel_minus_one, sample_sentinel_keys).

    sentinel_minus_one = records where the raw value is -1 (int) or "-1" (str).
    """
    path = DATA_DIR / "eric_zhu_730.json"
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("eric_zhu: expected top-level dict")
    total = 0
    valid = 0
    sentinel = 0
    sentinel_samples: list[str] = []
    for k, v in raw.items():
        if not isinstance(k, str):
            continue
        total += 1
        if isinstance(v, int) and v == -1:
            sentinel += 1
            if len(sentinel_samples) < 10:
                sentinel_samples.append(k)
            continue
        if isinstance(v, str) and v.strip() == "-1":
            sentinel += 1
            if len(sentinel_samples) < 10:
                sentinel_samples.append(k)
            continue
        if is_valid_goods_id(v):
            valid += 1
    return total, valid, sentinel, sentinel_samples


def raw_counts_items_wrapper(path: Path) -> tuple[int, int, int, list[str]]:
    """For ModestSerhat / TimofeyIvanenko: count records and how many have
    buff163_goods_id as None vs valid.
    """
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: expected top-level dict")
    items = raw.get("items")
    if not isinstance(items, dict):
        raise ValueError(f"{path.name}: expected 'items' key as dict")
    total = 0
    valid = 0
    null_or_invalid = 0
    samples: list[str] = []
    for k, v in items.items():
        if not isinstance(k, str) or not isinstance(v, dict):
            continue
        total += 1
        gid = v.get("buff163_goods_id")
        if gid is None:
            null_or_invalid += 1
            if len(samples) < 10:
                samples.append(f"NULL -> {k}")
            continue
        if is_valid_goods_id(gid):
            valid += 1
        else:
            null_or_invalid += 1
            if len(samples) < 10:
                samples.append(f"{gid!r} -> {k}")
    return total, valid, null_or_invalid, samples


def analyze_collisions(name: str, mapping: dict[str, str]) -> dict[str, Any]:
    """Count collisions in a single mapping."""
    by_gid: dict[str, list[str]] = {}
    for name_key, gid in mapping.items():
        by_gid.setdefault(gid, []).append(name_key)
    goods_id_collisions = {gid: names for gid, names in by_gid.items() if len(names) > 1}

    # market_hash_name uniqueness (dict keys are unique by construction in JSON, but be safe)
    mhn_counter: Counter[str] = Counter(mapping.keys())
    mhn_collisions = {n: c for n, c in mhn_counter.items() if c > 1}

    return {
        "name": name,
        "total_mappings": len(mapping),
        "unique_goods_ids": len(by_gid),
        "unique_market_hash_names": len(set(mapping.keys())),
        "goods_id_collision_count": len(goods_id_collisions),
        "goods_id_collision_samples": list(goods_id_collisions.items())[:5],
        "market_hash_name_collision_count": len(mhn_collisions),
        "market_hash_name_collision_samples": list(mhn_collisions.items())[:5],
    }


def cross_compare(
    name_a: str, mapping_a: dict[str, str], name_b: str, mapping_b: dict[str, str]
) -> dict[str, Any]:
    """Compare two mappings by (market_hash_name, goods_id) pair."""
    set_a_pairs = set(mapping_a.items())
    set_b_pairs = set(mapping_b.items())
    common_pairs = set_a_pairs & set_b_pairs

    # Overlap by market_hash_name
    a_keys = set(mapping_a.keys())
    b_keys = set(mapping_b.keys())
    overlap = a_keys & b_keys
    only_a = a_keys - b_keys
    only_b = b_keys - a_keys

    # Disagreement: same market_hash_name, different goods_id
    disagreements: list[tuple[str, str, str]] = []
    for k in overlap:
        gid_a = mapping_a[k]
        gid_b = mapping_b[k]
        if gid_a != gid_b:
            disagreements.append((k, gid_a, gid_b))

    return {
        "name_a": name_a,
        "name_b": name_b,
        "total_a_pairs": len(set_a_pairs),
        "total_b_pairs": len(set_b_pairs),
        "exact_pair_agreement": len(common_pairs),
        "market_hash_name_overlap": len(overlap),
        "only_in_a": len(only_a),
        "only_in_b": len(only_b),
        "disagreement_count": len(disagreements),
        "disagreement_samples": disagreements[:10],
    }


def spot_check(mapping: dict[str, str], names: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for n in names:
        out[n] = mapping.get(n, "<MISSING>")
    return out


def main() -> int:
    print("=" * 70)
    print("Phase 13N-3A: Quantitative catalog analysis")
    print("=" * 70)

    # --- Raw counts including sentinels ---
    ez_total, ez_valid, ez_sentinel, ez_samples = raw_counts_eric_zhu()
    print("\n[E1] EricZhu-42/SteamTradingSite-ID-Mapper buff/730.json")
    print(f"  total top-level records: {ez_total}")
    print(f"  valid goods_id records: {ez_valid}")
    print(f"  -1 sentinel records: {ez_sentinel}")
    if ez_samples:
        print(f"  sample -1 keys: {ez_samples}")

    ms_total, ms_valid, ms_null, ms_samples = raw_counts_items_wrapper(
        DATA_DIR / "modest_serhat.json"
    )
    print("\n[E2] ModestSerhat/cs2-marketplace-ids cs2_marketplaceids.json")
    print(f"  total items records: {ms_total}")
    print(f"  valid buff163_goods_id records: {ms_valid}")
    print(f"  null / invalid buff163_goods_id records: {ms_null}")
    if ms_samples:
        print(f"  sample missing/invalid: {ms_samples}")

    ti_total, ti_valid, ti_null, ti_samples = raw_counts_items_wrapper(
        DATA_DIR / "timofey_ivanenko.json"
    )
    print("\n[E3] TimofeyIvanenko/cs2-marketplace-mapping cs2_full_mapping.json")
    print(f"  total items records: {ti_total}")
    print(f"  valid buff163_goods_id records: {ti_valid}")
    print(f"  null / invalid buff163_goods_id records: {ti_null}")
    if ti_samples:
        print(f"  sample missing/invalid: {ti_samples}")

    # --- Load valid mappings ---
    ez = load_eric_zhu()
    ms = load_modest_serhat()
    ti = load_timofey_ivanenko()

    # --- Single-source collisions ---
    print("\n[C1] EricZhu collisions")
    for k, v in analyze_collisions("eric_zhu", ez).items():
        print(f"  {k}: {v}")

    print("\n[C2] ModestSerhat collisions")
    for k, v in analyze_collisions("modest_serhat", ms).items():
        print(f"  {k}: {v}")

    print("\n[C3] TimofeyIvanenko collisions")
    for k, v in analyze_collisions("timofey_ivanenko", ti).items():
        print(f"  {k}: {v}")

    # --- Cross-source ---
    print("\n[X1] EricZhu vs ModestSerhat")
    for k, v in cross_compare("eric_zhu", ez, "modest_serhat", ms).items():
        if k == "disagreement_samples":
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: {v}")

    print("\n[X2] EricZhu vs TimofeyIvanenko")
    for k, v in cross_compare("eric_zhu", ez, "timofey_ivanenko", ti).items():
        if k == "disagreement_samples":
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: {v}")

    print("\n[X3] ModestSerhat vs TimofeyIvanenko")
    for k, v in cross_compare("modest_serhat", ms, "timofey_ivanenko", ti).items():
        if k == "disagreement_samples":
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: {v}")

    # --- Spot checks ---
    print("\n[S1] Spot checks (deterministic samples)")
    spot_names = [
        "AK-47 | Redline (Field-Tested)",
        "★ Karambit | Doppler (Factory New)",
        "AWP | Dragon Lore (Factory New)",
        "StatTrak™ AK-47 | Redline (Field-Tested)",
        "Souvenir AWP | Dragon Lore (Factory New)",
        "Sticker | Howling Dawn",
        "AK-47 | The Empress (Field-Tested)",
        "Glock-18 | Fade (Factory New)",
        "★ M9 Bayonet | Fade (Factory New)",
        "Chroma Case",
        "Chroma 2 Case",
        "Operation Bravo Case",
    ]
    spot = {
        "eric_zhu": spot_check(ez, spot_names),
        "modest_serhat": spot_check(ms, spot_names),
        "timofey_ivanenko": spot_check(ti, spot_names),
    }

    report_path = DATA_DIR.parent / "analysis_report.txt"
    with report_path.open("w", encoding="utf-8") as f:
        for src, results in spot.items():
            f.write(f"\n  [{src}]\n")
            for n, v in results.items():
                f.write(f"    {n!r}: {v}\n")
        print(f"  (spot-check details written to {report_path})")

    return 0


if __name__ == "__main__":
    sys.exit(main())