from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .git_ops import get_status, git_log_name_only, list_checkpoint_tag_details
from .schemas import format_issues, validate_key_results_data, validate_tasks_data
from .state_ops import read_yaml


@dataclass
class AuditIssue:
    severity: str  # P0, P1, P2
    category: str
    message: str
    suggestion: str


@dataclass
class AuditResult:
    report_path: Path
    p0: int
    p1: int
    p2: int
    issues: list[AuditIssue]


def _required_file_checks(root: Path) -> list[AuditIssue]:
    required = [
        "AGENTS.md",
        "GUIDE.md",
        "state/STATE.md",
        "state/PLAN.md",
        "state/TASKS.yaml",
        "state/REVIEW_QUEUE.yaml",
        "state/KEY_RESULTS.yaml",
        "state/DECISIONS.md",
        "state/CHECKPOINTS.md",
        "state/HUMAN_REVIEW_LOG.md",
        "docs/WORKFLOW.md",
        "docs/DATA_MODEL.md",
        "docs/GOVERNANCE.md",
        "prompts/planner.md",
        "prompts/auditor.md",
    ]
    issues: list[AuditIssue] = []
    for path in required:
        if not (root / path).exists():
            issues.append(
                AuditIssue(
                    severity="P0",
                    category="repo_invariants",
                    message=f"Missing required file: {path}",
                    suggestion=f"Create `{path}` and fill minimum required structure.",
                )
            )
    return issues


def _tasks_results_consistency(tasks_data: dict, results_data: dict) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    task_ids = {item.get("id") for item in tasks_data.get("tasks", []) if isinstance(item, dict)}

    for idx, kr in enumerate(results_data.get("results", [])):
        if not isinstance(kr, dict):
            issues.append(
                AuditIssue(
                    severity="P0",
                    category="task_result_consistency",
                    message=f"results[{idx}] is not a mapping",
                    suggestion="Fix KEY_RESULTS.yaml structure.",
                )
            )
            continue

        kr_id = kr.get("id", f"results[{idx}]")
        for task_id in kr.get("related_tasks", []):
            if task_id not in task_ids:
                issues.append(
                    AuditIssue(
                        severity="P1",
                        category="task_result_consistency",
                        message=f"{kr_id} references missing task {task_id}",
                        suggestion="Add missing task or remove stale relation from KEY_RESULTS.",
                    )
                )

    return issues


def _verification_coverage(results_data: dict) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for idx, kr in enumerate(results_data.get("results", [])):
        if not isinstance(kr, dict):
            continue
        kr_id = kr.get("id", f"results[{idx}]")
        verification = kr.get("verification", [])
        evidence = kr.get("evidence", [])
        status = kr.get("status")
        if status != "deprecated" and (not verification or not evidence):
            issues.append(
                AuditIssue(
                    severity="P0",
                    category="verification_coverage",
                    message=f"{kr_id} is missing verification or evidence.",
                    suggestion="Add executable checks and evidence links before marking as active.",
                )
            )
    return issues


def _guide_derivation_consistency(root: Path) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    guide = root / "GUIDE.md"
    if not guide.exists():
        return issues

    content = guide.read_text(encoding="utf-8")
    refs = set(re.findall(r"derivations/[A-Za-z0-9_./-]+", content))

    for ref in sorted(refs):
        path = root / ref
        if not path.exists():
            issues.append(
                AuditIssue(
                    severity="P1",
                    category="guide_derivation_consistency",
                    message=f"GUIDE references missing derivation asset: {ref}",
                    suggestion="Create referenced file or fix broken link in GUIDE.md.",
                )
            )
    return issues


def _group_counts(issues: Iterable[AuditIssue]) -> tuple[int, int, int]:
    p0 = p1 = p2 = 0
    for issue in issues:
        if issue.severity == "P0":
            p0 += 1
        elif issue.severity == "P1":
            p1 += 1
        else:
            p2 += 1
    return p0, p1, p2


def run_audit(cwd: str | Path | None = None) -> AuditResult:
    root = Path(cwd) if cwd else Path.cwd()
    issues: list[AuditIssue] = []
    issues.extend(_required_file_checks(root))

    tasks_data = read_yaml(root / "state" / "TASKS.yaml")
    results_data = read_yaml(root / "state" / "KEY_RESULTS.yaml")

    ok_tasks, task_issues = validate_tasks_data(tasks_data)
    if not ok_tasks:
        for item in format_issues(task_issues):
            issues.append(
                AuditIssue(
                    severity="P0",
                    category="tasks_schema",
                    message=f"{item['path']}: {item['message']}",
                    suggestion=item["suggestion"],
                )
            )

    ok_results, kr_issues = validate_key_results_data(results_data)
    if not ok_results:
        for item in format_issues(kr_issues):
            issues.append(
                AuditIssue(
                    severity="P0",
                    category="key_results_schema",
                    message=f"{item['path']}: {item['message']}",
                    suggestion=item["suggestion"],
                )
            )

    issues.extend(_tasks_results_consistency(tasks_data, results_data))
    issues.extend(_verification_coverage(results_data))
    issues.extend(_guide_derivation_consistency(root))

    p0, p1, p2 = _group_counts(issues)

    status = get_status(cwd=root)
    tag_details = list_checkpoint_tag_details(limit=5, cwd=root)
    recent_changes = git_log_name_only(limit=8, cwd=root)

    now = datetime.now().strftime("%Y%m%d-%H%M")
    report_path = root / "artifacts" / "audit" / f"{now}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Audit Report",
        "",
        "## Summary",
        f"- Time: {datetime.now().isoformat(timespec='seconds')}",
        f"- P0: {p0}",
        f"- P1: {p1}",
        f"- P2: {p2}",
        "",
        "## Repo invariants checks",
    ]

    required_issues = [i for i in issues if i.category == "repo_invariants"]
    if required_issues:
        for issue in required_issues:
            lines.append(f"- [{issue.severity}] {issue.message} | Fix: {issue.suggestion}")
    else:
        lines.append("- PASS: required files exist.")

    lines.extend(["", "## Task/Result consistency checks"])
    consistency = [i for i in issues if i.category in {"tasks_schema", "key_results_schema", "task_result_consistency"}]
    if consistency:
        for issue in consistency:
            lines.append(f"- [{issue.severity}] {issue.message} | Fix: {issue.suggestion}")
    else:
        lines.append("- PASS: TASKS and KEY_RESULTS schemas are valid and linked tasks exist.")

    lines.extend(["", "## Verification coverage"])
    coverage = [i for i in issues if i.category == "verification_coverage"]
    if coverage:
        for issue in coverage:
            lines.append(f"- [{issue.severity}] {issue.message} | Fix: {issue.suggestion}")
    else:
        lines.append("- PASS: all active key results include verification + evidence.")

    lines.extend(["", "## GUIDE/derivations consistency"])
    gd = [i for i in issues if i.category == "guide_derivation_consistency"]
    if gd:
        for issue in gd:
            lines.append(f"- [{issue.severity}] {issue.message} | Fix: {issue.suggestion}")
    else:
        lines.append("- PASS: GUIDE derivation references resolved.")

    lines.extend(["", "## Git status"])
    lines.extend(
        [
            f"- Branch: {status.branch}",
            f"- HEAD: {status.head}",
            f"- Dirty files: {status.dirty_count}",
        ]
    )
    if tag_details:
        lines.append("- Recent checkpoints:")
        for tag in tag_details:
            lines.append(f"  - {tag.tag} -> {tag.commit[:8]} ({tag.date_iso}) {tag.subject}")
    else:
        lines.append("- Recent checkpoints: none")

    lines.extend(["", "## Recent changes (git log --name-only)", "```text", recent_changes or "", "```", ""])

    lines.extend(["## Recommended next actions"])
    if p0 > 0:
        lines.append("- Fix all P0 findings before creating/updating checkpoints.")
    if p1 > 0:
        lines.append("- Address P1 findings before requesting human approval.")
    if p0 == 0 and p1 == 0:
        lines.append("- No blocking findings. Continue with verify + review queue sync.")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return AuditResult(report_path=report_path, p0=p0, p1=p1, p2=p2, issues=issues)
