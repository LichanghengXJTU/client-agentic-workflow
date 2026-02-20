from __future__ import annotations

import subprocess
from pathlib import Path

from workflow.audit import run_audit


REQUIRED_TEXT = [
    "## Summary",
    "## Repo invariants checks",
    "## Task/Result consistency checks",
    "## Verification coverage",
    "## Recent changes (git log --name-only)",
    "## Recommended next actions",
]


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)
    return proc.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    (repo / "state").mkdir()
    (repo / "docs").mkdir()
    (repo / "prompts").mkdir()
    (repo / "derivations").mkdir()

    (repo / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (repo / "GUIDE.md").write_text("# GUIDE\n", encoding="utf-8")
    (repo / "state" / "STATE.md").write_text("# STATE\n", encoding="utf-8")
    (repo / "state" / "PLAN.md").write_text("# PLAN\n", encoding="utf-8")
    (repo / "state" / "REVIEW_QUEUE.yaml").write_text("items: []\n", encoding="utf-8")
    (repo / "state" / "DECISIONS.md").write_text("# DECISIONS\n", encoding="utf-8")
    (repo / "state" / "CHECKPOINTS.md").write_text("# CHECKPOINTS\n", encoding="utf-8")
    (repo / "state" / "HUMAN_REVIEW_LOG.md").write_text("# LOG\n", encoding="utf-8")
    (repo / "docs" / "WORKFLOW.md").write_text("# WORKFLOW\n", encoding="utf-8")
    (repo / "docs" / "DATA_MODEL.md").write_text("# DATA_MODEL\n", encoding="utf-8")
    (repo / "docs" / "GOVERNANCE.md").write_text("# GOVERNANCE\n", encoding="utf-8")
    (repo / "prompts" / "planner.md").write_text("# planner\n", encoding="utf-8")
    (repo / "prompts" / "auditor.md").write_text("# auditor\n", encoding="utf-8")

    (repo / "state" / "TASKS.yaml").write_text(
        """tasks:
  - id: \"T-0001\"
    title: \"Task\"
    type: \"code\"
    priority: \"P0\"
    owner: \"codex\"
    status: \"todo\"
    acceptance: [\"ok\"]
    evidence: []
    verification: [\"pytest\"]
    depends_on: []
    created_at: \"2026-02-20\"
    updated_at: \"2026-02-20\"
""",
        encoding="utf-8",
    )

    (repo / "state" / "KEY_RESULTS.yaml").write_text(
        """results:
  - id: \"KR-0001\"
    statement: \"x=x\"
    status: \"verified\"
    confidence: \"high\"
    evidence: [\"GUIDE.md\"]
    verification: [\"python check.py\"]
    related_tasks: [\"T-0001\"]
    first_seen_commit: \"abc\"
    last_confirmed_commit: \"abc\"
    checkpoint_tags: []
""",
        encoding="utf-8",
    )

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    return repo


def test_audit_generates_structured_report(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    result = run_audit(cwd=repo)

    assert result.report_path.exists()
    content = result.report_path.read_text(encoding="utf-8")
    for marker in REQUIRED_TEXT:
        assert marker in content
