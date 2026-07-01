import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "commit_state.sh"

IDENT = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def _snap(last_run: str) -> str:
    return '{"seeded": true, "last_run": "%s", "variants": {}}\n' % last_run


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        env={**os.environ, **IDENT},
        capture_output=True,
        text=True,
        check=True,
    )


def _clone(origin: Path, dest: Path) -> None:
    subprocess.run(
        ["git", "clone", str(origin), str(dest)],
        env={**os.environ, **IDENT},
        capture_output=True,
        text=True,
        check=True,
    )


def _setup_origin(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(origin), "symbolic-ref", "HEAD", "refs/heads/main"],
        capture_output=True,
        check=True,
    )
    seed = tmp_path / "seed"
    _clone(origin, seed)
    _git(seed, "checkout", "-b", "main")
    (seed / "state").mkdir()
    (seed / "state" / "store.json").write_text(_snap("2026-07-01T00:00:00Z"))
    _git(seed, "add", "-A")
    _git(seed, "commit", "-m", "base")
    _git(seed, "push", "origin", "main")
    return origin


def _run_commit_state(runner: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=str(runner),
        env={**os.environ, **IDENT, "RECONCILE_CMD": "true"},
        capture_output=True,
        text=True,
    )


def _origin_has(origin: Path, ref_path: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(origin), "cat-file", "-e", ref_path],
            capture_output=True,
        ).returncode
        == 0
    )


def _origin_show(origin: Path, ref_path: str) -> str:
    return subprocess.run(
        ["git", "-C", str(origin), "show", ref_path],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_commit_state_preserves_concurrent_nonstate_push(tmp_path: Path):
    origin = _setup_origin(tmp_path)
    runner = tmp_path / "runner"
    _clone(origin, runner)

    human = tmp_path / "human"
    _clone(origin, human)
    (human / "docs").mkdir()
    (human / "docs" / "keep.md").write_text("important handoff\n")
    _git(human, "add", "-A")
    _git(human, "commit", "-m", "docs: add keep")
    _git(human, "push", "origin", "main")

    (runner / "state" / "store.json").write_text(_snap("2026-07-01T01:00:00Z"))
    result = _run_commit_state(runner)
    assert result.returncode == 0, result.stderr

    assert _origin_has(origin, "main:docs/keep.md"), "concurrent non-state push was clobbered"
    assert "2026-07-01T01:00:00Z" in _origin_show(origin, "main:state/store.json")


def test_commit_state_pushes_state_change_without_race(tmp_path: Path):
    origin = _setup_origin(tmp_path)
    runner = tmp_path / "runner"
    _clone(origin, runner)

    (runner / "state" / "store.json").write_text(_snap("2026-07-01T02:00:00Z"))
    result = _run_commit_state(runner)
    assert result.returncode == 0, result.stderr

    assert "2026-07-01T02:00:00Z" in _origin_show(origin, "main:state/store.json")
