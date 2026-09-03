"""Phase 16F / 16F-R1 / 16F-R2 — One bounded read-only recipe-first BUFF live validation script.

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

R1 artifact-identity corrections (Phase 16F-R1):

- The ``repository_commit_oid`` field stores the exact output of
  ``git rev-parse HEAD`` verbatim (40-character Git SHA-1 lowercase
  hex). No hashing, no coercion, no fake SHA-256.
- The persisted case artifact bytes equal :func:`serialize_case`
  byte-for-byte. There is no trailing newline.
- ``case_sha256`` reported by the script is SHA-256 of the exact
  canonical bytes persisted as the case artifact; it equals
  :func:`hash_case` exactly. There is no longer a separate
  ``file_digest`` vs ``canonical_digest``.

R2 family-metadata-contract corrections (Phase 16F-R2):

- ``LIVE_CASE_SCHEMA_VERSION`` is now 3. v1 and v2 artifacts are
  rejected by the loader; they are not silently reinterpreted.
- The frozen family identity (``family_hash`` / ``family_key`` /
  ``input_rarity`` / ``stattrak_mode`` / ``collection_counts``) is
  produced by the authoritative ``build_recipe_family``. Manual
  hash construction is forbidden.
- Every plan item is proven against the pinned metadata snapshot,
  canonical intrinsic classifier, and authoritative recipe family
  builder BEFORE HTTP dispatch via
  ``verify_case_metadata_contract``.
- Souvenir is treated as concrete-input provenance only; structural
  family identity is canonical non-Souvenir.
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
from app.services.buff_intrinsic_flag_resolver import (
    BuffListingIntrinsicFlagResolver,
    CanonicalNameIntrinsicFlagResolver,
)
from app.services.market_universe_builder import StatTrakMode
from app.services.recipe_family import (
    RecipeFamilyIdentityError,
    build_recipe_family,
)
from app.services.recipe_family_geometry import (
    RecipeFamilyGeometryError,
    compute_recipe_family_geometry,
)
from app.services.recipe_first_live_case import (
    LIVE_CASE_SCHEMA_VERSION,
    LiveValidationCase,
    LiveValidationCaseError,
    LiveValidationPlanItem,
    freeze_case,
    hash_case,
    serialize_case,
    verify_case_identity,
    verify_case_metadata_contract,
)
from app.services.recipe_first_live_runner import (
    LIVE_RUN_RESULT_SCHEMA_VERSION,
    LiveValidationRunner,
    LiveValidationRunnerConfig,
)
from app.services.skin_metadata_resolver import (
    PinnedSkinMetadataResolver,
)
from app.services.structural_output_finish import StructuralOutputFinishIndex
from app.services.trade_up_input_enrichment import TradeUpInputMetadataResolver

RUN_GATE_ENV: str = "RECIPE_FIRST_RUN_BUFF_INTERFACE_VALIDATION"
ARTIFACT_DIR_ENV: str = "RECIPE_FIRST_PHASE16F_ARTIFACT_DIR"
CASE_FILENAME: str = "phase16f_case.json"
RESULT_FILENAME: str = "phase16f_result.json"

# Authoritative Phase 16F-R2 default live fixture.
# Derived from pinned identity + pinned metadata audit, not from
# fabricated hard-coded family fields.
DEFAULT_TARGET_MARKET_HASH_NAME: str = "AK-47 | Redline (Field-Tested)"
DEFAULT_TARGET_GOODS_ID: str = "33960"


def _print_lines(printer: Callable[[str], None], *lines: str) -> None:
    for line in lines:
        printer(line)


def _resolve_commit_oid(*, run_git: Callable[[Sequence[str]], str]) -> str:
    """Return the exact Git commit object ID for ``HEAD``.

    The result is the verbatim output of ``git rev-parse HEAD``,
    stripped of any trailing whitespace. No hashing, no expansion,
    no coercion. Validation accepts 40 or 64 lowercase hex chars.
    """

    return run_git(("rev-parse", "HEAD")).strip()


def _artifact_root(*, env: Mapping[str, str]) -> Path:
    raw = env.get(ARTIFACT_DIR_ENV)
    if raw is None or not raw.strip():
        return Path(os.environ.get("TEMP", "/tmp")) / "cs2-phase16f"
    return Path(raw)


def _default_case_purpose() -> str:
    return (
        "Phase 16F-R2 bounded recipe-first BUFF anonymous live "
        "interface validation; one corrected fixed single-collection "
        "Classified family and one anonymous goods-page request."
    )


@dataclass(frozen=True, kw_only=True)
class _PreparedCaseFixture:
    """Offline-only case construction inputs."""

    repository_commit_oid: str
    family_hash: str
    family_key: str
    input_rarity: str
    stattrak_mode: StatTrakMode
    collection_counts: tuple[tuple[str, int], ...]
    plan_items: tuple[LiveValidationPlanItem, ...]


def _build_default_fixture(
    *,
    repository_commit_oid: str,
    metadata_resolver: TradeUpInputMetadataResolver,
    intrinsic_resolver: BuffListingIntrinsicFlagResolver,
    finish_index: StructuralOutputFinishIndex,
    target_market_hash_name: str = DEFAULT_TARGET_MARKET_HASH_NAME,
    target_goods_id: str = DEFAULT_TARGET_GOODS_ID,
) -> _PreparedCaseFixture:
    """Build the authoritative fixture from pinned metadata.

    No manual hash duplication. The exact family hash, key, rarity,
    StatTrak mode, and collection_counts come from
    :func:`build_recipe_family`. The exact collection_name and
    input_rarity come from the pinned metadata snapshot. The exact
    StatTrak mode comes from the canonical intrinsic classifier.
    """

    metadata = metadata_resolver.resolve(target_market_hash_name)
    if metadata is None:
        raise LiveValidationCaseError(
            f"target {target_market_hash_name!r} is not in pinned metadata"
        )
    intrinsic = intrinsic_resolver.resolve(target_market_hash_name)
    if intrinsic is None:
        raise LiveValidationCaseError(
            f"target {target_market_hash_name!r} canonical intrinsic flags unresolved"
        )
    collection_name = metadata.collection_name
    input_rarity = metadata.rarity
    stattrak_mode = (
        StatTrakMode.STATTRAK if intrinsic.stattrak else StatTrakMode.NORMAL
    )
    try:
        family = build_recipe_family(
            input_rarity=input_rarity,
            stattrak_mode=stattrak_mode,
            collection_counts=((collection_name, 10),),
        )
        geometry = compute_recipe_family_geometry(
            family, finish_index=finish_index
        )
    except MemoryError:
        raise
    except (RecipeFamilyIdentityError, RecipeFamilyGeometryError) as exc:
        raise LiveValidationCaseError(
            "target cannot form a valid productive RecipeFamily"
        ) from exc
    if not geometry.outcomes:
        raise LiveValidationCaseError(
            "family geometry has no structural outcomes"
        )
    plan_item = LiveValidationPlanItem(
        market_hash_name=target_market_hash_name,
        goods_id=target_goods_id,
        collection_name=collection_name,
        priority_within_collection=1,
    )
    return _PreparedCaseFixture(
        repository_commit_oid=repository_commit_oid,
        family_hash=family.family_hash,
        family_key=family.family_key,
        input_rarity=family.input_rarity,
        stattrak_mode=family.stattrak_mode,
        collection_counts=family.collection_counts,
        plan_items=(plan_item,),
    )


async def prepare_case(
    *,
    env: Mapping[str, str],
    printer: Callable[[str], None] = print,
    snapshot_root: Path,
    run_git: Callable[[Sequence[str]], str] | None = None,
) -> int:
    """Offline preparation. Writes case artifact outside Git. Zero network."""

    try:
        commit_oid = _resolve_commit_oid(
            run_git=(run_git or (lambda argv: subprocess.check_output(
                ("git",) + tuple(argv), text=True
            )))
        )
    except Exception as exc:
        _print_lines(
            printer,
            "phase16f_r2_prepare: failed",
            f"reason: commit_oid_unavailable ({type(exc).__name__})",
            "live_validation_executed: no",
        )
        return 1
    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        snapshot_root / "data" / "identity" / "buff_identity_v1.json"
    )
    metadata_resolver = PinnedSkinMetadataResolver.from_snapshot_path(
        snapshot_root / "data" / "metadata" / "skin_metadata_v1.json"
    )
    skins = metadata_resolver.skins
    intrinsic_resolver: BuffListingIntrinsicFlagResolver = (
        CanonicalNameIntrinsicFlagResolver()
    )
    finish_index = StructuralOutputFinishIndex.from_skins(skins)
    try:
        fixture = _build_default_fixture(
            repository_commit_oid=commit_oid,
            metadata_resolver=metadata_resolver,
            intrinsic_resolver=intrinsic_resolver,
            finish_index=finish_index,
        )
    except LiveValidationCaseError as exc:
        _print_lines(
            printer,
            "phase16f_r2_prepare: failed",
            f"reason: fixture_invalid ({exc})",
            "live_validation_executed: no",
        )
        return 1
    try:
        case = freeze_case(
            repository_commit_oid=fixture.repository_commit_oid,
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
            "phase16f_r2_prepare: failed",
            f"reason: case_invalid ({exc})",
            "live_validation_executed: no",
        )
        return 1
    # Pre-persist identity + metadata contract proof.
    try:
        await verify_case_identity(case, identity_resolver=identity)
        verify_case_metadata_contract(
            case,
            metadata_resolver=metadata_resolver,
            intrinsic_resolver=intrinsic_resolver,
            skins=skins,
            finish_index=finish_index,
        )
    except LiveValidationCaseError as exc:
        _print_lines(
            printer,
            "phase16f_r2_prepare: failed",
            f"reason: metadata_contract_failed ({exc})",
            "live_validation_executed: no",
        )
        return 1
    root = _artifact_root(env=env)
    root.mkdir(parents=True, exist_ok=True)
    case_path = root / CASE_FILENAME
    case_bytes = serialize_case(case)
    case_path.write_bytes(case_bytes)
    case_sha = hashlib.sha256(case_bytes).hexdigest()
    if case_sha != hash_case(case):
        _print_lines(
            printer,
            "phase16f_r2_prepare: failed",
            "reason: case_digest_inconsistency",
            "live_validation_executed: no",
        )
        return 1
    _print_lines(
        printer,
        "phase16f_r2_prepare: ok",
        f"case_artifact_path: {case_path}",
        f"case_sha256: {case_sha}",
        f"repository_commit_oid: {case.repository_commit_oid}",
        f"input_rarity: {case.input_rarity}",
        f"stattrak_mode: {case.stattrak_mode.value}",
        f"collection_counts: {list(case.collection_counts)}",
        f"family_key: {case.family_key}",
        f"family_hash: {case.family_hash}",
        f"hard_request_count: {case.hard_request_count}",
        f"case_schema_version: {case.case_schema_version}",
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
            "phase16f_r2_execute: refused",
            f"reason: gate_missing ({RUN_GATE_ENV})",
            "live_validation_executed: no",
        )
        return 1
    root = _artifact_root(env=env)
    case_path = root / CASE_FILENAME
    if not case_path.is_file():
        _print_lines(
            printer,
            "phase16f_r2_execute: failed",
            f"reason: case_artifact_missing ({case_path})",
            "live_validation_executed: no",
        )
        return 1
    try:
        case = _load_case(case_path)
    except LiveValidationCaseError as exc:
        _print_lines(
            printer,
            "phase16f_r2_execute: failed",
            f"reason: case_invalid ({exc})",
            "live_validation_executed: no",
        )
        return 1
    identity = BuffCommunityIdentityResolver.from_snapshot_path(
        snapshot_root / "data" / "identity" / "buff_identity_v1.json"
    )
    metadata_resolver = PinnedSkinMetadataResolver.from_snapshot_path(
        snapshot_root / "data" / "metadata" / "skin_metadata_v1.json"
    )
    skins = metadata_resolver.skins
    intrinsic_resolver: BuffListingIntrinsicFlagResolver = (
        CanonicalNameIntrinsicFlagResolver()
    )
    finish_index = StructuralOutputFinishIndex.from_skins(skins)
    # Identity proof before HTTP.
    try:
        await verify_case_identity(case, identity_resolver=identity)
    except LiveValidationCaseError as exc:
        _print_lines(
            printer,
            "phase16f_r2_execute: failed",
            f"reason: identity_proof_failed ({exc})",
            "live_validation_executed: no",
        )
        return 1
    # Metadata + family contract proof before HTTP.
    try:
        verify_case_metadata_contract(
            case,
            metadata_resolver=metadata_resolver,
            intrinsic_resolver=intrinsic_resolver,
            skins=skins,
            finish_index=finish_index,
        )
    except LiveValidationCaseError as exc:
        _print_lines(
            printer,
            "phase16f_r2_execute: failed",
            f"reason: metadata_contract_failed ({exc})",
            "live_validation_executed: no",
        )
        return 1
    runner = LiveValidationRunner(
        case=case,
        identity_resolver=identity,
        metadata_resolver=metadata_resolver,
        intrinsic_resolver=intrinsic_resolver,
        config=runner_config or LiveValidationRunnerConfig(),
    )
    try:
        result = await runner.run()
    finally:
        await runner.aclose()
    result_path = root / RESULT_FILENAME
    result_bytes = _serialize_result(result)
    result_path.write_bytes(result_bytes)
    _print_lines(
        printer,
        "phase16f_r2_execute: complete",
        f"result_artifact_path: {result_path}",
        f"classification: {result.classification}",
        f"attempted: {result.attempted}",
        f"dispatched: {result.dispatched}",
        f"budget_exceeded: {result.budget_exceeded}",
        f"hard_request_count: {result.hard_request_count}",
        f"family_compatible_enriched_inputs: {result.family_compatible_enriched_inputs}",
        "live_validation_executed: yes",
    )
    return 0


def _load_case(path: Path) -> LiveValidationCase:
    payload = json.loads(path.read_bytes())
    if (
        type(payload) is not dict
        or payload.get("case_schema_version") != LIVE_CASE_SCHEMA_VERSION
    ):
        raise LiveValidationCaseError(
            f"unsupported case schema version: {payload.get('case_schema_version')!r}; "
            f"only {LIVE_CASE_SCHEMA_VERSION} is accepted"
        )
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
        repository_commit_oid=payload["repository_commit_oid"],
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
        "collection_counts": [
            [name, count] for name, count in result.collection_counts
        ],
        "dispatched": result.dispatched,
        "family_hash": result.family_hash,
        "family_key": result.family_key,
        "family_compatible_enriched_inputs": result.family_compatible_enriched_inputs,
        "family_incompatible_enriched_inputs": result.family_incompatible_enriched_inputs,
        "hard_request_count": result.hard_request_count,
        "input_rarity": result.input_rarity,
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
        "repository_commit_oid": result.repository_commit_oid,
        "schema_version": LIVE_RUN_RESULT_SCHEMA_VERSION,
        "stattrak_mode": result.stattrak_mode,
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
        description=(
            "Phase 16F / 16F-R1 / 16F-R2 bounded recipe-first BUFF "
            "live validation script"
        ),
    )
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("prepare", help="freeze and serialize validation case")
    sub.add_parser("execute", help="run one bounded live BUFF validation attempt")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    env = os.environ
    snapshot_root = Path(__file__).resolve().parents[1]
    if args.mode == "prepare":
        return asyncio.run(prepare_case(env=env, snapshot_root=snapshot_root))
    if args.mode == "execute":
        return asyncio.run(
            execute_case(env=env, snapshot_root=snapshot_root)
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())