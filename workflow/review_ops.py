from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .git_ops import is_ancestor
from .rollback import safe_rollback
from .state_ops import (
    append_human_review_log,
    append_state_event,
    load_key_results,
    review_item_by_id,
    load_tasks,
    save_key_results,
    save_tasks,
    set_review_item_status,
    task_by_id,
    update_task,
)


@dataclass
class ReviewActionResult:
    action: str
    review: dict[str, Any]
    task: dict[str, Any]
    rollback_branch: str | None = None
    reverted_count: int = 0
    closed_prs: list[int] | None = None


def _dependency_reset(tasks: list[dict[str, Any]], root_task_id: str) -> list[dict[str, Any]]:
    dependents: set[str] = set()
    changed = []

    while True:
        before = len(dependents)
        for item in tasks:
            deps = item.get("depends_on", [])
            if item.get("id") == root_task_id:
                continue
            if root_task_id in deps or any(dep in dependents for dep in deps):
                dependents.add(item.get("id"))
        if len(dependents) == before:
            break

    for item in tasks:
        tid = item.get("id")
        if tid == root_task_id:
            item["status"] = "blocked"
            changed.append(item)
        elif tid in dependents:
            item["status"] = "todo"
            changed.append(item)
    return changed


def _mark_key_results_after_anchor(anchor: str, cwd: str | Path | None = None) -> int:
    results = load_key_results()
    changed = 0
    for item in results:
        status = item.get("status")
        first_seen = item.get("first_seen_commit", "")
        if status == "deprecated":
            continue
        if first_seen in {"", "TBD"}:
            item["status"] = "proposed"
            changed += 1
            continue
        try:
            if not is_ancestor(first_seen, anchor, cwd=cwd):
                item["status"] = "proposed"
                changed += 1
        except Exception:
            item["status"] = "proposed"
            changed += 1
    if changed:
        save_key_results(results)
    return changed


def apply_review_action(
    review_id: str,
    reviewer: str,
    action: str,
    notes: str,
    anchor: str | None = None,
    cascade_scope: str | None = None,
    cwd: str | Path | None = None,
) -> ReviewActionResult:
    review_snapshot = review_item_by_id(review_id)
    if str(review_snapshot.get("scope", "task")) == "subtask":
        from .subtask_ops import apply_subtask_review_action

        subtask_result = apply_subtask_review_action(
            review_id=review_id,
            reviewer=reviewer,
            action=action,
            notes=notes,
            anchor=anchor,
            cascade_scope=cascade_scope,
            cwd=cwd,
        )
        return ReviewActionResult(
            action=action,
            review=subtask_result.review,
            task=subtask_result.task,
            rollback_branch=subtask_result.rollback_branch,
            reverted_count=subtask_result.reverted_count,
            closed_prs=subtask_result.closed_prs,
        )

    action_norm = action.lower()
    review_item = set_review_item_status(review_id, action_norm)
    task_id = review_item["task_id"]

    rollback_branch: str | None = None
    reverted_count = 0
    closed_prs: list[int] = []

    if action == "Approve":
        task = update_task(task_id, {"status": "done"})
    elif action == "Rework":
        task = update_task(task_id, {"status": "blocked"})
    elif action == "Reject":
        task = update_task(task_id, {"status": "blocked"})

        tasks = load_tasks()
        changed = _dependency_reset(tasks, task_id)
        if changed:
            save_tasks(tasks)

        if anchor:
            rb = safe_rollback(anchor_ref=anchor, cwd=cwd)
            rollback_branch = rb.branch
            reverted_count = rb.reverted_count
            _mark_key_results_after_anchor(anchor=anchor, cwd=cwd)

            try:
                from .pr_ops import close_superseded_prs

                closed_prs = close_superseded_prs(anchor_ref=anchor, cwd=cwd)
            except Exception:
                closed_prs = []
    else:
        raise ValueError(f"Unsupported review action: {action}")

    append_human_review_log(reviewer, item=review_id, action=action, notes=notes)
    append_state_event(
        "Review Action",
        [
            f"Review Item: {review_id}",
            f"Task: {task_id}",
            f"Action: {action}",
            f"Reviewer: {reviewer}",
            f"Anchor: {anchor or '-'}",
            f"Rollback branch: {rollback_branch or '-'}",
            f"Closed PRs: {closed_prs if closed_prs else '[]'}",
        ],
    )

    return ReviewActionResult(
        action=action,
        review=review_item,
        task=task_by_id(task_id),
        rollback_branch=rollback_branch,
        reverted_count=reverted_count,
        closed_prs=closed_prs,
    )
