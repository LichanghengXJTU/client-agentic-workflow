from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .project_ops import project_by_slug
from .state_ops import load_review_queue, load_task_intake, load_task_subtasks, read_yaml, task_by_id

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
_IMAGE_MD_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_PULL_URL_RE = re.compile(r"https://github\.com/([^\s/]+/[^\s/]+)/pull/(\d+)")


def _parse_time(value: str) -> datetime:
    if not value:
        return datetime.fromtimestamp(0)
    value = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(value)
    except Exception:
        pass
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.fromtimestamp(0)


def _collect_ai_events(task_id: str) -> list[dict[str, Any]]:
    ai_dir = Path("artifacts") / "tasks" / task_id / "ai"
    events: list[dict[str, Any]] = []
    if not ai_dir.exists():
        return events

    for path in sorted(ai_dir.glob("*.md")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        metadata: dict[str, str] = {}
        output_lines: list[str] = []
        output_started = False
        for line in lines[:120]:
            if line.startswith("- ") and ":" in line:
                key, value = line[2:].split(":", maxsplit=1)
                metadata[key.strip().lower()] = value.strip()
            if line.strip() == "## Output":
                output_started = True
                continue
            if output_started and line.strip():
                output_lines.append(line.strip())
                if len(output_lines) >= 6:
                    break

        summary = " ".join(output_lines)[:240] if output_lines else ""
        events.append(
            {
                "id": f"ai:{path.name}",
                "type": "ai_report",
                "time": metadata.get("time", ""),
                "title": path.name,
                "summary": summary,
                "path": path.as_posix(),
                "model": metadata.get("model", metadata.get("requested model", "")),
                "route": metadata.get("route", ""),
            }
        )
    return events


def _collect_run_events(task_id: str, owner_hint: str | None = None) -> list[dict[str, Any]]:
    run_index_path = Path("state") / "tasks" / task_id / "run_index.yaml"
    data = read_yaml(run_index_path)
    runs = data.get("runs", []) if isinstance(data, dict) else []
    events: list[dict[str, Any]] = []

    for item in runs:
        if not isinstance(item, dict):
            continue
        run_meta_path = item.get("run_meta_path")
        if not isinstance(run_meta_path, str):
            continue
        run_meta = read_yaml(run_meta_path)
        role = str(run_meta.get("role", ""))
        if owner_hint and role and owner_hint != role:
            continue

        events.append(
            {
                "id": str(run_meta.get("run_id", "")),
                "type": "run_meta",
                "time": str(run_meta.get("ended_at") or run_meta.get("started_at") or ""),
                "title": str(run_meta.get("command", ""))[:120],
                "summary": f"role={role}, exit={run_meta.get('exit_code', '')}",
                "path": run_meta_path,
                "role": role,
                "status": "success" if int(run_meta.get("exit_code", 1)) == 0 else "failed",
            }
        )
    return events


def _collect_review_events(task_id: str, subtask_id: str | None = None) -> list[dict[str, Any]]:
    data = load_task_subtasks(task_id)
    subtasks = data.get("subtasks", []) if isinstance(data, dict) else []
    events: list[dict[str, Any]] = []

    for sub in subtasks:
        if not isinstance(sub, dict):
            continue
        sid = str(sub.get("id", ""))
        if subtask_id and sid != subtask_id:
            continue
        for idx, entry in enumerate(sub.get("review_history", [])):
            if not isinstance(entry, dict):
                continue
            action = str(entry.get("action", ""))
            reviewer = str(entry.get("reviewer", ""))
            events.append(
                {
                    "id": f"review:{sid}:{idx}",
                    "type": "review",
                    "time": str(entry.get("time", "")),
                    "title": f"{action} by {reviewer}".strip(),
                    "summary": str(entry.get("notes", ""))[:240],
                    "subtask_id": sid,
                    "scope": str(entry.get("scope", "")),
                }
            )

    # Include latest queue status for pending subtask items.
    for item in load_review_queue():
        if str(item.get("scope", "task")) != "subtask":
            continue
        if str(item.get("task_id", "")) != task_id:
            continue
        sid = str(item.get("subtask_id", ""))
        if subtask_id and sid != subtask_id:
            continue
        events.append(
            {
                "id": f"queue:{item.get('id', '')}",
                "type": "review_queue",
                "time": str(item.get("updated_at") or item.get("created_at") or ""),
                "title": f"Queue {item.get('id')} ({item.get('status')})",
                "summary": str(item.get("title", "")),
                "subtask_id": sid,
                "scope": "subtask",
            }
        )

    return events


def _collect_verify_audit_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    verify_reports = sorted((Path("artifacts") / "test").glob("verify-*.md"))
    if verify_reports:
        path = verify_reports[-1]
        events.append(
            {
                "id": f"verify:{path.name}",
                "type": "verify",
                "time": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                "title": path.name,
                "summary": "Latest verify report",
                "path": path.as_posix(),
            }
        )

    audit_reports = sorted((Path("artifacts") / "audit").glob("*.md"))
    if audit_reports:
        path = audit_reports[-1]
        events.append(
            {
                "id": f"audit:{path.name}",
                "type": "audit",
                "time": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                "title": path.name,
                "summary": "Latest audit report",
                "path": path.as_posix(),
            }
        )

    return events


def list_task_activity(task_id: str, subtask_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    task = task_by_id(task_id)
    owner_hint: str | None = None
    if subtask_id:
        subtasks = load_task_subtasks(task_id).get("subtasks", [])
        for item in subtasks:
            if isinstance(item, dict) and item.get("id") == subtask_id:
                owner_hint = str(item.get("owner", ""))
                break

    events: list[dict[str, Any]] = []
    events.extend(_collect_ai_events(task_id))
    events.extend(_collect_run_events(task_id, owner_hint=owner_hint))
    events.extend(_collect_review_events(task_id, subtask_id=subtask_id))
    events.extend(_collect_verify_audit_events())

    for event in events:
        event.setdefault("task_id", task_id)
        event.setdefault("task_title", str(task.get("title", "")))

    events.sort(key=lambda item: _parse_time(str(item.get("time", ""))), reverse=True)
    return events[:limit]


def extract_task_images(task_id: str, subtask_id: str | None = None) -> list[str]:
    candidates: set[str] = set()

    outputs_root = Path("artifacts") / "tasks" / task_id / "outputs"
    if outputs_root.exists():
        for path in outputs_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in _IMAGE_EXTS:
                candidates.add(path.as_posix())
            if path.suffix.lower() == ".md":
                content = path.read_text(encoding="utf-8", errors="replace")
                for raw in _IMAGE_MD_RE.findall(content):
                    img_path = raw.strip()
                    if img_path.startswith("http://") or img_path.startswith("https://"):
                        continue
                    resolved = (path.parent / img_path).resolve()
                    if resolved.exists() and resolved.suffix.lower() in _IMAGE_EXTS:
                        candidates.add(resolved.as_posix())

    ai_root = Path("artifacts") / "tasks" / task_id / "ai"
    for md in sorted(ai_root.glob("*.md")) if ai_root.exists() else []:
        content = md.read_text(encoding="utf-8", errors="replace")
        for raw in _IMAGE_MD_RE.findall(content):
            img_path = raw.strip()
            if img_path.startswith("http://") or img_path.startswith("https://"):
                continue
            resolved = (md.parent / img_path).resolve()
            if resolved.exists() and resolved.suffix.lower() in _IMAGE_EXTS:
                candidates.add(resolved.as_posix())

    return sorted(candidates)


def _extract_explicit_pr_links(task_id: str) -> list[tuple[str, int]]:
    intake = load_task_intake(task_id)
    payload = json.dumps(intake, ensure_ascii=False) if intake else ""
    links: list[tuple[str, int]] = []
    for repo, number in _PULL_URL_RE.findall(payload):
        links.append((repo, int(number)))
    return links


def match_task_prs(task_id: str) -> list[dict[str, Any]]:
    task = task_by_id(task_id)
    intake = load_task_intake(task_id)
    project_slug = intake.get("project_slug") if isinstance(intake, dict) else None

    registry = read_yaml("state/PR_REGISTRY.yaml")
    prs = registry.get("prs", []) if isinstance(registry, dict) else []

    explicit = set(_extract_explicit_pr_links(task_id))
    project_repo = ""
    if isinstance(project_slug, str) and project_slug.strip():
        try:
            project = project_by_slug(project_slug.strip())
            project_repo = str(project.get("release_repo", ""))
        except Exception:
            project_repo = ""

    matched: list[dict[str, Any]] = []
    for item in prs:
        if not isinstance(item, dict):
            continue
        repo = str(item.get("repo", ""))
        number = int(item.get("number", -1)) if str(item.get("number", "")).isdigit() else -1

        reason = ""
        uncertain = False
        if (repo, number) in explicit:
            reason = "explicit"
            uncertain = False
        elif project_repo and repo == project_repo:
            reason = "project_repo"
            uncertain = False
        elif str(task.get("title", "")).lower().startswith("[rl-") and "rl-gridworld-qlearning" in repo:
            reason = "heuristic"
            uncertain = True
        elif str(item.get("role", "")) == "source":
            reason = "heuristic"
            uncertain = True

        if not reason:
            continue

        entry = dict(item)
        entry["match_reason"] = reason
        entry["uncertain"] = uncertain
        matched.append(entry)

    matched.sort(key=lambda row: str(row.get("updated_at", "")), reverse=True)
    return matched
