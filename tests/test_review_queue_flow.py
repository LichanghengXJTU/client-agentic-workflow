from __future__ import annotations

from pathlib import Path

from workflow.state_ops import (
    append_human_review_log,
    load_review_queue,
    save_review_queue,
    save_tasks,
    set_review_item_status,
    sync_review_queue_from_tasks,
    update_task,
)


def test_review_queue_sync_and_action(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    tasks_path = state_dir / "TASKS.yaml"
    queue_path = state_dir / "REVIEW_QUEUE.yaml"
    log_path = state_dir / "HUMAN_REVIEW_LOG.md"

    save_tasks(
        [
            {
                "id": "T-0001",
                "title": "Need review",
                "type": "code",
                "priority": "P0",
                "owner": "codex",
                "status": "waiting_review",
                "acceptance": ["ok"],
                "evidence": [],
                "verification": [],
                "depends_on": [],
                "created_at": "2026-02-20",
                "updated_at": "2026-02-20",
            }
        ],
        path=tasks_path,
    )

    items = sync_review_queue_from_tasks(tasks_path=tasks_path, queue_path=queue_path)
    assert len(items) == 1
    assert items[0]["task_id"] == "T-0001"

    set_review_item_status(items[0]["id"], "approved", queue_path=queue_path)
    queue = load_review_queue(path=queue_path)
    assert queue[0]["status"] == "approved"

    update_task("T-0001", {"status": "done"}, path=tasks_path)
    append_human_review_log("human", items[0]["id"], "Approve", "looks good", path=log_path)
    assert "Approve" in log_path.read_text(encoding="utf-8")


def test_review_queue_subtask_scope_compatibility(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    queue_path = state_dir / "REVIEW_QUEUE.yaml"

    save_review_queue(
        [
            {
                "id": "RQ-0001",
                "task_id": "T-0001",
                "subtask_id": "ST-001",
                "title": "subtask review",
                "scope": "subtask",
                "status": "pending",
                "created_at": "2026-02-22",
                "updated_at": "2026-02-22",
            }
        ],
        path=queue_path,
    )

    item = set_review_item_status("RQ-0001", "approve", queue_path=queue_path)
    assert item["scope"] == "subtask"
    assert item["subtask_id"] == "ST-001"
    assert item["status"] == "approve"


def test_sync_review_queue_from_tasks_preserves_subtask_items(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    tasks_path = state_dir / "TASKS.yaml"
    queue_path = state_dir / "REVIEW_QUEUE.yaml"

    save_tasks(
        [
            {
                "id": "T-0001",
                "title": "Need review",
                "type": "code",
                "priority": "P0",
                "owner": "codex",
                "status": "waiting_review",
                "acceptance": ["ok"],
                "evidence": [],
                "verification": [],
                "depends_on": [],
                "created_at": "2026-02-20",
                "updated_at": "2026-02-20",
            }
        ],
        path=tasks_path,
    )
    save_review_queue(
        [
            {
                "id": "RQ-0099",
                "task_id": "T-0100",
                "subtask_id": "ST-001",
                "title": "subtask item",
                "scope": "subtask",
                "status": "pending",
                "created_at": "2026-02-20",
                "updated_at": "2026-02-20",
            }
        ],
        path=queue_path,
    )

    merged = sync_review_queue_from_tasks(tasks_path=tasks_path, queue_path=queue_path)
    assert any(item.get("scope") == "subtask" for item in merged)
    assert any(item.get("task_id") == "T-0001" for item in merged)
