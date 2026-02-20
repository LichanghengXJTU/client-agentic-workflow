from __future__ import annotations

from pathlib import Path

from workflow.project_ops import add_project, list_projects, scaffold_project, update_project
from workflow.schemas import validate_project_registry_data
from workflow.state_ops import load_project_registry


def test_project_registry_add_update_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()

    item = add_project(
        slug="rl-gridworld-qlearning",
        title="RL Gridworld Q-learning",
        local_path="projects/rl-gridworld-qlearning",
        release_repo="demo/rl-gridworld-qlearning-release",
        release_visibility="public",
        release_default_branch="main",
        status="active",
    )
    assert item["id"] == "P-0001"

    saved = list_projects()
    assert len(saved) == 1
    assert saved[0]["slug"] == "rl-gridworld-qlearning"

    updated = update_project("rl-gridworld-qlearning", {"status": "archived"})
    assert updated["status"] == "archived"

    stored = load_project_registry()
    assert stored[0]["status"] == "archived"


def test_project_scaffold_creates_templates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    root = scaffold_project("rl-gridworld-qlearning", "RL Gridworld Q-learning")
    assert (root / "prompts").exists()
    assert (root / "derivations").exists()
    assert (root / "experiments").exists()
    assert (root / "reports").exists()
    assert (root / "prompts" / "prompt-01-initiation.md").exists()


def test_project_registry_schema_validation() -> None:
    valid = {
        "projects": [
            {
                "id": "P-0001",
                "slug": "rl-gridworld-qlearning",
                "title": "RL Gridworld Q-learning",
                "local_path": "projects/rl-gridworld-qlearning",
                "release_repo": "LichanghengXJTU/rl-gridworld-qlearning-release",
                "release_visibility": "public",
                "release_default_branch": "main",
                "status": "active",
                "created_at": "2026-02-21",
                "updated_at": "2026-02-21",
            }
        ]
    }
    ok, issues = validate_project_registry_data(valid)
    assert ok
    assert not issues

    invalid = {
        "projects": [
            {
                "id": "X-1",
                "slug": "bad slug",
                "title": "",
                "local_path": "",
                "release_repo": "not_repo",
                "release_visibility": "world",
                "release_default_branch": "",
                "status": "running",
                "created_at": "2026/02/21",
                "updated_at": "today",
            }
        ]
    }
    ok2, issues2 = validate_project_registry_data(invalid)
    assert not ok2
    paths = {issue.path for issue in issues2}
    assert "projects[0].id" in paths
    assert "projects[0].slug" in paths
    assert "projects[0].release_repo" in paths
