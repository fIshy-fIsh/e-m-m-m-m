"""Phase 16F — One bounded read-only recipe-first BUFF live validation script.

This script supports two deterministic modes:

* ``prepare`` — OFFLINE ONLY. Freeze the validation case from the pinned
  snapshots, serialize it to canonical UTF-8 JSON outside Git, and
  print the case SHA-256 + artifact location. Zero network I/O.
* ``execute`` — LIVE. Requires explicit
  ``RECIPE_FIRST_RUN_BUFF_INTERFACE_VALIDATION=true``. Loads the
  frozen case, performs exactly one anonymous BUFF page-1/default-sort
  HTTP request per plan item in order, with at most the case's
  ``hard_request_count`` total requests, and writes a redacted result
  JSON outside Git.

The script NEVER retries, paginates, or falls back. It is the only
admissible live BUFF HTTP entry point for Phase 16F.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.buff_community_identity_resolver import (
    BuffCommunityIdentityResolver,
)
from app.services.market_universe_builder import StatTrakMode
from app.services.recipe_first_live_case import (
    LiveValidationCase,
    LiveValidationCaseError,
    LiveValidationPlanItem,
    freeze_case,
    hash_case,
    serialize_case,
    verify_case_identity,
)
from app.services.recipe_first_live_runner import (
    LiveValidationRunner,
    LiveValidationRunnerConfig,
)
from app.services.skin_metadata_resolver import PinnedSkinMetadataResolver

RUN_GATE_ENV: str = "RECIPE_FIRST_RUN_BUFF_INTERFACE_VALIDATION"
ARTIFACT_DIR_ENV: str = "RECIPE_FIRST_PHASE16F_ARTIFACT_DIR"
CASE_FILENAME: str = "phase16f_case.json"
RESULT_FILENAME: str = "phase16f_result.json"


def _print_lines(printer: Callable[[str], None], *lines: str) -> None:
    for line in lines:
        printer(line)


def _resolve_head_sha(*, run_git: Callable[[Sequence[str]], str]) -> str:
    """Return the current repository HEAD SHA.

    Returns SHA-256 hex of the underlying git SHA-1 so the case field
    matches the project's strict 64-character lowercase hex contract.
    """

    raw = run_git(("rev-parse", "HEAD")).strip()
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def _artifact_root(*, env: Mapping[str, str]) -> Path:
    raw = env.get(ARTIFACT_DIR_ENV)
    if raw is None or not raw.strip():
        return Path(os.environ.get("TEMP", "/tmp")) / "cs2-phase16f"
    return Path(raw)


def _default_case_purpose() -> str:
    return (
        "Phase 16F bounded recipe-first BUFF anonymous live interface "
        "validation; one fixed single-collection Restricted/normal "
        "family and one anonymous goods-page request."
    )


@dataclass(frozen=True, kw_only=True)
class _PreparedCaseFixture:
    """Offline-only case construction inputs."""

    repository_head_sha: str
    family_hash: str
    family_key: str
    input_rarity: str
    stattrak_mode: StatTrakMode
    collection_counts: tuple[tuple[str, int], ...]
    plan_items: tuple[LiveValidationPlanItem, ...]


def _default_case_fixture(repository_head_sha: str) -> _PreparedCaseFixture:
    """Default single-collection Restricted/normal case for Phase 16F.

    Uses ``AK-47 | Redline (Field-Tested)`` -> ``33960``. This pair is
    present in the pinned BUFF community identity snapshot and
    corresponds to a real pinned metadata row in
    ``The 2018 Nuke Collection`` at Restricted / normal mode.

    The collection counts (``The 2018 Nuke Collection``, 10) require
    exactly one distinct pinned goods page request, satisfying the
    ``1 <= hard_request_count <= 10`` bound for this phase.
    """

    plan_item = LiveValidationPlanItem(
        market_hash_name="AK-47 | Redline (Field-Tested)",
        goods_id="33960",
        collection_name="The 2018 Nuke Collection",
        priority_within_collection=1,
    )
    # The family_hash below is the canonical SHA-256 of the structural
    # payload ``{"family_spec_version": 1, "input_rarity": "Restricted",
    # "stattrak_mode": "normal", "collection_counts": [["The 2018 Nuke
    # Collection", 10]]}``. The ``verify_case_identity`` step does NOT
    # depend on this hash; it only needs the goods_id <-> name pair to
    # reverse-resolve through the pinned identity snapshot. The hash is
    # used as a stable correlation identifier in the result artifact.
    family_hash = hashlib.sha256(
        json.dumps(
            {
                "family_spec_version": 1,
                "input_rarity": "Restricted",
                "stattrak_mode": "normal",
                "collection_counts": [["The 2018 Nuke Collection", 10]],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return _PreparedCaseFixture(
        repository_head_sha=repository_head_sha,
        family_hash=family_hash,
        family_key=family_hash[:24],
        input_rarity="Restricted",
        stattrak_mode=StatTrakMode.NORMAL,
        collection_counts=(("The 2018 Nuke Collection", 10),),
        plan_items=(plan_item,),
    )


async def prepare_case(
    *,
    env: Mapping[str, str],
    printer: Callable[[str], None] = print,
    run_git: Callable[[Sequence[str]], str] | None = None,
    fixture_factory: Callable[[str], _PreparedCaseFixture] | None = None,
) -> int:
    """Offline preparation. Writes case artifact outside Git. Zero network."""

    try:
        head_sha = _resolve_head_sha(
            run_git=(run_git or (lambda argv: subprocess.check_output(
                ("git",) + tuple(argv), text=True
            )))
        )
    except Exception as exc:
        _print_lines(
            printer,
            "phase16f_prepare: failed",
            f"reason: head_sha_unavailable ({type(exc).__name__})",
            "live_validation_executed: no",
        )
        return 1
    fixture = (fixture_factory or _default_case_fixture)(head_sha)
    try:
        case = freeze_case(
            repository_head_sha=fixture.repository_head_sha,
            case_purpose=_default_case_purpose(),
            family_hash=fixture.family_hash,
            family_key=fixture.family_key,
            input_rarity=fixture.input_rarity,
            stattrak_mode=fixture.stattrak_mode,
            collection_counts=fixture.collection_counts,
            plan_items=fixture.plan_items,
        )
    except LiveValidationCaseError as exc:
        _print_lines(
            printer,
            "phase16f_prepare: failed",
            f"reason: case_invalid ({exc})",
            "live_validation_executed: no",
        )
        return 1

    root = _artifact_root(env=env)
    root.mkdir(parents=True, exist_ok=True)
    case_path = root / CASE_FILENAME
    case_bytes = serialize_case(case) + b"\n"
    case_path.write_bytes(case_bytes)
    case_sha = hash_case(case)
    _print_lines(
        printer,
        "phase16f_prepare: ok",
        f"case_artifact_path: {case_path}",
        f"case_sha256: {case_sha}",
        f"family_key: {case.family_key}",
        f"family_hash: {case.family_hash}",
        f"hard_request_count: {case.hard_request_count}",
        "live_validation_executed: no",
    )
    return 0


async def execute_case(
    *,
    env: Mapping[str, str],
    printer: Callable[[str], None] = print,
    snapshot_root: Path,
    runner_config: LiveValidationRunnerConfig | None = None,
) -> int:
    """Live execution. Requires ``RUN_GATE_ENV`` to be truthy."""

    gate = env.get(RUN_GATE_ENV, "").strip().lower()
    if gate not in {"1", "true", "yes", "on"}:
        _print_lines(
            printer,
            "phase16f_execute: refused",
            f"reason: gate_missing ({RUN_GATE_ENV})",
            "live_validation_executed: no",
        )
        return 1
    root = _artifact_root(env=env)
    case_path = root / CASE_FILENAME
    if not case_path.is_file():
        _print_lines(
            printer,
            "phase16f_execute: failed",
            f"reason: case_artifact_missing ({case_path})",
            "live_validation_executed: no",
        )
        return 1
    try:
        case = _load_case(case_path)
    except LiveValidationCaseError as exc:
        _print_lines(
            printer,
            "phase16f_execute: failed",
            f"reason: case_invalid ({exc})",
            "live_validation_executed: no",
        )
        return 1
    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        snapshot_root / "data" / "identity" / "buff_identity_v1.json"
    )
    metadata = PinnedSkinMetadataResolver.from_snapshot_path(
        snapshot_root / "data" / "metadata" / "skin_metadata_v1.json"
    )
    # Identity proof before HTTP.
    try:
        await verify_case_identity(case, identity_resolver=identity)
    except LiveValidationCaseError as exc:
        _print_lines(
            printer,
            "phase16f_execute: failed",
            f"reason: identity_proof_failed ({exc})",
            "live_validation_executed: no",
        )
        return 1
    runner = LiveValidationRunner(
        case=case,
        identity_resolver=identity,
        metadata_resolver=metadata,
        config=runner_config or LiveValidationRunnerConfig(),
    )
    try:
        result = await runner.run()
    finally:
        await runner.aclose()
    result_path = root / RESULT_FILENAME
    result_path.write_bytes(_serialize_result(result) + b"\n")
    _print_lines(
        printer,
        "phase16f_execute: complete",
        f"result_artifact_path: {result_path}",
        f"classification: {result.classification}",
        f"attempted: {result.attempted}",
        f"dispatched: {result.dispatched}",
        f"budget_exceeded: {result.budget_exceeded}",
        f"hard_request_count: {result.hard_request_count}",
        "live_validation_executed: yes",
    )
    return 0


def _load_case(path: Path) -> LiveValidationCase:
    payload = json.loads(path.read_bytes())
    if (
        type(payload) is not dict
        or payload.get("case_schema_version") != 1
    ):
        raise LiveValidationCaseError("unsupported case schema version")
    stattrak_mode = StatTrakMode(payload["stattrak_mode"])
    plan_items_payload = payload["plan_items"]
    plan_items = tuple(
        LiveValidationPlanItem(
            market_hash_name=item["market_hash_name"],
            goods_id=item["goods_id"],
            collection_name=item["collection_name"],
            priority_within_collection=int(item["priority_within_collection"]),
        )
        for item in plan_items_payload
    )
    return freeze_case(
        repository_head_sha=payload["repository_head_sha"],
        case_purpose=payload["case_purpose"],
        family_hash=payload["family_hash"],
        family_key=payload["family_key"],
        input_rarity=payload["input_rarity"],
        stattrak_mode=stattrak_mode,
        collection_counts=tuple(
            (entry[0], int(entry[1])) for entry in payload["collection_counts"]
        ),
        plan_items=plan_items,
    )


def _serialize_result(result) -> bytes:
    payload = {
        "aggregate_candidate_accepted": result.aggregate_candidate_accepted,
        "aggregate_listings_received": result.aggregate_listings_received,
        "aggregate_metadata_resolved": result.aggregate_metadata_resolved,
        "attempted": result.attempted,
        "budget_exceeded": result.budget_exceeded,
        "case_sha256": result.case_sha256,
        "classification": result.classification,
        "dispatched": result.dispatched,
        "hard_request_count": result.hard_request_count,
        "page_results": [
            {
                "candidate_accepted": page.candidate_accepted,
                "candidate_rejected": page.candidate_rejected,
                "error_reason": page.error_reason,
                "goods_id": page.goods_id,
                "listing_count": page.listing_count,
                "market_hash_name": page.market_hash_name,
                "metadata_resolved": page.metadata_resolved,
                "metadata_unresolved": page.metadata_unresolved,
                "rejection_histograms": [
                    [key, count] for key, count in page.rejection_histograms
                ],
                "request_status": page.request_status,
            }
            for page in result.page_results
        ],
        "repository_head_sha": result.repository_head_sha,
        "schema_version": 1,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_live_recipe_first_buff_interface_validation",
        description="Phase 16F bounded recipe-first BUFF live validation script",
    )
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("prepare", help="freeze and serialize validation case")
    sub.add_parser("execute", help="run one bounded live BUFF validation attempt")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    env = os.environ
    if args.mode == "prepare":
        return asyncio.run(prepare_case(env=env))
    if args.mode == "execute":
        snapshot_root = Path(__file__).resolve().parents[1]
        return asyncio.run(
            execute_case(env=env, snapshot_root=snapshot_root)
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())