"""Phase 13O-1 catalog analysis script.

Reads the pinned identity snapshot and produces deterministic counts for
StatTrak and Souvenir prefixes according to the canonical Steam
`market_hash_name` conventions.

Conventions being tested:
  - StatTrak items: prefix 'StatTrak™ ' (10 codepoints; 12 UTF-8 bytes)
  - Souvenir items: prefix 'Souvenir ' (9 codepoints; 9 UTF-8 bytes)
  - These are mutually exclusive (no item is both StatTrak and Souvenir)
  - The two prefixes are NOT ambiguous; both are exact canonical
    strings

The analysis is read-only. The script writes a small report to stdout.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SNAPSHOT = Path("data/identity/buff_identity_v1.json")

TOKEN_STATTRAK = "StatTrak™ "
TOKEN_SOUVENIR = "Souvenir "


def main() -> None:
    raw = SNAPSHOT.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    parsed = json.loads(raw)
    items = parsed["items"]
    accepted = len(items)
    print(f"catalog accepted identities: {accepted}")
    print(f"pinned snapshot SHA-256:    {sha}")

    st_prefix = 0
    sv_prefix = 0
    both_prefix = 0
    neither_prefix = 0
    empty = 0
    with_whitespace = 0
    middle_st = 0
    middle_sv = 0
    neither_sample: list[str] = []
    canonical_prefixes_st: dict[str, int] = {}
    canonical_prefixes_sv: dict[str, int] = {}

    for name in items.keys():
        if not name:
            empty += 1
            continue
        if name != name.strip():
            with_whitespace += 1
        is_st = name.startswith(TOKEN_STATTRAK)
        is_sv = name.startswith(TOKEN_SOUVENIR)
        if is_st and is_sv:
            both_prefix += 1
        elif is_st:
            st_prefix += 1
        elif is_sv:
            sv_prefix += 1
        else:
            neither_prefix += 1
            if len(neither_sample) < 10:
                neither_sample.append(name)
        if TOKEN_STATTRAK in name and not is_st:
            middle_st += 1
        if TOKEN_SOUVENIR in name and not is_sv:
            middle_sv += 1
        # Capture canonical-string prefixes (Python str.startswith semantics).
        if name.startswith("StatTrak"):
            pfx = name[:10]
            canonical_prefixes_st[pfx] = canonical_prefixes_st.get(pfx, 0) + 1
        if name.startswith("Souvenir"):
            pfx = name[:10]
            canonical_prefixes_sv[pfx] = canonical_prefixes_sv.get(pfx, 0) + 1

    print()
    print("--- PREFIX ANALYSIS (exact canonical-string startswith) ---")
    print(f"  'StatTrak™ ' prefix: {st_prefix}")
    print(f"  'Souvenir ' prefix:     {sv_prefix}")
    print(f"  Both prefix simultaneously: {both_prefix}")
    print(f"  Neither prefix:          {neither_prefix}")
    print(f"  Empty names:             {empty}")
    print(f"  With leading/trailing ws: {with_whitespace}")
    print()
    print("--- MIDDLE CONTAINMENT (substring not at start) ---")
    print(f"  Contains 'StatTrak™ ' mid-name: {middle_st}")
    print(f"  Contains 'Souvenir ' mid-name:     {middle_sv}")
    print()
    print("--- CONVENTION CONSISTENCY ---")
    both_actual = sum(
        1 for n in items if n.startswith(TOKEN_STATTRAK) and n.startswith(TOKEN_SOUVENIR)
    )
    print(f"  Items with both prefixes simultaneously: {both_actual}")
    print()
    print("--- CANONICAL-STRING STATTRAK PREFIX VARIANTS ---")
    for p, c in sorted(canonical_prefixes_st.items(), key=lambda x: -x[1])[:10]:
        print(f"  {p!r}: {c}")
    print()
    print("--- CANONICAL-STRING SOUVENIR PREFIX VARIANTS ---")
    for p, c in sorted(canonical_prefixes_sv.items(), key=lambda x: -x[1])[:10]:
        print(f"  {p!r}: {c}")
    print()
    print("--- NEITHER PREFIX (first 10 samples) ---")
    for s in neither_sample:
        print(f"  {s[:80]!r}")
    print()
    # Counts for the classifier (independent and joint).
    print("--- CLASSIFIER RESULTS (independent flag counts) ---")
    print(f"  stattrak=true:  {st_prefix}")
    print(f"  stattrak=false: {accepted - st_prefix}")
    print(f"  souvenir=true:  {sv_prefix}")
    print(f"  souvenir=false: {accepted - sv_prefix}")
    print()
    print("--- CLASSIFIER RESULTS (joint counts) ---")
    print("  stattrak=true  & souvenir=true : 0")
    print(f"  stattrak=true  & souvenir=false: {st_prefix}")
    print(f"  stattrak=false & souvenir=true : {sv_prefix}")
    print(f"  stattrak=false & souvenir=false: {neither_prefix}")


if __name__ == "__main__":
    main()