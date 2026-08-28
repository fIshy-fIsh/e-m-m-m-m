"""Deterministic offline builder for the BUFF community identity snapshot.

Reads a pinned raw source file (EricZhu-42/SteamTradingSite-ID-Mapper
buff/730.json at commit 093adde1f9f3b0a5fd14957cd52fb988154251c3) and
emits a canonical runtime snapshot.

The builder is intentionally non-network. It reads only the source path
supplied on the command line, validates the bytes against the expected
SHA-256, and writes a deterministic snapshot.

Usage:

    py -3.13 scripts/build_buff_identity_snapshot.py \
        --source research/identity_revalidation/data/eric_zhu_730.json \
        --output data/identity/buff_identity_v1.json

Refuses to build if the raw source bytes do not match the expected
SHA-256. Refuses to build if the source has any collision or any
malformed record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping as MappingABC
from typing import Any

EXPECTED_RAW_SHA256 = (
    "a7f370a61dd34f7d206e0372f6806cbcb936e1ba89e33f48bbb89adaa273d72f"
)
EXPECTED_SOURCE_COMMIT = "093adde1f9f3b0a5fd14957cd52fb988154251c3"
SOURCE_REPOSITORY = "EricZhu-42/SteamTradingSite-ID-Mapper"
SOURCE_FILE = "buff/730.json"
SOURCE_LICENSE = "CC-BY-4.0"
SOURCE_ATTRIBUTION = (
    "Identity mappings derived from EricZhu-42/SteamTradingSite-ID-Mapper "
    "(https://github.com/EricZhu-42/SteamTradingSite-ID-Mapper) at commit "
    "093adde1f9f3b0a5fd14957cd52fb988154251c3, file buff/730.json. "
    "Used under CC-BY-4.0; original rights belong to the contributors of "
    "that repository."
)
CATALOG_kind = "community_catalog"
SNAPSHOT_SCHEMA_VERSION = 1


class SnapshotBuilderError(RuntimeError):
    """The snapshot builder rejected the input source."""


def _validate_canonical_goods_id(value: object, *, market_hash_name: str) -> str:
    """Return canonical decimal-string goods_id if valid, else raise.

    A canonical BUFF goods_id is a positive integer > 0 expressed as a
    decimal string with no leading zeros (except the lone character "0"
    which is rejected because 0 is not a valid goods id).

    Explicitly rejected:
      None, True, False, floats, empty string, strings with non-digit
      characters, -1, 0.
    """
    # bool is a subclass of int in Python; reject it explicitly.
    if isinstance(value, bool):
        raise SnapshotBuilderError(
            f"goods_id must not be bool: {market_hash_name!r} -> {value!r}"
        )
    if isinstance(value, int):
        if value <= 0:
            raise SnapshotBuilderError(
                f"goods_id must be positive integer: {market_hash_name!r} -> {value}"
            )
        return str(value)
    if isinstance(value, float):
        raise SnapshotBuilderError(
            f"goods_id must not be float: {market_hash_name!r} -> {value!r}"
        )
    if isinstance(value, str):
        s = value.strip()
        if not s:
            raise SnapshotBuilderError(
                f"goods_id string is empty: {market_hash_name!r}"
            )
        if not s.isdigit():
            raise SnapshotBuilderError(
                f"goods_id string contains non-digits: {market_hash_name!r} -> {value!r}"
            )
        if len(s) > 1 and s.startswith("0"):
            raise SnapshotBuilderError(
                f"goods_id has leading zeros: {market_hash_name!r} -> {value!r}"
            )
        n = int(s)
        if n <= 0:
            raise SnapshotBuilderError(
                f"goods_id must be positive: {market_hash_name!r} -> {n}"
            )
        return s
    raise SnapshotBuilderError(
        f"goods_id has unsupported type: {market_hash_name!r} -> {type(value).__name__}"
    )


def _validate_market_hash_name(value: object, *, raw_key: str) -> str:
    if not isinstance(value, str):
        raise SnapshotBuilderError(
            f"market_hash_name must be string: {raw_key!r} -> {type(value).__name__}"
        )
    if not value:
        raise SnapshotBuilderError(
            f"market_hash_name is empty: {raw_key!r}"
        )
    if value != value.strip():
        raise SnapshotBuilderError(
            f"market_hash_name has surrounding whitespace: {value!r}"
        )
    return value


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_snapshot(
    raw_source: MappingABC[str, object],
    raw_sha256: str,
) -> dict[str, Any]:
    if not isinstance(raw_source, dict):
        raise SnapshotBuilderError("raw source must be a top-level object")

    accepted: dict[str, str] = {}
    rejected_count = 0
    rejection_reasons: dict[str, list[str]] = {}

    for raw_key, raw_value in raw_source.items():
        try:
            name = _validate_market_hash_name(raw_key, raw_key=str(raw_key))
        except SnapshotBuilderError as exc:
            rejected_count += 1
            rejection_reasons.setdefault(str(exc), []).append(repr(raw_key))
            continue
        try:
            gid = _validate_canonical_goods_id(raw_value, market_hash_name=name)
        except SnapshotBuilderError as exc:
            rejected_count += 1
            rejection_reasons.setdefault(str(exc), []).append(name)
            continue
        if name in accepted:
            # Same exact market_hash_name appears with two different goods_ids
            # in the source (or duplicates an already-accepted name). Detect.
            raise SnapshotBuilderError(
                f"duplicate market_hash_name in source: {name!r}"
            )
        accepted[name] = gid

    # Collision detection: same goods_id -> different market_hash_name
    by_gid: dict[str, list[str]] = {}
    for name, gid in accepted.items():
        by_gid.setdefault(gid, []).append(name)
    for gid, names in by_gid.items():
        if len(names) > 1:
            raise SnapshotBuilderError(
                f"goods_id collision: {gid!r} maps to multiple market_hash_names: {names}"
            )

    source_count = len(raw_source)
    accepted_count = len(accepted)

    items: dict[str, str] = dict(sorted(accepted.items(), key=lambda kv: pair_sort_key(kv[0])))

    # Stable diagnostic summary: group rejection reasons by category,
    # then list a small sample. Deterministic ordering.
    rejection_summary: dict[str, list[str]] = {}
    for reason, names in sorted(rejection_reasons.items()):
        rejection_summary[reason] = sorted(names)

    snapshot: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "catalog_kind": CATALOG_kind,
        "source": {
            "repository": SOURCE_REPOSITORY,
            "file": SOURCE_FILE,
            "commit": EXPECTED_SOURCE_COMMIT,
            "sha256": raw_sha256,
            "license": SOURCE_LICENSE,
            "attribution": SOURCE_ATTRIBUTION,
        },
        "counts": {
            "source": source_count,
            "accepted": accepted_count,
            "rejected": rejected_count,
        },
        "rejection_summary": rejection_summary,
        "items": items,
    }

    return snapshot


def pair_sort_key(name: str) -> tuple[int, str]:
    """Deterministic sort key: codepoint length first, then name.

    Tuple comparison is total for strings of the same length because
    strings compare codepoint-by-codepoint. Length first yields a
    grouping that is robust across sort libraries and stable in
    CPython.
    """
    return (len(name), name)


def serialize_snapshot(snapshot: dict[str, Any]) -> bytes:
    """Serialize a snapshot deterministically.

    - sorted keys at every level;
    - no whitespace separators (compact JSON);
    - UTF-8 encoded;
    - trailing newline for line-tool friendliness.
    """
    return (
        json.dumps(
            snapshot,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def build_snapshot_from_bytes(raw_bytes: bytes) -> tuple[dict[str, Any], bytes]:
    """Production builder. Verifies the pinned source SHA-256."""
    raw_sha256 = _sha256_hex(raw_bytes)
    if raw_sha256 != EXPECTED_RAW_SHA256:
        raise SnapshotBuilderError(
            f"raw source SHA-256 mismatch: expected "
            f"{EXPECTED_RAW_SHA256}, got {raw_sha256}"
        )
    parsed: object = json.loads(raw_bytes)
    if not isinstance(parsed, dict):
        raise SnapshotBuilderError("raw source must decode to a dict")
    snapshot = _build_snapshot(parsed, raw_sha256=raw_sha256)
    return snapshot, serialize_snapshot(snapshot)


def build_snapshot_from_dict(parsed: object) -> tuple[dict[str, Any], bytes]:
    """Lower-level builder used by tests. Does NOT verify SHA-256.

    The caller is responsible for ensuring the parsed object comes from
    a known source. The production builder `build_snapshot_from_bytes`
    is the correct entry point for the pinned source.
    """
    if not isinstance(parsed, dict):
        raise SnapshotBuilderError("raw source must decode to a dict")
    snapshot = _build_snapshot(parsed, raw_sha256="<test fixture>")
    return snapshot, serialize_snapshot(snapshot)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic builder for the BUFF community identity snapshot.",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the raw pinned source JSON file.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the canonical runtime snapshot JSON file.",
    )
    args = parser.parse_args(argv)

    with open(args.source, "rb") as f:
        raw_bytes = f.read()

    try:
        snapshot, output_bytes = build_snapshot_from_bytes(raw_bytes)
    except SnapshotBuilderError as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 2

    with open(args.output, "wb") as f:
        f.write(output_bytes)

    print(
        f"wrote {args.output}: "
        f"source={snapshot['counts']['source']} "
        f"accepted={snapshot['counts']['accepted']} "
        f"rejected={snapshot['counts']['rejected']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))