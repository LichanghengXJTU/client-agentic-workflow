from __future__ import annotations

import subprocess
from pathlib import Path

from workflow.project_ops import add_project
from workflow.release_ops import bootstrap_release_repo, open_release_pr, publish_project_release
from workflow.state_ops import read_yaml


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)
    return proc.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "src"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "state").mkdir()
    return repo


def test_release_bootstrap_updates_project_registry(tmp_path: Path, monkeypatch) -> None:
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)

    add_project(
        slug="rl-gridworld-qlearning",
        title="RL",
        local_path="projects/rl-gridworld-qlearning",
        release_repo="",
    )

    monkeypatch.setattr("workflow.release_ops._remote_owner", lambda cwd=None: "demo")
    monkeypatch.setattr("workflow.release_ops._repo_exists", lambda repo: False)
    monkeypatch.setattr(
        "workflow.release_ops._ensure_default_branch_initialized",
        lambda release_repo, default_branch, project_slug, cwd=None: None,
    )

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], cwd=None) -> str:
        calls.append(cmd)
        return ""

    monkeypatch.setattr("workflow.release_ops._run", fake_run)

    result = bootstrap_release_repo("rl-gridworld-qlearning", visibility="public", default_branch="main")
    assert result.created
    assert result.release_repo == "demo/rl-gridworld-qlearning-release"

    projects = read_yaml("state/PROJECT_REGISTRY.yaml")["projects"]
    assert projects[0]["release_repo"] == "demo/rl-gridworld-qlearning-release"
    assert any(cmd[:3] == ["gh", "repo", "create"] for cmd in calls)


def test_release_publish_exports_project_to_remote(tmp_path: Path, monkeypatch) -> None:
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)

    project_dir = repo / "projects" / "rl-gridworld-qlearning"
    (project_dir / "experiments").mkdir(parents=True)
    (project_dir / "README.md").write_text("# RL Project\n", encoding="utf-8")
    (project_dir / "experiments" / "run.py").write_text("print('ok')\n", encoding="utf-8")

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add project")

    remote = tmp_path / "release.git"
    _git(tmp_path, "init", "--bare", str(remote))

    add_project(
        slug="rl-gridworld-qlearning",
        title="RL",
        local_path="projects/rl-gridworld-qlearning",
        release_repo=str(remote),
    )

    result = publish_project_release("rl-gridworld-qlearning", cwd=repo)
    assert result.changed_files >= 2
    assert result.branch.startswith("sync/")

    refs = _git(tmp_path, "--git-dir", str(remote), "for-each-ref", "--format=%(refname:short)", "refs/heads")
    assert result.branch in refs.splitlines()


def test_open_release_pr_records_registry(tmp_path: Path, monkeypatch) -> None:
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo)

    add_project(
        slug="rl-gridworld-qlearning",
        title="RL",
        local_path="projects/rl-gridworld-qlearning",
        release_repo="demo/rl-gridworld-qlearning-release",
    )

    monkeypatch.setattr("workflow.release_ops._latest_sync_branch", lambda _: "sync/20260221-0000-deadbeef")

    def fake_run(cmd: list[str], cwd=None) -> str:
        if cmd[:3] == ["gh", "pr", "list"]:
            return (
                '[{"number":2,"title":"release","state":"OPEN",'
                '"url":"https://github.com/demo/repo/pull/2",'
                '"headRefName":"sync/20260221-0000-deadbeef",'
                '"baseRefName":"main","headRefOid":"abc123"}]'
            )
        return ""

    monkeypatch.setattr("workflow.release_ops._run", fake_run)

    result = open_release_pr(
        "rl-gridworld-qlearning",
        title="release",
        body="body",
        base="main",
        head=None,
    )
    assert result.number == 2

    prs = read_yaml("state/PR_REGISTRY.yaml").get("prs", [])
    assert prs
    assert prs[0]["repo"] == "demo/rl-gridworld-qlearning-release"
    assert prs[0]["role"] == "release"
