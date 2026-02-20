from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .git_ops import get_status, list_checkpoint_tags


@dataclass
class AuditResult:
    report_path: Path
    p0: int
    p1: int
    p2: int


def run_audit() -> AuditResult:
    required = [
        "AGENTS.md",
        "GUIDE.md",
        "state/STATE.md",
        "state/TASKS.yaml",
        "state/KEY_RESULTS.yaml",
    ]
    missing = [f for f in required if not Path(f).exists()]

    p0 = len(missing)
    p1 = 0
    p2 = 0

    status = get_status()
    tags = list_checkpoint_tags(limit=5)

    now = datetime.now().strftime("%Y%m%d-%H%M")
    report_path = Path("artifacts/audit") / f"{now}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Audit Report",
        "",
        "## Summary",
        f"- P0: {p0}",
        f"- P1: {p1}",
        f"- P2: {p2}",
        "",
        "## Repo Invariants Checks",
        f"- Missing required files: {missing if missing else 'none'}",
        "",
        "## Git Status",
        f"- Branch: {status.branch}",
        f"- HEAD: {status.head}",
        f"- Dirty files: {status.dirty_count}",
        f"- Recent checkpoints: {tags if tags else 'none'}",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return AuditResult(report_path=report_path, p0=p0, p1=p1, p2=p2)
