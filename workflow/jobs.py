from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .git_ops import process_exists
from .state_ops import JOBS_PATH, atomic_write_yaml, read_yaml


@dataclass
class JobResult:
    id: str
    command: str
    pid: int
    status: str
    log_path: str


def _load_jobs(path: Path = JOBS_PATH) -> list[dict[str, Any]]:
    data = read_yaml(path)
    return data.get("jobs", [])


def _save_jobs(items: list[dict[str, Any]], path: Path = JOBS_PATH) -> None:
    atomic_write_yaml(path, {"jobs": items})


def _next_job_id(items: list[dict[str, Any]]) -> str:
    nums = []
    for item in items:
        jid = str(item.get("id", ""))
        if jid.startswith("J-"):
            tail = jid.split("-", maxsplit=1)[1]
            if tail.isdigit():
                nums.append(int(tail))
    return f"J-{(max(nums) + 1 if nums else 1):04d}"


def refresh_jobs(path: Path = JOBS_PATH) -> list[dict[str, Any]]:
    jobs = _load_jobs(path)
    changed = False
    for item in jobs:
        if item.get("status") == "running":
            pid = int(item.get("pid", 0))
            if not process_exists(pid):
                item["status"] = "exited"
                item["updated_at"] = datetime.now().isoformat(timespec="seconds")
                changed = True
    if changed:
        _save_jobs(jobs, path)
    return jobs


def start_job(command: str, workdir: str | None = None, path: Path = JOBS_PATH) -> JobResult:
    jobs = refresh_jobs(path)
    jid = _next_job_id(jobs)

    logs_dir = Path("artifacts") / "test"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"job-{jid}.log"
    with log_path.open("a", encoding="utf-8") as log:
        proc = subprocess.Popen(  # noqa: S602 - intentional shell mode for user commands
            command,
            cwd=workdir,
            shell=True,
            stdout=log,
            stderr=log,
            start_new_session=True,
            text=True,
        )

    item = {
        "id": jid,
        "command": command,
        "pid": proc.pid,
        "status": "running",
        "log_path": str(log_path),
        "workdir": workdir or str(Path.cwd()),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    jobs.append(item)
    _save_jobs(jobs, path)

    return JobResult(id=jid, command=command, pid=proc.pid, status="running", log_path=str(log_path))


def list_jobs(path: Path = JOBS_PATH) -> list[dict[str, Any]]:
    return refresh_jobs(path)


def stop_job(job_id: str, force: bool = False, path: Path = JOBS_PATH) -> dict[str, Any]:
    jobs = refresh_jobs(path)
    for item in jobs:
        if item.get("id") != job_id:
            continue

        pid = int(item.get("pid", 0))
        if item.get("status") != "running":
            return item

        try:
            if os.name == "posix":
                sig = signal.SIGKILL if force else signal.SIGTERM
                os.killpg(pid, sig)
            else:
                sig = signal.SIGTERM
                os.kill(pid, sig)
            item["status"] = "stopped"
        except ProcessLookupError:
            item["status"] = "exited"
        item["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _save_jobs(jobs, path)
        return item

    raise KeyError(f"Job not found: {job_id}")


def tail_job_log(job_id: str, lines: int = 80, path: Path = JOBS_PATH) -> str:
    jobs = _load_jobs(path)
    for item in jobs:
        if item.get("id") == job_id:
            log_path = Path(item.get("log_path", ""))
            if not log_path.exists():
                return ""
            text = log_path.read_text(encoding="utf-8", errors="replace")
            all_lines = text.splitlines()
            return "\n".join(all_lines[-lines:])
    raise KeyError(f"Job not found: {job_id}")
