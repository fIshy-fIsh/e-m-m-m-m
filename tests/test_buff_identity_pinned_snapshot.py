"""Integration test for the actual pinned BUFF community identity snapshot."""

import asyncio
from pathlib import Path

import pytest

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)

SNAPSHOT_PATH = Path("data/identity/buff_identity_v1.json")
PINNED_COMMIT = "093adde1f9f3b0a5fd14957cd52fb988154251c3"
PINNED_RAW_SHA256 = "a7f370a61dd34f7d206e0372f6806cbcb936e1ba89e33f48bbb89adaa273d72f"


@pytest.fixture(scope="module")
def resolver() -> BuffCommunityIdentityResolver:
    if not SNAPSHOT_PATH.exists():
        pytest.skip(f"pinned snapshot not present at {SNAPSHOT_PATH}")
    return BuffCommunityIdentityResolver.from_snapshot_path(SNAPSHOT_PATH)


def test_snapshot_schema_and_counts(resolver: BuffCommunityIdentityResolver) -> None:
    md = resolver.metadata
    assert md.schema_version == 1
    assert md.catalog_kind == "community_catalog"
    assert md.repository == "EricZhu-42/SteamTradingSite-ID-Mapper"
    assert md.file == "buff/730.json"
    assert md.commit == PINNED_COMMIT
    assert md.sha256 == PINNED_RAW_SHA256
    assert md.license == "CC-BY-4.0"
    assert md.source_count == 34417
    assert md.accepted_count == 34402
    assert md.rejected_count == 15


def test_snapshot_indexes_size(resolver: BuffCommunityIdentityResolver) -> None:
    md = resolver.metadata
    # Both indexes must contain exactly the accepted count.
    assert len(resolver._forward) == md.accepted_count  # type: ignore[attr-defined]
    assert len(resolver._reverse) == md.accepted_count  # type: ignore[attr-defined]
    assert md.accepted_count == 34402


def test_snapshot_records_real_examples() -> None:
    """Verify a small set of deterministic exact-lookup entries.

    These are real entries from the pinned dataset; if the snapshot
    is regenerated from a different pin they will not match and the
    test will fail.
    """
    if not SNAPSHOT_PATH.exists():
        pytest.skip("pinned snapshot not present")
    r = BuffCommunityIdentityResolver.from_snapshot_path(SNAPSHOT_PATH)
    samples = [
        ("AK-47 | Redline (Field-Tested)", "33960"),
        ("★ Karambit | Doppler (Factory New)", "42998"),
        ("AWP | Dragon Lore (Factory New)", "44060"),
        ("StatTrak™ AK-47 | Redline (Field-Tested)", "38220"),
        ("Souvenir AWP | Dragon Lore (Factory New)", "45462"),
        ("Sticker | Howling Dawn", "40335"),
        ("AK-47 | The Empress (Field-Tested)", "33970"),
        ("Glock-18 | Fade (Factory New)", "35020"),
        ("★ M9 Bayonet | Fade (Factory New)", "33812"),
        ("Chroma Case", "33813"),
        ("Chroma 2 Case", "34369"),
        ("Operation Bravo Case", "35879"),
    ]
    for name, gid in samples:
        ident = r._forward.get(name)  # type: ignore[attr-defined]
        assert ident == gid, f"expected {name!r} -> {gid!r}, got {ident!r}"


def test_forward_lookup_round_trip() -> None:
    if not SNAPSHOT_PATH.exists():
        pytest.skip("pinned snapshot not present")
    r = BuffCommunityIdentityResolver.from_snapshot_path(SNAPSHOT_PATH)
    ident = asyncio.run(r.resolve("AK-47 | Redline (Field-Tested)"))
    assert ident is not None
    assert ident.goods_id == "33960"
    rev = asyncio.run(r.resolve_goods_id("33960"))
    assert rev is not None
    assert rev.market_hash_name == "AK-47 | Redline (Field-Tested)"


def test_pinned_snapshot_sha256_of_canonical_output() -> None:
    """The version-controlled canonical snapshot must hash to a known value.

    This guards against accidental edits to the snapshot file.
    """
    if not SNAPSHOT_PATH.exists():
        pytest.skip("pinned snapshot not present")
    import hashlib

    actual = hashlib.sha256(SNAPSHOT_PATH.read_bytes()).hexdigest()
    expected = "e3aab46d570869e0b6866eac44b26bca7492ea7c2c54669e74b2b4feeec506ac"
    assert actual == expected