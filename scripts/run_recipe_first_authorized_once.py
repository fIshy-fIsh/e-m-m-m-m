"""Case-bound one-shot launcher for an explicitly authorized recipe-first run.

The launcher does not implement scanner logic. Its only child program is
``scripts/run_recipe_first_scan_once.py`` with argv frozen in an external case
manifest. Secrets are consumed only from a deterministic outside-Git file,
unlinked before spawn, and passed only in the child environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

SECRET_HANDOFF_ROOT: Final[Path] = Path(
    r"C:\Users\lijie\AppData\Local\Temp\cs2-secret-handoff"
)
SECRET_FILE_MAX_BYTES: Final[int] = 4096
SECRET_PATH_RULE: Final[str] = (
    "C:\\Users\\lijie\\AppData\\Local\\Temp\\cs2-secret-handoff\\"
    "steamdt_<first16-of-case-sha>.once"
)
OPERATOR_CONTRACT_ID: Final[str] = "recipe-first-one-shot-live-operator-contract-v1"
OPERATOR_CONTRACT_PATH: Final[str] = (
    "docs/recipe-first-one-shot-live-operator-contract.md"
)
CHILD_SCRIPT: Final[str] = "scripts/run_recipe_first_scan_once.py"


class LauncherError(RuntimeError):
    """Safe pre-spawn launcher failure."""


class ChildProcess(Protocol):
    returncode: int | None

    def communicate(self) -> tuple[str | None, str | None]: ...


PopenFactory = Callable[..., ChildProcess]
GitRunner = Callable[[Sequence[str]], str]
Printer = Callable[[str], None]


@dataclass(frozen=True, kw_only=True)
class LaunchPaths:
    secret_file: Path
    state_file: Path


@dataclass(frozen=True, kw_only=True)
class FrozenCase:
    case_path: Path
    case_sha256: str
    repository_commit_oid: str
    branch: str
    child_argv: tuple[str, ...]
    result_artifact_path: Path
    secret_path_rule: str
    operator_contract_id: str
    operator_contract_path: str


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _exact_sha256(value: object, *, field: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise LauncherError(f"{field} must be lowercase SHA-256 hex")
    return value


def _exact_text(value: object, *, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise LauncherError(f"{field} must be an exact non-empty string")
    return value


def derive_launch_paths(
    case_sha256: str,
    *,
    secret_root: Path = SECRET_HANDOFF_ROOT,
) -> LaunchPaths:
    digest = _exact_sha256(case_sha256, field="case_sha256")
    prefix = digest[:16]
    return LaunchPaths(
        secret_file=secret_root / f"steamdt_{prefix}.once",
        state_file=secret_root / f"steamdt_{prefix}.launch-state.json",
    )


def _default_git(argv: Sequence[str]) -> str:
    return subprocess.check_output(("git",) + tuple(argv), text=True)


def _validate_child_argv(value: object) -> tuple[str, ...]:
    if type(value) is not list or not value:
        raise LauncherError("child_argv must be a non-empty JSON array")
    argv = tuple(_exact_text(item, field="child_argv item") for item in value)
    if len(argv) < 3:
        raise LauncherError("child_argv must contain Python, script, and arguments")
    if argv[0] not in {
        ".venv/Scripts/python.exe",
        "./.venv/Scripts/python.exe",
    }:
        raise LauncherError("child_argv Python path is not the frozen project interpreter")
    if argv[1] != CHILD_SCRIPT:
        raise LauncherError("child_argv must launch the recipe-first operator CLI")
    if "--enable-recipe-first" not in argv:
        raise LauncherError("child_argv lacks explicit recipe-first enablement")
    if "--preview" in argv:
        raise LauncherError("child_argv must not launch preview mode")
    forbidden_fragments = (
        "STEAMDT_API_KEY",
        "--api-key",
        "Authorization",
        "Bearer ",
    )
    if any(fragment in item for fragment in forbidden_fragments for item in argv):
        raise LauncherError("child_argv contains a forbidden secret-bearing field")
    return argv


def load_frozen_case(
    case_file: Path,
    *,
    expected_case_sha256: str,
    repository_root: Path,
    run_git: GitRunner = _default_git,
) -> FrozenCase:
    expected = _exact_sha256(
        expected_case_sha256,
        field="expected_case_sha256",
    )
    if not case_file.is_file():
        raise LauncherError("case file is missing or not a regular file")
    raw = case_file.read_bytes()
    if _sha256(raw) != expected:
        raise LauncherError("case SHA-256 mismatch")
    try:
        payload: object = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LauncherError("case file is not canonical JSON") from exc
    if type(payload) is not dict:
        raise LauncherError("case payload must be a JSON object")
    if raw != _canonical_json_bytes(payload):
        raise LauncherError("case file is not canonical JSON")

    repository_commit_oid = _exact_text(
        payload.get("repository_commit_oid"),
        field="repository_commit_oid",
    )
    current_head = run_git(("rev-parse", "HEAD")).strip()
    if current_head != repository_commit_oid:
        raise LauncherError("case repository commit does not match current HEAD")
    upstream_head = run_git(("rev-parse", "@{u}")).strip()
    if upstream_head != current_head:
        raise LauncherError("current HEAD does not match upstream")
    tracked_status = run_git(
        ("status", "--porcelain", "--untracked-files=no")
    ).strip()
    if tracked_status:
        raise LauncherError("tracked working tree is not clean")
    branch = _exact_text(payload.get("branch"), field="branch")
    current_branch = run_git(("branch", "--show-current")).strip()
    if current_branch != branch:
        raise LauncherError("case branch does not match current branch")

    child_argv = _validate_child_argv(payload.get("child_argv"))
    artifact = payload.get("result_artifact")
    if type(artifact) is not dict:
        raise LauncherError("result_artifact must be an object")
    result_path = Path(
        _exact_text(artifact.get("path"), field="result artifact path")
    )
    if result_path.resolve().is_relative_to(repository_root.resolve()):
        raise LauncherError("result artifact path must be outside the repository")

    secret_rule = _exact_text(
        payload.get("secret_path_rule"),
        field="secret_path_rule",
    )
    if secret_rule != SECRET_PATH_RULE:
        raise LauncherError("secret path rule does not match launcher authority")
    contract = payload.get("operator_contract")
    if type(contract) is not dict:
        raise LauncherError("operator_contract must be an object")
    contract_id = _exact_text(contract.get("id"), field="operator contract id")
    contract_path = _exact_text(
        contract.get("path"),
        field="operator contract path",
    )
    if contract_id != OPERATOR_CONTRACT_ID or contract_path != OPERATOR_CONTRACT_PATH:
        raise LauncherError("operator contract identity mismatch")

    return FrozenCase(
        case_path=case_file,
        case_sha256=expected,
        repository_commit_oid=repository_commit_oid,
        branch=branch,
        child_argv=child_argv,
        result_artifact_path=result_path,
        secret_path_rule=secret_rule,
        operator_contract_id=contract_id,
        operator_contract_path=contract_path,
    )


def _write_state_exclusive(path: Path, payload: Mapping[str, object]) -> None:
    raw = _canonical_json_bytes(payload)
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise


def _write_state(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_json_bytes(payload))
    os.replace(temporary, path)


def _safe_unlink(path: Path) -> None:
    path.unlink()
    if path.exists():
        raise LauncherError("one-shot secret unlink did not complete")


def _load_secret(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise LauncherError("one-shot secret file is missing or invalid")
    stat = path.stat()
    if stat.st_size <= 0 or stat.st_size > SECRET_FILE_MAX_BYTES:
        raise LauncherError("one-shot secret file is missing or invalid")
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LauncherError("one-shot secret file is missing or invalid") from exc
    if not value or value != value.strip() or "\x00" in value:
        raise LauncherError("one-shot secret file is missing or invalid")
    return value


def redact_secret(text: str | None, secret: str) -> str:
    if not text:
        return ""
    return text.replace(secret, "[REDACTED]")


def _print(printer: Printer, *lines: str) -> None:
    for line in lines:
        printer(line)


def run_authorized_once(
    *,
    case_file: Path,
    expected_case_sha256: str,
    preflight_only: bool,
    repository_root: Path,
    secret_root: Path = SECRET_HANDOFF_ROOT,
    run_git: GitRunner = _default_git,
    popen_factory: PopenFactory = subprocess.Popen,
    parent_environment: Mapping[str, str] | None = None,
    printer: Printer = print,
) -> int:
    """Validate and optionally spawn exactly one frozen recipe-first child."""

    try:
        case = load_frozen_case(
            case_file,
            expected_case_sha256=expected_case_sha256,
            repository_root=repository_root,
            run_git=run_git,
        )
        paths = derive_launch_paths(case.case_sha256, secret_root=secret_root)
        if paths.secret_file.resolve().is_relative_to(repository_root.resolve()):
            raise LauncherError("derived secret path must be outside repository")
        if paths.state_file.resolve().is_relative_to(repository_root.resolve()):
            raise LauncherError("derived launch-state path must be outside repository")
        if paths.state_file.exists():
            raise LauncherError("case launch state already exists")
    except (LauncherError, OSError, subprocess.SubprocessError) as exc:
        _print(
            printer,
            "launcher_status=SECRET_HANDOFF_PRECHECK_BLOCKED",
            f"reason={type(exc).__name__}",
            "authorization_consumed=NO",
            "operator_live_invocation_count=0",
        )
        return 3

    if preflight_only:
        _print(
            printer,
            "launcher_status=PREFLIGHT_OK",
            "authorization_consumed=NO",
            "operator_live_invocation_count=0",
            "secret_accessed=NO",
            "child_spawned=NO",
        )
        return 0

    try:
        secret_root.mkdir(parents=True, exist_ok=True)
        _write_state_exclusive(
            paths.state_file,
            {
                "case_sha256": case.case_sha256,
                "repository_commit_oid": case.repository_commit_oid,
                "status": "RESERVED_NOT_CONSUMED",
            },
        )
        try:
            secret = _load_secret(paths.secret_file)
            _print(printer, "secret_handoff_ready=true")
            child_environment = dict(
                parent_environment if parent_environment is not None else os.environ
            )
            child_environment["STEAMDT_API_KEY"] = secret
            child_environment["STEAMDT_DRY_RUN"] = "false"
            _safe_unlink(paths.secret_file)
            argv = list(case.child_argv)
            try:
                process = popen_factory(
                    argv,
                    cwd=str(repository_root),
                    env=child_environment,
                    shell=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except Exception:
                child_environment.pop("STEAMDT_API_KEY", None)
                os.environ.pop("STEAMDT_API_KEY", None)
                del secret
                paths.state_file.unlink(missing_ok=True)
                _print(
                    printer,
                    "launcher_status=SPAWN_FAILED_NOT_CONSUMED",
                    "authorization_consumed=NO",
                    "operator_live_invocation_count=0",
                )
                return 3

            # Popen returned a process handle: authorization is now consumed.
            state_warning = ""
            try:
                _write_state(
                    paths.state_file,
                    {
                        "case_sha256": case.case_sha256,
                        "repository_commit_oid": case.repository_commit_oid,
                        "status": "CONSUMED",
                    },
                )
            except OSError:
                # The exclusive reservation file remains present and continues
                # to hard-block another launch for this case.
                state_warning = "CONSUMED_MARKER_UPDATE_FAILED_RESERVATION_RETAINED"
            child_environment.pop("STEAMDT_API_KEY", None)
            os.environ.pop("STEAMDT_API_KEY", None)
            try:
                stdout, stderr = process.communicate()
            except Exception as exc:
                del secret
                _print(
                    printer,
                    "launcher_status=CHILD_COMMUNICATION_FAILED",
                    "authorization_consumed=YES",
                    "operator_live_invocation_count=1",
                    f"reason={type(exc).__name__}",
                )
                if state_warning:
                    _print(printer, f"launch_state_warning={state_warning}")
                return 1
            return_code = process.returncode
            safe_stdout = redact_secret(stdout, secret)
            safe_stderr = redact_secret(stderr, secret)
            del secret
            _print(
                printer,
                "launcher_status=CHILD_COMPLETED",
                "authorization_consumed=YES",
                "operator_live_invocation_count=1",
                f"child_return_code={return_code}",
            )
            if state_warning:
                _print(printer, f"launch_state_warning={state_warning}")
            if safe_stdout:
                _print(printer, "child_stdout_begin", safe_stdout, "child_stdout_end")
            if safe_stderr:
                _print(printer, "child_stderr_begin", safe_stderr, "child_stderr_end")
            return int(return_code if return_code is not None else 1)
        except (LauncherError, OSError) as exc:
            paths.state_file.unlink(missing_ok=True)
            _print(
                printer,
                "secret_handoff_ready=false",
                "launcher_status=SECRET_HANDOFF_PRECHECK_BLOCKED",
                f"reason={type(exc).__name__}",
                "authorization_consumed=NO",
                "operator_live_invocation_count=0",
            )
            return 3
    except FileExistsError:
        _print(
            printer,
            "secret_handoff_ready=false",
            "launcher_status=SECRET_HANDOFF_PRECHECK_BLOCKED",
            "reason=CONSUMED_OR_RESERVED",
            "authorization_consumed=NO",
            "operator_live_invocation_count=0",
        )
        return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_recipe_first_authorized_once",
        description="Launch one explicitly authorized frozen recipe-first case",
    )
    parser.add_argument("--case-file", type=Path, required=True)
    parser.add_argument("--expected-case-sha256", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository_root = Path(__file__).resolve().parents[1]
    return run_authorized_once(
        case_file=args.case_file,
        expected_case_sha256=args.expected_case_sha256,
        preflight_only=args.preflight_only,
        repository_root=repository_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
