from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .git_ops import (
    commits_after,
    create_branch,
    hard_reset,
    revert_commit,
    slugify,
)

HARD_CONFIRM_PHRASE = "I_UNDERSTAND_HARD_RESET"


@dataclass
class RollbackResult:
    mode: str
    anchor_ref: str
    branch: str | None
    reverted_count: int


def safe_rollback(anchor_ref: str, cwd: str | Path | None = None) -> RollbackResult:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    branch = f"rollback/{slugify(anchor_ref)[:24]}-{ts}"
    create_branch(branch=branch, cwd=cwd)

    to_revert = commits_after(anchor_ref, head="HEAD", cwd=cwd)
    reverted = 0
    for sha in to_revert:
        revert_commit(sha, cwd=cwd)
        reverted += 1

    return RollbackResult(mode="safe", anchor_ref=anchor_ref, branch=branch, reverted_count=reverted)


def hard_rollback(
    anchor_ref: str,
    confirm_phrase: str,
    cwd: str | Path | None = None,
) -> RollbackResult:
    if confirm_phrase != HARD_CONFIRM_PHRASE:
        raise ValueError(
            "Hard rollback blocked. Provide the exact confirmation phrase "
            f"{HARD_CONFIRM_PHRASE!r}."
        )
    hard_reset(anchor_ref, cwd=cwd)
    return RollbackResult(mode="hard", anchor_ref=anchor_ref, branch=None, reverted_count=0)


def rollback(
    anchor_ref: str,
    mode: str = "safe",
    confirm_phrase: str | None = None,
    cwd: str | Path | None = None,
) -> RollbackResult:
    if mode == "safe":
        return safe_rollback(anchor_ref=anchor_ref, cwd=cwd)
    if mode == "hard":
        return hard_rollback(anchor_ref=anchor_ref, confirm_phrase=confirm_phrase or "", cwd=cwd)
    raise ValueError(f"Unsupported rollback mode: {mode}")
