from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .audit import run_audit
from .checkpoint import create_checkpoint, list_checkpoints
from .git_ops import get_status, list_checkpoint_tags
from .review_ops import apply_review_action
from .rollback import HARD_CONFIRM_PHRASE, rollback
from .state_ops import (
    add_task,
    append_state_event,
    load_review_queue,
    load_tasks,
    sync_review_queue_from_tasks,
    update_task,
)
from .verify import run_verify


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _parse_list(values: list[str] | None) -> list[str]:
    return values or []


def cmd_status(_: argparse.Namespace) -> int:
    status = get_status()
    tags = list_checkpoint_tags(limit=1)
    payload = {
        "branch": status.branch,
        "head": status.head,
        "is_dirty": status.is_dirty,
        "dirty_count": status.dirty_count,
        "recent_checkpoint": tags[0] if tags else None,
    }
    _print(payload)
    return 0


def cmd_audit(_: argparse.Namespace) -> int:
    result = run_audit()
    _print(
        {
            "report": str(result.report_path),
            "p0": result.p0,
            "p1": result.p1,
            "p2": result.p2,
        }
    )
    return 1 if result.p0 > 0 else 0


def cmd_verify(_: argparse.Namespace) -> int:
    result = run_verify()
    _print(
        {
            "ok": result.ok,
            "report": str(result.report_path) if result.report_path else None,
            "steps": [
                {
                    "command": step.command,
                    "returncode": step.returncode,
                }
                for step in result.steps
            ],
        }
    )
    return 0 if result.ok else 1


def cmd_checkpoint(args: argparse.Namespace) -> int:
    result = create_checkpoint(
        summary=args.summary,
        commit_message=args.message,
        related_key_results=args.key_result or [],
    )
    _print(
        {
            "tag": result.tag,
            "snapshot_commit": result.snapshot_commit,
            "record_commit": result.record_commit,
            "wrote_snapshot_metadata": result.wrote_snapshot_metadata,
        }
    )
    return 0


def cmd_checkpoints(_: argparse.Namespace) -> int:
    _print(list_checkpoints())
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    result = rollback(anchor_ref=args.anchor, mode=args.mode, confirm_phrase=args.confirm_phrase)
    append_state_event(
        "Rollback Update",
        [
            f"Mode: {result.mode}",
            f"Anchor: {result.anchor_ref}",
            f"Branch: {result.branch}",
            f"Reverted count: {result.reverted_count}",
        ],
    )
    _print(
        {
            "mode": result.mode,
            "anchor_ref": result.anchor_ref,
            "branch": result.branch,
            "reverted_count": result.reverted_count,
        }
    )
    return 0


def cmd_tasks_list(_: argparse.Namespace) -> int:
    _print({"tasks": load_tasks()})
    return 0


def cmd_tasks_add(args: argparse.Namespace) -> int:
    item = add_task(
        title=args.title,
        task_type=args.type,
        priority=args.priority,
        owner=args.owner,
        status=args.status,
        acceptance=_parse_list(args.acceptance),
        evidence=_parse_list(args.evidence),
        verification=_parse_list(args.verification),
        depends_on=_parse_list(args.depends_on),
    )
    append_state_event("Task Added", [f"Task: {item['id']}", f"Title: {item['title']}"])
    _print(item)
    return 0


def cmd_tasks_update(args: argparse.Namespace) -> int:
    updates: dict[str, Any] = {}
    for key in ["title", "type", "priority", "owner", "status"]:
        value = getattr(args, key)
        if value is not None:
            updates[key] = value

    if args.acceptance is not None:
        updates["acceptance"] = args.acceptance
    if args.evidence is not None:
        updates["evidence"] = args.evidence
    if args.verification is not None:
        updates["verification"] = args.verification
    if args.depends_on is not None:
        updates["depends_on"] = args.depends_on

    item = update_task(args.id, updates)
    append_state_event("Task Updated", [f"Task: {item['id']}", f"Status: {item['status']}"])
    _print(item)
    return 0


def cmd_review_sync(_: argparse.Namespace) -> int:
    items = sync_review_queue_from_tasks()
    _print({"items": items, "count": len(items)})
    return 0


def cmd_review_list(_: argparse.Namespace) -> int:
    _print({"items": load_review_queue()})
    return 0


def cmd_review_approve(args: argparse.Namespace) -> int:
    result = apply_review_action(args.id, args.reviewer, "Approve", args.notes or "")
    _print(result.__dict__)
    return 0


def cmd_review_rework(args: argparse.Namespace) -> int:
    result = apply_review_action(args.id, args.reviewer, "Rework", args.notes or "")
    _print(result.__dict__)
    return 0


def cmd_review_reject(args: argparse.Namespace) -> int:
    if not args.anchor:
        raise ValueError("Reject requires --anchor to trigger cascade restart from a checkpoint/commit.")
    result = apply_review_action(args.id, args.reviewer, "Reject", args.notes or "", anchor=args.anchor)
    _print(result.__dict__)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m workflow")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Show git/workflow status")
    p_status.set_defaults(func=cmd_status)

    p_audit = sub.add_parser("audit", help="Run local audit and generate markdown report")
    p_audit.set_defaults(func=cmd_audit)

    p_verify = sub.add_parser("verify", help="Run pytest + derivation verification checks")
    p_verify.set_defaults(func=cmd_verify)

    p_checkpoint = sub.add_parser("checkpoint", help="Create a checkpoint commit/tag + state records")
    p_checkpoint.add_argument("--summary", required=True, help="Checkpoint summary")
    p_checkpoint.add_argument(
        "--message",
        default=None,
        help="Commit message for staged changes before checkpoint (optional)",
    )
    p_checkpoint.add_argument(
        "--key-result",
        action="append",
        help="Related KEY_RESULTS id (repeatable), e.g. KR-0001",
    )
    p_checkpoint.set_defaults(func=cmd_checkpoint)

    p_checkpoints = sub.add_parser("checkpoints", help="List checkpoint tags with commit/date/subject")
    p_checkpoints.set_defaults(func=cmd_checkpoints)

    p_rollback = sub.add_parser("rollback", help="Rollback from a checkpoint/tag/commit")
    p_rollback.add_argument("--anchor", required=True, help="Tag or commit used as rollback anchor")
    p_rollback.add_argument("--mode", choices=["safe", "hard"], default="safe")
    p_rollback.add_argument(
        "--confirm-phrase",
        default=None,
        help=f"Required for hard rollback: {HARD_CONFIRM_PHRASE}",
    )
    p_rollback.set_defaults(func=cmd_rollback)

    p_tasks = sub.add_parser("tasks", help="List/add/update TASKS.yaml")
    tasks_sub = p_tasks.add_subparsers(dest="tasks_cmd", required=True)

    p_tasks_list = tasks_sub.add_parser("list", help="List tasks")
    p_tasks_list.set_defaults(func=cmd_tasks_list)

    p_tasks_add = tasks_sub.add_parser("add", help="Add a task")
    p_tasks_add.add_argument("--title", required=True)
    p_tasks_add.add_argument("--type", default="code")
    p_tasks_add.add_argument("--priority", default="P1")
    p_tasks_add.add_argument("--owner", default="codex")
    p_tasks_add.add_argument("--status", default="todo")
    p_tasks_add.add_argument("--acceptance", action="append", default=[])
    p_tasks_add.add_argument("--evidence", action="append", default=[])
    p_tasks_add.add_argument("--verification", action="append", default=[])
    p_tasks_add.add_argument("--depends-on", action="append", default=[])
    p_tasks_add.set_defaults(func=cmd_tasks_add)

    p_tasks_update = tasks_sub.add_parser("update", help="Update a task")
    p_tasks_update.add_argument("--id", required=True)
    p_tasks_update.add_argument("--title")
    p_tasks_update.add_argument("--type")
    p_tasks_update.add_argument("--priority")
    p_tasks_update.add_argument("--owner")
    p_tasks_update.add_argument("--status")
    p_tasks_update.add_argument("--acceptance", action="append")
    p_tasks_update.add_argument("--evidence", action="append")
    p_tasks_update.add_argument("--verification", action="append")
    p_tasks_update.add_argument("--depends-on", action="append")
    p_tasks_update.set_defaults(func=cmd_tasks_update)

    p_review = sub.add_parser("review-queue", help="Sync/list/approve/rework/reject review queue")
    review_sub = p_review.add_subparsers(dest="review_cmd", required=True)

    p_review_sync = review_sub.add_parser("sync", help="Sync review queue from TASKS waiting_review")
    p_review_sync.set_defaults(func=cmd_review_sync)

    p_review_list = review_sub.add_parser("list", help="List review queue")
    p_review_list.set_defaults(func=cmd_review_list)

    p_review_approve = review_sub.add_parser("approve", help="Approve a review item")
    p_review_approve.add_argument("--id", required=True)
    p_review_approve.add_argument("--reviewer", default="human")
    p_review_approve.add_argument("--notes", default="")
    p_review_approve.set_defaults(func=cmd_review_approve)

    p_review_rework = review_sub.add_parser("rework", help="Request rework for a review item")
    p_review_rework.add_argument("--id", required=True)
    p_review_rework.add_argument("--reviewer", default="human")
    p_review_rework.add_argument("--notes", default="")
    p_review_rework.set_defaults(func=cmd_review_rework)

    p_review_reject = review_sub.add_parser("reject", help="Reject a review item and optionally trigger rollback")
    p_review_reject.add_argument("--id", required=True)
    p_review_reject.add_argument("--reviewer", default="human")
    p_review_reject.add_argument("--notes", default="")
    p_review_reject.add_argument("--anchor", help="Rollback anchor tag/commit for cascade restart")
    p_review_reject.set_defaults(func=cmd_review_reject)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # pragma: no cover - CLI top-level guard
        _print({"error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
