"""Phase 16G — Bounded Recipe-First + SteamDT live validation script.

This script supports two deterministic modes:

* ``prepare`` — OFFLINE ONLY. Freeze the Phase 16G validation case
  from the corrected R2 family plus reachable-output wear names, and
  serialize it to canonical UTF-8 JSON outside Git. Zero network I/O.
* ``execute`` — LIVE. Requires explicit
  ``RECIPE_FIRST_RUN_PHASE16G_LIVE_VALIDATION=true``. Loads the
  frozen case, performs exactly:

  1. one SteamDT strict BUFF batch pre-screen
  2. one BUFF anonymous page-1/default-sort GET
  3. up to two SteamDT strict single-name final valuation requests
  4. (optional) offline EV / risk over already-valued evidence

  ..and writes a redacted result JSON outside Git.

The script NEVER retries, paginates, or falls back.
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
from app.services.metadata_models import SkinMetadata
from app.services.recipe_family import build_recipe_family
from app.services.recipe_first_live_case import (
    LIVE_CASE_SCHEMA_VERSION,
    LiveValidationCaseError,
    LiveValidationPlanItem,
    freeze_case,
    verify_case_metadata_contract,
)
from app.services.recipe_first_steamdt_live_case import (
    LIVE_STEAMDT_CASE_SCHEMA_VERSION,
    RecipeFirstSteamDTCase,
    RecipeFirstSteamDTCaseError,
    freeze_recipe_first_steamdt_case,
    hash_recipe_first_steamdt_case,
    serialize_recipe_first_steamdt_case,
)
from app.services.recipe_first_steamdt_live_runner import (
    RecipeFirstSteamDTLiveRunner,
    RecipeFirstSteamDTLiveRunnerConfig,
)
from app.services.skin_metadata_resolver import (
    PinnedSkinMetadataResolver,
)
from app.services.static_float_feasibility import (
    StaticFloatFeasibilityStatus,
    compute_static_float_feasibility,
)
from app.services.structural_output_finish import StructuralOutputFinishIndex

RUN_GATE_ENV: str = "RECIPE_FIRST_RUN_PHASE16G_LIVE_VALIDATION"
ARTIFACT_DIR_ENV: str = "RECIPE_FIRST_PHASE16G_ARTIFACT_DIR"
API_KEY_ENV: str = "STEAMDT_API_KEY"
CASE_FILENAME: str = "phase16g_case.json"
RESULT_FILENAME: str = "phase16g_result.json"

_DEFAULT_TARGET_MARKET_HASH_NAME: str = "AK-47 | Redline (Field-Tested)"
_DEFAULT_TARGET_GOODS_ID: str = "33960"
_MAX_PRESCREEN_NAMES: int = 10


def _print_lines(printer: Callable[[str], None], *lines: str) -> None:
    for line in lines:
        printer(line)


def _resolve_commit_oid(*, run_git: Callable[[Sequence[str]], str]) -> str:
    return run_git(("rev-parse", "HEAD")).strip()


def _artifact_root(*, env: Mapping[str, str]) -> Path:
    raw = env.get(ARTIFACT_DIR_ENV)
    if raw is None or not raw.strip():
        return Path(os.environ.get("TEMP", "/tmp")) / "cs2-phase16g"
    return Path(raw)


def _load_skins(snapshot_root: Path) -> tuple[SkinMetadata, ...]:
    payload = json.loads(
        (snapshot_root / "data" / "metadata" / "skin_metadata_v1.json").read_bytes()
    )
    return tuple(
        SkinMetadata(
            market_hash_name=item["market_hash_name"],
            name=item.get("name"),
            weapon=item.get("weapon"),
            rarity=item["rarity"],
            category=item.get("category"),
            collection_name=item.get("collection_name"),
            min_float=item["min_float"],
            max_float=item["max_float"],
            stattrak=bool(item.get("stattrak", False)),
            souvenir=bool(item.get("souvenir", False)),
            paint_index=item.get("paint_index"),
            raw=None,
        )
        for item in payload["items"]
    )


def _resolve_prescreen_names(
    *,
    family_plan_items: tuple[LiveValidationPlanItem, ...],
    reachable_outputs: tuple,
) -> tuple[str, ...]:
    """Compose plan names first, then reachable outputs (deduped)."""

    plan_names = tuple(item.market_hash_name for item in family_plan_items)
    output_names = tuple(
        entry.exact_market_hash_name for entry in reachable_outputs
    )
    combined: list[str] = []
    seen: set[str] = set()
    for name in plan_names + output_names:
        if name not in seen:
            seen.add(name)
            combined.append(name)
    if not (1 <= len(combined) <= _MAX_PRESCREEN_NAMES):
        raise RecipeFirstSteamDTCaseError(
            f"pre-screen set size {len(combined)} out of range 1..{_MAX_PRESCREEN_NAMES}"
        )
    return tuple(combined)


async def prepare_case(
    *,
    env: Mapping[str, str],
    printer: Callable[[str], None] = print,
    snapshot_root: Path,
    run_git: Callable[[Sequence[str]], str] | None = None,
) -> int:
    try:
        commit_oid = _resolve_commit_oid(
            run_git=(run_git or (lambda argv: subprocess.check_output(
                ("git",) + tuple(argv), text=True
            )))
        )
    except Exception as exc:
        _print_lines(
            printer,
            "phase16g_prepare: failed",
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
    intrinsic_resolver: BuffListingIntrinsicFlagResolver = (
        CanonicalNameIntrinsicFlagResolver()
    )
    skins = _load_skins(snapshot_root)
    finish_index = StructuralOutputFinishIndex.from_skins(skins)

    metadata = metadata_resolver.resolve(_DEFAULT_TARGET_MARKET_HASH_NAME)
    if metadata is None:
        _print_lines(printer, "phase16g_prepare: failed",
        "reason: target not in pinned metadata",
        "live_validation_executed: no",
    )
        return 1
    intrinsic = intrinsic_resolver.resolve(_DEFAULT_TARGET_MARKET_HASH_NAME)
    if intrinsic is None:
        _print_lines(printer, "phase16g_prepare: failed",
        "reason: target intrinsic unresolved",
        "live_validation_executed: no",
    )
        return 1
    stattrak_mode = (
        StatTrakMode.STATTRAK if intrinsic.stattrak else StatTrakMode.NORMAL
    )
    family = build_recipe_family(
        input_rarity=metadata.rarity,
        stattrak_mode=stattrak_mode,
        collection_counts=((metadata.collection_name, 10),),
    )
    plan_item = LiveValidationPlanItem(
        market_hash_name=_DEFAULT_TARGET_MARKET_HASH_NAME,
        goods_id=_DEFAULT_TARGET_GOODS_ID,
        collection_name=metadata.collection_name,
        priority_within_collection=1,
    )
    buff_case = freeze_case(
        repository_commit_oid=commit_oid,
        case_purpose="Phase 16G bounded recipe-first SteamDT live validation",
        family_hash=family.family_hash,
        family_key=family.family_key,
        input_rarity=family.input_rarity,
        stattrak_mode=family.stattrak_mode,
        collection_counts=family.collection_counts,
        plan_items=(plan_item,),
    )
    try:
        verify_case_metadata_contract(
            buff_case,
            metadata_resolver=metadata_resolver,
            intrinsic_resolver=intrinsic_resolver,
            finish_index=finish_index,
        )
    except LiveValidationCaseError as exc:
        _print_lines(
            printer,
            "phase16g_prepare: failed",
            f"reason: metadata_contract_failed ({exc})",
            "live_validation_executed: no",
        )
        return 1

    feasibility = compute_static_float_feasibility(
        family,
        skins=skins,
        identity_resolver=identity,
        finish_index=finish_index,
    )
    if feasibility.status is not StaticFloatFeasibilityStatus.FEASIBLE:
        _print_lines(
            printer,
            "phase16g_prepare: failed",
            f"reason: static_feasibility_not_feasible ({feasibility.status.value})",
            "live_validation_executed: no",
        )
        return 1

    try:
        prescreen_names = _resolve_prescreen_names(
            family_plan_items=buff_case.plan_items,
            reachable_outputs=feasibility.reachable_outputs,
        )
    except RecipeFirstSteamDTCaseError as exc:
        _print_lines(
            printer,
            "phase16g_prepare: failed",
            f"reason: prescreen_set_invalid ({exc})",
            "live_validation_executed: no",
        )
        return 1

    try:
        case = freeze_recipe_first_steamdt_case(
            repository_commit_oid=commit_oid,
            buff_case=buff_case,
            prescreen_market_hash_names=prescreen_names,
        )
    except RecipeFirstSteamDTCaseError as exc:
        _print_lines(
            printer,
            "phase16g_prepare: failed",
            f"reason: case_invalid ({exc})",
            "live_validation_executed: no",
        )
        return 1

    root = _artifact_root(env=env)
    root.mkdir(parents=True, exist_ok=True)
    case_path = root / CASE_FILENAME
    case_bytes = serialize_recipe_first_steamdt_case(case)
    case_path.write_bytes(case_bytes)
    case_sha = hashlib.sha256(case_bytes).hexdigest()
    if case_sha != hash_recipe_first_steamdt_case(case):
        _print_lines(
            printer,
            "phase16g_prepare: failed",
            "reason: case_digest_inconsistency",
            "live_validation_executed: no",
        )
        return 1
    _print_lines(
        printer,
        "phase16g_prepare: ok",
        f"case_artifact_path: {case_path}",
        f"case_sha256: {case_sha}",
        f"repository_commit_oid: {case.repository_commit_oid}",
        f"family_key: {case.buff_case.family_key}",
        f"family_hash: {case.buff_case.family_hash}",
        f"input_rarity: {case.buff_case.input_rarity}",
        f"collection_counts: {list(case.buff_case.collection_counts)}",
        f"static_feasibility_status: {feasibility.status.value}",
        f"prescreen_count: {len(prescreen_names)}",
        f"buff_http_cap: {case.buff_http_cap}",
        f"steamdt_batch_http_cap: {case.steamdt_batch_http_cap}",
        f"steamdt_final_single_http_cap: {case.steamdt_final_single_http_cap}",
        f"steamdt_total_http_cap: {case.steamdt_total_http_cap}",
        f"case_schema_version: {case.case_schema_version}",
        "live_validation_executed: no",
    )
    return 0


async def execute_case(
    *,
    env: Mapping[str, str],
    printer: Callable[[str], None] = print,
    snapshot_root: Path,
    api_key: str | None,
    runner_config: RecipeFirstSteamDTLiveRunnerConfig | None = None,
) -> int:
    gate = env.get(RUN_GATE_ENV, "").strip().lower()
    if gate not in {"1", "true", "yes", "on"}:
        _print_lines(
            printer,
            "phase16g_execute: refused",
            f"reason: gate_missing ({RUN_GATE_ENV})",
            "live_validation_executed: no",
        )
        return 1
    if api_key is None or not api_key.strip():
        _print_lines(
            printer,
            "phase16g_execute: refused",
            f"reason: api_key_missing ({API_KEY_ENV})",
            "live_validation_executed: no",
        )
        return 1
    root = _artifact_root(env=env)
    case_path = root / CASE_FILENAME
    if not case_path.is_file():
        _print_lines(
            printer,
            "phase16g_execute: failed",
            f"reason: case_artifact_missing ({case_path})",
            "live_validation_executed: no",
        )
        return 1
    try:
        case = _load_case(case_path)
    except (RecipeFirstSteamDTCaseError, LiveValidationCaseError) as exc:
        _print_lines(
            printer,
            "phase16g_execute: failed",
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
    intrinsic_resolver: BuffListingIntrinsicFlagResolver = (
        CanonicalNameIntrinsicFlagResolver()
    )
    runner = RecipeFirstSteamDTLiveRunner(
        case=case,
        buff_identity_resolver=identity,
        metadata_resolver=metadata_resolver,
        intrinsic_resolver=intrinsic_resolver,
        config=runner_config
        or RecipeFirstSteamDTLiveRunnerConfig(api_key=api_key),
    )
    try:
        result = await runner.run(live_validation_authorized=True)
    finally:
        await runner.aclose()
    result_path = root / RESULT_FILENAME
    result_bytes = _serialize_result(result)
    result_path.write_bytes(result_bytes)
    _print_lines(
        printer,
        "phase16g_execute: complete",
        f"result_artifact_path: {result_path}",
        f"classification: {result.classification}",
        f"case_sha: {result.case_sha256}",
        f"family_hash: {result.family_hash}",
        f"static_feasibility_status: {result.static_feasibility_status}",
        f"prescreen_count: {len(result.prescreen_names)}",
        f"family_compatible_enriched_inputs: {result.family_compatible_enriched_inputs}",
        f"final_quotes_count: {len(result.final_quotes)}",
        f"final_missing_count: {len(result.final_missing_names)}",
        f"final_errors_count: {len(result.final_errors)}",
        f"request_state: {result.request_state}",
        "live_validation_executed: yes",
    )
    return 0


def _load_case(
    path: Path,
) -> RecipeFirstSteamDTCase:
    payload = json.loads(path.read_bytes())
    if (
        type(payload) is not dict
        or payload.get("case_schema_version") != LIVE_STEAMDT_CASE_SCHEMA_VERSION
    ):
        raise RecipeFirstSteamDTCaseError("unsupported case schema version")
    buff_payload = payload["buff_case"]
    if buff_payload.get("case_schema_version") != LIVE_CASE_SCHEMA_VERSION:
        raise LiveValidationCaseError("unsupported buff case schema version")
    plan_items_payload = buff_payload["plan_items"]
    plan_items = tuple(
        LiveValidationPlanItem(
            market_hash_name=item["market_hash_name"],
            goods_id=item["goods_id"],
            collection_name=item["collection_name"],
            priority_within_collection=int(item["priority_within_collection"]),
        )
        for item in plan_items_payload
    )
    buff_case = freeze_case(
        repository_commit_oid=buff_payload["repository_commit_oid"],
        case_purpose=buff_payload["case_purpose"],
        family_hash=buff_payload["family_hash"],
        family_key=buff_payload["family_key"],
        input_rarity=buff_payload["input_rarity"],
        stattrak_mode=StatTrakMode(buff_payload["stattrak_mode"]),
        collection_counts=tuple(
            (entry[0], int(entry[1]))
            for entry in buff_payload["collection_counts"]
        ),
        plan_items=plan_items,
    )
    return freeze_recipe_first_steamdt_case(
        repository_commit_oid=payload["repository_commit_oid"],
        buff_case=buff_case,
        prescreen_market_hash_names=tuple(payload["prescreen_market_hash_names"]),
    )


def _serialize_result(result) -> bytes:
    payload = {
        "buff_http_cap": result.page_results and "buff" or None,
        "case_sha256": result.case_sha256,
        "classification": result.classification,
        "concrete_output_market_hash_names": list(
            result.concrete_output_market_hash_names
        ),
        "concrete_selection_count": result.concrete_selection_count,
        "family_compatible_enriched_inputs": result.family_compatible_enriched_inputs,
        "family_hash": result.family_hash,
        "family_incompatible_enriched_inputs": result.family_incompatible_enriched_inputs,
        "family_key": result.family_key,
        "final_errors": list(result.final_errors),
        "final_missing_names": list(result.final_missing_names),
        "final_new_live_names": list(result.final_new_live_names),
        "final_quotes": [
            {
                "market_hash_name": quote.market_hash_name,
                "price_cny": str(quote.price_cny),
                "source": quote.source,
            }
            for quote in result.final_quotes
        ],
        "hard_request_count": result.hard_request_count,
        "input_rarity": result.input_rarity,
        "page_results": [
            {
                "candidate_accepted": page.candidate_accepted,
                "family_compatible": page.family_compatible,
                "family_incompatible": page.family_incompatible,
                "goods_id": page.goods_id,
                "listing_count": page.listing_count,
                "market_hash_name": page.market_hash_name,
                "metadata_resolved": page.metadata_resolved,
                "request_status": page.request_status,
            }
            for page in result.page_results
        ],
        "phases": [
            {"detail": phase.detail, "name": phase.name, "status": phase.status}
            for phase in result.phases
        ],
        "prescreen_failure_names": [
            list(pair) for pair in result.prescreen_failure_names
        ],
        "prescreen_missing_names": list(result.prescreen_missing_names),
        "prescreen_names": list(result.prescreen_names),
        "prescreen_quotes": [
            {
                "market_hash_name": quote.market_hash_name,
                "sell_count": quote.sell_count,
                "sell_price_cny": str(quote.sell_price_cny),
                "source": quote.source,
                "update_time": quote.update_time,
            }
            for quote in result.prescreen_quotes
        ],
        "repository_commit_oid": result.repository_commit_oid,
        "request_state": {
            "buff_attempted": result.request_state.buff_attempted,
            "buff_dispatched": result.request_state.buff_dispatched,
            "steamdt_batch_attempted": result.request_state.steamdt_batch_attempted,
            "steamdt_batch_dispatched": result.request_state.steamdt_batch_dispatched,
            "steamdt_single_attempted": result.request_state.steamdt_single_attempted,
            "steamdt_single_dispatched": result.request_state.steamdt_single_dispatched,
        },
        "schema_version": result.schema_version,
        "stattrak_mode": result.stattrak_mode,
        "static_feasibility_status": result.static_feasibility_status,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_live_recipe_first_steamdt_validation",
        description=(
            "Phase 16G bounded Recipe-First + SteamDT live validation script"
        ),
    )
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("prepare", help="freeze and serialize validation case")
    sub.add_parser("execute", help="run one bounded live attempt")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    env = os.environ
    snapshot_root = Path(__file__).resolve().parents[1]
    if args.mode == "prepare":
        return asyncio.run(prepare_case(env=env, snapshot_root=snapshot_root))
    if args.mode == "execute":
        api_key = env.get(API_KEY_ENV)
        return asyncio.run(
            execute_case(
                env=env,
                snapshot_root=snapshot_root,
                api_key=api_key,
            )
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())