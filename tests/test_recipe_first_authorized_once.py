"""Phase17D-R2 one-shot secret handoff launcher tests.

Every secret value is a local fake inside pytest's temporary directory. No
provider client or external process is created.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import run_recipe_first_authorized_once as launcher

FAKE_CASE_SHA_PREFIXED_KEY = "test-only-fake-steamdt-key"
HEAD = "a" * 40
BRANCH = "feature/phase17d-r2-secret-handoff-prelive-freeze"


class _Process:
    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str = "terminal_group=success\nlive_attempted=0\n",
        stderr: str = "",
    ) -> None:
        self.returncode: int | None = returncode
        self._stdout = stdout
        self._stderr = stderr

    def communicate(self) -> tuple[str, str]:
        return self._stdout, self._stderr


def _fake_git(argv: tuple[str, ...]) -> str:
    if argv == ("rev-parse", "HEAD"):
        return HEAD + "\n"
    if argv == ("rev-parse", "@{u}"):
        return HEAD + "\n"
    if argv == ("status", "--porcelain", "--untracked-files=no"):
        return ""
    if argv == ("branch", "--show-current"):
        return BRANCH + "\n"
    raise AssertionError(argv)


def _manifest_payload(*, repository_root: Path, artifact_root: Path) -> dict[str, object]:
    result_path = artifact_root / "phase17b_result.json"
    return {
        "schema_version": 1,
        "phase": "PHASE17D_R2_PRELIVE_CASE",
        "repository_commit_oid": HEAD,
        "branch": BRANCH,
        "child_argv": [
            "./.venv/Scripts/python.exe",
            "scripts/run_recipe_first_scan_once.py",
            "--enable-recipe-first",
            "--input-rarity",
            "Classified",
            "--stattrak-mode",
            "normal",
            "--collection",
            "The Phoenix Collection",
            "--max-family-states-considered",
            "1",
            "--max-prescreen-names",
            "20",
            "--max-prescreen-batch-dispatches",
            "2",
            "--max-targeted-buff-goods-ids",
            "10",
            "--max-final-valuation-requests",
            "2",
            "--max-recipe-candidates-returned",
            "1",
            "--max-candidate-states-explored",
            "256",
            "--cache-backend",
            "inmemory",
            "--output-format",
            "json",
            "--artifact-dir",
            artifact_root.as_posix(),
        ],
        "result_artifact": {
            "path": result_path.as_posix(),
            "filename": result_path.name,
        },
        "secret_path_rule": launcher.SECRET_PATH_RULE,
        "operator_contract": {
            "id": launcher.OPERATOR_CONTRACT_ID,
            "path": launcher.OPERATOR_CONTRACT_PATH,
        },
    }


def _write_case(
    tmp_path: Path,
    *,
    payload: dict[str, object] | None = None,
) -> tuple[Path, str, dict[str, object]]:
    repository_root = tmp_path / "repo"
    repository_root.mkdir(exist_ok=True)
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir(exist_ok=True)
    case_payload = payload or _manifest_payload(
        repository_root=repository_root,
        artifact_root=artifact_root,
    )
    raw = launcher._canonical_json_bytes(case_payload)
    case_file = tmp_path / "case.json"
    case_file.write_bytes(raw)
    return case_file, launcher._sha256(raw), case_payload


def _run(
    tmp_path: Path,
    *,
    expected_sha: str | None = None,
    preflight_only: bool = False,
    popen_factory=None,
    create_secret: bool = False,
    secret_value: str = FAKE_CASE_SHA_PREFIXED_KEY,
    payload: dict[str, object] | None = None,
) -> tuple[int, list[str], Path, str, Path, dict[str, object]]:
    case_file, case_sha, case_payload = _write_case(tmp_path, payload=payload)
    secret_root = tmp_path / "secret-root"
    paths = launcher.derive_launch_paths(case_sha, secret_root=secret_root)
    if create_secret:
        secret_root.mkdir(parents=True, exist_ok=True)
        paths.secret_file.write_text(secret_value, encoding="utf-8")
    output: list[str] = []
    kwargs: dict[str, Any] = {
        "case_file": case_file,
        "expected_case_sha256": expected_sha or case_sha,
        "preflight_only": preflight_only,
        "repository_root": tmp_path / "repo",
        "secret_root": secret_root,
        "run_git": _fake_git,
        "parent_environment": {"SAFE": "1"},
        "printer": output.append,
    }
    if popen_factory is not None:
        kwargs["popen_factory"] = popen_factory
    rc = launcher.run_authorized_once(**kwargs)
    return rc, output, paths.secret_file, case_sha, paths.state_file, case_payload


def test_wrong_case_sha_blocks_without_secret_or_spawn(tmp_path: Path) -> None:
    calls = 0

    def popen(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _Process()

    rc, output, _secret, _sha, state, _payload = _run(
        tmp_path,
        expected_sha="0" * 64,
        popen_factory=popen,
    )
    assert rc == 3
    assert calls == 0
    assert not state.exists()
    assert "authorization_consumed=NO" in output


def test_wrong_bound_commit_blocks(tmp_path: Path) -> None:
    payload = _manifest_payload(
        repository_root=tmp_path / "repo",
        artifact_root=tmp_path / "artifact",
    )
    payload["repository_commit_oid"] = "b" * 40
    rc, output, *_ = _run(tmp_path, payload=payload)
    assert rc == 3
    assert "authorization_consumed=NO" in output


def test_preflight_only_reads_no_secret_and_spawns_no_child(tmp_path: Path) -> None:
    calls = 0

    def popen(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _Process()

    rc, output, secret, _sha, state, _payload = _run(
        tmp_path,
        preflight_only=True,
        popen_factory=popen,
        create_secret=False,
    )
    assert rc == 0
    assert calls == 0
    assert not secret.exists()
    assert not state.exists()
    assert "secret_accessed=NO" in output
    assert "child_spawned=NO" in output


def test_secret_and_state_paths_are_case_bound() -> None:
    digest = "0123456789abcdef" + "0" * 48
    paths = launcher.derive_launch_paths(digest)
    assert paths.secret_file.name == "steamdt_0123456789abcdef.once"
    assert paths.state_file.name == "steamdt_0123456789abcdef.launch-state.json"


def test_parser_accepts_no_arbitrary_secret_path() -> None:
    parser = launcher.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--case-file",
                "case.json",
                "--expected-case-sha256",
                "0" * 64,
                "--secret-file",
                "arbitrary",
            ]
        )


@pytest.mark.parametrize(
    "content",
    ["", " "],
)
def test_empty_or_noncanonical_secret_blocks_before_spawn(
    tmp_path: Path,
    content: str,
) -> None:
    case_file, case_sha, _payload = _write_case(tmp_path)
    secret_root = tmp_path / "secret-root"
    paths = launcher.derive_launch_paths(case_sha, secret_root=secret_root)
    secret_root.mkdir(parents=True)
    paths.secret_file.write_text(content, encoding="utf-8")
    calls = 0

    def popen(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _Process()

    output: list[str] = []
    rc = launcher.run_authorized_once(
        case_file=case_file,
        expected_case_sha256=case_sha,
        preflight_only=False,
        repository_root=tmp_path / "repo",
        secret_root=secret_root,
        run_git=_fake_git,
        popen_factory=popen,
        parent_environment={"SAFE": "1"},
        printer=output.append,
    )
    assert rc == 3
    assert calls == 0
    assert "secret_handoff_ready=false" in output
    assert "authorization_consumed=NO" in output


def test_oversize_secret_blocks_before_spawn(tmp_path: Path) -> None:
    case_file, case_sha, _payload = _write_case(tmp_path)
    secret_root = tmp_path / "secret-root"
    paths = launcher.derive_launch_paths(case_sha, secret_root=secret_root)
    secret_root.mkdir(parents=True)
    paths.secret_file.write_text(
        "x" * (launcher.SECRET_FILE_MAX_BYTES + 1),
        encoding="utf-8",
    )
    calls = 0

    def popen(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _Process()

    rc = launcher.run_authorized_once(
        case_file=case_file,
        expected_case_sha256=case_sha,
        preflight_only=False,
        repository_root=tmp_path / "repo",
        secret_root=secret_root,
        run_git=_fake_git,
        popen_factory=popen,
        parent_environment={"SAFE": "1"},
        printer=lambda _line: None,
    )
    assert rc == 3
    assert calls == 0


def test_secret_unlinked_before_popen_and_never_in_argv(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def popen(argv, **kwargs):
        captured["argv"] = tuple(argv)
        captured["shell"] = kwargs["shell"]
        captured["env"] = dict(kwargs["env"])
        case_sha = captured["case_sha"]
        secret_path = launcher.derive_launch_paths(
            case_sha, secret_root=tmp_path / "secret-root"
        ).secret_file
        assert not secret_path.exists()
        return _Process()

    case_file, case_sha, _payload = _write_case(tmp_path)
    captured["case_sha"] = case_sha
    secret_root = tmp_path / "secret-root"
    paths = launcher.derive_launch_paths(case_sha, secret_root=secret_root)
    secret_root.mkdir(parents=True)
    paths.secret_file.write_text(FAKE_CASE_SHA_PREFIXED_KEY, encoding="utf-8")
    output: list[str] = []
    rc = launcher.run_authorized_once(
        case_file=case_file,
        expected_case_sha256=case_sha,
        preflight_only=False,
        repository_root=tmp_path / "repo",
        secret_root=secret_root,
        run_git=_fake_git,
        popen_factory=popen,
        parent_environment={"SAFE": "1"},
        printer=output.append,
    )
    assert rc == 0
    assert FAKE_CASE_SHA_PREFIXED_KEY not in captured["argv"]
    assert captured["shell"] is False
    assert captured["env"]["STEAMDT_API_KEY"] == FAKE_CASE_SHA_PREFIXED_KEY
    assert captured["env"]["STEAMDT_DRY_RUN"] == "false"
    assert "secret_handoff_ready=true" in output


def test_popen_failure_is_not_consumed_and_not_retried(tmp_path: Path) -> None:
    calls = 0

    def popen(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise OSError("offline spawn failure")

    rc, output, secret, _sha, state, _payload = _run(
        tmp_path,
        create_secret=True,
        popen_factory=popen,
    )
    assert rc == 3
    assert calls == 1
    assert not secret.exists()
    assert not state.exists()
    assert "authorization_consumed=NO" in output
    assert "operator_live_invocation_count=0" in output


def test_successful_popen_marks_consumed_and_preserves_child_code(
    tmp_path: Path,
) -> None:
    calls = 0

    def popen(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _Process(returncode=7, stdout="live_attempted=0\n")

    rc, output, secret, _sha, state, _payload = _run(
        tmp_path,
        create_secret=True,
        popen_factory=popen,
    )
    assert rc == 7
    assert calls == 1
    assert not secret.exists()
    assert json.loads(state.read_text(encoding="utf-8"))["status"] == "CONSUMED"
    assert "authorization_consumed=YES" in output
    assert "operator_live_invocation_count=1" in output
    assert "child_return_code=7" in output
    assert any("live_attempted=0" in line for line in output)


def test_consumed_marker_blocks_second_launch(tmp_path: Path) -> None:
    calls = 0

    def popen(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _Process()

    first = _run(tmp_path, create_secret=True, popen_factory=popen)
    assert first[0] == 0
    first[2].write_text(FAKE_CASE_SHA_PREFIXED_KEY, encoding="utf-8")
    second_output: list[str] = []
    second_rc = launcher.run_authorized_once(
        case_file=tmp_path / "case.json",
        expected_case_sha256=first[3],
        preflight_only=False,
        repository_root=tmp_path / "repo",
        secret_root=tmp_path / "secret-root",
        run_git=_fake_git,
        popen_factory=popen,
        parent_environment={"SAFE": "1"},
        printer=second_output.append,
    )
    assert second_rc == 3
    assert calls == 1
    assert "authorization_consumed=NO" in second_output


def test_stdout_and_stderr_are_secret_redacted(tmp_path: Path) -> None:
    def popen(*args, **kwargs):
        return _Process(
            stdout=f"value={FAKE_CASE_SHA_PREFIXED_KEY}",
            stderr=f"error={FAKE_CASE_SHA_PREFIXED_KEY}",
        )

    rc, output, *_ = _run(
        tmp_path,
        create_secret=True,
        popen_factory=popen,
    )
    assert rc == 0
    rendered = "\n".join(output)
    assert FAKE_CASE_SHA_PREFIXED_KEY not in rendered
    assert rendered.count("[REDACTED]") == 2


def test_secret_unlink_failure_blocks_before_spawn(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    def popen(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _Process()

    def fail_unlink(path: Path) -> None:
        raise launcher.LauncherError("unlink failure")

    monkeypatch.setattr(launcher, "_safe_unlink", fail_unlink)
    rc, output, *_ = _run(
        tmp_path,
        create_secret=True,
        popen_factory=popen,
    )
    assert rc == 3
    assert calls == 0
    assert "authorization_consumed=NO" in output


def test_child_argv_is_manifest_exact_and_shell_false(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def popen(argv, **kwargs):
        captured["argv"] = tuple(argv)
        captured["shell"] = kwargs["shell"]
        return _Process()

    rc, _output, _secret, _sha, _state, payload = _run(
        tmp_path,
        create_secret=True,
        popen_factory=popen,
    )
    assert rc == 0
    assert captured["argv"] == tuple(payload["child_argv"])
    assert captured["shell"] is False
