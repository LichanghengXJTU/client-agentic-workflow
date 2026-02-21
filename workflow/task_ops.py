from __future__ import annotations

import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .citation_ops import file_sha256
from .state_ops import atomic_write_yaml, read_yaml

TASK_STATE_ROOT = Path("state") / "tasks"
TASK_ARTIFACT_ROOT = Path("artifacts") / "tasks"
TASK_ROLES = {"planner", "retriever", "implementer", "critic", "scribe"}


@dataclass
class TaskRunResult:
    run_id: str
    task_id: str
    role: str
    exit_code: int
    run_meta_path: str
    stdout_log: str
    stderr_log: str


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _next_run_id() -> str:
    return f"RUN-{datetime.now().strftime('%Y%m%d-%H%M%S%f')}"


def _safe_markdown(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ").strip()


def _task_state_dir(task_id: str) -> Path:
    return TASK_STATE_ROOT / task_id


def _task_artifact_dir(task_id: str) -> Path:
    return TASK_ARTIFACT_ROOT / task_id


def task_required_state_files(task_id: str) -> list[Path]:
    base = _task_state_dir(task_id)
    return [
        base / "brief.yaml",
        base / "worklog.md",
        base / "evidence_map.yaml",
        base / "notes.md",
        base / "handoff.yaml",
        base / "run_index.yaml",
    ]


def scaffold_task_record(task_id: str, title: str = "...", owner: str = "codex") -> dict[str, str]:
    state_dir = _task_state_dir(task_id)
    artifact_dir = _task_artifact_dir(task_id)
    state_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (artifact_dir / "outputs").mkdir(parents=True, exist_ok=True)
    (artifact_dir / "runs").mkdir(parents=True, exist_ok=True)
    (artifact_dir / "cache").mkdir(parents=True, exist_ok=True)

    brief_path = state_dir / "brief.yaml"
    if not brief_path.exists():
        atomic_write_yaml(
            brief_path,
            {
                "task_id": task_id,
                "title": title,
                "owner": owner,
                "goal": "...",
                "success_criteria": ["..."],
                "scope_in": [],
                "scope_out": [],
                "constraints": [],
                "long_inputs": [],
                "assumptions": [],
            },
        )

    worklog_path = state_dir / "worklog.md"
    if not worklog_path.exists():
        worklog_path.write_text(
            "\n".join(
                [
                    f"# Worklog: {task_id}",
                    "",
                    "| Time | Phase | Action | Evidence | Decision | Risk | Verification | Next |",
                    "|---|---|---|---|---|---|---|---|",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    evidence_map_path = state_dir / "evidence_map.yaml"
    if not evidence_map_path.exists():
        atomic_write_yaml(evidence_map_path, {"task_id": task_id, "claims": []})

    notes_path = state_dir / "notes.md"
    if not notes_path.exists():
        notes_path.write_text(f"# Notes: {task_id}\n\n## Retrieved Facts\n\n## Open Questions\n", encoding="utf-8")

    handoff_path = state_dir / "handoff.yaml"
    if not handoff_path.exists():
        atomic_write_yaml(handoff_path, {"task_id": task_id, "handoffs": []})

    run_index_path = state_dir / "run_index.yaml"
    if not run_index_path.exists():
        atomic_write_yaml(run_index_path, {"task_id": task_id, "runs": []})

    return {
        "brief": str(brief_path),
        "worklog": str(worklog_path),
        "evidence_map": str(evidence_map_path),
        "notes": str(notes_path),
        "handoff": str(handoff_path),
        "run_index": str(run_index_path),
    }


def _path_entry(path: Path) -> dict[str, str]:
    rel = path.as_posix()
    if path.exists() and path.is_file():
        return {"path": rel, "sha256": file_sha256(path)}
    return {"path": rel, "sha256": "missing"}


def _append_run_index(task_id: str, run_entry: dict[str, Any]) -> None:
    path = _task_state_dir(task_id) / "run_index.yaml"
    data = read_yaml(path)
    if not data:
        data = {"task_id": task_id, "runs": []}
    runs = data.setdefault("runs", [])
    runs.append(run_entry)
    atomic_write_yaml(path, data)


def _append_worklog_row(
    task_id: str,
    phase: str,
    action: str,
    evidence: str = "",
    decision: str = "",
    risk: str = "",
    verification: str = "",
    next_step: str = "",
) -> None:
    worklog_path = _task_state_dir(task_id) / "worklog.md"
    if not worklog_path.exists():
        scaffold_task_record(task_id=task_id)
    row = (
        f"| {_now_iso()} | {_safe_markdown(phase)} | {_safe_markdown(action)} | {_safe_markdown(evidence)} | "
        f"{_safe_markdown(decision)} | {_safe_markdown(risk)} | {_safe_markdown(verification)} | "
        f"{_safe_markdown(next_step)} |"
    )
    with worklog_path.open("a", encoding="utf-8") as f:
        f.write(row + "\n")


def record_task_run(
    task_id: str,
    role: str,
    command: str,
    args: list[str],
    workdir: str,
    seed: int | None,
    inputs: list[Path],
    outputs: list[Path],
    exit_code: int,
    stdout: str,
    stderr: str,
    started_at: str | None = None,
    ended_at: str | None = None,
    add_worklog: bool = True,
) -> TaskRunResult:
    if role not in TASK_ROLES:
        raise ValueError(f"Unsupported role: {role}. Expected one of {sorted(TASK_ROLES)}.")

    scaffold_task_record(task_id=task_id)
    run_id = _next_run_id()
    run_dir = _task_artifact_dir(task_id) / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    stdout_log = run_dir / "stdout.log"
    stderr_log = run_dir / "stderr.log"
    stdout_log.write_text(stdout or "", encoding="utf-8")
    stderr_log.write_text(stderr or "", encoding="utf-8")

    started = started_at or _now_iso()
    ended = ended_at or _now_iso()
    run_meta_path = run_dir / "run_meta.yaml"

    run_meta = {
        "run_id": run_id,
        "task_id": task_id,
        "role": role,
        "started_at": started,
        "ended_at": ended,
        "command": command,
        "args": args,
        "workdir": workdir,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "key_presence": {"OPENAI_API_KEY": "present" if os.getenv("OPENAI_API_KEY") else "absent"},
        },
        "seed": seed,
        "inputs": [_path_entry(path) for path in inputs],
        "outputs": [_path_entry(path) for path in outputs],
        "exit_code": exit_code,
        "logs": {"stdout": stdout_log.as_posix(), "stderr": stderr_log.as_posix()},
    }
    atomic_write_yaml(run_meta_path, run_meta)

    _append_run_index(
        task_id,
        {
            "run_id": run_id,
            "role": role,
            "run_meta_path": run_meta_path.as_posix(),
            "status": "success" if exit_code == 0 else "failed",
        },
    )

    if add_worklog:
        _append_worklog_row(
            task_id=task_id,
            phase="Do",
            action=f"{role}: {command}",
            evidence=run_meta_path.as_posix(),
            verification=f"exit_code={exit_code}",
            next_step="Critic handoff" if exit_code == 0 else "Rework",
        )

    return TaskRunResult(
        run_id=run_id,
        task_id=task_id,
        role=role,
        exit_code=exit_code,
        run_meta_path=run_meta_path.as_posix(),
        stdout_log=stdout_log.as_posix(),
        stderr_log=stderr_log.as_posix(),
    )


def run_task_command(
    task_id: str,
    role: str,
    command: str,
    workdir: str | None = None,
    seed: int | None = None,
) -> TaskRunResult:
    cwd = workdir or "."
    started = _now_iso()
    proc = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True)  # noqa: S602
    ended = _now_iso()

    task_state = _task_state_dir(task_id)
    inputs = [
        task_state / "brief.yaml",
        task_state / "handoff.yaml",
        task_state / "evidence_map.yaml",
    ]

    return record_task_run(
        task_id=task_id,
        role=role,
        command=command,
        args=[],
        workdir=cwd,
        seed=seed,
        inputs=inputs,
        outputs=[],
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        started_at=started,
        ended_at=ended,
        add_worklog=True,
    )
