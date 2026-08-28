"""Tests for the bounded market universe builder (Phase 13R).

Pure, offline, deterministic tests. No network, no I/O, no async. The
builder must remain a planning-layer module and never call BUFF or
SteamDT.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.buff_community_identity_resolver import (
    EXPECTED_SCHEMA_VERSION,
    BuffCommunityIdentityResolver,
    BuffCommunitySnapshotMetadata,
)
from app.services.market_universe_builder import (
    BoundedMarketUniverseBuilderError,
    MarketUniverseErrorReason,
    MarketUniverseSpec,
    SouvenirInclusion,
    StatTrakMode,
    UniverseAllocationStrategy,
    build_universe_goods_ids,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver


def _metadata(
    *,
    sha256: str = "deadbeef" * 8,
    source_count: int = 1,
    accepted_count: int = 1,
    rejected_count: int = 0,
) -> BuffCommunitySnapshotMetadata:
    return BuffCommunitySnapshotMetadata(
        schema_version=EXPECTED_SCHEMA_VERSION,
        catalog_kind="community_catalog",
        repository="example/test",
        file="x.json",
        commit="abc",
        sha256=sha256,
        license="CC-BY-4.0",
        attribution="test",
        source_count=source_count,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
    )


def _resolver(pairs: dict[str, str]) -> BuffCommunityIdentityResolver:
    forward = dict(pairs)
    reverse = {gid: name for name, gid in forward.items()}
    return BuffCommunityIdentityResolver(
        forward=forward, reverse=reverse, metadata=_metadata()
    )


def _metadata_entry(
    *,
    market_hash_name: str,
    collection_name: str,
    rarity: str,
    stattrak: bool = False,
    souvenir: bool = False,
) -> dict[str, object]:
    return {
        "market_hash_name": market_hash_name,
        "collection_name": collection_name,
        "rarity": rarity,
        "min_float": 0.0,
        "max_float": 1.0,
        "stattrak": stattrak,
        "souvenir": souvenir,
    }


def _resolver_from_metadata(
    entries: list[dict[str, object]],
) -> BuffCommunityIdentityResolver:
    pairs = {
        str(entry["market_hash_name"]): str(index)
        for index, entry in enumerate(entries, start=1)
    }
    return _resolver(pairs)


def _metadata_resolver_from_entries(
    entries: list[dict[str, object]],
) -> PinnedSkinMetadataResolver:
    return PinnedSkinMetadataResolver.from_payload(entries)


def test_identities_property_is_deterministic_length_name_sorted() -> None:
    resolver = _resolver(
        {
            "ZZ | Redline": "1",
            "AB | Redline": "2",
            "A | Redline": "3",
        }
    )
    identities = resolver.identities
    assert [name for name, _gid in identities] == [
        "A | Redline",
        "AB | Redline",
        "ZZ | Redline",
    ]
    assert identities == tuple(sorted(identities, key=lambda kv: (len(kv[0]), kv[0])))


def test_productive_rarities_are_first_five() -> None:
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        souvenir_inclusion=SouvenirInclusion.INCLUDE,
        cap=1,
    )
    assert spec.rarity in (
        "Consumer Grade",
        "Industrial Grade",
        "Mil-Spec Grade",
        "Restricted",
        "Classified",
    )


def test_unsupported_rarity_rejected() -> None:
    with pytest.raises(BoundedMarketUniverseBuilderError) as info:
        MarketUniverseSpec(
            rarity="Covert",
            stattrak_mode=StatTrakMode.NORMAL,
            souvenir_inclusion=SouvenirInclusion.INCLUDE,
            cap=1,
        )
    assert info.value.reason == MarketUniverseErrorReason.UNSUPPORTED_RARITY.value


def test_unknown_rarity_rejected() -> None:
    with pytest.raises(BoundedMarketUniverseBuilderError) as info:
        MarketUniverseSpec(
            rarity="Mythology",
            stattrak_mode=StatTrakMode.NORMAL,
            souvenir_inclusion=SouvenirInclusion.INCLUDE,
            cap=1,
        )
    assert info.value.reason == MarketUniverseErrorReason.UNSUPPORTED_RARITY.value


def test_cap_must_be_in_unit_interval() -> None:
    with pytest.raises(BoundedMarketUniverseBuilderError) as info:
        MarketUniverseSpec(
            rarity="Restricted",
            stattrak_mode=StatTrakMode.NORMAL,
            souvenir_inclusion=SouvenirInclusion.INCLUDE,
            cap=0,
        )
    assert info.value.reason == MarketUniverseErrorReason.UNIVERSE_OVER_HARD_MAX.value
    with pytest.raises(BoundedMarketUniverseBuilderError) as info:
        MarketUniverseSpec(
            rarity="Restricted",
            stattrak_mode=StatTrakMode.NORMAL,
            souvenir_inclusion=SouvenirInclusion.INCLUDE,
            cap=11,
        )
    assert info.value.reason == MarketUniverseErrorReason.UNIVERSE_OVER_HARD_MAX.value


def test_collection_allowlist_invalid_value_rejected() -> None:
    with pytest.raises(BoundedMarketUniverseBuilderError) as info:
        MarketUniverseSpec(
            rarity="Restricted",
            stattrak_mode=StatTrakMode.NORMAL,
            souvenir_inclusion=SouvenirInclusion.INCLUDE,
            cap=1,
            collection_allowlist=("   ",),
        )
    assert info.value.reason == MarketUniverseErrorReason.COLLECTION_NOT_IN_CATALOG.value


def _two_collection_metadata() -> list[dict[str, object]]:
    return [
        # Cobblestone Restricted inputs
        _metadata_entry(
            market_hash_name="CZ75-Auto | Chalice (Factory New)",
            collection_name="The Cobblestone Collection",
            rarity="Restricted",
        ),
        _metadata_entry(
            market_hash_name="CZ75-Auto | Chalice (Minimal Wear)",
            collection_name="The Cobblestone Collection",
            rarity="Restricted",
        ),
        # Cobblestone Restricted Souvenir inputs
        _metadata_entry(
            market_hash_name="Souvenir CZ75-Auto | Chalice (Factory New)",
            collection_name="The Cobblestone Collection",
            rarity="Restricted",
            souvenir=True,
        ),
        # Cobblestone Classified outputs (canonical non-Souvenir)
        _metadata_entry(
            market_hash_name="M4A1-S | Knight (Factory New)",
            collection_name="The Cobblestone Collection",
            rarity="Classified",
        ),
        _metadata_entry(
            market_hash_name="M4A1-S | Knight (Minimal Wear)",
            collection_name="The Cobblestone Collection",
            rarity="Classified",
        ),
        # Ancient Collection Restricted input + Classified output
        _metadata_entry(
            market_hash_name="USP-S | Cortex (Factory New)",
            collection_name="The Ancient Collection",
            rarity="Restricted",
        ),
        _metadata_entry(
            market_hash_name="XM1014 | Red Python (Factory New)",
            collection_name="The Ancient Collection",
            rarity="Classified",
        ),
        # A metadata row with no matching identity
        _metadata_entry(
            market_hash_name="OrphanSkin",
            collection_name="The Cobblestone Collection",
            rarity="Restricted",
        ),
        # A metadata row whose collection has no valid next-rarity output
        _metadata_entry(
            market_hash_name="LonelySkin",
            collection_name="The Lonely Collection",
            rarity="Restricted",
        ),
    ]


def test_default_restricted_normal_include_selects_within_hard_bound() -> None:
    entries = _two_collection_metadata()
    identity = _resolver_from_metadata(entries)
    metadata = _metadata_resolver_from_entries(entries)
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        souvenir_inclusion=SouvenirInclusion.INCLUDE,
        cap=10,
    )
    result = build_universe_goods_ids(
        identity_resolver=identity,
        metadata_resolver=metadata,
        spec=spec,
    )
    assert len(result.goods_ids) <= 10
    assert len(result.goods_ids) >= 1
    assert all(
        market_hash_name in {entry["market_hash_name"] for entry in entries}
        for market_hash_name in result.selected_market_hash_names
    )


def test_two_runs_produce_byte_equal_universes() -> None:
    entries = _two_collection_metadata()
    identity = _resolver_from_metadata(entries)
    metadata = _metadata_resolver_from_entries(entries)
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        souvenir_inclusion=SouvenirInclusion.INCLUDE,
        cap=4,
    )
    a = build_universe_goods_ids(
        identity_resolver=identity, metadata_resolver=metadata, spec=spec
    )
    b = build_universe_goods_ids(
        identity_resolver=identity, metadata_resolver=metadata, spec=spec
    )
    assert a.goods_ids == b.goods_ids
    assert a.selected_market_hash_names == b.selected_market_hash_names


def test_round_robin_spans_collections() -> None:
    entries = _two_collection_metadata()
    identity = _resolver_from_metadata(entries)
    metadata = _metadata_resolver_from_entries(entries)
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        souvenir_inclusion=SouvenirInclusion.INCLUDE,
        cap=2,
    )
    result = build_universe_goods_ids(
        identity_resolver=identity, metadata_resolver=metadata, spec=spec
    )
    assert len(result.goods_ids) == 2
    assert len(set(result.goods_ids)) == 2


def test_collection_allowlist_filters_deterministically() -> None:
    entries = _two_collection_metadata()
    identity = _resolver_from_metadata(entries)
    metadata = _metadata_resolver_from_entries(entries)
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        souvenir_inclusion=SouvenirInclusion.INCLUDE,
        cap=5,
        collection_allowlist=("The Cobblestone Collection",),
    )
    result = build_universe_goods_ids(
        identity_resolver=identity, metadata_resolver=metadata, spec=spec
    )
    assert result.goods_ids, "expected at least one Cobblestone target"
    # The fixture gives every metadata row an identity; we only verify that
    # Ancient Collection rows were excluded and the lonely-collection row had
    # no valid output. Either way, the allowlist counter must reflect at
    # least the Ancient rows.
    assert result.diagnostics.excluded_by_allowlist >= 1
    assert all(
        not name.startswith("USP-S") and not name.startswith("XM1014")
        for name in result.selected_market_hash_names
    )


def test_stattrak_mode_bucket_excludes_other_mode() -> None:
    entries = [
        _metadata_entry(
            market_hash_name="StatTrak™ AK-47 | Redline (Field-Tested)",
            collection_name="Col A",
            rarity="Restricted",
            stattrak=True,
        ),
        _metadata_entry(
            market_hash_name="AK-47 | Redline (Field-Tested)",
            collection_name="Col A",
            rarity="Restricted",
            stattrak=False,
        ),
        _metadata_entry(
            market_hash_name="StatTrak™ M4A4 | Asiimov (Factory New)",
            collection_name="Col A",
            rarity="Classified",
            stattrak=True,
        ),
    ]
    identity = _resolver_from_metadata(entries)
    metadata = _metadata_resolver_from_entries(entries)
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.STATTRAK,
        souvenir_inclusion=SouvenirInclusion.INCLUDE,
        cap=5,
    )
    result = build_universe_goods_ids(
        identity_resolver=identity, metadata_resolver=metadata, spec=spec
    )
    assert all(
        market_hash_name.startswith("StatTrak")
        for market_hash_name in result.selected_market_hash_names
    )


def test_souvenir_exclude_drops_souvenir_rows() -> None:
    entries = _two_collection_metadata()
    identity = _resolver_from_metadata(entries)
    metadata = _metadata_resolver_from_entries(entries)
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        souvenir_inclusion=SouvenirInclusion.EXCLUDE,
        cap=5,
    )
    result = build_universe_goods_ids(
        identity_resolver=identity, metadata_resolver=metadata, spec=spec
    )
    assert all(
        not market_hash_name.startswith("Souvenir ")
        for market_hash_name in result.selected_market_hash_names
    )


def test_inputs_without_valid_output_counted_in_no_valid_output() -> None:
    entries = _two_collection_metadata()
    identity = _resolver_from_metadata(entries)
    metadata = _metadata_resolver_from_entries(entries)
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        souvenir_inclusion=SouvenirInclusion.INCLUDE,
        cap=10,
    )
    result = build_universe_goods_ids(
        identity_resolver=identity, metadata_resolver=metadata, spec=spec
    )
    assert result.diagnostics.excluded_no_valid_output >= 1


def test_metadata_without_identity_counted_in_no_identity() -> None:
    entries = _two_collection_metadata()
    # Restrict the identity catalog to a single Chalice so other rows
    # become truthful `no_identity` candidates.
    identity = _resolver(
        {"CZ75-Auto | Chalice (Factory New)": "1"}
    )
    metadata = _metadata_resolver_from_entries(entries)
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        souvenir_inclusion=SouvenirInclusion.INCLUDE,
        cap=10,
    )
    result = build_universe_goods_ids(
        identity_resolver=identity, metadata_resolver=metadata, spec=spec
    )
    assert result.diagnostics.excluded_no_identity >= 1


def test_empty_eligible_universe_fails_closed() -> None:
    entries = _two_collection_metadata()
    identity = _resolver({})
    metadata = _metadata_resolver_from_entries(entries)
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        souvenir_inclusion=SouvenirInclusion.INCLUDE,
        cap=10,
    )
    with pytest.raises(BoundedMarketUniverseBuilderError) as info:
        build_universe_goods_ids(
            identity_resolver=identity, metadata_resolver=metadata, spec=spec
        )
    assert info.value.reason == MarketUniverseErrorReason.UNIVERSE_EMPTY.value


def test_memory_error_propagates_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = MemoryError("builder sentinel")

    def fail(**_: object) -> None:
        raise sentinel

    monkeypatch.setattr(
        "app.services.market_universe_builder.is_current_standard_trade_up_output_eligible",
        fail,
    )
    entries = _two_collection_metadata()
    identity = _resolver_from_metadata(entries)
    metadata = _metadata_resolver_from_entries(entries)
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        souvenir_inclusion=SouvenirInclusion.INCLUDE,
        cap=5,
    )
    with pytest.raises(MemoryError) as info:
        build_universe_goods_ids(
            identity_resolver=identity, metadata_resolver=metadata, spec=spec
        )
    assert info.value is sentinel


def _allocation_metadata(
    capacities: tuple[tuple[str, int, int], ...],
) -> list[dict[str, object]]:
    """Build normal/Souvenir Restricted inputs plus canonical outputs."""
    entries: list[dict[str, object]] = []
    for collection_name, normal_count, souvenir_count in capacities:
        for index in range(normal_count):
            entries.append(
                _metadata_entry(
                    market_hash_name=f"{collection_name} Normal {index:02d}",
                    collection_name=collection_name,
                    rarity="Restricted",
                )
            )
        for index in range(souvenir_count):
            entries.append(
                _metadata_entry(
                    market_hash_name=f"Souvenir {collection_name} {index:02d}",
                    collection_name=collection_name,
                    rarity="Restricted",
                    souvenir=True,
                )
            )
        entries.append(
            _metadata_entry(
                market_hash_name=f"{collection_name} Canonical Output",
                collection_name=collection_name,
                rarity="Classified",
            )
        )
    return entries


def _build_allocation_universe(
    capacities: tuple[tuple[str, int, int], ...],
    *,
    strategy: UniverseAllocationStrategy,
    cap: int = 10,
    target_cohort_count: int = 3,
    souvenir_inclusion: SouvenirInclusion = SouvenirInclusion.INCLUDE,
):
    entries = _allocation_metadata(capacities)
    return build_universe_goods_ids(
        identity_resolver=_resolver_from_metadata(entries),
        metadata_resolver=_metadata_resolver_from_entries(entries),
        spec=MarketUniverseSpec(
            rarity="Restricted",
            stattrak_mode=StatTrakMode.NORMAL,
            souvenir_inclusion=souvenir_inclusion,
            cap=cap,
            allocation_strategy=strategy,
            target_cohort_count=target_cohort_count,
        ),
    )


def test_allocation_defaults_preserve_phase_13r_breadth() -> None:
    spec = MarketUniverseSpec(
        rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        souvenir_inclusion=SouvenirInclusion.INCLUDE,
        cap=2,
    )
    assert spec.allocation_strategy is UniverseAllocationStrategy.BREADTH
    assert spec.target_cohort_count == 3

    result = _build_allocation_universe(
        (("Collection A", 2, 0), ("Collection B", 2, 0)),
        strategy=UniverseAllocationStrategy.BREADTH,
        cap=4,
    )
    assert result.selected_market_hash_names == (
        "Collection A Normal 00",
        "Collection B Normal 00",
        "Collection A Normal 01",
        "Collection B Normal 01",
    )


@pytest.mark.parametrize("target", [0, -1, 11, True])
def test_target_cohort_count_validation(target: object) -> None:
    with pytest.raises(BoundedMarketUniverseBuilderError) as info:
        MarketUniverseSpec(
            rarity="Restricted",
            stattrak_mode=StatTrakMode.NORMAL,
            souvenir_inclusion=SouvenirInclusion.INCLUDE,
            cap=10,
            allocation_strategy=UniverseAllocationStrategy.COHORT_DEPTH,
            target_cohort_count=target,  # type: ignore[arg-type]
        )
    assert info.value.reason == "invalid_target_cohort_count"


def test_depth_target_greater_than_budget_fails_closed() -> None:
    with pytest.raises(BoundedMarketUniverseBuilderError) as info:
        MarketUniverseSpec(
            rarity="Restricted",
            stattrak_mode=StatTrakMode.NORMAL,
            souvenir_inclusion=SouvenirInclusion.INCLUDE,
            cap=2,
            allocation_strategy=UniverseAllocationStrategy.COHORT_DEPTH,
            target_cohort_count=3,
        )
    assert info.value.reason == "invalid_target_cohort_count"


def test_depth_allocates_ten_slots_as_four_three_three() -> None:
    result = _build_allocation_universe(
        (
            ("Collection A", 10, 0),
            ("Collection B", 10, 0),
            ("Collection C", 10, 0),
            ("Collection D", 9, 0),
        ),
        strategy=UniverseAllocationStrategy.COHORT_DEPTH,
    )
    assert [
        cohort.key.collection_name for cohort in result.diagnostics.selected_cohorts
    ] == ["Collection A", "Collection B", "Collection C"]
    assert [
        cohort.allocated_slots for cohort in result.diagnostics.selected_cohorts
    ] == [4, 3, 3]
    assert result.diagnostics.eligible_cohort_count == 4
    assert result.diagnostics.selected_cohort_count == 3
    assert len(result.goods_ids) == 10


def test_depth_redistributes_capacity_limited_slots() -> None:
    result = _build_allocation_universe(
        (
            ("Collection A", 10, 0),
            ("Collection B", 10, 0),
            ("Collection C", 2, 0),
        ),
        strategy=UniverseAllocationStrategy.COHORT_DEPTH,
    )
    assert [
        cohort.allocated_slots for cohort in result.diagnostics.selected_cohorts
    ] == [4, 4, 2]


def test_depth_does_not_promote_a_fourth_cohort_when_target_is_short() -> None:
    result = _build_allocation_universe(
        (
            ("Collection A", 2, 0),
            ("Collection B", 1, 0),
            ("Collection C", 1, 0),
            ("Collection D", 1, 0),
        ),
        strategy=UniverseAllocationStrategy.COHORT_DEPTH,
        target_cohort_count=2,
    )
    assert len(result.goods_ids) == 3
    assert result.diagnostics.selected_cohort_count == 2
    assert {
        cohort.key.collection_name for cohort in result.diagnostics.selected_cohorts
    } == {"Collection A", "Collection B"}


@pytest.mark.parametrize(
    ("capacities", "expected_slots"),
    [
        ((("Collection A", 10, 0),), [10]),
        ((("Collection A", 10, 0), ("Collection B", 10, 0)), [5, 5]),
    ],
)
def test_depth_supports_fewer_cohorts_than_target(
    capacities: tuple[tuple[str, int, int], ...],
    expected_slots: list[int],
) -> None:
    result = _build_allocation_universe(
        capacities,
        strategy=UniverseAllocationStrategy.COHORT_DEPTH,
    )
    assert [
        cohort.allocated_slots for cohort in result.diagnostics.selected_cohorts
    ] == expected_slots


def test_depth_ranking_uses_capacity_then_lexical_key() -> None:
    result = _build_allocation_universe(
        (
            ("Collection Z", 5, 0),
            ("Collection B", 7, 0),
            ("Collection A", 7, 0),
            ("Collection C", 6, 0),
        ),
        strategy=UniverseAllocationStrategy.COHORT_DEPTH,
        cap=3,
        target_cohort_count=3,
    )
    assert [
        cohort.key.collection_name for cohort in result.diagnostics.selected_cohorts
    ] == ["Collection A", "Collection B", "Collection C"]


def test_normal_and_souvenir_interleave_in_same_cohort() -> None:
    result = _build_allocation_universe(
        (("Collection A", 3, 3),),
        strategy=UniverseAllocationStrategy.COHORT_DEPTH,
        cap=6,
        target_cohort_count=1,
    )
    cohort = result.diagnostics.selected_cohorts[0]
    assert cohort.catalog_capacity == 6
    assert cohort.normal_identity_count == 3
    assert cohort.souvenir_identity_count == 3
    assert cohort.canonical_output_count == 1
    assert [entry.souvenir for entry in cohort.selected_entries] == [
        False,
        True,
        False,
        True,
        False,
        True,
    ]
    assert cohort.key.stattrak is False


def test_souvenir_exclusion_changes_effective_catalog_capacity() -> None:
    result = _build_allocation_universe(
        (("Collection A", 3, 3),),
        strategy=UniverseAllocationStrategy.COHORT_DEPTH,
        cap=3,
        target_cohort_count=1,
        souvenir_inclusion=SouvenirInclusion.EXCLUDE,
    )
    cohort = result.diagnostics.selected_cohorts[0]
    assert cohort.catalog_capacity == 3
    assert cohort.normal_identity_count == 3
    assert cohort.souvenir_identity_count == 0
    assert all(not entry.souvenir for entry in cohort.selected_entries)


def test_depth_result_and_diagnostics_are_byte_equal() -> None:
    capacities = (
        ("Collection A", 6, 4),
        ("Collection B", 6, 4),
        ("Collection C", 6, 4),
    )
    first = _build_allocation_universe(
        capacities,
        strategy=UniverseAllocationStrategy.COHORT_DEPTH,
    )
    second = _build_allocation_universe(
        capacities,
        strategy=UniverseAllocationStrategy.COHORT_DEPTH,
    )
    assert first == second
    assert len(set(first.goods_ids)) == len(first.goods_ids)
    assert tuple(entry.goods_id for entry in first.selected_entries) == first.goods_ids
    assert sum(
        cohort.allocated_slots for cohort in first.diagnostics.selected_cohorts
    ) == first.diagnostics.selected_count


def test_module_has_no_network_async_or_financial_imports() -> None:
    import ast

    source = Path(__file__).with_name("..").joinpath(
        "app", "services", "market_universe_builder.py"
    )
    tree = ast.parse(source.read_text(encoding="utf-8"))
    forbidden = {
        "httpx",
        "asyncio",
        "requests",
        "urllib",
        "socket",
        "os",
        "steamdt_buff_price_provider",
        "valuation_service",
        "ev_service",
        "risk_filter",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top not in forbidden, top
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            parts = node.module.split(".")
            assert parts[0] not in forbidden, parts[0]
            assert not any(part in forbidden for part in parts), node.module
