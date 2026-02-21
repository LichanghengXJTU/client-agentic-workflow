from __future__ import annotations

from pathlib import Path

from workflow.state_ops import read_yaml, save_tasks, task_by_id
from workflow.subtask_ops import aggregate_task_status, ensure_subtasks, update_subtask_status


def _seed_task(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    save_tasks(
        [
            {
                "id": "T-1000",
                "title": "demo task",
                "type": "code",
                "priority": "P0",
                "owner": "codex",
                "status": "todo",
                "acceptance": ["ok"],
                "evidence": [],
                "verification": [],
                "depends_on": [],
                "created_at": "2026-02-21",
                "updated_at": "2026-02-21",
            }
        ],
        path=state_dir / "TASKS.yaml",
    )


def test_ensure_subtasks_lazy_migration(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_task(tmp_path)

    subtasks = ensure_subtasks("T-1000", lazy=True)
    assert len(subtasks) >= 3

    subtask_file = Path("state/tasks/T-1000/subtasks.yaml")
    intake_file = Path("state/tasks/T-1000/intake.yaml")
    assert subtask_file.exists()
    assert intake_file.exists()

    data = read_yaml(subtask_file)
    assert data["task_id"] == "T-1000"


def test_update_subtask_status_updates_parent_task(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_task(tmp_path)
    subtasks = ensure_subtasks("T-1000", lazy=True)

    for sub in subtasks:
        update_subtask_status("T-1000", sub["id"], "done")

    task = task_by_id("T-1000")
    assert task["status"] == "done"
    assert aggregate_task_status(subtasks=[{"status": "todo"}], fallback="todo") == "todo"
