from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .citation_ops import validate_cite
from .git_ops import get_status, git_log_name_only, list_checkpoint_tag_details
from .schemas import (
    format_issues,
    validate_kb_manifest_data,
    validate_key_results_data,
    validate_project_registry_data,
    validate_tasks_data,
)
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
        "state/PROJECT_REGISTRY.yaml",
        "state/KB_CONFIG.yaml",
        "state/KB_MANIFEST.yaml",
        "state/DECISIONS.md",
        "state/CHECKPOINTS.md",
        "state/HUMAN_REVIEW_LOG.md",
        "docs/WORKFLOW.md",
        "docs/TASK_WORKFLOW.md",
        "docs/KB_WORKFLOW.md",
        "docs/DATA_MODEL.md",
        "docs/GOVERNANCE.md",
        "prompts/planner.md",
        "prompts/auditor.md",
        "prompts/retriever.md",
        "prompts/implementer.md",
        "prompts/scribe.md",
        "prompts/critic.md",
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


def _task_artifact_presence(root: Path, tasks_data: dict) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    task_root = root / "state" / "tasks"
    if not task_root.exists():
        return issues

    required = ["brief.yaml", "worklog.md", "evidence_map.yaml"]
    active_status = {"in_progress", "waiting_review", "done"}
    for task in tasks_data.get("tasks", []):
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id", "")).strip()
        if not task_id or task.get("status") not in active_status:
            continue
        task_dir = task_root / task_id
        if not task_dir.exists():
            continue
        for name in required:
            if not (task_dir / name).exists():
                issues.append(
                    AuditIssue(
                        severity="P1",
                        category="task_artifact_presence",
                        message=f"{task_id} missing task artifact `{name}`.",
                        suggestion=f"Create state/tasks/{task_id}/{name}.",
                    )
                )
    return issues


def _evidence_map_schema(root: Path) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    task_root = root / "state" / "tasks"
    if not task_root.exists():
        return issues

    for task_dir in sorted(path for path in task_root.iterdir() if path.is_dir()):
        path = task_dir / "evidence_map.yaml"
        if not path.exists():
            continue
        data = read_yaml(path)
        claims = data.get("claims")
        if not isinstance(claims, list):
            issues.append(
                AuditIssue(
                    severity="P0",
                    category="evidence_map_schema",
                    message=f"{path.as_posix()} has non-list `claims`.",
                    suggestion="Set claims as YAML list.",
                )
            )
            continue

        run_index = read_yaml(task_dir / "run_index.yaml")
        known_runs = {
            str(item.get("run_id"))
            for item in run_index.get("runs", [])
            if isinstance(item, dict) and item.get("run_id")
        }
        seen_claim_ids: set[str] = set()
        for idx, claim in enumerate(claims):
            base = f"{path.as_posix()}::claims[{idx}]"
            if not isinstance(claim, dict):
                issues.append(
                    AuditIssue(
                        severity="P0",
                        category="evidence_map_schema",
                        message=f"{base} is not a mapping.",
                        suggestion="Rewrite claim as mapping.",
                    )
                )
                continue
            claim_id = claim.get("claim_id")
            if not isinstance(claim_id, str) or not claim_id.strip():
                issues.append(
                    AuditIssue(
                        severity="P0",
                        category="evidence_map_schema",
                        message=f"{base}.claim_id missing.",
                        suggestion="Set non-empty claim_id.",
                    )
                )
            elif claim_id in seen_claim_ids:
                issues.append(
                    AuditIssue(
                        severity="P0",
                        category="evidence_map_schema",
                        message=f"{base}.claim_id duplicate: {claim_id}",
                        suggestion="Ensure claim_id uniqueness in one evidence_map.",
                    )
                )
            else:
                seen_claim_ids.add(claim_id)

            confidence = claim.get("confidence")
            if confidence not in {"low", "medium", "high"}:
                issues.append(
                    AuditIssue(
                        severity="P0",
                        category="evidence_map_schema",
                        message=f"{base}.confidence invalid.",
                        suggestion="Use low/medium/high.",
                    )
                )
            status = claim.get("status")
            if status not in {"proposed", "verified", "rejected"}:
                issues.append(
                    AuditIssue(
                        severity="P0",
                        category="evidence_map_schema",
                        message=f"{base}.status invalid.",
                        suggestion="Use proposed/verified/rejected.",
                    )
                )

            verifications = claim.get("verification", [])
            if not isinstance(verifications, list):
                issues.append(
                    AuditIssue(
                        severity="P0",
                        category="evidence_map_schema",
                        message=f"{base}.verification must be list.",
                        suggestion="Use YAML list with command/run_id entries.",
                    )
                )
            else:
                for vidx, verification in enumerate(verifications):
                    if not isinstance(verification, dict):
                        issues.append(
                            AuditIssue(
                                severity="P0",
                                category="evidence_map_schema",
                                message=f"{base}.verification[{vidx}] is not mapping.",
                                suggestion="Set verification entry as mapping.",
                            )
                        )
                        continue
                    run_id = verification.get("run_id")
                    if isinstance(run_id, str) and run_id and run_id not in known_runs:
                        issues.append(
                            AuditIssue(
                                severity="P0",
                                category="evidence_map_schema",
                                message=f"{base}.verification[{vidx}] references missing run_id {run_id}.",
                                suggestion="Record run first or fix run_id.",
                            )
                        )
    return issues


def _citation_validity(root: Path) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    task_root = root / "state" / "tasks"
    if not task_root.exists():
        return issues
    for evidence_path in sorted(task_root.glob("*/evidence_map.yaml")):
        data = read_yaml(evidence_path)
        for idx, claim in enumerate(data.get("claims", [])):
            if not isinstance(claim, dict):
                continue
            evidence_list = claim.get("evidence", [])
            if not isinstance(evidence_list, list):
                continue
            for eidx, ev in enumerate(evidence_list):
                if not isinstance(ev, dict):
                    continue
                cite = ev.get("cite")
                if not isinstance(cite, str) or not cite.strip():
                    continue
                ok, msg = validate_cite(cite, source_sha256=ev.get("source_sha256"), cwd=root)
                if not ok:
                    issues.append(
                        AuditIssue(
                            severity="P0",
                            category="citation_validity",
                            message=f"{evidence_path.as_posix()} claims[{idx}] evidence[{eidx}] invalid cite: {msg}",
                            suggestion="Fix cite to valid path+line and matching sha256.",
                        )
                    )
    return issues


def _handoff_integrity(root: Path) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    task_root = root / "state" / "tasks"
    if not task_root.exists():
        return issues
    for handoff_path in sorted(task_root.glob("*/handoff.yaml")):
        data = read_yaml(handoff_path)
        handoffs = data.get("handoffs", [])
        if not isinstance(handoffs, list):
            issues.append(
                AuditIssue(
                    severity="P1",
                    category="handoff_integrity",
                    message=f"{handoff_path.as_posix()} has non-list `handoffs`.",
                    suggestion="Set handoffs as list of role transitions.",
                )
            )
            continue
        for idx, item in enumerate(handoffs):
            if not isinstance(item, dict):
                issues.append(
                    AuditIssue(
                        severity="P1",
                        category="handoff_integrity",
                        message=f"{handoff_path.as_posix()} handoffs[{idx}] is not mapping.",
                        suggestion="Rewrite handoff entry as mapping.",
                    )
                )
                continue
            for key in ["from_role", "to_role", "status"]:
                value = item.get(key)
                if not isinstance(value, str) or not value.strip():
                    issues.append(
                        AuditIssue(
                            severity="P1",
                            category="handoff_integrity",
                            message=f"{handoff_path.as_posix()} handoffs[{idx}] missing `{key}`.",
                            suggestion=f"Set handoffs[{idx}].{key}.",
                        )
                    )
            if item.get("status") == "accepted" and not item.get("accepted_at"):
                issues.append(
                    AuditIssue(
                        severity="P1",
                        category="handoff_integrity",
                        message=f"{handoff_path.as_posix()} handoffs[{idx}] accepted but missing accepted_at.",
                        suggestion="Set accepted_at timestamp.",
                    )
                )
    return issues


def _run_meta_completeness(root: Path) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for run_meta_path in sorted((root / "artifacts" / "tasks").glob("*/runs/*/run_meta.yaml")):
        data = read_yaml(run_meta_path)
        required = [
            "run_id",
            "task_id",
            "role",
            "started_at",
            "ended_at",
            "command",
            "args",
            "workdir",
            "environment",
            "seed",
            "inputs",
            "outputs",
            "exit_code",
            "logs",
        ]
        for key in required:
            if key not in data:
                issues.append(
                    AuditIssue(
                        severity="P1",
                        category="run_meta_completeness",
                        message=f"{run_meta_path.as_posix()} missing `{key}`.",
                        suggestion=f"Add `{key}` to run_meta.",
                    )
                )
        logs = data.get("logs", {})
        if isinstance(logs, dict):
            for key in ["stdout", "stderr"]:
                value = logs.get(key)
                if isinstance(value, str) and value:
                    if not (root / value).exists():
                        issues.append(
                            AuditIssue(
                                severity="P1",
                                category="run_meta_completeness",
                                message=f"{run_meta_path.as_posix()} log path missing: {value}",
                                suggestion="Create log file or correct path.",
                            )
                        )
    return issues


def _kb_manifest_quality(root: Path) -> list[AuditIssue]:
    path = root / "state" / "KB_MANIFEST.yaml"
    if not path.exists():
        return []
    data = read_yaml(path)
    ok, manifest_issues = validate_kb_manifest_data(data)
    if ok:
        return []
    issues: list[AuditIssue] = []
    for item in format_issues(manifest_issues):
        issues.append(
            AuditIssue(
                severity="P1",
                category="kb_manifest_quality",
                message=f"{item['path']}: {item['message']}",
                suggestion=item["suggestion"],
            )
        )
    return issues


def _secret_path_guard(root: Path, tasks_data: dict, results_data: dict, kb_manifest: dict) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    banned_fragment = "state/AI_SECRETS.local.yaml#L"
    for task in tasks_data.get("tasks", []):
        if not isinstance(task, dict):
            continue
        for ev in task.get("evidence", []):
            if isinstance(ev, str) and banned_fragment in ev:
                issues.append(
                    AuditIssue(
                        severity="P0",
                        category="secret_path_guard",
                        message=f"{task.get('id')}: evidence points to secret content lines.",
                        suggestion="Only allow existence-level reference without line-level secret citation.",
                    )
                )

    for kr in results_data.get("results", []):
        if not isinstance(kr, dict):
            continue
        for ev in kr.get("evidence", []):
            if isinstance(ev, str) and banned_fragment in ev:
                issues.append(
                    AuditIssue(
                        severity="P0",
                        category="secret_path_guard",
                        message=f"{kr.get('id')}: evidence points to secret content lines.",
                        suggestion="Remove line-level citation for AI_SECRETS.local.yaml.",
                    )
                )

    for doc in kb_manifest.get("documents", []):
        if not isinstance(doc, dict):
            continue
        src = doc.get("source_uri", "")
        if isinstance(src, str) and banned_fragment in src:
            issues.append(
                AuditIssue(
                    severity="P0",
                    category="secret_path_guard",
                    message=f"{doc.get('doc_id')}: KB source_uri references secret content lines.",
                    suggestion="Do not ingest line-level secret content citations.",
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
    projects_data = read_yaml(root / "state" / "PROJECT_REGISTRY.yaml")
    kb_manifest_data = read_yaml(root / "state" / "KB_MANIFEST.yaml")

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

    ok_projects, project_issues = validate_project_registry_data(projects_data)
    if not ok_projects:
        for item in format_issues(project_issues):
            issues.append(
                AuditIssue(
                    severity="P0",
                    category="project_registry_schema",
                    message=f"{item['path']}: {item['message']}",
                    suggestion=item["suggestion"],
                )
            )

    issues.extend(_tasks_results_consistency(tasks_data, results_data))
    issues.extend(_verification_coverage(results_data))
    issues.extend(_guide_derivation_consistency(root))
    issues.extend(_task_artifact_presence(root, tasks_data))
    issues.extend(_evidence_map_schema(root))
    issues.extend(_citation_validity(root))
    issues.extend(_handoff_integrity(root))
    issues.extend(_run_meta_completeness(root))
    issues.extend(_kb_manifest_quality(root))
    issues.extend(_secret_path_guard(root, tasks_data, results_data, kb_manifest_data))

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
    consistency = [
        i
        for i in issues
        if i.category in {"tasks_schema", "key_results_schema", "project_registry_schema", "task_result_consistency"}
    ]
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

    lines.extend(["", "## Task artifact checks"])
    task_artifacts = [i for i in issues if i.category == "task_artifact_presence"]
    if task_artifacts:
        for issue in task_artifacts:
            lines.append(f"- [{issue.severity}] {issue.message} | Fix: {issue.suggestion}")
    else:
        lines.append("- PASS: task artifact presence checks did not find blocking gaps.")

    lines.extend(["", "## Evidence map schema"])
    evidence_schema = [i for i in issues if i.category == "evidence_map_schema"]
    if evidence_schema:
        for issue in evidence_schema:
            lines.append(f"- [{issue.severity}] {issue.message} | Fix: {issue.suggestion}")
    else:
        lines.append("- PASS: evidence_map schema checks passed.")

    lines.extend(["", "## Citation validity"])
    citation_issues = [i for i in issues if i.category == "citation_validity"]
    if citation_issues:
        for issue in citation_issues:
            lines.append(f"- [{issue.severity}] {issue.message} | Fix: {issue.suggestion}")
    else:
        lines.append("- PASS: citations are syntactically and cryptographically valid.")

    lines.extend(["", "## Handoff integrity"])
    handoff = [i for i in issues if i.category == "handoff_integrity"]
    if handoff:
        for issue in handoff:
            lines.append(f"- [{issue.severity}] {issue.message} | Fix: {issue.suggestion}")
    else:
        lines.append("- PASS: handoff records are complete.")

    lines.extend(["", "## Run meta completeness"])
    run_meta = [i for i in issues if i.category == "run_meta_completeness"]
    if run_meta:
        for issue in run_meta:
            lines.append(f"- [{issue.severity}] {issue.message} | Fix: {issue.suggestion}")
    else:
        lines.append("- PASS: run_meta records are complete.")

    lines.extend(["", "## KB manifest quality"])
    kb_manifest = [i for i in issues if i.category == "kb_manifest_quality"]
    if kb_manifest:
        for issue in kb_manifest:
            lines.append(f"- [{issue.severity}] {issue.message} | Fix: {issue.suggestion}")
    else:
        lines.append("- PASS: KB manifest quality checks passed.")

    lines.extend(["", "## Secret path guard"])
    secret_guard = [i for i in issues if i.category == "secret_path_guard"]
    if secret_guard:
        for issue in secret_guard:
            lines.append(f"- [{issue.severity}] {issue.message} | Fix: {issue.suggestion}")
    else:
        lines.append("- PASS: no secret-content citation leakage detected.")

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
