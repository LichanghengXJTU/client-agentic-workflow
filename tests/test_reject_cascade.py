from __future__ import annotations

import subprocess
from pathlib import Path

from workflow.review_ops import apply_review_action
from workflow.state_ops import load_key_results, load_tasks


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)
    return proc.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    (repo / "f.txt").write_text("0\n", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")

    (repo / "f.txt").write_text("1\n", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-m", "c1")
    (repo / "g.txt").write_text("2\n", encoding="utf-8")
    _git(repo, "add", "g.txt")
    _git(repo, "commit", "-m", "c2")

    (repo / "state").mkdir()
    (repo / "state" / "TASKS.yaml").write_text(
        """tasks:
  - id: "T-0001"
    title: "Root"
    type: "code"
    priority: "P0"
    owner: "codex"
    status: "waiting_review"
    acceptance: ["ok"]
    evidence: []
    verification: []
    depends_on: []
    created_at: "2026-02-20"
    updated_at: "2026-02-20"
  - id: "T-0002"
    title: "Child"
    type: "code"
    priority: "P1"
    owner: "codex"
    status: "done"
    acceptance: ["ok"]
    evidence: []
    verification: []
    depends_on: ["T-0001"]
    created_at: "2026-02-20"
    updated_at: "2026-02-20"
""",
        encoding="utf-8",
    )
    (repo / "state" / "REVIEW_QUEUE.yaml").write_text(
        """items:
  - id: "RQ-0001"
    task_id: "T-0001"
    title: "Root"
    status: "pending"
    created_at: "2026-02-20"
    updated_at: "2026-02-20"
""",
        encoding="utf-8",
    )
    (repo / "state" / "KEY_RESULTS.yaml").write_text(
        """results:
  - id: "KR-0001"
    statement: "Something"
    status: "verified"
    confidence: "high"
    evidence: ["GUIDE.md"]
    verification: ["pytest"]
    related_tasks: ["T-0001"]
    first_seen_commit: "TBD"
    last_confirmed_commit: "TBD"
    checkpoint_tags: []
""",
        encoding="utf-8",
    )
    (repo / "state" / "HUMAN_REVIEW_LOG.md").write_text(
        "# HUMAN REVIEW LOG\n\n| Time | Reviewer | Item | Action | Notes |\n|---|---|---|---|---|\n",
        encoding="utf-8",
    )
    (repo / "state" / "STATE.md").write_text("# STATE\n", encoding="utf-8")

    return repo, base


def test_reject_cascade_resets_tasks_and_rolls_back(tmp_path: Path, monkeypatch) -> None:
    repo, base = _init_repo(tmp_path)
    monkeypatch.chdir(repo)

    result = apply_review_action(
        review_id="RQ-0001",
        reviewer="human",
        action="Reject",
        notes="incorrect",
        anchor=base,
        cwd=repo,
    )

    assert result.rollback_branch and result.rollback_branch.startswith("rollback/")
    assert result.reverted_count == 2

    tasks = load_tasks()
    by_id = {item["id"]: item for item in tasks}
    assert by_id["T-0001"]["status"] == "blocked"
    assert by_id["T-0002"]["status"] == "todo"

    results = load_key_results()
    assert results[0]["status"] == "proposed"
