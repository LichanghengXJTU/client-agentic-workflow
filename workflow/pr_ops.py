from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .git_ops import current_branch, current_head, detect_default_base_branch, is_ancestor, remote_exists
from .state_ops import PR_REGISTRY_PATH, atomic_write_yaml, read_yaml


def _run_gh(args: list[str], cwd: str | Path | None = None) -> str:
    proc = subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "gh command failed")
    return proc.stdout.strip()


def _load_registry(path: Path = PR_REGISTRY_PATH) -> list[dict[str, Any]]:
    data = read_yaml(path)
    return data.get("prs", [])


def _save_registry(items: list[dict[str, Any]], path: Path = PR_REGISTRY_PATH) -> None:
    atomic_write_yaml(path, {"prs": items})


def _upsert_registry(entry: dict[str, Any], path: Path = PR_REGISTRY_PATH) -> None:
    prs = _load_registry(path)
    number = int(entry["number"])
    found = False
    for item in prs:
        if int(item.get("number", -1)) == number:
            item.update(entry)
            found = True
            break
    if not found:
        prs.append(entry)
    _save_registry(prs, path)


def open_pr(
    title: str,
    body: str,
    base: str | None = None,
    head: str | None = None,
    draft: bool = False,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    if not remote_exists(cwd=cwd):
        raise RuntimeError("Git remote `origin` is not configured. Configure remote before opening PR.")

    base_branch = base or detect_default_base_branch(cwd=cwd)
    head_branch = head or current_branch(cwd=cwd)

    args = [
        "pr",
        "create",
        "--title",
        title,
        "--body",
        body,
        "--base",
        base_branch,
        "--head",
        head_branch,
    ]
    if draft:
        args.append("--draft")
    _run_gh(args, cwd=cwd)

    view = json.loads(
        _run_gh(
            [
                "pr",
                "view",
                "--json",
                "number,title,state,url,headRefName,baseRefName,headRefOid",
            ],
            cwd=cwd,
        )
    )

    entry = {
        "number": view["number"],
        "title": view["title"],
        "state": view["state"],
        "url": view["url"],
        "head_ref": view["headRefName"],
        "base_ref": view["baseRefName"],
        "head_sha": view["headRefOid"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    _upsert_registry(entry)
    return entry


def update_pr(
    number: int,
    title: str | None = None,
    body: str | None = None,
    add_comment: str | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    if title or body:
        args = ["pr", "edit", str(number)]
        if title:
            args.extend(["--title", title])
        if body:
            args.extend(["--body", body])
        _run_gh(args, cwd=cwd)

    if add_comment:
        _run_gh(["pr", "comment", str(number), "--body", add_comment], cwd=cwd)

    view = json.loads(
        _run_gh(
            [
                "pr",
                "view",
                str(number),
                "--json",
                "number,title,state,url,headRefName,baseRefName,headRefOid",
            ],
            cwd=cwd,
        )
    )
    entry = {
        "number": view["number"],
        "title": view["title"],
        "state": view["state"],
        "url": view["url"],
        "head_ref": view["headRefName"],
        "base_ref": view["baseRefName"],
        "head_sha": view["headRefOid"],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    _upsert_registry(entry)
    return entry


def list_prs(cwd: str | Path | None = None) -> list[dict[str, Any]]:
    prs = _load_registry()
    return sorted(prs, key=lambda x: x.get("updated_at", ""), reverse=True)


def close_pr(number: int, comment: str | None = None, cwd: str | Path | None = None) -> None:
    if comment:
        _run_gh(["pr", "comment", str(number), "--body", comment], cwd=cwd)
    _run_gh(["pr", "close", str(number)], cwd=cwd)

    prs = _load_registry()
    for item in prs:
        if int(item.get("number", -1)) == number:
            item["state"] = "CLOSED"
            item["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _save_registry(prs)


def close_superseded_prs(anchor_ref: str, cwd: str | Path | None = None) -> list[int]:
    closed: list[int] = []
    prs = _load_registry()
    for item in prs:
        number = int(item.get("number", -1))
        state = str(item.get("state", "")).upper()
        head_sha = item.get("head_sha", "")

        if state != "OPEN" or not head_sha:
            continue
        try:
            if is_ancestor(anchor_ref, head_sha, cwd=cwd):
                close_pr(
                    number,
                    comment=(
                        "Closed automatically by reject-cascade rollback. "
                        f"Anchor: `{anchor_ref}`. This PR is superseded."
                    ),
                    cwd=cwd,
                )
                closed.append(number)
        except Exception:
            continue

    return closed


def current_pr_context(cwd: str | Path | None = None) -> dict[str, str]:
    return {
        "branch": current_branch(cwd=cwd),
        "head": current_head(cwd=cwd),
        "base": detect_default_base_branch(cwd=cwd),
    }
