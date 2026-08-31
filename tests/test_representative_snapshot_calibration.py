from __future__ import annotations

import ast
import asyncio
import copy
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
    BuffCommunitySnapshotMetadata,
)
from app.services.buff_listing_provider import (
    BuffListing,
    BuffListingProviderError,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from research.valuation_budget_calibration import capture_snapshot_once
from research.valuation_budget_calibration.measurement import (
    measure_output_name_sequences,
)
from research.valuation_budget_calibration.snapshot_collector import (
    collect_observation,
)
from research.valuation_budget_calibration.snapshot_protocol import (
    ObservationPlan,
    ObservationSpec,
    PlannedGood,
    PlanningFailure,
    build_snapshot_id,
    calculate_jitter_minutes,
    plan_observation,
    scheduled_timestamp,
)
from research.valuation_budget_calibration.snapshot_replay import (
    SnapshotReplayError,
    replay_snapshot,
    replay_snapshot_path,
)
from research.valuation_budget_calibration.snapshot_schema import (
    ObservationStatus,
    RepresentativeSnapshot,
    SecretMaterialError,
    SnapshotProvenance,
    SnapshotSchemaError,
    canonical_snapshot_bytes,
    parse_snapshot_bytes,
    parse_snapshot_payload,
    scan_for_secret_material,
)
from research.valuation_budget_calibration.snapshot_storage import (
    ManifestEntry,
    SnapshotArtifactStore,
    SnapshotStorageError,
    manifest_entry_for_snapshot,
    verify_snapshot_hash,
)

EXAMPLE_PATH = Path(
    "research/valuation_budget_calibration/snapshot_schema_v1.example.json"
)
IMPLEMENTATION_FILES = (
    "snapshot_protocol.py",
    "snapshot_schema.py",
    "snapshot_storage.py",
    "snapshot_collector.py",
    "snapshot_replay.py",
    "capture_snapshot_once.py",
)
COLLECTIONS = (
    "Synthetic Snapshot Collection A",
    "Synthetic Snapshot Collection B",
    "Synthetic Snapshot Collection C",
)
INPUT_NAMES = tuple(
    f"Synthetic Snapshot Input {index:02d} (Field-Tested)"
    for index in range(10)
)
OUTPUT_NAMES = (
    "Synthetic Snapshot Output A1 (Factory New)",
    "Synthetic Snapshot Output A2 (Factory New)",
    "Synthetic Snapshot Output B1 (Factory New)",
    "Synthetic Snapshot Output B2 (Factory New)",
    "Synthetic Snapshot Output B3 (Factory New)",
    "Synthetic Snapshot Output C1 (Factory New)",
)


def _example_payload() -> dict[str, Any]:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def _metadata_row(
    name: str,
    *,
    collection: str,
    rarity: str,
) -> dict[str, object]:
    return {
        "market_hash_name": name,
        "collection_name": collection,
        "rarity": rarity,
        "min_float": 0.0,
        "max_float": 1.0,
        "stattrak": False,
        "souvenir": False,
    }


def _fixture_pair(
    *,
    input_count: int = 10,
) -> tuple[BuffCommunityIdentityResolver, PinnedSkinMetadataResolver]:
    input_rows: list[dict[str, object]] = []
    forward: dict[str, str] = {}
    capacities = (4, 3, 3)
    index = 0
    for collection, capacity in zip(COLLECTIONS, capacities, strict=True):
        for _ in range(capacity):
            if index >= input_count:
                break
            name = INPUT_NAMES[index]
            input_rows.append(
                _metadata_row(
                    name,
                    collection=collection,
                    rarity="Restricted",
                )
            )
            forward[name] = str(5000 + index)
            index += 1
    output_rows = [
        _metadata_row(name, collection=COLLECTIONS[0], rarity="Classified")
        for name in OUTPUT_NAMES[:2]
    ] + [
        _metadata_row(name, collection=COLLECTIONS[1], rarity="Classified")
        for name in OUTPUT_NAMES[2:5]
    ] + [
        _metadata_row(name, collection=COLLECTIONS[2], rarity="Classified")
        for name in OUTPUT_NAMES[5:]
    ]
    metadata = PinnedSkinMetadataResolver.from_payload(
        [*input_rows, *output_rows]
    )
    reverse = {goods_id: name for name, goods_id in forward.items()}
    identity = BuffCommunityIdentityResolver(
        forward=forward,
        reverse=reverse,
        metadata=BuffCommunitySnapshotMetadata(
            schema_version=1,
            catalog_kind="community_catalog",
            repository="synthetic/example",
            file="synthetic.json",
            commit="0" * 40,
            sha256="0" * 64,
            license="synthetic",
            attribution="synthetic",
            source_count=len(forward),
            accepted_count=len(forward),
            rejected_count=0,
        ),
    )
    return identity, metadata


def _plan(
    identity: BuffCommunityIdentityResolver,
    metadata: PinnedSkinMetadataResolver,
) -> ObservationPlan:
    result = plan_observation(
        spec=ObservationSpec(
            campaign_id="synthetic-test-campaign",
            nominal_slot_utc="2000-01-01T00:17:00Z",
            input_rarity="Restricted",
            stattrak_mode="normal",
        ),
        identity_resolver=identity,
        metadata_resolver=metadata,
    )
    assert isinstance(result, ObservationPlan)
    return result


def _provenance() -> SnapshotProvenance:
    return SnapshotProvenance(
        collector_git_commit="0" * 40,
        identity_snapshot_path="data/identity/synthetic.json",
        identity_snapshot_sha256="1" * 64,
        metadata_snapshot_path="data/metadata/synthetic.json",
        metadata_snapshot_sha256="2" * 64,
    )


def _listing(
    planned: PlannedGood,
    *,
    index: int,
    price: str = "10.00",
    paintwear: str = "0.10",
    market_hash_name: str | None = None,
) -> BuffListing:
    return BuffListing(
        listing_id=f"synthetic-listing-{planned.universe_rank}-{index}",
        goods_id=planned.goods_id,
        market_hash_name=market_hash_name,
        price_cny=Decimal(price),
        paintwear=Decimal(paintwear),
        asset_id=f"synthetic-asset-{planned.universe_rank}-{index}",
        paintseed=None,
        source="buff",
    )


class FakeProvider:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values
        self.calls: list[str] = []

    async def get_listings(self, goods_id: str) -> list[BuffListing]:
        self.calls.append(goods_id)
        value = self.values.get(goods_id, [])
        if isinstance(value, BaseException):
            raise value
        assert isinstance(value, list)
        return value


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleep_calls: list[float] = []

    def monotonic(self) -> float:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.value += seconds


def _fixed_utc_clock() -> Any:
    values = iter(
        (
            datetime(2000, 1, 1, 0, 14, 1, tzinfo=UTC),
            datetime(2000, 1, 1, 0, 14, 25, tzinfo=UTC),
        )
    )
    return lambda: next(values)


def _successful_values(plan: ObservationPlan) -> dict[str, object]:
    return {
        planned.goods_id: [_listing(planned, index=0)]
        for planned in plan.planned_goods
    }


async def _collect(
    *,
    plan: ObservationPlan,
    provider: FakeProvider,
    identity: BuffCommunityIdentityResolver,
    metadata: PinnedSkinMetadataResolver,
    clock: FakeClock | None = None,
) -> RepresentativeSnapshot:
    pacing = clock or FakeClock()
    result = await collect_observation(
        plan=plan,
        listing_provider=provider,
        identity_resolver=identity,
        metadata_resolver=metadata,
        provenance=_provenance(),
        request_interval_seconds=2.0,
        sleeper=pacing.sleep,
        monotonic=pacing.monotonic,
        utc_now=_fixed_utc_clock(),
    )
    assert result.request_count == 10
    return result.snapshot


def test_frozen_synthetic_example_parses_strictly() -> None:
    snapshot = parse_snapshot_bytes(EXAMPLE_PATH.read_bytes())

    assert snapshot.observation_status is ObservationStatus.COMPLETE
    assert len(snapshot.planned_goods) == len(snapshot.pages) == 10
    assert snapshot.acquisition_summary.listings_received == 1


def test_duplicate_json_keys_are_rejected() -> None:
    raw = EXAMPLE_PATH.read_text(encoding="utf-8")
    duplicate = raw.replace(
        '"schema_version": 1,',
        '"schema_version": 1, "schema_version": 1,',
        1,
    )

    with pytest.raises(SnapshotSchemaError) as exc_info:
        parse_snapshot_bytes(duplicate.encode())

    assert exc_info.value.reason == "duplicate_json_key"


def test_unknown_keys_are_rejected() -> None:
    payload = _example_payload()
    payload["unexpected"] = "synthetic"

    with pytest.raises(SnapshotSchemaError):
        parse_snapshot_payload(payload)


def test_bad_decimal_strings_are_rejected() -> None:
    payload = _example_payload()
    payload["pages"][0]["listings"][0]["price_cny"] = "1e2"

    with pytest.raises(SnapshotSchemaError) as exc_info:
        parse_snapshot_payload(payload)

    assert exc_info.value.reason == "decimal_invalid"


def test_duplicate_page_goods_are_rejected() -> None:
    payload = _example_payload()
    payload["pages"][1]["goods_id"] = payload["pages"][0]["goods_id"]

    with pytest.raises(SnapshotSchemaError):
        parse_snapshot_payload(payload)


def test_duplicate_listing_references_are_rejected() -> None:
    payload = _example_payload()
    duplicate = copy.deepcopy(payload["pages"][0]["listings"][0])
    planned = payload["universe"]["planned_goods"][1]
    duplicate.update(
        {
            "goods_id": planned["goods_id"],
            "market_hash_name": planned["market_hash_name"],
            "rarity": planned["rarity"],
            "collection_name": planned["cohort_collection"],
        }
    )
    payload["pages"][1].update(
        {
            "acquisition_status": "SUCCESS",
            "listing_count": 1,
            "listings": [duplicate],
        }
    )

    with pytest.raises(SnapshotSchemaError) as exc_info:
        parse_snapshot_payload(payload)

    assert exc_info.value.reason == "duplicate_listing_reference"


def test_count_and_status_contradictions_are_rejected() -> None:
    payload = _example_payload()
    payload["acquisition_summary"]["listings_received"] = 2
    with pytest.raises(SnapshotSchemaError):
        parse_snapshot_payload(payload)

    payload = _example_payload()
    payload["observation_status"] = "PARTIAL"
    with pytest.raises(SnapshotSchemaError) as exc_info:
        parse_snapshot_payload(payload)
    assert exc_info.value.reason == "observation_status_invalid"


def test_snapshot_id_and_jitter_match_frozen_formula() -> None:
    spec = ObservationSpec(
        campaign_id="synthetic-example-campaign",
        nominal_slot_utc="2000-01-01T00:17:00Z",
        input_rarity="Restricted",
        stattrak_mode="normal",
    )

    assert build_snapshot_id(spec) == "snap-v1-0ab63cc8123edaf92fb0c4b8"
    assert calculate_jitter_minutes(
        campaign_id=spec.campaign_id,
        nominal_slot_utc=spec.nominal_slot_utc,
    ) == -3
    assert scheduled_timestamp(spec) == "2000-01-01T00:14:00Z"


def test_canonical_json_and_hash_are_deterministic() -> None:
    snapshot = parse_snapshot_payload(_example_payload())

    first = canonical_snapshot_bytes(snapshot)
    second = canonical_snapshot_bytes(snapshot)

    assert first == second
    assert first.endswith(b"\n") and not first.endswith(b"\n\n")
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


def test_secret_shaped_key_and_value_fail_without_value_disclosure() -> None:
    marker = "synthetic-secret-marker-should-not-appear"
    for payload in (
        {"authorization": marker},
        {"raw_payload": marker},
        {"seller": marker},
        {"safe": f"Bearer {marker}"},
        {"safe": "https://synthetic.invalid/path?x=1"},
        {"safe": f"Cookie: {marker}"},
        {"safe": f"?access={marker}"},
    ):
        with pytest.raises(SecretMaterialError) as exc_info:
            scan_for_secret_material(payload)
        assert marker not in str(exc_info.value)
        assert marker not in repr(exc_info.value)


def test_storage_is_immutable_and_manifest_is_append_only(tmp_path: Path) -> None:
    snapshot = parse_snapshot_payload(_example_payload())
    store = SnapshotArtifactStore(
        artifact_root=tmp_path,
        campaign_id=snapshot.campaign_id,
    )

    receipt = store.write_snapshot(snapshot)
    verify_snapshot_hash(receipt.snapshot_path, receipt.snapshot_sha256)
    with pytest.raises(SnapshotStorageError) as exc_info:
        store.write_snapshot(snapshot)
    assert exc_info.value.reason == "snapshot_exists"

    entry = manifest_entry_for_snapshot(
        snapshot=snapshot,
        receipt=receipt,
        request_count=10,
    )
    store.append_manifest(entry)
    first = store.manifest_path.read_bytes()
    store.append_manifest(replace(entry, supersedes_snapshot_id=snapshot.snapshot_id))
    second = store.manifest_path.read_bytes()
    assert second.startswith(first)
    assert len(second.splitlines()) == 2


def test_manifest_only_planning_failure_writes_no_snapshot(tmp_path: Path) -> None:
    store = SnapshotArtifactStore(
        artifact_root=tmp_path,
        campaign_id="synthetic-test-campaign",
    )
    entry = ManifestEntry(
        campaign_id="synthetic-test-campaign",
        snapshot_id="snap-v1-000000000000000000000000",
        nominal_slot_utc="2000-01-01T00:17:00Z",
        scheduled_for_utc="2000-01-01T00:14:00Z",
        observed_at_utc=None,
        capture_completed_at_utc=None,
        input_rarity="Restricted",
        stattrak_mode="normal",
        outcome="INVALID_FOR_CALIBRATION",
        reason="UNIVERSE_NOT_EXACTLY_TEN",
        snapshot_path=None,
        snapshot_sha256=None,
        request_count=0,
        pages_completed=0,
        pages_failed=0,
        listings_received=0,
    )

    store.append_manifest(entry)

    assert store.manifest_path.is_file()
    assert not (store.campaign_root / "snapshots").exists()


def test_missed_observation_manifest_has_no_snapshot(tmp_path: Path) -> None:
    store = SnapshotArtifactStore(
        artifact_root=tmp_path,
        campaign_id="synthetic-test-campaign",
    )
    store.append_manifest(
        ManifestEntry(
            campaign_id="synthetic-test-campaign",
            snapshot_id=None,
            nominal_slot_utc="2000-01-01T00:17:00Z",
            scheduled_for_utc="2000-01-01T00:14:00Z",
            observed_at_utc=None,
            capture_completed_at_utc=None,
            input_rarity="Restricted",
            stattrak_mode="normal",
            outcome="MISSED_OBSERVATION",
            reason="MISSED_OBSERVATION",
            snapshot_path=None,
            snapshot_sha256=None,
            request_count=0,
            pages_completed=0,
            pages_failed=0,
            listings_received=0,
        )
    )

    payload = json.loads(store.manifest_path.read_text(encoding="utf-8"))
    assert payload["snapshot_id"] is None
    assert payload["snapshot_path"] is None
    assert payload["snapshot_sha256"] is None
    assert not (store.campaign_root / "snapshots").exists()


def test_ten_successful_pages_are_complete_and_paced() -> None:
    identity, metadata = _fixture_pair()
    plan = _plan(identity, metadata)
    provider = FakeProvider(_successful_values(plan))
    clock = FakeClock()

    snapshot = asyncio.run(
        _collect(
            plan=plan,
            provider=provider,
            identity=identity,
            metadata=metadata,
            clock=clock,
        )
    )

    assert snapshot.observation_status is ObservationStatus.COMPLETE
    assert provider.calls == list(plan.goods_ids)
    assert clock.sleep_calls == [2.0] * 9
    assert snapshot.acquisition_summary.pages_completed == 10
    assert snapshot.acquisition_summary.listings_received == 10


def test_collector_rejects_pacing_below_frozen_minimum() -> None:
    identity, metadata = _fixture_pair()
    plan = _plan(identity, metadata)

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            collect_observation(
                plan=plan,
                listing_provider=FakeProvider(_successful_values(plan)),
                identity_resolver=identity,
                metadata_resolver=metadata,
                provenance=_provenance(),
                request_interval_seconds=1.99,
            )
        )

    assert getattr(exc_info.value, "reason", None) == "invalid_request_interval"


def test_valid_empty_pages_remain_complete() -> None:
    identity, metadata = _fixture_pair()
    plan = _plan(identity, metadata)
    values = _successful_values(plan)
    values[plan.goods_ids[-1]] = []

    snapshot = asyncio.run(
        _collect(
            plan=plan,
            provider=FakeProvider(values),
            identity=identity,
            metadata=metadata,
        )
    )

    assert snapshot.observation_status is ObservationStatus.COMPLETE
    assert snapshot.acquisition_summary.pages_empty == 1


@pytest.mark.parametrize(
    ("reason", "expected_status"),
    [
        ("request_failed", "FETCH_FAILED"),
        ("response_schema_invalid", "PARSE_FAILED"),
    ],
)
def test_one_provider_failure_is_partial_without_retry(
    reason: str,
    expected_status: str,
) -> None:
    identity, metadata = _fixture_pair()
    plan = _plan(identity, metadata)
    values = _successful_values(plan)
    values[plan.goods_ids[4]] = BuffListingProviderError(reason=reason)
    provider = FakeProvider(values)

    snapshot = asyncio.run(
        _collect(
            plan=plan,
            provider=provider,
            identity=identity,
            metadata=metadata,
        )
    )

    assert snapshot.observation_status is ObservationStatus.PARTIAL
    assert provider.calls == list(plan.goods_ids)
    assert provider.calls.count(plan.goods_ids[4]) == 1
    assert snapshot.pages[4].acquisition_status.value == expected_status


def test_binding_conflict_is_invalid() -> None:
    identity, metadata = _fixture_pair()
    plan = _plan(identity, metadata)
    values = _successful_values(plan)
    values[plan.goods_ids[2]] = [
        _listing(
            plan.planned_goods[2],
            index=0,
            market_hash_name="Synthetic Conflicting Identity",
        )
    ]

    snapshot = asyncio.run(
        _collect(
            plan=plan,
            provider=FakeProvider(values),
            identity=identity,
            metadata=metadata,
        )
    )

    assert snapshot.observation_status is ObservationStatus.INVALID
    assert snapshot.pages[2].acquisition_status.value == "BINDING_FAILED"


def test_catalog_contradiction_is_invalid() -> None:
    identity, metadata = _fixture_pair()
    plan = _plan(identity, metadata)
    rows = [
        _metadata_row(
            planned.market_hash_name,
            collection=(
                "Synthetic Wrong Collection"
                if index == 0
                else planned.cohort_collection
            ),
            rarity=planned.rarity,
        )
        for index, planned in enumerate(plan.planned_goods)
    ]
    rows.append(
        _metadata_row(
            "Synthetic Wrong Output",
            collection="Synthetic Wrong Collection",
            rarity="Classified",
        )
    )
    mismatched = PinnedSkinMetadataResolver.from_payload(rows)

    snapshot = asyncio.run(
        _collect(
            plan=plan,
            provider=FakeProvider(_successful_values(plan)),
            identity=identity,
            metadata=mismatched,
        )
    )

    assert snapshot.observation_status is ObservationStatus.INVALID


def test_fewer_than_ten_universe_is_planning_failure() -> None:
    identity, metadata = _fixture_pair(input_count=9)
    result = plan_observation(
        spec=ObservationSpec(
            campaign_id="synthetic-test-campaign",
            nominal_slot_utc="2000-01-01T00:17:00Z",
            input_rarity="Restricted",
            stattrak_mode="normal",
        ),
        identity_resolver=identity,
        metadata_resolver=metadata,
    )

    assert isinstance(result, PlanningFailure)
    assert result.reason == "UNIVERSE_NOT_EXACTLY_TEN"


def test_complete_zero_recipe_snapshot_is_retained() -> None:
    identity, metadata = _fixture_pair()
    plan = _plan(identity, metadata)
    values = {goods_id: [] for goods_id in plan.goods_ids}
    values[plan.goods_ids[0]] = [_listing(plan.planned_goods[0], index=0)]
    snapshot = asyncio.run(
        _collect(
            plan=plan,
            provider=FakeProvider(values),
            identity=identity,
            metadata=metadata,
        )
    )

    result = replay_snapshot(snapshot=snapshot, metadata_resolver=metadata)

    assert snapshot.observation_status is ObservationStatus.COMPLETE
    assert result.recipe_count == 0
    assert result.run_unique_output_names == 0
    assert result.per_recipe_unique_counts == ()
    assert result.composition_states_explored == 0


def test_complete_replay_uses_phase15a_exact_name_semantics() -> None:
    identity, metadata = _fixture_pair()
    plan = _plan(identity, metadata)
    values = {goods_id: [] for goods_id in plan.goods_ids}
    values[plan.goods_ids[0]] = [
        _listing(
            plan.planned_goods[0],
            index=index,
            price=f"10.{index:02d}",
            paintwear=f"0.{10 + index:02d}",
        )
        for index in range(10)
    ]
    values[plan.goods_ids[4]] = [
        _listing(
            plan.planned_goods[4],
            index=0,
            price="20.00",
            paintwear="0.90",
        )
    ]
    snapshot = asyncio.run(
        _collect(
            plan=plan,
            provider=FakeProvider(values),
            identity=identity,
            metadata=metadata,
        )
    )

    result = replay_snapshot(snapshot=snapshot, metadata_resolver=metadata)
    direct = measure_output_name_sequences(result.per_recipe_unique_output_names)

    assert result.recipe_count == 2
    assert result.per_recipe_unique_counts == (2, 5)
    assert result.run_unique_output_names == 5
    assert result.recipe_2_incremental_new_names == 3
    assert result.cross_recipe_overlap_count == 2
    assert direct.run_unique_output_names == result.run_unique_output_names
    assert direct.recipe_2_incremental_new_names == 3
    assert result.composition_states_explored == 2


def test_partial_and_invalid_snapshots_are_excluded_from_replay() -> None:
    example = parse_snapshot_payload(_example_payload())
    for status in (ObservationStatus.PARTIAL, ObservationStatus.INVALID):
        snapshot = replace(example, observation_status=status)
        with pytest.raises(SnapshotReplayError) as exc_info:
            replay_snapshot(
                snapshot=snapshot,
                metadata_resolver=PinnedSkinMetadataResolver.from_payload(
                    [
                        _metadata_row(
                            "Synthetic Example Input 01 (Field-Tested)",
                            collection="Synthetic Collection A",
                            rarity="Restricted",
                        ),
                        _metadata_row(
                            "Synthetic Example Output",
                            collection="Synthetic Collection A",
                            rarity="Classified",
                        ),
                    ]
                ),
            )
        assert exc_info.value.reason == "snapshot_not_complete"


def test_snapshot_hash_verification_rejects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.json"
    path.write_bytes(b"synthetic\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    verify_snapshot_hash(path, digest)
    path.write_bytes(b"tampered\n")

    with pytest.raises(SnapshotStorageError) as exc_info:
        verify_snapshot_hash(path, digest)

    assert exc_info.value.reason == "snapshot_hash_mismatch"


def test_replay_path_verifies_hash_and_pinned_provenance(
    tmp_path: Path,
) -> None:
    identity_path = Path("data/identity/buff_identity_v1.json")
    metadata_path = Path("data/metadata/skin_metadata_v1.json")
    identity = BuffCommunityIdentityResolver.from_snapshot_path(identity_path)
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(metadata_path)
    plan_result = plan_observation(
        spec=ObservationSpec(
            campaign_id="synthetic-path-replay",
            nominal_slot_utc="2000-01-01T00:17:00Z",
            input_rarity="Restricted",
            stattrak_mode="normal",
        ),
        identity_resolver=identity,
        metadata_resolver=metadata,
    )
    assert isinstance(plan_result, ObservationPlan)
    snapshot = asyncio.run(
        _collect(
            plan=plan_result,
            provider=FakeProvider(
                {goods_id: [] for goods_id in plan_result.goods_ids}
            ),
            identity=identity,
            metadata=metadata,
        )
    )
    snapshot = replace(
        snapshot,
        provenance=SnapshotProvenance(
            collector_git_commit="0" * 40,
            identity_snapshot_path=identity_path.as_posix(),
            identity_snapshot_sha256=hashlib.sha256(
                identity_path.read_bytes()
            ).hexdigest(),
            metadata_snapshot_path=metadata_path.as_posix(),
            metadata_snapshot_sha256=hashlib.sha256(
                metadata_path.read_bytes()
            ).hexdigest(),
        ),
    )
    store = SnapshotArtifactStore(
        artifact_root=tmp_path,
        campaign_id=snapshot.campaign_id,
    )
    receipt = store.write_snapshot(snapshot)

    replay = replay_snapshot_path(
        snapshot_path=receipt.snapshot_path,
        metadata_snapshot_path=metadata_path,
        identity_snapshot_path=identity_path,
        expected_snapshot_sha256=receipt.snapshot_sha256,
    )
    assert replay.recipe_count == 0
    assert replay.run_unique_output_names == 0

    identity_copy = tmp_path / "data/identity/buff_identity_v1.json"
    metadata_copy = tmp_path / "data/metadata/skin_metadata_v1.json"
    identity_copy.parent.mkdir(parents=True)
    metadata_copy.parent.mkdir(parents=True)
    identity_copy.write_bytes(identity_path.read_bytes())
    metadata_copy.write_bytes(metadata_path.read_bytes())
    identity_copy.write_bytes(identity_copy.read_bytes() + b"\n")
    with pytest.raises(SnapshotReplayError) as exc_info:
        replay_snapshot_path(
            snapshot_path=receipt.snapshot_path,
            metadata_snapshot_path=metadata_copy,
            identity_snapshot_path=identity_copy,
        )
    assert exc_info.value.reason == "pinned_provenance_mismatch"


def test_plan_only_cli_constructs_no_http_client(monkeypatch, capsys) -> None:
    def forbidden_http(*args, **kwargs):
        raise AssertionError("plan-only constructed HTTP client")

    monkeypatch.setattr(capture_snapshot_once.httpx, "AsyncClient", forbidden_http)
    code = capture_snapshot_once.main(
        [
            "--campaign-id",
            "synthetic-plan-only",
            "--nominal-slot-utc",
            "2000-01-01T00:17:00Z",
            "--rarity",
            "Restricted",
            "--stattrak-mode",
            "normal",
            "--plan-only",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["mode"] == "plan-only"
    assert output["goods_count"] == 10
    assert output["network_requests"] == 0


def test_research_modules_have_no_forbidden_runtime_imports() -> None:
    root = Path("research/valuation_budget_calibration")
    forbidden = (
        "app.jobs",
        "app.services.ev_service",
        "app.services.price_cache",
        "app.services.redis",
        "app.services.risk_filter",
        "app.services.scanner_orchestrator",
        "app.services.steamdt",
        "app.services.valuation_service",
        "app.webhook",
        "apscheduler",
    )
    for filename in IMPLEMENTATION_FILES:
        tree = ast.parse((root / filename).read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.append(node.module)
        for imported in imports:
            assert not imported.startswith(forbidden), (filename, imported)


def test_collector_module_has_one_provider_call_site_and_no_retry_loop() -> None:
    path = Path("research/valuation_budget_calibration/snapshot_collector.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    provider_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get_listings"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "listing_provider"
    ]
    while_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.While)]

    assert len(provider_calls) == 1
    assert while_nodes == []
