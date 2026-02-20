from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

TASK_TYPE_SET = {"derivation", "code", "writing", "literature", "experiment", "meta"}
PRIORITY_SET = {"P0", "P1", "P2"}
OWNER_SET = {"codex", "chatgpt", "human"}
TASK_STATUS_SET = {"todo", "in_progress", "waiting_review", "done", "blocked"}

KR_STATUS_SET = {"proposed", "verified", "deprecated"}
CONFIDENCE_SET = {"low", "medium", "high"}
PROJECT_STATUS_SET = {"active", "archived", "draft"}
VISIBILITY_SET = {"public", "private", "internal"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TASK_ID_RE = re.compile(r"^T-\d{4}$")
KR_ID_RE = re.compile(r"^KR-\d{4}$")
PROJECT_ID_RE = re.compile(r"^P-\d{4}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass
class ValidationIssue:
    path: str
    message: str
    suggestion: str
    severity: str = "P0"


def _is_list_of_str(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def validate_tasks_data(data: dict[str, Any]) -> tuple[bool, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []

    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        issues.append(
            ValidationIssue(
                path="tasks",
                message="`tasks` must be a list.",
                suggestion="Set top-level key as `tasks: []`.",
            )
        )
        return False, issues

    seen_ids: set[str] = set()
    for idx, task in enumerate(tasks):
        base = f"tasks[{idx}]"
        if not isinstance(task, dict):
            issues.append(
                ValidationIssue(
                    path=base,
                    message="Each task item must be a mapping.",
                    suggestion="Use YAML mapping with required fields like id/title/status.",
                )
            )
            continue

        required = [
            "id",
            "title",
            "type",
            "priority",
            "owner",
            "status",
            "acceptance",
            "evidence",
            "verification",
            "depends_on",
            "created_at",
            "updated_at",
        ]
        for key in required:
            if key not in task:
                issues.append(
                    ValidationIssue(
                        path=f"{base}.{key}",
                        message=f"Missing required field `{key}`.",
                        suggestion=f"Add `{key}` according to docs/DATA_MODEL.md.",
                    )
                )

        task_id = task.get("id")
        if not isinstance(task_id, str) or not TASK_ID_RE.match(task_id):
            issues.append(
                ValidationIssue(
                    path=f"{base}.id",
                    message="Task id must match pattern `T-0001`.",
                    suggestion="Rename id to `T-` + 4 digits.",
                )
            )
        elif task_id in seen_ids:
            issues.append(
                ValidationIssue(
                    path=f"{base}.id",
                    message=f"Duplicate task id `{task_id}`.",
                    suggestion="Ensure each task id is unique.",
                )
            )
        else:
            seen_ids.add(task_id)

        if not isinstance(task.get("title"), str) or not task["title"].strip():
            issues.append(
                ValidationIssue(
                    path=f"{base}.title",
                    message="Task title must be a non-empty string.",
                    suggestion="Provide a concise actionable title.",
                )
            )

        if task.get("type") not in TASK_TYPE_SET:
            issues.append(
                ValidationIssue(
                    path=f"{base}.type",
                    message=f"Task type must be one of {sorted(TASK_TYPE_SET)}.",
                    suggestion="Use a supported task type enum.",
                )
            )

        if task.get("priority") not in PRIORITY_SET:
            issues.append(
                ValidationIssue(
                    path=f"{base}.priority",
                    message=f"Priority must be one of {sorted(PRIORITY_SET)}.",
                    suggestion="Set priority to P0/P1/P2.",
                )
            )

        if task.get("owner") not in OWNER_SET:
            issues.append(
                ValidationIssue(
                    path=f"{base}.owner",
                    message=f"Owner must be one of {sorted(OWNER_SET)}.",
                    suggestion="Use owner enum codex/chatgpt/human.",
                )
            )

        if task.get("status") not in TASK_STATUS_SET:
            issues.append(
                ValidationIssue(
                    path=f"{base}.status",
                    message=f"Status must be one of {sorted(TASK_STATUS_SET)}.",
                    suggestion="Use todo/in_progress/waiting_review/done/blocked.",
                )
            )

        for key in ["acceptance", "evidence", "verification", "depends_on"]:
            if not _is_list_of_str(task.get(key)):
                issues.append(
                    ValidationIssue(
                        path=f"{base}.{key}",
                        message=f"`{key}` must be a list of strings.",
                        suggestion=f"Rewrite `{key}` as YAML string list.",
                    )
                )

        for key in ["created_at", "updated_at"]:
            value = task.get(key)
            if not isinstance(value, str) or not DATE_RE.match(value):
                issues.append(
                    ValidationIssue(
                        path=f"{base}.{key}",
                        message=f"`{key}` must be YYYY-MM-DD.",
                        suggestion=f"Set `{key}` like `2026-02-20`.",
                    )
                )

    return len(issues) == 0, issues


def validate_key_results_data(data: dict[str, Any]) -> tuple[bool, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []

    results = data.get("results")
    if not isinstance(results, list):
        issues.append(
            ValidationIssue(
                path="results",
                message="`results` must be a list.",
                suggestion="Set top-level key as `results: []`.",
            )
        )
        return False, issues

    seen_ids: set[str] = set()
    for idx, item in enumerate(results):
        base = f"results[{idx}]"
        if not isinstance(item, dict):
            issues.append(
                ValidationIssue(
                    path=base,
                    message="Each result item must be a mapping.",
                    suggestion="Use YAML mapping with required key result fields.",
                )
            )
            continue

        required = [
            "id",
            "statement",
            "status",
            "confidence",
            "evidence",
            "verification",
            "related_tasks",
            "first_seen_commit",
            "last_confirmed_commit",
            "checkpoint_tags",
        ]
        for key in required:
            if key not in item:
                issues.append(
                    ValidationIssue(
                        path=f"{base}.{key}",
                        message=f"Missing required field `{key}`.",
                        suggestion=f"Add `{key}` according to docs/DATA_MODEL.md.",
                    )
                )

        kr_id = item.get("id")
        if not isinstance(kr_id, str) or not KR_ID_RE.match(kr_id):
            issues.append(
                ValidationIssue(
                    path=f"{base}.id",
                    message="Key result id must match `KR-0001`.",
                    suggestion="Rename id with KR prefix and four digits.",
                )
            )
        elif kr_id in seen_ids:
            issues.append(
                ValidationIssue(
                    path=f"{base}.id",
                    message=f"Duplicate key result id `{kr_id}`.",
                    suggestion="Ensure each KR id is unique.",
                )
            )
        else:
            seen_ids.add(kr_id)

        if not isinstance(item.get("statement"), str) or not item["statement"].strip():
            issues.append(
                ValidationIssue(
                    path=f"{base}.statement",
                    message="`statement` must be non-empty.",
                    suggestion="Provide a clear, testable conclusion statement.",
                )
            )

        if item.get("status") not in KR_STATUS_SET:
            issues.append(
                ValidationIssue(
                    path=f"{base}.status",
                    message=f"Status must be one of {sorted(KR_STATUS_SET)}.",
                    suggestion="Use proposed/verified/deprecated.",
                )
            )

        if item.get("confidence") not in CONFIDENCE_SET:
            issues.append(
                ValidationIssue(
                    path=f"{base}.confidence",
                    message=f"Confidence must be one of {sorted(CONFIDENCE_SET)}.",
                    suggestion="Use low/medium/high.",
                )
            )

        for key in ["evidence", "verification", "related_tasks", "checkpoint_tags"]:
            if not _is_list_of_str(item.get(key)):
                issues.append(
                    ValidationIssue(
                        path=f"{base}.{key}",
                        message=f"`{key}` must be a list of strings.",
                        suggestion=f"Rewrite `{key}` as YAML string list.",
                    )
                )

        for key in ["first_seen_commit", "last_confirmed_commit"]:
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                issues.append(
                    ValidationIssue(
                        path=f"{base}.{key}",
                        message=f"`{key}` must be non-empty commit hash/ref string.",
                        suggestion=f"Set `{key}` to a commit hash (or `TBD` temporarily).",
                    )
                )

    return len(issues) == 0, issues


def validate_project_registry_data(data: dict[str, Any]) -> tuple[bool, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    projects = data.get("projects")
    if not isinstance(projects, list):
        issues.append(
            ValidationIssue(
                path="projects",
                message="`projects` must be a list.",
                suggestion="Set top-level key as `projects: []`.",
            )
        )
        return False, issues

    seen_ids: set[str] = set()
    seen_slugs: set[str] = set()
    for idx, item in enumerate(projects):
        base = f"projects[{idx}]"
        if not isinstance(item, dict):
            issues.append(
                ValidationIssue(
                    path=base,
                    message="Each project item must be a mapping.",
                    suggestion="Use YAML mapping with required project registry fields.",
                )
            )
            continue

        required = [
            "id",
            "slug",
            "title",
            "local_path",
            "release_repo",
            "release_visibility",
            "release_default_branch",
            "status",
            "created_at",
            "updated_at",
        ]
        for key in required:
            if key not in item:
                issues.append(
                    ValidationIssue(
                        path=f"{base}.{key}",
                        message=f"Missing required field `{key}`.",
                        suggestion=f"Add `{key}` according to docs/DATA_MODEL.md.",
                    )
                )

        project_id = item.get("id")
        if not isinstance(project_id, str) or not PROJECT_ID_RE.match(project_id):
            issues.append(
                ValidationIssue(
                    path=f"{base}.id",
                    message="Project id must match pattern `P-0001`.",
                    suggestion="Rename id to `P-` + 4 digits.",
                )
            )
        elif project_id in seen_ids:
            issues.append(
                ValidationIssue(
                    path=f"{base}.id",
                    message=f"Duplicate project id `{project_id}`.",
                    suggestion="Ensure each project id is unique.",
                )
            )
        else:
            seen_ids.add(project_id)

        slug = item.get("slug")
        if not isinstance(slug, str) or not SLUG_RE.match(slug):
            issues.append(
                ValidationIssue(
                    path=f"{base}.slug",
                    message="Project slug must match `[a-z0-9-]+`.",
                    suggestion="Use lowercase slug like `rl-gridworld-qlearning`.",
                )
            )
        elif slug in seen_slugs:
            issues.append(
                ValidationIssue(
                    path=f"{base}.slug",
                    message=f"Duplicate project slug `{slug}`.",
                    suggestion="Ensure each project slug is unique.",
                )
            )
        else:
            seen_slugs.add(slug)

        for key in ["title", "local_path", "release_default_branch"]:
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                issues.append(
                    ValidationIssue(
                        path=f"{base}.{key}",
                        message=f"`{key}` must be a non-empty string.",
                        suggestion=f"Provide `{key}` with a valid value.",
                    )
                )

        release_repo = item.get("release_repo")
        if not isinstance(release_repo, str) or not REPO_RE.match(release_repo):
            issues.append(
                ValidationIssue(
                    path=f"{base}.release_repo",
                    message="`release_repo` must match `owner/name`.",
                    suggestion="Set release_repo like `LichanghengXJTU/rl-gridworld-qlearning-release`.",
                )
            )

        if item.get("release_visibility") not in VISIBILITY_SET:
            issues.append(
                ValidationIssue(
                    path=f"{base}.release_visibility",
                    message=f"release_visibility must be one of {sorted(VISIBILITY_SET)}.",
                    suggestion="Use public/private/internal.",
                )
            )

        if item.get("status") not in PROJECT_STATUS_SET:
            issues.append(
                ValidationIssue(
                    path=f"{base}.status",
                    message=f"status must be one of {sorted(PROJECT_STATUS_SET)}.",
                    suggestion="Use active/archived/draft.",
                )
            )

        for key in ["created_at", "updated_at"]:
            value = item.get(key)
            if not isinstance(value, str) or not DATE_RE.match(value):
                issues.append(
                    ValidationIssue(
                        path=f"{base}.{key}",
                        message=f"`{key}` must be YYYY-MM-DD.",
                        suggestion=f"Set `{key}` like `2026-02-21`.",
                    )
                )

    return len(issues) == 0, issues


def format_issues(issues: list[ValidationIssue]) -> list[dict[str, str]]:
    return [
        {
            "path": i.path,
            "message": i.message,
            "suggestion": i.suggestion,
            "severity": i.severity,
        }
        for i in issues
    ]
