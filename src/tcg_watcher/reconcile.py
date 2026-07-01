from __future__ import annotations
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _key(snapshot: dict | None) -> datetime:
    last_run = (snapshot or {}).get("last_run")
    if not last_run:
        return _MIN
    return datetime.fromisoformat(last_run.replace("Z", "+00:00"))


def pick_newer(ours: dict | None, theirs: dict | None) -> dict | None:
    if ours is None:
        return theirs
    if theirs is None:
        return ours
    return theirs if _key(theirs) > _key(ours) else ours


def reconcile_files(
    state_dir: Path,
    read_theirs: Callable[[str], dict | None],
    list_theirs: Callable[[], list[str]],
) -> list[str]:
    state_dir = Path(state_dir)
    names = {p.name for p in state_dir.glob("*.json")} | set(list_theirs())
    changed: list[str] = []
    for name in sorted(names):
        path = state_dir / name
        ours = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        winner = pick_newer(ours, read_theirs(name))
        if winner is not None and winner is not ours:
            path.write_text(
                json.dumps(winner, indent=2, sort_keys=True, ensure_ascii=False),
                encoding="utf-8",
            )
            changed.append(name)
    return changed


def _git_show(ref_path: str) -> dict | None:
    result = subprocess.run(["git", "show", ref_path], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def _git_ls(state_dir: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-tree", "--name-only", "origin/main", f"{state_dir}/"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.rsplit("/", 1)[-1] for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    state_dir = Path(argv[0]) if argv else Path("state")
    sd = state_dir.as_posix()
    changed = reconcile_files(
        state_dir,
        lambda name: _git_show(f"origin/main:{sd}/{name}"),
        lambda: _git_ls(sd),
    )
    print("reconcile: took-origin=" + (",".join(changed) if changed else "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
