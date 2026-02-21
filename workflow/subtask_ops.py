from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .git_ops import is_ancestor
from .rollback import safe_rollback
from .state_ops import (
    append_human_review_log,
    append_state_event,
    load_key_results,
    load_review_queue,
    load_task_intake,
    load_tasks,
    now_iso,
    review_item_by_id,
    save_key_results,
    save_review_queue,
    save_task_intake_data,
    save_task_subtasks,
    task_by_id,
    task_state_dir,
    today_str,
    update_review_item,
    update_task,
)

SUBTASK_OWNER_SET = {"planner", "retriever", "implementer", "critic", "scribe", "human"}
SUBTASK_STATUS_SET = {"todo", "in_progress", "waiting_review", "done", "blocked"}
CASCADE_SCOPE_SET = {"self_only", "downstream", "all"}


@dataclass
class SubtaskReviewActionResult:
    action: str
    review: dict[str, Any]
    task: dict[str, Any]
    subtask: dict[str, Any]
    cascade_scope: str
    affected_subtasks: list[str]
    rollback_branch: str | None = None
    reverted_count: int = 0
    closed_prs: list[int] | None = None


def _next_prefixed_id(values: list[str], prefix: str) -> str:
    nums: list[int] = []
    for value in values:
        if not isinstance(value, str) or not value.startswith(prefix):
            continue
        tail = value.split("-", maxsplit=1)[1]
        if tail.isdigit():
            nums.append(int(tail))
    nxt = (max(nums) + 1) if nums else 1
    return f"{prefix}-{nxt:04d}"


def _default_subtasks(task: dict[str, Any]) -> list[dict[str, Any]]:
    tid = str(task.get("id", ""))
    title = str(task.get("title", ""))
    return [
        {
            "id": "ST-001",
            "title": f"{title} - Scope & Plan",
            "objective": f"Clarify objective and boundaries for {tid}.",
            "owner": "planner",
            "priority": task.get("priority", "P1"),
            "status": "todo",
            "depends_on": [],
            "prompt_contract": {
                "core_task": "",
                "required_files": [],
                "workflow": [],
                "response_style": "",
                "deliverables": [],
                "verification": [],
            },
            "latest_summary": "",
            "latest_event_at": "",
            "review_history": [],
        },
        {
            "id": "ST-002",
            "title": f"{title} - Retrieval",
            "objective": "Collect source files, references, and evidence pointers.",
            "owner": "retriever",
            "priority": task.get("priority", "P1"),
            "status": "todo",
            "depends_on": ["ST-001"],
            "prompt_contract": {
                "core_task": "",
                "required_files": [],
                "workflow": [],
                "response_style": "",
                "deliverables": [],
                "verification": [],
            },
            "latest_summary": "",
            "latest_event_at": "",
            "review_history": [],
        },
        {
            "id": "ST-003",
            "title": f"{title} - Implementation",
            "objective": "Implement code/derivation changes and produce outputs.",
            "owner": "implementer",
            "priority": task.get("priority", "P1"),
            "status": "todo",
            "depends_on": ["ST-002"],
            "prompt_contract": {
                "core_task": "",
                "required_files": [],
                "workflow": [],
                "response_style": "",
                "deliverables": [],
                "verification": [],
            },
            "latest_summary": "",
            "latest_event_at": "",
            "review_history": [],
        },
        {
            "id": "ST-004",
            "title": f"{title} - Check",
            "objective": "Run verify/audit and inspect regressions.",
            "owner": "critic",
            "priority": task.get("priority", "P1"),
            "status": "todo",
            "depends_on": ["ST-003"],
            "prompt_contract": {
                "core_task": "",
                "required_files": [],
                "workflow": [],
                "response_style": "",
                "deliverables": [],
                "verification": [],
            },
            "latest_summary": "",
            "latest_event_at": "",
            "review_history": [],
        },
        {
            "id": "ST-005",
            "title": f"{title} - Handoff",
            "objective": "Summarize evidence and prepare review packet.",
            "owner": "scribe",
            "priority": task.get("priority", "P1"),
            "status": "todo",
            "depends_on": ["ST-004"],
            "prompt_contract": {
                "core_task": "",
                "required_files": [],
                "workflow": [],
                "response_style": "",
                "deliverables": [],
                "verification": [],
            },
            "latest_summary": "",
            "latest_event_at": "",
            "review_history": [],
        },
    ]


def _min_intake_from_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task.get("id"),
        "project_slug": None,
        "raw_prompt_ref": "",
        "sections": {
            "core_task": str(task.get("title", "")),
            "required_files": list(task.get("evidence", [])),
            "workflow": ["Plan", "Do", "Check", "Act"],
            "response_style": "qa_zh",
            "acceptance": list(task.get("acceptance", [])),
            "constraints": ["uncertain: legacy task backfilled from TASKS.yaml"],
            "deliverables": [],
            "visualization": "auto",
        },
        "completeness": {
            "missing_required": [],
            "score": 0.8,
            "tag": "uncertain",
        },
        "attachments": [],
        "created_at": now_iso(),
        "source": "lazy_backfill_uncertain",
    }


def _normalize_subtask(raw: dict[str, Any], fallback_id: str) -> dict[str, Any]:
    item = dict(raw)
    item.setdefault("id", fallback_id)
    item.setdefault("title", "")
    item.setdefault("objective", "")
    owner = str(item.get("owner", "human"))
    item["owner"] = owner if owner in SUBTASK_OWNER_SET else "human"
    status = str(item.get("status", "todo"))
    item["status"] = status if status in SUBTASK_STATUS_SET else "todo"
    item.setdefault("priority", "P1")
    deps = item.get("depends_on", [])
    item["depends_on"] = [str(x) for x in deps] if isinstance(deps, list) else []
    prompt_contract = item.get("prompt_contract", {})
    if not isinstance(prompt_contract, dict):
        prompt_contract = {}
    item["prompt_contract"] = {
        "core_task": str(prompt_contract.get("core_task", "")),
        "required_files": [str(x) for x in prompt_contract.get("required_files", []) if str(x).strip()],
        "workflow": [str(x) for x in prompt_contract.get("workflow", []) if str(x).strip()],
        "response_style": str(prompt_contract.get("response_style", "")),
        "deliverables": [str(x) for x in prompt_contract.get("deliverables", []) if str(x).strip()],
        "verification": [str(x) for x in prompt_contract.get("verification", []) if str(x).strip()],
    }
    item["latest_summary"] = str(item.get("latest_summary", ""))
    item["latest_event_at"] = str(item.get("latest_event_at", ""))
    hist = item.get("review_history", [])
    item["review_history"] = hist if isinstance(hist, list) else []
    return item


def _load_subtasks(task_id: str) -> dict[str, Any]:
    path = task_state_dir(task_id) / "subtasks.yaml"
    if not path.exists():
        return {"task_id": task_id, "subtasks": []}
    from .state_ops import read_yaml

    data = read_yaml(path)
    data.setdefault("task_id", task_id)
    subtasks = data.get("subtasks", [])
    if not isinstance(subtasks, list):
        subtasks = []
    data["subtasks"] = [_normalize_subtask(item, f"ST-{idx+1:03d}") for idx, item in enumerate(subtasks) if isinstance(item, dict)]
    return data


def _save_subtasks(task_id: str, subtasks: list[dict[str, Any]]) -> None:
    save_task_subtasks(task_id, {"task_id": task_id, "subtasks": subtasks})


def ensure_subtasks(task_id: str, lazy: bool = True) -> list[dict[str, Any]]:
    task = task_by_id(task_id)
    state_dir = task_state_dir(task_id)
    state_dir.mkdir(parents=True, exist_ok=True)

    intake = load_task_intake(task_id)
    if not intake and lazy:
        save_task_intake_data(task_id, _min_intake_from_task(task))

    data = _load_subtasks(task_id)
    subtasks = data.get("subtasks", [])
    if subtasks:
        _save_subtasks(task_id, subtasks)
        return subtasks

    if not lazy:
        return []

    generated = _default_subtasks(task)
    _save_subtasks(task_id, generated)
    return generated


def aggregate_task_status(subtasks: list[dict[str, Any]], fallback: str = "todo") -> str:
    if not subtasks:
        return fallback
    statuses = [str(item.get("status", "todo")) for item in subtasks]
    if all(status == "done" for status in statuses):
        return "done"
    if any(status == "in_progress" for status in statuses):
        return "in_progress"
    if any(status == "waiting_review" for status in statuses):
        return "waiting_review"
    if any(status == "blocked" for status in statuses):
        return "blocked"
    if any(status == "todo" for status in statuses):
        return "todo"
    return fallback


def _subtask_by_id(subtasks: list[dict[str, Any]], subtask_id: str) -> dict[str, Any]:
    for item in subtasks:
        if item.get("id") == subtask_id:
            return item
    raise KeyError(f"Subtask not found: {subtask_id}")


def _dependents_map(subtasks: list[dict[str, Any]]) -> dict[str, set[str]]:
    deps: dict[str, set[str]] = {str(item.get("id")): set() for item in subtasks}
    for item in subtasks:
        sid = str(item.get("id"))
        for dep in item.get("depends_on", []):
            dep_id = str(dep)
            deps.setdefault(dep_id, set()).add(sid)
    return deps


def _collect_downstream(subtasks: list[dict[str, Any]], root_id: str) -> set[str]:
    deps_map = _dependents_map(subtasks)
    seen: set[str] = set()
    queue = list(deps_map.get(root_id, set()))
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        queue.extend(deps_map.get(current, set()))
    return seen


def update_subtask_status(task_id: str, subtask_id: str, status: str) -> dict[str, Any]:
    if status not in SUBTASK_STATUS_SET:
        raise ValueError(f"Unsupported subtask status: {status}")
    subtasks = ensure_subtasks(task_id, lazy=True)
    subtask = _subtask_by_id(subtasks, subtask_id)
    subtask["status"] = status
    subtask["latest_event_at"] = now_iso()
    subtask["latest_summary"] = f"status updated to {status}"
    _save_subtasks(task_id, subtasks)
    _update_task_status_from_subtasks(task_id, subtasks)
    return subtask


def sync_review_queue_from_subtasks(task_id: str | None = None) -> list[dict[str, Any]]:
    tasks = load_tasks()
    queue = load_review_queue()
    now = today_str()

    task_scope_items = [item for item in queue if str(item.get("scope", "task")) != "subtask"]
    existing_subtask = {
        (item.get("task_id"), item.get("subtask_id")): item
        for item in queue
        if str(item.get("scope", "task")) == "subtask"
    }

    merged_subtask: list[dict[str, Any]] = []
    all_ids = [str(item.get("id", "")) for item in queue]

    for task in tasks:
        tid = str(task.get("id", ""))
        if task_id and tid != task_id:
            continue
        subtasks = ensure_subtasks(tid, lazy=True)
        for sub in subtasks:
            if sub.get("status") != "waiting_review":
                continue
            key = (tid, sub.get("id"))
            old = existing_subtask.get(key)
            if old:
                old["title"] = str(sub.get("title", old.get("title", "")))
                old["status"] = old.get("status", "pending")
                old["scope"] = "subtask"
                old["updated_at"] = now
                merged_subtask.append(old)
                continue

            rq_id = _next_prefixed_id(all_ids + [str(item.get("id", "")) for item in merged_subtask], "RQ")
            merged_subtask.append(
                {
                    "id": rq_id,
                    "task_id": tid,
                    "subtask_id": str(sub.get("id")),
                    "title": str(sub.get("title", "")),
                    "scope": "subtask",
                    "status": "pending",
                    "created_at": now,
                    "updated_at": now,
                }
            )

    final_items = task_scope_items + merged_subtask
    save_review_queue(final_items)
    return final_items


def _heuristic_scope(action: str, reviewer_note: str, subtasks: list[dict[str, Any]], subtask_id: str) -> tuple[str, list[str], str, str, bool]:
    note = (reviewer_note or "").lower()
    downstream = sorted(_collect_downstream(subtasks, subtask_id))

    if any(token in note for token in ["all", "全部", "global", "前置", "核心", "critical"]):
        return "all", [str(item.get("id")) for item in subtasks], "high", "reviewer_note_forced_all", False

    if any(token in note for token in ["minor", "小", "细枝", "typo", "文案", "docs"]):
        return "self_only", [subtask_id], "medium", "reviewer_note_minor_scope", True

    if action.lower() == "reject":
        if downstream:
            return "downstream", [subtask_id, *downstream], "high", "reject_on_dependency_chain", False
        return "self_only", [subtask_id], "medium", "reject_without_dependents", True

    if downstream:
        return "downstream", [subtask_id, *downstream], "medium", "rework_on_dependency_chain", True
    return "self_only", [subtask_id], "medium", "rework_without_dependents", True


def _load_local_api_key() -> str | None:
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key
    from .state_ops import read_yaml

    local = read_yaml("state/AI_SECRETS.local.yaml")
    if isinstance(local, dict):
        key = local.get("openai_api_key")
        if isinstance(key, str) and key.strip():
            return key.strip()
    return None


def _ai_refine_scope(task_id: str, subtask_id: str, action: str, reviewer_note: str, candidate: str) -> tuple[str, str, bool]:
    key = _load_local_api_key()
    if not key:
        return candidate, "missing_api_key_rule_fallback", True

    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        prompt = (
            "Decide cascade scope for subtask review action. "
            "Return only one token from {self_only,downstream,all}."
            f"\nTask={task_id}\nSubtask={subtask_id}\nAction={action}\nCandidate={candidate}"
            f"\nReviewerNote={reviewer_note[:800]}"
        )
        response = client.responses.create(
            model="gpt-5-mini",
            reasoning={"effort": "low"},
            input=prompt,
        )
        text = (getattr(response, "output_text", "") or "").strip().lower()
        for scope in ["self_only", "downstream", "all"]:
            if scope in text:
                return scope, "ai_refined", False
        return candidate, "ai_unparsed_rule_fallback", True
    except Exception:
        return candidate, "ai_error_rule_fallback", True


def suggest_cascade_scope(task_id: str, subtask_id: str, action: str, reviewer_note: str) -> dict[str, Any]:
    subtasks = ensure_subtasks(task_id, lazy=True)
    _subtask_by_id(subtasks, subtask_id)

    suggested_scope, affected, confidence, reason, uncertain = _heuristic_scope(action, reviewer_note, subtasks, subtask_id)
    refined_scope, source_note, ai_uncertain = _ai_refine_scope(task_id, subtask_id, action, reviewer_note, suggested_scope)

    if refined_scope != suggested_scope:
        uncertain = uncertain or ai_uncertain
        reason = f"{reason}|{source_note}"
    else:
        reason = f"{reason}|{source_note}"

    if refined_scope == "downstream":
        affected = [subtask_id, *sorted(_collect_downstream(subtasks, subtask_id))]
    elif refined_scope == "all":
        affected = [str(item.get("id")) for item in subtasks]
    else:
        affected = [subtask_id]

    artifact_dir = Path("artifacts") / "tasks" / task_id / "ai"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"cascade-advice-{datetime.now().strftime('%Y%m%d-%H%M%S')}.yaml"
    payload = {
        "task_id": task_id,
        "subtask_id": subtask_id,
        "action": action,
        "suggested_scope": refined_scope,
        "affected_subtasks": affected,
        "reason": reason,
        "confidence": confidence,
        "uncertain": bool(uncertain),
        "reviewer_note": reviewer_note,
        "created_at": now_iso(),
    }
    from .state_ops import atomic_write_yaml

    atomic_write_yaml(path, payload)
    payload["artifact_path"] = path.as_posix()
    return payload


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


def _set_cascade_state(
    subtasks: list[dict[str, Any]],
    current_id: str,
    cascade_scope: str,
    action: str,
) -> list[str]:
    affected: list[str] = []
    target_ids: set[str]

    if cascade_scope == "all":
        target_ids = {str(item.get("id")) for item in subtasks}
    elif cascade_scope == "downstream":
        target_ids = _collect_downstream(subtasks, current_id) | {current_id}
    else:
        target_ids = {current_id}

    for item in subtasks:
        sid = str(item.get("id"))
        if sid not in target_ids:
            continue
        affected.append(sid)
        if sid == current_id:
            item["status"] = "done" if action == "Approve" else "blocked"
            continue
        if action == "Approve":
            continue
        item["status"] = "todo"

    return affected


def _update_task_status_from_subtasks(task_id: str, subtasks: list[dict[str, Any]]) -> dict[str, Any]:
    task = task_by_id(task_id)
    status = aggregate_task_status(subtasks, fallback=str(task.get("status", "todo")))
    return update_task(task_id, {"status": status})


def apply_subtask_review_action(
    review_id: str,
    reviewer: str,
    action: str,
    notes: str,
    anchor: str | None = None,
    cascade_scope: str | None = None,
    cwd: str | Path | None = None,
) -> SubtaskReviewActionResult:
    review_item = review_item_by_id(review_id)
    scope = str(review_item.get("scope", "task"))
    if scope != "subtask":
        raise ValueError(f"Review item {review_id} is not subtask scope.")

    task_id = str(review_item.get("task_id"))
    subtask_id = str(review_item.get("subtask_id"))
    subtasks = ensure_subtasks(task_id, lazy=True)
    subtask = _subtask_by_id(subtasks, subtask_id)

    action_norm = action.strip().lower()
    if action not in {"Approve", "Rework", "Reject"}:
        raise ValueError(f"Unsupported action: {action}")

    suggestion = suggest_cascade_scope(task_id=task_id, subtask_id=subtask_id, action=action, reviewer_note=notes)
    scope_to_apply = str(cascade_scope or suggestion.get("suggested_scope") or "self_only")
    if scope_to_apply not in CASCADE_SCOPE_SET:
        scope_to_apply = "self_only"

    if action == "Reject" and not (anchor or "").strip():
        raise ValueError("Reject requires anchor checkpoint/commit.")

    affected_subtasks = _set_cascade_state(subtasks, subtask_id, scope_to_apply, action)
    subtask = _subtask_by_id(subtasks, subtask_id)

    review_entry = {
        "time": now_iso(),
        "reviewer": reviewer,
        "action": action,
        "notes": notes,
        "scope": scope_to_apply,
        "affected_subtasks": affected_subtasks,
        "anchor": anchor or "",
    }
    subtask.setdefault("review_history", []).append(review_entry)
    subtask["latest_event_at"] = now_iso()
    subtask["latest_summary"] = f"{action} by {reviewer}: {notes[:120]}"

    _save_subtasks(task_id, subtasks)
    task = _update_task_status_from_subtasks(task_id, subtasks)

    rollback_branch: str | None = None
    reverted_count = 0
    closed_prs: list[int] = []

    if action == "Reject":
        rb = safe_rollback(anchor_ref=str(anchor), cwd=cwd)
        rollback_branch = rb.branch
        reverted_count = rb.reverted_count
        _mark_key_results_after_anchor(anchor=str(anchor), cwd=cwd)

        try:
            from .pr_ops import close_superseded_prs

            closed_prs = close_superseded_prs(anchor_ref=str(anchor), cwd=cwd)
        except Exception:
            closed_prs = []

    updated_review = update_review_item(
        review_id,
        {
            "status": action_norm,
            "scope": "subtask",
            "subtask_id": subtask_id,
            "cascade_scope": scope_to_apply,
            "cascade_advice_ref": suggestion.get("artifact_path", ""),
            "title": subtask.get("title", review_item.get("title", "")),
        },
    )

    append_human_review_log(
        reviewer,
        item=review_id,
        action=action,
        notes=f"task={task_id};subtask={subtask_id};scope={scope_to_apply};notes={notes}",
    )
    append_state_event(
        "Subtask Review Action",
        [
            f"Review Item: {review_id}",
            f"Task: {task_id}",
            f"Subtask: {subtask_id}",
            f"Action: {action}",
            f"Reviewer: {reviewer}",
            f"Cascade scope: {scope_to_apply}",
            f"Affected subtasks: {json.dumps(affected_subtasks, ensure_ascii=False)}",
            f"Cascade advice: {suggestion.get('artifact_path', '-')}",
            f"Anchor: {anchor or '-'}",
            f"Rollback branch: {rollback_branch or '-'}",
            f"Closed PRs: {closed_prs if closed_prs else '[]'}",
        ],
    )

    return SubtaskReviewActionResult(
        action=action,
        review=updated_review,
        task=task,
        subtask=subtask,
        cascade_scope=scope_to_apply,
        affected_subtasks=affected_subtasks,
        rollback_branch=rollback_branch,
        reverted_count=reverted_count,
        closed_prs=closed_prs,
    )
