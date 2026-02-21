from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

STATE_DIR = Path("state")
TASKS_PATH = STATE_DIR / "TASKS.yaml"
REVIEW_QUEUE_PATH = STATE_DIR / "REVIEW_QUEUE.yaml"
KEY_RESULTS_PATH = STATE_DIR / "KEY_RESULTS.yaml"
HUMAN_REVIEW_LOG_PATH = STATE_DIR / "HUMAN_REVIEW_LOG.md"
STATE_MD_PATH = STATE_DIR / "STATE.md"
PR_REGISTRY_PATH = STATE_DIR / "PR_REGISTRY.yaml"
JOBS_PATH = STATE_DIR / "JOBS.yaml"
AI_CONFIG_PATH = STATE_DIR / "AI_CONFIG.yaml"
AI_BUDGET_PATH = STATE_DIR / "AI_BUDGET.yaml"
PROJECT_REGISTRY_PATH = STATE_DIR / "PROJECT_REGISTRY.yaml"
KB_CONFIG_PATH = STATE_DIR / "KB_CONFIG.yaml"
KB_MANIFEST_PATH = STATE_DIR / "KB_MANIFEST.yaml"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def read_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def atomic_write_yaml(path: str | Path, data: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(p.parent), delete=False) as tf:
        yaml.safe_dump(data, tf, allow_unicode=True, sort_keys=False)
        temp_path = Path(tf.name)
    temp_path.replace(p)


def _next_prefixed_id(values: list[str], prefix: str) -> str:
    nums = []
    for value in values:
        if value.startswith(prefix):
            part = value.split("-", maxsplit=1)[1]
            if part.isdigit():
                nums.append(int(part))
    nxt = (max(nums) + 1) if nums else 1
    return f"{prefix}-{nxt:04d}"


def load_tasks(path: str | Path = TASKS_PATH) -> list[dict[str, Any]]:
    data = read_yaml(path)
    return data.get("tasks", [])


def save_tasks(tasks: list[dict[str, Any]], path: str | Path = TASKS_PATH) -> None:
    atomic_write_yaml(path, {"tasks": tasks})


def add_task(
    title: str,
    task_type: str,
    priority: str,
    owner: str,
    status: str,
    acceptance: list[str],
    evidence: list[str] | None = None,
    verification: list[str] | None = None,
    depends_on: list[str] | None = None,
    path: str | Path = TASKS_PATH,
) -> dict[str, Any]:
    tasks = load_tasks(path)
    task_id = _next_prefixed_id([t.get("id", "") for t in tasks], "T")
    item = {
        "id": task_id,
        "title": title,
        "type": task_type,
        "priority": priority,
        "owner": owner,
        "status": status,
        "acceptance": acceptance,
        "evidence": evidence or [],
        "verification": verification or [],
        "depends_on": depends_on or [],
        "created_at": today_str(),
        "updated_at": today_str(),
    }
    tasks.append(item)
    save_tasks(tasks, path)
    return item


def update_task(task_id: str, updates: dict[str, Any], path: str | Path = TASKS_PATH) -> dict[str, Any]:
    tasks = load_tasks(path)
    for task in tasks:
        if task.get("id") == task_id:
            task.update(updates)
            task["updated_at"] = today_str()
            save_tasks(tasks, path)
            return task
    raise KeyError(f"Task not found: {task_id}")


def task_by_id(task_id: str, path: str | Path = TASKS_PATH) -> dict[str, Any]:
    for task in load_tasks(path):
        if task.get("id") == task_id:
            return task
    raise KeyError(f"Task not found: {task_id}")


def load_review_queue(path: str | Path = REVIEW_QUEUE_PATH) -> list[dict[str, Any]]:
    data = read_yaml(path)
    return data.get("items", [])


def save_review_queue(items: list[dict[str, Any]], path: str | Path = REVIEW_QUEUE_PATH) -> None:
    atomic_write_yaml(path, {"items": items})


def sync_review_queue_from_tasks(
    tasks_path: str | Path = TASKS_PATH,
    queue_path: str | Path = REVIEW_QUEUE_PATH,
) -> list[dict[str, Any]]:
    tasks = load_tasks(tasks_path)
    queue = load_review_queue(queue_path)
    now = today_str()

    existing_by_task = {item.get("task_id"): item for item in queue}
    merged: list[dict[str, Any]] = []

    for task in tasks:
        if task.get("status") != "waiting_review":
            continue
        old = existing_by_task.get(task["id"])
        if old:
            old["title"] = task["title"]
            old["updated_at"] = now
            merged.append(old)
            continue
        rq_id = _next_prefixed_id([it.get("id", "") for it in queue + merged], "RQ")
        merged.append(
            {
                "id": rq_id,
                "task_id": task["id"],
                "title": task["title"],
                "status": "pending",
                "created_at": now,
                "updated_at": now,
            }
        )

    save_review_queue(merged, queue_path)
    return merged


def set_review_item_status(
    review_id: str,
    status: str,
    queue_path: str | Path = REVIEW_QUEUE_PATH,
) -> dict[str, Any]:
    items = load_review_queue(queue_path)
    for item in items:
        if item.get("id") == review_id:
            item["status"] = status
            item["updated_at"] = today_str()
            save_review_queue(items, queue_path)
            return item
    raise KeyError(f"Review item not found: {review_id}")


def append_human_review_log(
    reviewer: str,
    item: str,
    action: str,
    notes: str,
    path: str | Path = HUMAN_REVIEW_LOG_PATH,
) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("# HUMAN REVIEW LOG\n\n| Time | Reviewer | Item | Action | Notes |\n|---|---|---|---|---|\n", encoding="utf-8")
    with p.open("a", encoding="utf-8") as f:
        f.write(
            f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {reviewer} | {item} | {action} | {notes.replace('|', '/')} |\n"
        )


def append_state_event(title: str, details: list[str], path: str | Path = STATE_MD_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("# STATE Snapshot\n\n", encoding="utf-8")
    with p.open("a", encoding="utf-8") as f:
        f.write(f"\n## {title}\n")
        for line in details:
            f.write(f"- {line}\n")


def load_key_results(path: str | Path = KEY_RESULTS_PATH) -> list[dict[str, Any]]:
    data = read_yaml(path)
    return data.get("results", [])


def save_key_results(results: list[dict[str, Any]], path: str | Path = KEY_RESULTS_PATH) -> None:
    atomic_write_yaml(path, {"results": results})


def load_project_registry(path: str | Path = PROJECT_REGISTRY_PATH) -> list[dict[str, Any]]:
    data = read_yaml(path)
    return data.get("projects", [])


def save_project_registry(items: list[dict[str, Any]], path: str | Path = PROJECT_REGISTRY_PATH) -> None:
    atomic_write_yaml(path, {"projects": items})


def load_kb_manifest(path: str | Path = KB_MANIFEST_PATH) -> list[dict[str, Any]]:
    data = read_yaml(path)
    return data.get("documents", [])


def save_kb_manifest(items: list[dict[str, Any]], path: str | Path = KB_MANIFEST_PATH) -> None:
    atomic_write_yaml(path, {"documents": items})


def ensure_minimum_state_files() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    defaults: list[tuple[Path, dict[str, Any]]] = [
        (TASKS_PATH, {"tasks": []}),
        (REVIEW_QUEUE_PATH, {"items": []}),
        (KEY_RESULTS_PATH, {"results": []}),
        (PR_REGISTRY_PATH, {"prs": []}),
        (PROJECT_REGISTRY_PATH, {"projects": []}),
        (KB_MANIFEST_PATH, {"documents": []}),
        (JOBS_PATH, {"jobs": []}),
        (
            AI_BUDGET_PATH,
            {
                "monthly_budget_usd": 2000.0,
                "alert_threshold": 0.8,
                "hard_limit_threshold": 1.0,
                "current_month": datetime.now().strftime("%Y-%m"),
                "spend_usd": 0.0,
                "entries": [],
            },
        ),
    ]
    for path, content in defaults:
        if not path.exists():
            atomic_write_yaml(path, content)

    if not HUMAN_REVIEW_LOG_PATH.exists():
        append_human_review_log("system", "bootstrap", "init", "Initialize human review log")

    if not AI_CONFIG_PATH.exists():
        atomic_write_yaml(
            AI_CONFIG_PATH,
            {
                "default_model": "gpt-5",
                "low_cost_model": "gpt-4.1-mini",
                "reasoning_effort": "high",
                "price_per_1m_input_usd": 10.0,
                "price_per_1m_output_usd": 30.0,
                "price_per_1m_cached_input_usd": 2.5,
                "notes": "Do not store API key here. Put key in state/AI_SECRETS.local.yaml or OPENAI_API_KEY env.",
            },
        )

    if not KB_CONFIG_PATH.exists():
        atomic_write_yaml(
            KB_CONFIG_PATH,
            {
                "external_roots": ["/Volumes/workflow-kb"],
                "ignore_globs": ["**/.git/**", "**/.venv/**", "**/__pycache__/**"],
                "max_repo_file_mb": 20,
                "chunk_policy": {"default_max_chars": 1200, "default_overlap_chars": 200},
            },
        )
