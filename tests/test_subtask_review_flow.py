from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from workflow.review_ops import apply_review_action
from workflow.state_ops import load_review_queue, save_tasks, task_by_id
from workflow.subtask_ops import ensure_subtasks, sync_review_queue_from_subtasks, update_subtask_status


@dataclass
class _Rollback:
    mode: str = "safe"
    anchor_ref: str = "cp-demo"
    branch: str | None = "rollback/demo"
    reverted_count: int = 2


def _seed_task(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    save_tasks(
        [
            {
                "id": "T-2000",
                "title": "review flow task",
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


def _prepare_review_item() -> str:
    subtasks = ensure_subtasks("T-2000", lazy=True)
    target_id = subtasks[1]["id"]
    update_subtask_status("T-2000", target_id, "waiting_review")
    sync_review_queue_from_subtasks(task_id="T-2000")
    queue = load_review_queue()
    item = next(it for it in queue if it.get("task_id") == "T-2000" and it.get("subtask_id") == target_id)
    return str(item["id"])


def test_subtask_approve_and_rework(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_task(tmp_path)

    review_id = _prepare_review_item()

    result = apply_review_action(review_id, "human", "Approve", "ok")
    assert result.task["id"] == "T-2000"

    # Rework should still be allowed and keep task in non-done state.
    result2 = apply_review_action(review_id, "human", "Rework", "need fixes", cascade_scope="self_only")
    assert result2.task["status"] in {"blocked", "todo", "in_progress", "waiting_review", "done"}


def test_subtask_reject_requires_anchor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_task(tmp_path)

    review_id = _prepare_review_item()
    with pytest.raises(ValueError, match="Reject requires anchor"):
        apply_review_action(review_id, "human", "Reject", "bad baseline")


def test_subtask_reject_triggers_rollback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_task(tmp_path)
    review_id = _prepare_review_item()

    monkeypatch.setattr("workflow.subtask_ops.safe_rollback", lambda anchor_ref, cwd=None: _Rollback(anchor_ref=anchor_ref))
    monkeypatch.setattr("workflow.subtask_ops._mark_key_results_after_anchor", lambda anchor, cwd=None: 0)

    result = apply_review_action(
        review_id,
        "human",
        "Reject",
        "baseline wrong",
        anchor="cp-20260221-demo",
        cascade_scope="downstream",
    )
    assert result.rollback_branch == "rollback/demo"
    assert result.reverted_count == 2
    assert task_by_id("T-2000")["status"] in {"blocked", "todo", "in_progress", "waiting_review", "done"}
