from __future__ import annotations

import subprocess
from pathlib import Path

from workflow.checkpoint import create_checkpoint
from workflow.rollback import HARD_CONFIRM_PHRASE, hard_rollback, safe_rollback


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)
    return proc.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")
    return repo


def test_checkpoint_creates_tag_and_state_record(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "state").mkdir()
    (repo / "state" / "CHECKPOINTS.md").write_text(
        "# CHECKPOINTS\n\n| Time | Tag | Commit | Summary | Related Key Results |\n|---|---|---|---|---|\n",
        encoding="utf-8",
    )
    (repo / "state" / "STATE.md").write_text("# STATE Snapshot\n", encoding="utf-8")
    (repo / "state" / "KEY_RESULTS.yaml").write_text("results: []\n", encoding="utf-8")

    (repo / "x.txt").write_text("x\n", encoding="utf-8")
    result = create_checkpoint(summary="phase-c", cwd=repo)

    tags = _git(repo, "tag", "--list", "cp-*")
    assert result.tag in tags
    assert result.snapshot_commit
    checkpoints_md = (repo / "state" / "CHECKPOINTS.md").read_text(encoding="utf-8")
    assert result.tag in checkpoints_md


def test_safe_rollback_reverts_commits(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    base = _git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("1\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "add a")
    (repo / "b.txt").write_text("2\n", encoding="utf-8")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-m", "add b")

    result = safe_rollback(anchor_ref=base, cwd=repo)

    branch = _git(repo, "branch", "--show-current")
    assert branch == result.branch
    assert result.reverted_count == 2
    log = _git(repo, "log", "--oneline", "-n", "5")
    assert "Revert \"add b\"" in log


def test_hard_rollback_requires_phrase(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    try:
        hard_rollback(anchor_ref="HEAD", confirm_phrase="NOPE", cwd=repo)
    except ValueError as exc:
        assert HARD_CONFIRM_PHRASE in str(exc)
    else:
        raise AssertionError("hard rollback should reject incorrect phrase")
