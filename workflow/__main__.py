from __future__ import annotations

import argparse
import json
import sys

from .checkpoint import create_checkpoint, list_checkpoints
from .audit import run_audit
from .git_ops import get_status, list_checkpoint_tags
from .rollback import HARD_CONFIRM_PHRASE, rollback


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
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_audit(_: argparse.Namespace) -> int:
    result = run_audit()
    print(
        json.dumps(
            {
                "report": str(result.report_path),
                "p0": result.p0,
                "p1": result.p1,
                "p2": result.p2,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if result.p0 > 0 else 0


def cmd_checkpoint(args: argparse.Namespace) -> int:
    result = create_checkpoint(
        summary=args.summary,
        commit_message=args.message,
        related_key_results=args.key_result or [],
    )
    print(
        json.dumps(
            {
                "tag": result.tag,
                "snapshot_commit": result.snapshot_commit,
                "record_commit": result.record_commit,
                "wrote_snapshot_metadata": result.wrote_snapshot_metadata,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_checkpoints(_: argparse.Namespace) -> int:
    items = list_checkpoints()
    print(json.dumps(items, ensure_ascii=False, indent=2))
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    result = rollback(anchor_ref=args.anchor, mode=args.mode, confirm_phrase=args.confirm_phrase)
    print(
        json.dumps(
            {
                "mode": result.mode,
                "anchor_ref": result.anchor_ref,
                "branch": result.branch,
                "reverted_count": result.reverted_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m workflow")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Show git/workflow status")
    p_status.set_defaults(func=cmd_status)

    p_audit = sub.add_parser("audit", help="Run local audit and generate markdown report")
    p_audit.set_defaults(func=cmd_audit)

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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # pragma: no cover - last-resort CLI handler
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
