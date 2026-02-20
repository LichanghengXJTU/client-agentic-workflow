from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .git_ops import current_head
from .pr_ops import upsert_pr_registry
from .project_ops import project_by_slug, update_project


@dataclass
class ReleaseBootstrapResult:
    project: str
    release_repo: str
    visibility: str
    default_branch: str
    created: bool


@dataclass
class ReleasePublishResult:
    project: str
    release_repo: str
    branch: str
    source_head: str
    release_head: str
    changed_files: int


@dataclass
class ReleasePRResult:
    project: str
    release_repo: str
    number: int
    url: str
    state: str
    head_ref: str
    base_ref: str


def _run(cmd: list[str], cwd: str | Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"command failed: {' '.join(cmd)}")
    return proc.stdout.strip()


def _remote_owner(cwd: str | Path | None = None) -> str:
    remote = _run(["git", "remote", "get-url", "origin"], cwd=cwd)
    if remote.startswith("git@github.com:"):
        payload = remote.split("git@github.com:", maxsplit=1)[1]
        return payload.split("/", maxsplit=1)[0]
    if remote.startswith("https://github.com/"):
        payload = remote.split("https://github.com/", maxsplit=1)[1]
        return payload.split("/", maxsplit=1)[0]
    raise RuntimeError(f"Unsupported remote origin URL: {remote}")


def _repo_exists(repo: str) -> bool:
    proc = subprocess.run(
        ["gh", "repo", "view", repo, "--json", "nameWithOwner"],
        text=True,
        capture_output=True,
    )
    return proc.returncode == 0


def _repo_git_url(release_repo: str) -> str:
    if release_repo.startswith("/") or release_repo.startswith("./") or release_repo.startswith("../"):
        return release_repo
    if release_repo.startswith("file://"):
        return release_repo
    if release_repo.endswith(".git") and (release_repo.startswith("ssh://") or release_repo.startswith("https://")):
        return release_repo
    return f"git@github.com:{release_repo}.git"


def _has_remote_branch(release_repo: str, branch: str) -> bool:
    try:
        out = _run(["git", "ls-remote", "--heads", _repo_git_url(release_repo), f"refs/heads/{branch}"])
    except RuntimeError:
        return False
    return bool(out.strip())


def _ensure_default_branch_initialized(
    release_repo: str,
    default_branch: str,
    project_slug: str,
    cwd: str | Path | None = None,
) -> None:
    if _has_remote_branch(release_repo, default_branch):
        return

    with tempfile.TemporaryDirectory(prefix="release-bootstrap-") as tmp:
        temp_root = Path(tmp)
        release_dir = temp_root / "release"
        _run(["git", "clone", _repo_git_url(release_repo), str(release_dir)], cwd=cwd)
        _ensure_git_identity(release_dir, source_cwd=cwd)
        _run(["git", "checkout", "--orphan", default_branch], cwd=release_dir)
        (release_dir / "README.md").write_text(
            f"# {project_slug} release repository\n\nInitialized by workflow release bootstrap.\n",
            encoding="utf-8",
        )
        _run(["git", "add", "README.md"], cwd=release_dir)
        _run(["git", "commit", "-m", "chore: initialize release base branch"], cwd=release_dir)
        _run(["git", "push", "-u", "origin", default_branch], cwd=release_dir)


def bootstrap_release_repo(
    project_slug: str,
    visibility: str = "public",
    default_branch: str = "main",
    release_repo: str | None = None,
    cwd: str | Path | None = None,
) -> ReleaseBootstrapResult:
    project = project_by_slug(project_slug)
    owner = _remote_owner(cwd=cwd)
    target_repo = release_repo or project.get("release_repo") or f"{owner}/{project_slug}-release"

    created = False
    if not _repo_exists(target_repo):
        _run(
            [
                "gh",
                "repo",
                "create",
                target_repo,
                f"--{visibility}",
                "--disable-issues",
                "--description",
                f"Release repository for project {project_slug}",
            ],
            cwd=cwd,
        )
        created = True

    _ensure_default_branch_initialized(
        release_repo=target_repo,
        default_branch=default_branch,
        project_slug=project_slug,
        cwd=cwd,
    )

    update_project(
        project_slug,
        {
            "release_repo": target_repo,
            "release_visibility": visibility,
            "release_default_branch": default_branch,
            "status": "active",
        },
    )

    return ReleaseBootstrapResult(
        project=project_slug,
        release_repo=target_repo,
        visibility=visibility,
        default_branch=default_branch,
        created=created,
    )


def _clear_dir_except_git(path: Path) -> None:
    for item in path.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def _copy_project_tree(src: Path, dst: Path) -> None:
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _read_git_config(key: str, cwd: str | Path | None = None) -> str:
    proc = subprocess.run(["git", "config", "--get", key], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _ensure_git_identity(target_repo: Path, source_cwd: str | Path | None = None) -> None:
    name = _read_git_config("user.name", cwd=source_cwd) or _read_git_config("user.name") or "workflow-bot"
    email = _read_git_config("user.email", cwd=source_cwd) or _read_git_config("user.email") or "workflow@example.com"
    _run(["git", "config", "user.name", name], cwd=target_repo)
    _run(["git", "config", "user.email", email], cwd=target_repo)


def _git_has_head(repo_dir: Path) -> bool:
    proc = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=repo_dir, capture_output=True, text=True)
    return proc.returncode == 0


def _latest_sync_branch(release_repo: str) -> str | None:
    out = _run(["git", "ls-remote", "--heads", _repo_git_url(release_repo), "refs/heads/sync/*"])
    branches: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        ref = line.split()[1]
        branches.append(ref.removeprefix("refs/heads/"))
    if not branches:
        return None
    return sorted(branches)[-1]


def publish_project_release(
    project_slug: str,
    cwd: str | Path | None = None,
) -> ReleasePublishResult:
    project = project_by_slug(project_slug)
    release_repo = str(project.get("release_repo", "")).strip()
    default_branch = str(project.get("release_default_branch", "main"))
    if not release_repo:
        raise RuntimeError(f"Project {project_slug} has no release_repo configured.")

    root = Path(cwd) if cwd else Path.cwd()
    source_path = root / str(project.get("local_path", ""))
    if not source_path.exists():
        raise RuntimeError(f"Project local_path does not exist: {source_path}")

    source_head = current_head(cwd=cwd)
    branch = f"sync/{datetime.now().strftime('%Y%m%d-%H%M')}-{source_head[:8]}"

    with tempfile.TemporaryDirectory(prefix="release-publish-") as tmp:
        temp_root = Path(tmp)
        release_dir = temp_root / "release"
        _run(["git", "clone", _repo_git_url(release_repo), str(release_dir)], cwd=cwd)
        _ensure_git_identity(release_dir, source_cwd=cwd)

        has_head = _git_has_head(release_dir)
        has_default = _has_remote_branch(release_repo, default_branch)

        if has_default:
            _run(["git", "checkout", "-B", default_branch, f"origin/{default_branch}"], cwd=release_dir)
            _run(["git", "checkout", "-b", branch], cwd=release_dir)
        elif has_head:
            _run(["git", "checkout", "-b", branch], cwd=release_dir)
        else:
            _run(["git", "checkout", "--orphan", branch], cwd=release_dir)

        _clear_dir_except_git(release_dir)
        _copy_project_tree(source_path, release_dir)

        _run(["git", "add", "-A"], cwd=release_dir)
        names = _run(["git", "diff", "--cached", "--name-only"], cwd=release_dir)
        changed_files = len([line for line in names.splitlines() if line.strip()])

        if changed_files > 0:
            _run(["git", "commit", "-m", f"sync: {project_slug} from {source_head[:8]}"], cwd=release_dir)

        _run(["git", "push", "-u", "origin", branch], cwd=release_dir)
        release_head = _run(["git", "rev-parse", "HEAD"], cwd=release_dir)

    return ReleasePublishResult(
        project=project_slug,
        release_repo=release_repo,
        branch=branch,
        source_head=source_head,
        release_head=release_head,
        changed_files=changed_files,
    )


def open_release_pr(
    project_slug: str,
    title: str,
    body: str,
    base: str | None = None,
    head: str | None = None,
    cwd: str | Path | None = None,
) -> ReleasePRResult:
    project = project_by_slug(project_slug)
    release_repo = str(project.get("release_repo", "")).strip()
    if not release_repo:
        raise RuntimeError(f"Project {project_slug} has no release_repo configured.")

    base_branch = base or str(project.get("release_default_branch", "main"))
    head_branch = head or _latest_sync_branch(release_repo)
    if not head_branch:
        raise RuntimeError("No release branch found. Run `workflow release publish` first or pass --head.")

    _run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            release_repo,
            "--title",
            title,
            "--body",
            body,
            "--base",
            base_branch,
            "--head",
            head_branch,
        ],
        cwd=cwd,
    )

    out = _run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            release_repo,
            "--state",
            "open",
            "--head",
            head_branch,
            "--json",
            "number,title,state,url,headRefName,baseRefName,headRefOid",
        ],
        cwd=cwd,
    )
    rows = json.loads(out)
    if not rows:
        raise RuntimeError("Unable to locate created release PR.")
    view = rows[0]

    upsert_pr_registry(
        {
            "number": view["number"],
            "title": view["title"],
            "state": view["state"],
            "url": view["url"],
            "head_ref": view["headRefName"],
            "base_ref": view["baseRefName"],
            "head_sha": view["headRefOid"],
            "repo": release_repo,
            "role": "release",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )

    return ReleasePRResult(
        project=project_slug,
        release_repo=release_repo,
        number=view["number"],
        url=view["url"],
        state=view["state"],
        head_ref=view["headRefName"],
        base_ref=view["baseRefName"],
    )
