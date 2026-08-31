"""One-shot research CLI for frozen representative snapshot collection."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from app.clients.buff_anonymous_listing_client import (
    BuffAnonymousListingHttpClient,
)
from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.buff_listing_provider import BuffListingProvider
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver
from research.valuation_budget_calibration.snapshot_collector import (
    collect_observation,
)
from research.valuation_budget_calibration.snapshot_protocol import (
    MINIMUM_REQUEST_START_INTERVAL_SECONDS,
    ObservationPlan,
    ObservationSpec,
    PlanningFailure,
    file_sha256,
    plan_observation,
)
from research.valuation_budget_calibration.snapshot_replay import (
    replay_snapshot_path,
)
from research.valuation_budget_calibration.snapshot_schema import (
    SnapshotProvenance,
)
from research.valuation_budget_calibration.snapshot_storage import (
    ManifestEntry,
    SnapshotArtifactStore,
    manifest_entry_for_snapshot,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IDENTITY_SNAPSHOT = REPOSITORY_ROOT / "data/identity/buff_identity_v1.json"
DEFAULT_METADATA_SNAPSHOT = REPOSITORY_ROOT / "data/metadata/skin_metadata_v1.json"

_FIXED_FAILURE = "PHASE15C2_CAPTURE_FAILED"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or capture one representative research snapshot.",
    )
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--nominal-slot-utc", required=True)
    parser.add_argument("--rarity", required=True)
    parser.add_argument(
        "--stattrak-mode",
        choices=("normal", "stattrak"),
        required=True,
    )
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--execute-live-smoke", action="store_true")
    parser.add_argument("--replay-written", action="store_true")
    parser.add_argument(
        "--identity-snapshot",
        type=Path,
        default=DEFAULT_IDENTITY_SNAPSHOT,
    )
    parser.add_argument(
        "--metadata-snapshot",
        type=Path,
        default=DEFAULT_METADATA_SNAPSHOT,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.plan_only == args.execute_live_smoke:
        print(_FIXED_FAILURE)
        return 2
    try:
        identity_path = _repository_file(args.identity_snapshot)
        metadata_path = _repository_file(args.metadata_snapshot)
        identity = BuffCommunityIdentityResolver.from_snapshot_path(identity_path)
        metadata = PinnedSkinMetadataResolver.from_snapshot_path(metadata_path)
        spec = ObservationSpec(
            campaign_id=args.campaign_id,
            nominal_slot_utc=args.nominal_slot_utc,
            input_rarity=args.rarity,
            stattrak_mode=args.stattrak_mode,
        )
        plan = plan_observation(
            spec=spec,
            identity_resolver=identity,
            metadata_resolver=metadata,
        )
        if isinstance(plan, PlanningFailure):
            if args.execute_live_smoke:
                if (
                    "non-policy-smoke" not in args.campaign_id
                    or args.artifact_root is None
                    or not _within_smoke_window(plan)
                ):
                    print(_FIXED_FAILURE)
                    return 2
                artifact_root = args.artifact_root.resolve()
                if _is_within(artifact_root, REPOSITORY_ROOT):
                    print(_FIXED_FAILURE)
                    return 2
                store = SnapshotArtifactStore(
                    artifact_root=artifact_root,
                    campaign_id=args.campaign_id,
                )
                store.append_manifest(
                    ManifestEntry(
                        campaign_id=args.campaign_id,
                        snapshot_id=plan.snapshot_id,
                        nominal_slot_utc=plan.spec.nominal_slot_utc,
                        scheduled_for_utc=plan.scheduled_for_utc,
                        observed_at_utc=None,
                        capture_completed_at_utc=None,
                        input_rarity=plan.spec.input_rarity,
                        stattrak_mode=plan.spec.stattrak_mode,
                        outcome="INVALID_FOR_CALIBRATION",
                        reason=plan.reason,
                        snapshot_path=None,
                        snapshot_sha256=None,
                        request_count=0,
                        pages_completed=0,
                        pages_failed=0,
                        listings_received=0,
                    )
                )
            print(
                json.dumps(
                    {
                        "mode": "plan",
                        "outcome": "INVALID_FOR_CALIBRATION",
                        "reason": plan.reason,
                        "snapshot_id": plan.snapshot_id,
                    },
                    sort_keys=True,
                )
            )
            return 1
        assert isinstance(plan, ObservationPlan)
        if args.plan_only:
            _print_plan(plan)
            return 0
        if "non-policy-smoke" not in args.campaign_id:
            print(_FIXED_FAILURE)
            return 2
        if not _within_smoke_window(plan):
            print(_FIXED_FAILURE)
            return 2
        if args.artifact_root is None:
            print(_FIXED_FAILURE)
            return 2
        artifact_root = args.artifact_root.resolve()
        if _is_within(artifact_root, REPOSITORY_ROOT):
            print(_FIXED_FAILURE)
            return 2
        result = asyncio.run(
            _collect_live_once(
                plan=plan,
                identity_resolver=identity,
                metadata_resolver=metadata,
                identity_path=identity_path,
                metadata_path=metadata_path,
            )
        )
        store = SnapshotArtifactStore(
            artifact_root=artifact_root,
            campaign_id=args.campaign_id,
        )
        receipt = store.write_snapshot(result.snapshot)
        store.append_manifest(
            manifest_entry_for_snapshot(
                snapshot=result.snapshot,
                receipt=receipt,
                request_count=result.request_count,
            )
        )
        output: dict[str, object] = {
            "mode": "non-policy-smoke",
            "outcome": result.snapshot.observation_status.value,
            "request_count": result.request_count,
            "snapshot_id": result.snapshot.snapshot_id,
            "snapshot_sha256": receipt.snapshot_sha256,
        }
        if args.replay_written and result.snapshot.observation_status.value == "COMPLETE":
            replay = replay_snapshot_path(
                snapshot_path=receipt.snapshot_path,
                metadata_snapshot_path=metadata_path,
                identity_snapshot_path=identity_path,
                expected_snapshot_sha256=receipt.snapshot_sha256,
            )
            output["replay"] = {
                "recipe_count": replay.recipe_count,
                "run_unique_output_names": replay.run_unique_output_names,
                "composition_states_explored": replay.composition_states_explored,
            }
        print(json.dumps(output, sort_keys=True))
        return 0
    except MemoryError:
        raise
    except KeyboardInterrupt:
        return 130
    except Exception:
        print(_FIXED_FAILURE)
        return 1


async def _collect_live_once(
    *,
    plan: ObservationPlan,
    identity_resolver: BuffCommunityIdentityResolver,
    metadata_resolver: PinnedSkinMetadataResolver,
    identity_path: Path,
    metadata_path: Path,
):
    provenance = SnapshotProvenance(
        collector_git_commit=_git_head(),
        identity_snapshot_path=identity_path.relative_to(REPOSITORY_ROOT).as_posix(),
        identity_snapshot_sha256=file_sha256(identity_path),
        metadata_snapshot_path=metadata_path.relative_to(REPOSITORY_ROOT).as_posix(),
        metadata_snapshot_sha256=file_sha256(metadata_path),
    )
    async with AsyncExitStack() as stack:
        http_client = httpx.AsyncClient(timeout=10.0, trust_env=False)
        stack.push_async_callback(http_client.aclose)
        provider = BuffListingProvider(BuffAnonymousListingHttpClient(http_client))
        return await collect_observation(
            plan=plan,
            listing_provider=provider,
            identity_resolver=identity_resolver,
            metadata_resolver=metadata_resolver,
            provenance=provenance,
            request_interval_seconds=MINIMUM_REQUEST_START_INTERVAL_SECONDS,
        )


def _print_plan(plan: ObservationPlan) -> None:
    print(
        json.dumps(
            {
                "mode": "plan-only",
                "snapshot_id": plan.snapshot_id,
                "scheduled_for_utc": plan.scheduled_for_utc,
                "jitter_minutes": plan.jitter_minutes,
                "input_rarity": plan.spec.input_rarity,
                "stattrak_mode": plan.spec.stattrak_mode,
                "goods_count": len(plan.planned_goods),
                "selected_cohort_count": plan.selected_cohort_count,
                "network_requests": 0,
            },
            sort_keys=True,
        )
    )


def _within_smoke_window(plan: ObservationPlan) -> bool:
    scheduled = datetime.strptime(
        plan.scheduled_for_utc,
        "%Y-%m-%dT%H:%M:%SZ",
    ).replace(tzinfo=UTC)
    now = datetime.now(UTC)
    return timedelta(0) <= now - scheduled <= timedelta(minutes=30)


def _repository_file(path: Path) -> Path:
    resolved = path.resolve()
    if not _is_within(resolved, REPOSITORY_ROOT) or not resolved.is_file():
        raise ValueError("snapshot path must be an existing repository file")
    return resolved


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    value = result.stdout.strip()
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("invalid git head")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
