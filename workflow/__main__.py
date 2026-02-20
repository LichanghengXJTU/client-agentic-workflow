from __future__ import annotations

import argparse
import json
import sys

from .audit import run_audit
from .git_ops import get_status, list_checkpoint_tags


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m workflow")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Show git/workflow status")
    p_status.set_defaults(func=cmd_status)

    p_audit = sub.add_parser("audit", help="Run local audit and generate markdown report")
    p_audit.set_defaults(func=cmd_audit)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
