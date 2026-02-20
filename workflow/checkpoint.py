from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .git_ops import (
    GitCommandError,
    add_all,
    checkpoint_tag_name,
    commit,
    create_annotated_tag,
    current_head,
    dirty_count,
    is_dirty,
    run_cmd,
)
from .state_ops import atomic_write_yaml, read_yaml


@dataclass
class CheckpointResult:
    tag: str
    snapshot_commit: str
    record_commit: str | None
    wrote_snapshot_metadata: bool


def _ensure_unique_tag(base_tag: str, cwd: str | Path | None = None) -> str:
    candidate = base_tag
    idx = 1
    while True:
        proc = run_cmd(["git", "rev-parse", "--verify", f"refs/tags/{candidate}"], cwd=cwd)
        if proc.returncode != 0:
            return candidate
        candidate = f"{base_tag}-{idx}"
        idx += 1


def _append_checkpoint_markdown(
    tag: str,
    commit_sha: str,
    summary: str,
    related_key_results: list[str],
    cwd: str | Path | None = None,
) -> None:
    root = Path(cwd) if cwd else Path.cwd()
    checkpoints_md = root / "state" / "CHECKPOINTS.md"
    checkpoints_md.parent.mkdir(parents=True, exist_ok=True)
    if not checkpoints_md.exists():
        checkpoints_md.write_text(
            "# CHECKPOINTS\n\n| Time | Tag | Commit | Summary | Related Key Results |\n|---|---|---|---|---|\n",
            encoding="utf-8",
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    row = (
        f"| {now} | `{tag}` | `{commit_sha[:8]}` | {summary} | "
        f"{', '.join(related_key_results) if related_key_results else '-'} |\n"
    )
    with checkpoints_md.open("a", encoding="utf-8") as f:
        f.write(row)


def _append_state_snapshot_line(tag: str, commit_sha: str, summary: str, cwd: str | Path | None = None) -> None:
    root = Path(cwd) if cwd else Path.cwd()
    state_md = root / "state" / "STATE.md"
    if not state_md.exists():
        state_md.write_text("# STATE Snapshot\n\n", encoding="utf-8")
    with state_md.open("a", encoding="utf-8") as f:
        f.write(
            "\n## Checkpoint Update\n"
            f"- Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- Tag: `{tag}`\n"
            f"- Snapshot commit: `{commit_sha}`\n"
            f"- Summary: {summary}\n"
        )


def _update_key_results_checkpoint_tags(
    related_key_results: list[str],
    tag: str,
    commit_sha: str,
    cwd: str | Path | None = None,
) -> None:
    if not related_key_results:
        return

    root = Path(cwd) if cwd else Path.cwd()
    path = root / "state" / "KEY_RESULTS.yaml"
    data = read_yaml(path)
    results = data.get("results", [])
    changed = False

    for item in results:
        if item.get("id") in related_key_results:
            tags = item.setdefault("checkpoint_tags", [])
            if tag not in tags:
                tags.append(tag)
                changed = True
            item["last_confirmed_commit"] = commit_sha
            changed = True

    if changed:
        atomic_write_yaml(path, data)


def create_checkpoint(
    summary: str,
    commit_message: str | None = None,
    related_key_results: list[str] | None = None,
    cwd: str | Path | None = None,
) -> CheckpointResult:
    related_key_results = related_key_results or []

    snapshot_commit: str
    if is_dirty(cwd=cwd):
        add_all(cwd=cwd)
        msg = commit_message or f"checkpoint: {summary}"
        snapshot_commit = commit(msg, cwd=cwd)
    else:
        snapshot_commit = current_head(cwd=cwd)

    tag = _ensure_unique_tag(checkpoint_tag_name(summary), cwd=cwd)
    _append_checkpoint_markdown(tag, snapshot_commit, summary, related_key_results, cwd=cwd)
    _append_state_snapshot_line(tag, snapshot_commit, summary, cwd=cwd)
    _update_key_results_checkpoint_tags(related_key_results, tag, snapshot_commit, cwd=cwd)

    record_commit: str | None = None
    if dirty_count(cwd=cwd) > 0:
        add_all(cwd=cwd)
        record_commit = commit(f"chore: record checkpoint {tag}", cwd=cwd)

    create_annotated_tag(tag=tag, target=snapshot_commit, message=summary, cwd=cwd)
    return CheckpointResult(
        tag=tag,
        snapshot_commit=snapshot_commit,
        record_commit=record_commit,
        wrote_snapshot_metadata=record_commit is not None,
    )


def list_checkpoints(cwd: str | Path | None = None) -> list[dict[str, str]]:
    from .git_ops import list_checkpoint_tag_details

    tags = list_checkpoint_tag_details(cwd=cwd)
    return [
        {
            "tag": item.tag,
            "commit": item.commit,
            "date": item.date_iso,
            "subject": item.subject,
        }
        for item in tags
    ]


def resolve_checkpoint(ref: str, cwd: str | Path | None = None) -> str:
    proc = run_cmd(["git", "rev-parse", "--verify", ref], cwd=cwd)
    if proc.returncode != 0:
        raise GitCommandError(f"Unknown checkpoint/tag/commit: {ref}")
    return proc.stdout.strip()
