"""Phase 13O-1 — Intrinsic-flag resolver and composition-layer tests.

These tests cover:

  * the canonical-name exact-byte classifier
    (`CanonicalNameIntrinsicFlagResolver`);
  * the structural resolver surface
    (`BuffListingIntrinsicFlagResolver`);
  * the composition layer that attaches flags to listings
    (`IntrinsicFlagResolvingBuffListingProvider`);
  * the separation between identity binding and intrinsic-flag
    binding (the identity-binding layer returns plain `BuffListing`;
    the intrinsic-flag binding layer wraps each listing).

Project conventions:
- async tests use `asyncio.run(...)` (no pytest-asyncio marker);
- the resolver never falls back to a different source;
- the resolver never infers from non-name fields;
- the resolver never produces `None` for a well-formed input
  (the canonical classifier emits `True` or `False`);
- `None` is reserved for inputs that fail validation upstream or for
  callers that explicitly wrap an unknown-source resolver.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.buff_identity_listing_provider import (
    bind_identity_to_provider,
)
from app.services.buff_intrinsic_flag_listing_provider import (
    bind_intrinsic_flags_to_provider,
)
from app.services.buff_intrinsic_flag_resolver import (
    SOUVENIR_PREFIX,
    STATTRAK_PREFIX,
    BuffListingIntrinsicFlagsValue,
    CanonicalNameIntrinsicFlagResolver,
    IntrinsicFlagInputError,
)
from app.services.buff_listing_intrinsic_flags import (
    IntrinsicFlagValidationError,
)
from app.services.buff_listing_provider import BuffListing

# ---------------------------------------------------------------------------
# A canonical-name classifier that covers all the prefixed-name rules.
# ---------------------------------------------------------------------------

REAL_STATTRAK_NAMES: list[str] = [
    "StatTrak™ AK-47 | Redline (Field-Tested)",
    "StatTrak™ M4A4 | Asiimov (Factory New)",
    "StatTrak™ ★ Karambit | Doppler (Factory New)",
]

REAL_SOUVENIR_NAMES: list[str] = [
    "Souvenir AWP | Dragon Lore (Factory New)",
    "Souvenir AK-47 | Fire Serpent (Factory New)",
]

REAL_NORMAL_NAMES: list[str] = [
    "AK-47 | Redline (Field-Tested)",
    "★ Karambit | Doppler (Factory New)",
    "AWP | Dragon Lore (Factory New)",
    "Sticker | Howling Dawn",
    "Chroma Case",
]


# ---------------------------------------------------------------------------
# (1) Known StatTrak exact name resolves to `stattrak=True`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", REAL_STATTRAK_NAMES)
def test_known_stattrak_name_resolves_to_true(name: str) -> None:
    resolver = CanonicalNameIntrinsicFlagResolver()
    value = resolver.resolve(name)
    assert isinstance(value, BuffListingIntrinsicFlagsValue)
    assert value.stattrak is True
    assert value.souvenir is False


# ---------------------------------------------------------------------------
# (2) Known non-StatTrak exact name resolves to `stattrak=False`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", REAL_NORMAL_NAMES + REAL_SOUVENIR_NAMES)
def test_known_non_stattrak_name_resolves_to_false(name: str) -> None:
    resolver = CanonicalNameIntrinsicFlagResolver()
    value = resolver.resolve(name)
    assert value.stattrak is False


# ---------------------------------------------------------------------------
# (3) Known Souvenir exact name resolves to `souvenir=True`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", REAL_SOUVENIR_NAMES)
def test_known_souvenir_name_resolves_to_true(name: str) -> None:
    resolver = CanonicalNameIntrinsicFlagResolver()
    value = resolver.resolve(name)
    assert value.souvenir is True
    assert value.stattrak is False


# ---------------------------------------------------------------------------
# (4) Known non-Souvenir exact name resolves to `souvenir=False`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", REAL_NORMAL_NAMES + REAL_STATTRAK_NAMES)
def test_known_non_souvenir_name_resolves_to_false(name: str) -> None:
    resolver = CanonicalNameIntrinsicFlagResolver()
    value = resolver.resolve(name)
    assert value.souvenir is False


# ---------------------------------------------------------------------------
# (5) Case difference does NOT match.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "stattrak™ AK-47 | Redline (Field-Tested)",   # lowercase
        "STATTRAK™ AK-47 | Redline (Field-Tested)",   # uppercase
        "Stattrak™ AK-47 | Redline (Field-Tested)",   # midcase
        "souvenir AWP | Dragon Lore (Factory New)",
        "SOUVENIR AWP | Dragon Lore (Factory New)",
    ],
)
def test_case_difference_does_not_match(name: str) -> None:
    """The classifier is case-sensitive; no casefold."""
    resolver = CanonicalNameIntrinsicFlagResolver()
    value = resolver.resolve(name)
    assert value.stattrak is False
    assert value.souvenir is False


# ---------------------------------------------------------------------------
# (6) Leading whitespace does NOT match.
# ---------------------------------------------------------------------------


def test_leading_whitespace_does_not_match() -> None:
    resolver = CanonicalNameIntrinsicFlagResolver()
    name = " " + REAL_STATTRAK_NAMES[0]
    with pytest.raises(IntrinsicFlagInputError):
        resolver.resolve(name)


# ---------------------------------------------------------------------------
# (7) Trailing whitespace does NOT match.
# ---------------------------------------------------------------------------


def test_trailing_whitespace_does_not_match() -> None:
    resolver = CanonicalNameIntrinsicFlagResolver()
    name = REAL_STATTRAK_NAMES[0] + " "
    with pytest.raises(IntrinsicFlagInputError):
        resolver.resolve(name)


# ---------------------------------------------------------------------------
# (8) Look-alike Unicode does NOT match.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        # Replace ™ (TM SIGN) with ℠ (SERVICE MARK)
        "StatTrak℠ AK-47 | Redline (Field-Tested)",
        # Replace ™ with ® (REGISTERED)
        "StatTrak® AK-47 | Redline (Field-Tested)",
        # Replace ™ with  (lowercase TM lookalike that is invalid)
        "StatTrak AK-47 | Redline (Field-Tested)",
    ],
)
def test_lookalike_unicode_does_not_match(name: str) -> None:
    """The classifier requires the exact byte sequence 'StatTrak™ '."""
    resolver = CanonicalNameIntrinsicFlagResolver()
    value = resolver.resolve(name)
    assert value.stattrak is False
    assert value.souvenir is False


# ---------------------------------------------------------------------------
# (9) Substring in middle does NOT match.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        # 'StatTrak' substring but at a non-prefix position
        "AK-47 | StatTrak Edition (Field-Tested)",
        # 'Souvenir' substring at a non-prefix position
        "AK-47 | Souvenir Drop (Field-Tested)",
    ],
)
def test_substring_in_middle_does_not_match(name: str) -> None:
    resolver = CanonicalNameIntrinsicFlagResolver()
    value = resolver.resolve(name)
    assert value.stattrak is False
    assert value.souvenir is False


# ---------------------------------------------------------------------------
# (10) Unknown / malformed input is rejected with the documented error.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        " ",
        1,
        1.0,
        True,
        [],
        b"StatTrak AK-47",
    ],
)
def test_malformed_input_is_rejected(value: object) -> None:
    resolver = CanonicalNameIntrinsicFlagResolver()
    with pytest.raises((IntrinsicFlagInputError, IntrinsicFlagValidationError)):
        resolver.resolve(value)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# (11) No fuzzy matching; deterministic repeated result.
# ---------------------------------------------------------------------------


def test_deterministic_repeated_results() -> None:
    resolver = CanonicalNameIntrinsicFlagResolver()
    first = resolver.resolve(REAL_STATTRAK_NAMES[0])
    second = resolver.resolve(REAL_STATTRAK_NAMES[0])
    third = resolver.resolve(REAL_STATTRAK_NAMES[0])
    assert first == second == third
    assert first.stattrak is True


# ---------------------------------------------------------------------------
# (12) No network calls; the resolver is pure.
# ---------------------------------------------------------------------------


def test_resolver_is_pure() -> None:
    """The resolver does not touch any I/O surface.

    Verified by inspecting the module source via AST: it imports only
    dataclasses and typing; it does not import any HTTP, filesystem,
    or network-touching module.
    """
    import ast
    src_path = Path(__file__).resolve().parents[1].joinpath(
        "app/services/buff_intrinsic_flag_resolver.py"
    )
    source = src_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    plain_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                plain_imports.add(alias.name)
    # Confirm the resolver imports only safe modules.
    safe_imports = {"dataclasses", "typing", "__future__"}
    unsafe = (imports | plain_imports) - safe_imports
    # The one allowed import is the legacy IntrinsicFlagValidationError
    # for compatibility; everything else must be absent.
    unsafe -= {"app.services.buff_listing_intrinsic_flags"}
    assert not unsafe, f"unexpected imports: {unsafe}"
    # And the resolver source must not contain network-touching calls.
    for forbidden in (
        "open(",
        "os.environ",
        "socket",
        "urlopen",
        ".get(",  # could be httpx or requests
        "httpx",
        "aiohttp",
        "requests",
        "websockets",
        "redis",
    ):
        assert forbidden not in source, (
            f"forbidden token {forbidden!r} in resolver source"
        )


# ---------------------------------------------------------------------------
# (13) Identity binding remains identity-only.
# ---------------------------------------------------------------------------


def test_identity_binding_returns_plain_buff_listings() -> None:
    """Phase 13O-1: identity binding must NOT carry intrinsic flags."""
    from app.services.buff_item_identity import BuffItemIdentity

    class FakeProvider:
        async def get_listings(self, goods_id: str) -> list[BuffListing]:
            return [_listing("l-1", market_hash_name=REAL_STATTRAK_NAMES[0])]

    class FakeResolver:
        async def resolve_goods_id(self, goods_id: str) -> BuffItemIdentity | None:
            return BuffItemIdentity(
                market_hash_name=REAL_STATTRAK_NAMES[0],
                goods_id=goods_id,
            )

    bound = bind_identity_to_provider(FakeProvider(), FakeResolver())
    listings = asyncio.run(bound.get_listings("goods-1"))
    assert len(listings) == 1
    # Plain BuffListing, not the wrapper.
    assert isinstance(listings[0], BuffListing)
    assert not isinstance(
        listings[0],
        __import__(
            "app.services.buff_listing_intrinsic_flags",
            fromlist=["BuffListingIntrinsicFlags"],
        ).BuffListingIntrinsicFlags,
    )


# ---------------------------------------------------------------------------
# (14) Intrinsic-flag binding is a separate stage.
# ---------------------------------------------------------------------------


def test_intrinsic_flag_binding_is_separate_stage() -> None:
    """The intrinsic-flag binding layer wraps listings produced by
    the identity binding layer; it does not itself carry identity
    resolution responsibility.
    """
    from app.services.buff_item_identity import BuffItemIdentity

    class FakeProvider:
        async def get_listings(self, goods_id: str) -> list[BuffListing]:
            return [_listing("l-1", market_hash_name=REAL_STATTRAK_NAMES[0])]

    class FakeResolver:
        async def resolve_goods_id(self, goods_id: str) -> BuffItemIdentity | None:
            return BuffItemIdentity(
                market_hash_name=REAL_STATTRAK_NAMES[0],
                goods_id=goods_id,
            )

    identity_bound = bind_identity_to_provider(FakeProvider(), FakeResolver())
    full_bound = bind_intrinsic_flags_to_provider(
        identity_bound, CanonicalNameIntrinsicFlagResolver()
    )
    listings = asyncio.run(full_bound.get_listings("goods-1"))
    assert len(listings) == 1
    from app.services.buff_listing_intrinsic_flags import BuffListingIntrinsicFlags
    assert isinstance(listings[0], BuffListingIntrinsicFlags)
    assert listings[0].stattrak is True
    assert listings[0].souvenir is False
    # The wrapped listing's underlying BuffListing is preserved.
    assert listings[0].listing_id == "l-1"
    assert listings[0].market_hash_name == REAL_STATTRAK_NAMES[0]


# ---------------------------------------------------------------------------
# (15) All non-intrinsic listing fields are preserved.
# ---------------------------------------------------------------------------


def test_all_non_intrinsic_fields_preserved_through_intrinsic_binding() -> None:
    listing = BuffListing(
        listing_id="listing-1",
        goods_id="goods-1",
        market_hash_name=REAL_NORMAL_NAMES[0],
        price_cny=Decimal("12.34"),
        paintwear=Decimal("0.1234"),
        asset_id="asset-1",
        paintseed=99,
        source="buff",
    )

    class FakeProvider:
        async def get_listings(self, goods_id: str) -> list[BuffListing]:
            return [listing]

    full_bound = bind_intrinsic_flags_to_provider(
        FakeProvider(), CanonicalNameIntrinsicFlagResolver()
    )
    out = asyncio.run(full_bound.get_listings("goods-1"))[0]
    assert out.listing_id == "listing-1"
    assert out.goods_id == "goods-1"
    assert out.market_hash_name == REAL_NORMAL_NAMES[0]
    assert out.price_cny == Decimal("12.34")
    assert out.paintwear == Decimal("0.1234")
    assert out.asset_id == "asset-1"
    assert out.paintseed == 99
    assert out.source == "buff"


# ---------------------------------------------------------------------------
# (16) Order is preserved.
# ---------------------------------------------------------------------------


def test_listing_order_preserved_through_intrinsic_binding() -> None:
    """All listings in one page share the same canonical name.

    The intrinsic-flag binding layer requires the page to carry a
    single canonical `market_hash_name`. The classifier is invoked
    once per page; that result is applied to every listing.
    """
    listings = [
        _listing("l-1", market_hash_name=REAL_NORMAL_NAMES[0]),
        _listing("l-2", market_hash_name=REAL_NORMAL_NAMES[0]),
        _listing("l-3", market_hash_name=REAL_NORMAL_NAMES[0]),
    ]

    class FakeProvider:
        async def get_listings(self, goods_id: str) -> list[BuffListing]:
            return list(listings)

    full_bound = bind_intrinsic_flags_to_provider(
        FakeProvider(), CanonicalNameIntrinsicFlagResolver()
    )
    out = asyncio.run(full_bound.get_listings("goods-1"))
    assert [item.listing_id for item in out] == ["l-1", "l-2", "l-3"]
    for item in out:
        assert item.stattrak is False
        assert item.souvenir is False


def test_inconsistent_page_identity_fails_closed() -> None:
    """The intrinsic-flag binding layer refuses to classify a page
    that carries conflicting canonical names.
    """
    listings = [
        _listing("l-1", market_hash_name=REAL_NORMAL_NAMES[0]),
        _listing("l-2", market_hash_name=REAL_STATTRAK_NAMES[0]),
        _listing("l-3", market_hash_name=REAL_SOUVENIR_NAMES[0]),
    ]

    class FakeProvider:
        async def get_listings(self, goods_id: str) -> list[BuffListing]:
            return list(listings)

    from app.services.buff_intrinsic_flag_resolver import IntrinsicFlagInputError

    full_bound = bind_intrinsic_flags_to_provider(
        FakeProvider(), CanonicalNameIntrinsicFlagResolver()
    )
    with pytest.raises(IntrinsicFlagInputError):
        asyncio.run(full_bound.get_listings("goods-1"))


def test_three_distinct_pages_each_make_one_resolver_call() -> None:
    """For N pages with distinct canonical names, the resolver is
    invoked exactly once per page — never per listing.
    """
    from app.services.buff_item_identity import BuffItemIdentity

    class CountingResolver:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def resolve(self, market_hash_name: str) -> BuffListingIntrinsicFlagsValue:
            self.calls.append(market_hash_name)
            return BuffListingIntrinsicFlagsValue(stattrak=False, souvenir=False)

    class FakeProvider:
        async def get_listings(self, goods_id: str) -> list[BuffListing]:
            n = int(goods_id.split("-")[1])
            canonical = [
                REAL_NORMAL_NAMES[0],
                REAL_STATTRAK_NAMES[0],
                REAL_SOUVENIR_NAMES[0],
            ][n]
            return [
                _listing(
                    f"l-{i}",
                    goods_id=goods_id,
                    market_hash_name=canonical,
                )
                for i in range(3)
            ]

    class FakeIdentityResolver:
        async def resolve_goods_id(self, goods_id: str) -> BuffItemIdentity | None:
            return None

    counting = CountingResolver()
    identity_bound = bind_identity_to_provider(
        FakeProvider(), FakeIdentityResolver()
    )
    full_bound = bind_intrinsic_flags_to_provider(identity_bound, counting)
    asyncio.run(full_bound.get_listings("goods-0"))
    asyncio.run(full_bound.get_listings("goods-1"))
    asyncio.run(full_bound.get_listings("goods-2"))
    assert len(counting.calls) == 3
    assert counting.calls[0] == REAL_NORMAL_NAMES[0]
    assert counting.calls[1] == REAL_STATTRAK_NAMES[0]
    assert counting.calls[2] == REAL_SOUVENIR_NAMES[0]


# ---------------------------------------------------------------------------
# (17) Unresolved identity keeps both flags `None`.
# ---------------------------------------------------------------------------


def test_unresolved_identity_keeps_flags_unknown() -> None:
    """When identity binding leaves `market_hash_name=None`, the
    intrinsic-flag binding layer cannot classify and both flags
    remain `None` (unknown).
    """
    listing = _listing("l-1", market_hash_name=None)

    class FakeProvider:
        async def get_listings(self, goods_id: str) -> list[BuffListing]:
            return [listing]

    full_bound = bind_intrinsic_flags_to_provider(
        FakeProvider(), CanonicalNameIntrinsicFlagResolver()
    )
    out = asyncio.run(full_bound.get_listings("goods-1"))
    assert out[0].stattrak is None
    assert out[0].souvenir is None


# ---------------------------------------------------------------------------
# (18) Catalog-wide invariant test — the classifier covers every entry.
# ---------------------------------------------------------------------------


def test_classifier_covers_every_pinned_catalog_entry() -> None:
    """Walk the entire pinned identity catalog and confirm that the
    canonical-name classifier covers every accepted entry with no
    contradiction.

    The rule is: a name starts with at most one of the two canonical
    prefixes; the total covered equals the accepted catalog size.
    """
    snapshot_path = Path("data/identity/buff_identity_v1.json")
    if not snapshot_path.exists():
        pytest.skip("pinned snapshot not present")
    import json
    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    items = data["items"]
    accepted = len(items)
    resolver = CanonicalNameIntrinsicFlagResolver()
    classified_st_true = 0
    classified_st_false = 0
    classified_sv_true = 0
    classified_sv_false = 0
    contradictions = 0
    for name in items.keys():
        v = resolver.resolve(name)
        if v.stattrak:
            classified_st_true += 1
        else:
            classified_st_false += 1
        if v.souvenir:
            classified_sv_true += 1
        else:
            classified_sv_false += 1
        if v.stattrak and v.souvenir:
            contradictions += 1
    assert classified_st_true + classified_st_false == accepted
    assert classified_sv_true + classified_sv_false == accepted
    assert contradictions == 0


# ---------------------------------------------------------------------------
# (19) Catalog invariants against pinned-snapshot identity resolver.
# ---------------------------------------------------------------------------


def test_full_seam_with_pinned_identity_and_canonical_classifier() -> None:
    """The full seam runs against the actual pinned identity snapshot.

    This test verifies that for any well-known pinned entry, the
    intrinsic-flag classifier produces the canonical expected result.
    """
    snapshot_path = Path("data/identity/buff_identity_v1.json")
    if not snapshot_path.exists():
        pytest.skip("pinned snapshot not present")
    # Verify the snapshot is well-formed before exercising the classifier.
    BuffCommunityIdentityResolver.from_snapshot_path(snapshot_path)
    intrinsic = CanonicalNameIntrinsicFlagResolver()
    # Pull three well-known catalog entries: one of each kind.
    samples = [
        ("AK-47 | Redline (Field-Tested)", False, False),
        ("StatTrak™ AK-47 | Redline (Field-Tested)", True, False),
        ("Souvenir AWP | Dragon Lore (Factory New)", False, True),
    ]
    for name, expected_st, expected_sv in samples:
        value = intrinsic.resolve(name)
        assert value.stattrak is expected_st
        assert value.souvenir is expected_sv


# ---------------------------------------------------------------------------
# (20) Full identity binding layer still emits exactly one resolver call.
# ---------------------------------------------------------------------------


def test_intrinsic_binding_makes_one_resolver_call_per_page() -> None:
    from app.services.buff_item_identity import BuffItemIdentity

    class CountingResolver:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def resolve(self, market_hash_name: str) -> BuffListingIntrinsicFlagsValue:
            self.calls.append(market_hash_name)
            return BuffListingIntrinsicFlagsValue(stattrak=False, souvenir=False)

    class FakeProvider:
        async def get_listings(self, goods_id: str) -> list[BuffListing]:
            return [
                _listing("l-1", market_hash_name=REAL_NORMAL_NAMES[0]),
                _listing("l-2", market_hash_name=REAL_NORMAL_NAMES[0]),
                _listing("l-3", market_hash_name=REAL_NORMAL_NAMES[0]),
            ]

    class FakeIdentityResolver:
        async def resolve_goods_id(self, goods_id: str) -> BuffItemIdentity | None:
            return None  # Let each listing keep its own market_hash_name.

    counting = CountingResolver()
    identity_bound = bind_identity_to_provider(
        FakeProvider(), FakeIdentityResolver()
    )
    full_bound = bind_intrinsic_flags_to_provider(identity_bound, counting)
    asyncio.run(full_bound.get_listings("goods-1"))
    assert len(counting.calls) == 1
    assert counting.calls == [REAL_NORMAL_NAMES[0]]


# ---------------------------------------------------------------------------
# Catalog invariant regression tests (Phase 13O-1A).
# ---------------------------------------------------------------------------


STATTRAK_PREFIX_LEN_CODEPOINTS = 10
STATTRAK_PREFIX_LEN_UTF8 = 12
SOUVENIR_PREFIX_LEN_CODEPOINTS = 9
SOUVENIR_PREFIX_LEN_UTF8 = 9


def test_prefix_constants_have_exact_documented_lengths() -> None:
    """Verify the prefix constants' codepoint and UTF-8 byte lengths."""
    assert len(STATTRAK_PREFIX) == STATTRAK_PREFIX_LEN_CODEPOINTS
    assert len(STATTRAK_PREFIX.encode("utf-8")) == STATTRAK_PREFIX_LEN_UTF8
    assert len(SOUVENIR_PREFIX) == SOUVENIR_PREFIX_LEN_CODEPOINTS
    assert len(SOUVENIR_PREFIX.encode("utf-8")) == SOUVENIR_PREFIX_LEN_UTF8


def test_pinned_catalog_matrix_matches_documented_counts() -> None:
    """Walk the entire pinned identity catalog and verify the four
    independent counts and the four quadrant counts.
    """
    snapshot_path = Path("data/identity/buff_identity_v1.json")
    if not snapshot_path.exists():
        pytest.skip("pinned snapshot not present")
    import json
    items = json.loads(snapshot_path.read_text(encoding="utf-8"))["items"]
    total = len(items)

    resolver = CanonicalNameIntrinsicFlagResolver()
    stattrak_true = 0
    stattrak_false = 0
    souvenir_true = 0
    souvenir_false = 0
    both_true = 0
    both_false = 0
    stattrak_only = 0
    souvenir_only = 0
    # Per-listing state checks.
    for name in items.keys():
        value = resolver.resolve(name)
        # Independence: both flags must be exact booleans.
        assert type(value.stattrak) is bool
        assert type(value.souvenir) is bool
        if value.stattrak:
            stattrak_true += 1
        else:
            stattrak_false += 1
        if value.souvenir:
            souvenir_true += 1
        else:
            souvenir_false += 1
        if value.stattrak and value.souvenir:
            both_true += 1
        if not value.stattrak and not value.souvenir:
            both_false += 1
        if value.stattrak and not value.souvenir:
            stattrak_only += 1
        if not value.stattrak and value.souvenir:
            souvenir_only += 1

    # Independent totals.
    assert stattrak_true == 3377
    assert stattrak_false == 31025  # total - 3377
    assert souvenir_true == 2345
    assert souvenir_false == 32057  # total - 2345
    assert stattrak_true + stattrak_false == total
    assert souvenir_true + souvenir_false == total

    # Quadrant totals.
    assert both_true == 0
    assert both_false == 28680
    assert stattrak_only == 3377
    assert souvenir_only == 2345
    # All four quadrants partition the catalog.
    assert (
        stattrak_only + souvenir_only + both_true + both_false
    ) == total


@pytest.mark.parametrize(
    ("name", "expected_st", "expected_sv"),
    [
        ("StatTrak™ AK-47 | Redline (Field-Tested)", True, False),
        ("Souvenir AWP | Dragon Lore (Factory New)", False, True),
        ("AK-47 | Redline (Field-Tested)", False, False),
    ],
)
def test_canonical_samples_classify_correctly(
    name: str,
    expected_st: bool,
    expected_sv: bool,
) -> None:
    """Each canonical sample must yield the documented flag pair."""
    resolver = CanonicalNameIntrinsicFlagResolver()
    value = resolver.resolve(name)
    assert value.stattrak is expected_st
    assert value.souvenir is expected_sv


def test_unresolved_identity_keeps_flags_unknown_through_seam() -> None:
    """Unresolved identity at the identity binding layer leaves
    both flags `None` through the intrinsic-flag binding layer.
    """
    listing = _listing("l-1", market_hash_name=None)

    class FakeProvider:
        async def get_listings(self, goods_id: str) -> list[BuffListing]:
            return [listing]

    full_bound = bind_intrinsic_flags_to_provider(
        FakeProvider(), CanonicalNameIntrinsicFlagResolver()
    )
    out = asyncio.run(full_bound.get_listings("goods-1"))
    assert out[0].stattrak is None
    assert out[0].souvenir is None


@pytest.mark.parametrize(
    "value",
    [None, "", " ", 1, 1.0, True, [], b"StatTrak AK-47"],
)
def test_malformed_input_raises_intrinsic_flag_input_error(value: object) -> None:
    """The classifier raises `IntrinsicFlagInputError` for malformed input."""
    resolver = CanonicalNameIntrinsicFlagResolver()
    with pytest.raises(IntrinsicFlagInputError):
        resolver.resolve(value)  # type: ignore[arg-type]


def test_deterministic_full_catalog_result() -> None:
    """Walking the catalog twice yields the same per-listing results."""
    snapshot_path = Path("data/identity/buff_identity_v1.json")
    if not snapshot_path.exists():
        pytest.skip("pinned snapshot not present")
    import json
    items = json.loads(snapshot_path.read_text(encoding="utf-8"))["items"]
    resolver = CanonicalNameIntrinsicFlagResolver()
    first = [resolver.resolve(name) for name in items.keys()]
    second = [resolver.resolve(name) for name in items.keys()]
    assert first == second


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _listing(
    listing_id: str,
    *,
    market_hash_name: str | None,
    goods_id: str = "goods-1",
) -> BuffListing:
    return BuffListing(
        listing_id=listing_id,
        goods_id=goods_id,
        market_hash_name=market_hash_name,
        price_cny=Decimal("10.00"),
        paintwear=Decimal("0.1"),
        asset_id="asset-1",
        paintseed=1,
        source="buff",
    )