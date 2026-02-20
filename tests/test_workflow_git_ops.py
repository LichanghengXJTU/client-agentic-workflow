from __future__ import annotations

import subprocess
from pathlib import Path

from workflow.git_ops import get_status, git_log_name_only, list_checkpoint_tags


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)
    return proc.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "f.txt").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-m", "init")
    return repo


def test_get_status_and_dirty_detection(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    status = get_status(cwd=repo)
    assert status.branch == "main"
    assert status.dirty_count == 0

    (repo / "f.txt").write_text("changed\n", encoding="utf-8")
    status2 = get_status(cwd=repo)
    assert status2.is_dirty
    assert status2.dirty_count >= 1


def test_list_checkpoint_tags(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "tag", "-a", "cp-20260220-1200-demo", head, "-m", "demo")

    tags = list_checkpoint_tags(cwd=repo)
    assert "cp-20260220-1200-demo" in tags


def test_git_log_name_only(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    out = git_log_name_only(limit=1, cwd=repo)
    assert "init" in out
    assert "f.txt" in out
