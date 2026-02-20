from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List


@dataclass
class GitStatus:
    branch: str
    head: str
    dirty_count: int
    is_dirty: bool


def _run_git(args: List[str]) -> str:
    proc = subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    return proc.stdout.strip()


def get_status() -> GitStatus:
    branch = _run_git(["branch", "--show-current"])
    head = _run_git(["rev-parse", "HEAD"])
    dirty_lines = _run_git(["status", "--porcelain"]).splitlines()
    dirty_count = len([line for line in dirty_lines if line.strip()])
    return GitStatus(branch=branch, head=head, dirty_count=dirty_count, is_dirty=dirty_count > 0)


def list_checkpoint_tags(limit: int = 20) -> list[str]:
    out = _run_git(["tag", "--list", "cp-*", "--sort=-creatordate"])
    tags = [line.strip() for line in out.splitlines() if line.strip()]
    return tags[:limit]
