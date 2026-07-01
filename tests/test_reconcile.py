import json
import subprocess
from pathlib import Path

import pytest

from tcg_watcher.reconcile import pick_newer, reconcile_files, _git_show


def snap(last_run, variants=None, seeded=True):
    return {"seeded": seeded, "last_run": last_run, "variants": variants or {}}


def _write(p, obj):
    p.write_text(json.dumps(obj))


def test_ours_newer_keeps_ours():
    ours = snap("2026-07-01T16:05:00Z", {"v1": {"price": 1}})
    theirs = snap("2026-07-01T16:00:00Z", {"v1": {"price": 2}})
    assert pick_newer(ours, theirs) is ours


def test_theirs_newer_keeps_theirs():
    ours = snap("2026-07-01T16:00:00Z")
    theirs = snap("2026-07-01T16:05:00Z")
    assert pick_newer(ours, theirs) is theirs


def test_theirs_missing_keeps_ours():
    ours = snap("2026-07-01T16:00:00Z")
    assert pick_newer(ours, None) is ours


def test_ours_missing_takes_theirs():
    theirs = snap("2026-07-01T16:00:00Z", {"v1": {"price": 1}})
    assert pick_newer(None, theirs) is theirs


def test_ours_unseeded_keeps_theirs():
    ours = {"seeded": False, "last_run": None, "variants": {}}
    theirs = snap("2026-07-01T16:00:00Z", {"v1": {"price": 1}})
    assert pick_newer(ours, theirs) is theirs


def test_equal_last_run_keeps_ours():
    ours = snap("2026-07-01T16:00:00Z", {"a": 1})
    theirs = snap("2026-07-01T16:00:00Z", {"b": 2})
    assert pick_newer(ours, theirs) is ours


def test_reconcile_files_takes_newer_per_file(tmp_path: Path):
    _write(tmp_path / "a.json", snap("2026-07-01T16:05:00Z", {"x": 1}))
    _write(tmp_path / "b.json", snap("2026-07-01T16:00:00Z", {"y": 1}))
    theirs = {
        "a.json": snap("2026-07-01T16:00:00Z", {"x": 0}),
        "b.json": snap("2026-07-01T16:05:00Z", {"y": 9}),
    }
    changed = reconcile_files(tmp_path, lambda n: theirs.get(n), lambda: list(theirs))
    assert changed == ["b.json"]
    assert json.loads((tmp_path / "a.json").read_text())["variants"] == {"x": 1}
    assert json.loads((tmp_path / "b.json").read_text())["variants"] == {"y": 9}


def test_reconcile_files_theirs_missing_leaves_ours(tmp_path: Path):
    _write(tmp_path / "a.json", snap("2026-07-01T16:00:00Z", {"x": 1}))
    changed = reconcile_files(tmp_path, lambda n: None, lambda: [])
    assert changed == []
    assert json.loads((tmp_path / "a.json").read_text())["variants"] == {"x": 1}


def test_reconcile_files_materializes_origin_only_file(tmp_path: Path):
    _write(tmp_path / "a.json", snap("2026-07-01T16:00:00Z", {"x": 1}))
    theirs = {
        "a.json": snap("2026-07-01T16:00:00Z", {"x": 1}),
        "c.json": snap("2026-07-01T16:00:00Z", {"z": 7}),
    }
    changed = reconcile_files(tmp_path, lambda n: theirs.get(n), lambda: list(theirs))
    assert changed == ["c.json"]
    assert (tmp_path / "c.json").exists()
    assert json.loads((tmp_path / "c.json").read_text())["variants"] == {"z": 7}
    assert json.loads((tmp_path / "a.json").read_text())["variants"] == {"x": 1}


def test_reconcile_files_keeps_worktree_only_file(tmp_path: Path):
    _write(tmp_path / "a.json", snap("2026-07-01T16:00:00Z", {"x": 1}))
    changed = reconcile_files(tmp_path, lambda n: None, lambda: [])
    assert changed == []
    assert (tmp_path / "a.json").exists()


def _fake_run(returncode, stdout="", stderr=""):
    def run(cmd, capture_output=True, text=True):
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
    return run


def test_git_show_success_parses_json(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(0, stdout='{"seeded": true}'))
    assert _git_show("origin/main:state/a.json") == {"seeded": True}


def test_git_show_missing_path_returns_none(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        _fake_run(128, stderr="fatal: path 'state/a.json' does not exist in 'origin/main'"),
    )
    assert _git_show("origin/main:state/a.json") is None


def test_git_show_missing_on_disk_returns_none(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        _fake_run(128, stderr="fatal: path 'state/a.json' exists on disk, but not in 'origin/main'"),
    )
    assert _git_show("origin/main:state/a.json") is None


def test_git_show_transient_failure_raises(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        _fake_run(128, stderr="fatal: unable to access remote: Could not resolve host"),
    )
    with pytest.raises(RuntimeError):
        _git_show("origin/main:state/a.json")


def test_git_show_nonzero_non128_raises(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run(1, stderr="some other error"))
    with pytest.raises(RuntimeError):
        _git_show("origin/main:state/a.json")
