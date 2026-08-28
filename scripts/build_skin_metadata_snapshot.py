"""Build the pinned skin metadata snapshot from a ByMykel skins catalog.

Pinned source:
  repository: ByMykel/CSGO-API
  file: public/api/en/skins.json
  commit: 8a785962b291d57a023b79408416c6792782712e
  raw SHA-256: 7aeb9582c5f3308be78c78d2fd3681e3c469c67c0aeeeb7a9e54adb5c3be32d7
  license: MIT

The builder is offline and deterministic. It performs no network I/O.
It verifies the raw source hash, expands each skin into exact
wear-qualified market_hash_name variants, includes explicit
`StatTrak™ ` and `Souvenir ` variants when the source marks those
variants available, sorts by `(len(name), name)`, and writes canonical
compact UTF-8 JSON with a trailing newline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SOURCE_REPOSITORY = "ByMykel/CSGO-API"
SOURCE_FILE = "public/api/en/skins.json"
SOURCE_COMMIT = "8a785962b291d57a023b79408416c6792782712e"
SOURCE_SHA256 = "7aeb9582c5f3308be78c78d2fd3681e3c469c67c0aeeeb7a9e54adb5c3be32d7"
SOURCE_LICENSE = "MIT"
SNAPSHOT_SCHEMA_VERSION = 1
SNAPSHOT_KIND = "pinned_skin_metadata"


class SkinMetadataSnapshotBuilderError(RuntimeError):
    """The source catalog cannot produce the pinned snapshot."""


def build_snapshot_from_bytes(raw: bytes) -> dict[str, Any]:
    """Verify the pinned raw hash and build a deterministic snapshot."""
    actual = hashlib.sha256(raw).hexdigest()
    if actual != SOURCE_SHA256:
        raise SkinMetadataSnapshotBuilderError(
            "raw source SHA-256 mismatch"
        )
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SkinMetadataSnapshotBuilderError("raw source JSON is malformed") from exc
    return build_snapshot_from_payload(parsed)


def build_snapshot_from_payload(parsed: object) -> dict[str, Any]:
    """Build a deterministic snapshot from a parsed source payload."""
    if not isinstance(parsed, list):
        raise SkinMetadataSnapshotBuilderError("raw source must be a JSON array")
    rows: dict[str, dict[str, Any]] = {}
    rejected = 0

    for source_index, raw in enumerate(parsed):
        if not isinstance(raw, dict):
            rejected += 1
            continue
        expanded = _expand_source_row(raw, source_index=source_index)
        if not expanded:
            rejected += 1
            continue
        for item in expanded:
            name = item["market_hash_name"]
            existing = rows.get(name)
            if existing is not None and existing != item:
                raise SkinMetadataSnapshotBuilderError(
                    f"duplicate market_hash_name collision: {name!r}"
                )
            rows[name] = item

    items = [
        rows[name]
        for name in sorted(rows, key=lambda value: (len(value), value))
    ]
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_kind": SNAPSHOT_KIND,
        "provenance": {
            "repository": SOURCE_REPOSITORY,
            "file": SOURCE_FILE,
            "commit": SOURCE_COMMIT,
            "sha256": SOURCE_SHA256,
            "license": SOURCE_LICENSE,
            "attribution": (
                "Derived from ByMykel/CSGO-API public/api/en/skins.json "
                f"at commit {SOURCE_COMMIT} under MIT. Snapshot expands each "
                "catalog skin into exact market_hash_name wear variants, "
                "including explicit StatTrak™ and Souvenir variants when the "
                "source catalog marks those variants available."
            ),
        },
        "counts": {
            "source": len(parsed),
            "accepted": len(items),
            "rejected": rejected,
        },
        "items": items,
    }


def serialize_snapshot(snapshot: dict[str, Any]) -> bytes:
    """Serialize the snapshot as canonical compact UTF-8 JSON."""
    return (
        json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _expand_source_row(
    raw: dict[str, Any],
    *,
    source_index: int,
) -> list[dict[str, Any]]:
    name = _exact_string(raw.get("name"))
    rarity = raw.get("rarity")
    rarity_name = _exact_string(
        rarity.get("name") if isinstance(rarity, dict) else None
    )
    collections = raw.get("collections")
    collection_name: str | None = None
    if isinstance(collections, list) and collections and isinstance(collections[0], dict):
        collection_name = _exact_string(collections[0].get("name"))
    min_float = raw.get("min_float")
    max_float = raw.get("max_float")
    if (
        name is None
        or rarity_name is None
        or collection_name is None
        or type(min_float) not in (float, int)
        or type(max_float) not in (float, int)
    ):
        return []
    min_value = float(min_float)
    max_value = float(max_float)
    if not (0.0 <= min_value < max_value <= 1.0):
        return []

    variants: list[tuple[str, bool, bool]] = [("", False, False)]
    if raw.get("stattrak") is True:
        variants.append(("StatTrak™ ", True, False))
    if raw.get("souvenir") is True:
        variants.append(("Souvenir ", False, True))

    weapon = raw.get("weapon")
    weapon_name = _exact_string(
        weapon.get("name") if isinstance(weapon, dict) else None
    )
    category = raw.get("category")
    category_name = _exact_string(
        category.get("name") if isinstance(category, dict) else None
    )
    paint_index = raw.get("paint_index")
    if type(paint_index) is not int:
        paint_index = None

    wears = raw.get("wears")
    if not isinstance(wears, list):
        return []
    output: list[dict[str, Any]] = []
    for wear in wears:
        if not isinstance(wear, dict):
            continue
        wear_name = _exact_string(wear.get("name"))
        if wear_name is None:
            continue
        for prefix, stattrak, souvenir in variants:
            output.append(
                {
                    "market_hash_name": f"{prefix}{name} ({wear_name})",
                    "name": name,
                    "weapon": weapon_name,
                    "rarity": rarity_name,
                    "category": category_name,
                    "collection_name": collection_name,
                    "min_float": min_value,
                    "max_float": max_value,
                    "stattrak": stattrak,
                    "souvenir": souvenir,
                    "paint_index": paint_index,
                }
            )
    return output


def _exact_string(value: object) -> str | None:
    if type(value) is not str or not value or value != value.strip():
        return None
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    snapshot = build_snapshot_from_bytes(args.source.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(serialize_snapshot(snapshot))
    print(
        f"wrote {args.output}: source={snapshot['counts']['source']} "
        f"accepted={snapshot['counts']['accepted']} "
        f"rejected={snapshot['counts']['rejected']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
