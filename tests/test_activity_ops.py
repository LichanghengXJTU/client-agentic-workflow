from __future__ import annotations

from pathlib import Path

from workflow.activity_ops import extract_task_images, list_task_activity, match_task_prs
from workflow.state_ops import atomic_write_yaml, save_tasks


def _seed_task(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    save_tasks(
        [
            {
                "id": "T-3000",
                "title": "[RL-007] activity center",
                "type": "code",
                "priority": "P1",
                "owner": "codex",
                "status": "in_progress",
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


def test_activity_pr_and_image_extraction(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_task(tmp_path)

    # intake + subtasks
    task_state = Path("state/tasks/T-3000")
    task_state.mkdir(parents=True, exist_ok=True)
    atomic_write_yaml(
        task_state / "intake.yaml",
        {
            "task_id": "T-3000",
            "project_slug": "rl-gridworld-qlearning",
            "sections": {
                "core_task": "related PR https://github.com/demo/repo/pull/8",
            },
        },
    )
    atomic_write_yaml(
        task_state / "subtasks.yaml",
        {
            "task_id": "T-3000",
            "subtasks": [
                {
                    "id": "ST-001",
                    "title": "demo",
                    "owner": "implementer",
                    "status": "in_progress",
                    "depends_on": [],
                    "prompt_contract": {},
                    "latest_summary": "",
                    "latest_event_at": "",
                    "review_history": [
                        {
                            "time": "2026-02-22T00:10:00",
                            "reviewer": "human",
                            "action": "Rework",
                            "notes": "add tests",
                            "scope": "downstream",
                        }
                    ],
                }
            ],
        },
    )

    # run meta
    run_dir = Path("artifacts/tasks/T-3000/runs/RUN-20260222-001000")
    run_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_yaml(
        run_dir / "run_meta.yaml",
        {
            "run_id": "RUN-20260222-001000",
            "task_id": "T-3000",
            "role": "implementer",
            "started_at": "2026-02-22T00:09:00",
            "ended_at": "2026-02-22T00:11:00",
            "command": "python -m workflow verify",
            "exit_code": 0,
        },
    )
    atomic_write_yaml(
        task_state / "run_index.yaml",
        {
            "task_id": "T-3000",
            "runs": [
                {
                    "run_id": "RUN-20260222-001000",
                    "role": "implementer",
                    "run_meta_path": "artifacts/tasks/T-3000/runs/RUN-20260222-001000/run_meta.yaml",
                    "status": "success",
                }
            ],
        },
    )

    # ai report
    ai_dir = Path("artifacts/tasks/T-3000/ai")
    ai_dir.mkdir(parents=True, exist_ok=True)
    (ai_dir / "ai-20260222-001200.md").write_text(
        """# AI Task Report

- Time: 2026-02-22T00:12:00
- Route: codex
- Model: gpt-5.2-codex

## Output
Implemented dashboard.
""",
        encoding="utf-8",
    )

    # image output
    output_dir = Path("artifacts/tasks/T-3000/outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "figure.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    # registries
    atomic_write_yaml(
        Path("state/PR_REGISTRY.yaml"),
        {
            "prs": [
                {
                    "number": 8,
                    "title": "explicit",
                    "state": "OPEN",
                    "url": "https://github.com/demo/repo/pull/8",
                    "repo": "demo/repo",
                    "role": "source",
                    "updated_at": "2026-02-22T00:20:00",
                },
                {
                    "number": 1,
                    "title": "release",
                    "state": "OPEN",
                    "url": "https://github.com/LichanghengXJTU/rl-gridworld-qlearning-release/pull/1",
                    "repo": "LichanghengXJTU/rl-gridworld-qlearning-release",
                    "role": "release",
                    "updated_at": "2026-02-22T00:30:00",
                },
            ]
        },
    )
    atomic_write_yaml(
        Path("state/PROJECT_REGISTRY.yaml"),
        {
            "projects": [
                {
                    "id": "P-0001",
                    "slug": "rl-gridworld-qlearning",
                    "title": "RL",
                    "local_path": "projects/rl-gridworld-qlearning",
                    "release_repo": "LichanghengXJTU/rl-gridworld-qlearning-release",
                    "release_visibility": "public",
                    "release_default_branch": "main",
                    "status": "active",
                    "created_at": "2026-02-21",
                    "updated_at": "2026-02-21",
                }
            ]
        },
    )

    events = list_task_activity("T-3000", subtask_id="ST-001", limit=20)
    assert events
    assert any(item["type"] == "ai_report" for item in events)
    assert any(item["type"] == "run_meta" for item in events)

    images = extract_task_images("T-3000")
    assert any(path.endswith("figure.png") for path in images)

    prs = match_task_prs("T-3000")
    assert prs
    assert any(item["match_reason"] == "explicit" for item in prs)
    assert any(item["match_reason"] == "project_repo" for item in prs)
