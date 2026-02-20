from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List


class GitCommandError(RuntimeError):
    """Raised when a git subprocess exits with non-zero status."""


@dataclass
class GitStatus:
    branch: str
    head: str
    dirty_count: int
    is_dirty: bool


@dataclass
class CheckpointTag:
    tag: str
    commit: str
    date_iso: str
    subject: str


def run_cmd(args: list[str], cwd: str | Path | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    return proc


def _run_git(args: List[str], cwd: str | Path | None = None) -> str:
    proc = run_cmd(["git", *args], cwd=cwd)
    if proc.returncode != 0:
        raise GitCommandError(proc.stderr.strip() or proc.stdout.strip() or "git command failed")
    return proc.stdout.strip()


def get_status(cwd: str | Path | None = None) -> GitStatus:
    branch = _run_git(["branch", "--show-current"], cwd=cwd)
    head = _run_git(["rev-parse", "HEAD"], cwd=cwd)
    dirty_lines = _run_git(["status", "--porcelain"], cwd=cwd).splitlines()
    dirty_count = len([line for line in dirty_lines if line.strip()])
    return GitStatus(branch=branch, head=head, dirty_count=dirty_count, is_dirty=dirty_count > 0)


def get_repo_root(cwd: str | Path | None = None) -> Path:
    return Path(_run_git(["rev-parse", "--show-toplevel"], cwd=cwd))


def is_dirty(cwd: str | Path | None = None) -> bool:
    return bool(_run_git(["status", "--porcelain"], cwd=cwd).strip())


def dirty_count(cwd: str | Path | None = None) -> int:
    return len([line for line in _run_git(["status", "--porcelain"], cwd=cwd).splitlines() if line.strip()])


def add_all(cwd: str | Path | None = None) -> None:
    _run_git(["add", "-A"], cwd=cwd)


def commit(message: str, cwd: str | Path | None = None) -> str:
    _run_git(["commit", "-m", message], cwd=cwd)
    return _run_git(["rev-parse", "HEAD"], cwd=cwd)


def current_head(cwd: str | Path | None = None) -> str:
    return _run_git(["rev-parse", "HEAD"], cwd=cwd)


def short_sha(sha: str) -> str:
    return sha[:8]


def current_branch(cwd: str | Path | None = None) -> str:
    return _run_git(["branch", "--show-current"], cwd=cwd)


def create_annotated_tag(tag: str, target: str, message: str, cwd: str | Path | None = None) -> None:
    _run_git(["tag", "-a", tag, target, "-m", message], cwd=cwd)


def resolve_ref(ref: str, cwd: str | Path | None = None) -> str:
    return _run_git(["rev-parse", ref], cwd=cwd)


def list_checkpoint_tags(limit: int = 20, cwd: str | Path | None = None) -> list[str]:
    out = _run_git(["tag", "--list", "cp-*", "--sort=-creatordate"], cwd=cwd)
    tags = [line.strip() for line in out.splitlines() if line.strip()]
    return tags[:limit]


def list_checkpoint_tag_details(limit: int = 50, cwd: str | Path | None = None) -> list[CheckpointTag]:
    tags = list_checkpoint_tags(limit=limit, cwd=cwd)
    items: list[CheckpointTag] = []
    for tag in tags:
        fmt = "%H%x1f%cI%x1f%s"
        out = _run_git(["log", "-1", f"--pretty=format:{fmt}", tag], cwd=cwd)
        commit, date_iso, subject = out.split("\x1f", maxsplit=2)
        items.append(CheckpointTag(tag=tag, commit=commit, date_iso=date_iso, subject=subject))
    return items


def commits_after(ref: str, head: str = "HEAD", cwd: str | Path | None = None) -> list[str]:
    out = _run_git(["rev-list", "--reverse", f"{ref}..{head}"], cwd=cwd)
    return [line.strip() for line in out.splitlines() if line.strip()]


def create_branch(branch: str, start_point: str = "HEAD", cwd: str | Path | None = None) -> None:
    _run_git(["checkout", "-b", branch, start_point], cwd=cwd)


def revert_commit(sha: str, cwd: str | Path | None = None) -> None:
    _run_git(["revert", "--no-edit", sha], cwd=cwd)


def hard_reset(ref: str, cwd: str | Path | None = None) -> None:
    _run_git(["reset", "--hard", ref], cwd=cwd)


def remote_exists(name: str = "origin", cwd: str | Path | None = None) -> bool:
    proc = run_cmd(["git", "remote", "get-url", name], cwd=cwd)
    return proc.returncode == 0


def fetch(remote: str = "origin", cwd: str | Path | None = None) -> None:
    _run_git(["fetch", remote], cwd=cwd)


def pull_rebase(remote: str = "origin", branch: str | None = None, cwd: str | Path | None = None) -> None:
    if branch is None:
        branch = current_branch(cwd=cwd)
    _run_git(["pull", "--rebase", remote, branch], cwd=cwd)


def push(remote: str = "origin", branch: str | None = None, cwd: str | Path | None = None) -> None:
    if branch is None:
        branch = current_branch(cwd=cwd)
    _run_git(["push", remote, branch], cwd=cwd)


def git_log_name_only(limit: int = 10, cwd: str | Path | None = None) -> str:
    return _run_git(["log", f"-n{limit}", "--name-only", "--pretty=format:%h %cI %s"], cwd=cwd)


def slugify(text: str) -> str:
    raw = "".join(ch.lower() if ch.isalnum() else "-" for ch in text.strip())
    while "--" in raw:
        raw = raw.replace("--", "-")
    return raw.strip("-") or "checkpoint"


def checkpoint_tag_name(summary: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return f"cp-{ts}-{slugify(summary)[:24]}"


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True
