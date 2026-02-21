from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .ai import run_ai_audit, run_ai_plan, run_ai_task
from .audit import run_audit
from .checkpoint import create_checkpoint, list_checkpoints
from .git_ops import fetch, get_status, list_checkpoint_tags, pull_rebase, remote_exists
from .jobs import list_jobs, start_job, stop_job, tail_job_log
from .kb_ops import ingest_kb_sources, query_kb
from .pr_ops import close_superseded_prs, current_pr_context, list_prs, open_pr, update_pr
from .project_ops import add_project, list_projects, scaffold_project, update_project as update_project_record
from .release_ops import bootstrap_release_repo, open_release_pr, publish_project_release
from .review_ops import apply_review_action
from .rollback import HARD_CONFIRM_PHRASE, rollback
from .state_ops import (
    add_task,
    append_state_event,
    load_review_queue,
    load_tasks,
    read_yaml,
    sync_review_queue_from_tasks,
    task_by_id,
    update_task,
)
from .task_ops import TASK_ROLES, run_task_command
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


def cmd_sync(_: argparse.Namespace) -> int:
    if not remote_exists():
        _print({"synced": False, "reason": "remote `origin` not configured"})
        return 0
    fetch("origin")
    pull_rebase("origin")
    append_state_event("Sync Update", ["Operation: git fetch + git pull --rebase", "Remote: origin"])
    _print({"synced": True, "mode": "fetch+pull --rebase"})
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


def cmd_jobs_start(args: argparse.Namespace) -> int:
    command = " ".join(args.command)
    if not command.strip():
        raise ValueError("jobs start requires a command after `--` or as trailing args.")
    result = start_job(command=command, workdir=args.workdir)
    append_state_event("Job Started", [f"Job: {result.id}", f"Command: {result.command}"])
    _print(result.__dict__)
    return 0


def cmd_jobs_list(_: argparse.Namespace) -> int:
    _print({"jobs": list_jobs()})
    return 0


def cmd_jobs_stop(args: argparse.Namespace) -> int:
    item = stop_job(job_id=args.id, force=args.force)
    append_state_event("Job Stopped", [f"Job: {args.id}", f"Force: {args.force}"])
    _print(item)
    return 0


def cmd_jobs_logs(args: argparse.Namespace) -> int:
    _print({"id": args.id, "logs": tail_job_log(args.id, lines=args.lines)})
    return 0


def cmd_task_run(args: argparse.Namespace) -> int:
    result = run_task_command(
        task_id=args.id,
        role=args.role,
        command=args.cmd,
        workdir=args.workdir,
        seed=args.seed,
    )
    _print(result.__dict__)
    return 0 if result.exit_code == 0 else 1


def cmd_kb_ingest(args: argparse.Namespace) -> int:
    result = ingest_kb_sources(
        sources=args.src or [],
        task_id=args.task,
        external_root=args.external_root,
        purpose=args.purpose,
        trust_level=args.trust_level,
        license_name=args.license,
    )
    _print(result.__dict__)
    return 0


def cmd_kb_query(args: argparse.Namespace) -> int:
    result = query_kb(
        query=args.q,
        task_id=args.task,
        top_k=args.top_k,
        purpose=args.purpose,
        trust_level=args.trust_level,
        license_name=args.license,
    )
    _print({"report_path": result.report_path, "hits": result.hits})
    return 0


def cmd_pr_open(args: argparse.Namespace) -> int:
    context = current_pr_context()
    entry = open_pr(
        title=args.title,
        body=args.body,
        base=args.base,
        head=args.head,
        draft=args.draft,
    )
    append_state_event(
        "PR Opened",
        [
            f"PR: #{entry['number']}",
            f"Head: {entry['head_ref']}",
            f"Base: {entry['base_ref']}",
            f"Current branch: {context['branch']}",
        ],
    )
    _print(entry)
    return 0


def cmd_pr_update(args: argparse.Namespace) -> int:
    entry = update_pr(number=args.number, title=args.title, body=args.body, add_comment=args.comment)
    append_state_event("PR Updated", [f"PR: #{args.number}"])
    _print(entry)
    return 0


def cmd_pr_list(_: argparse.Namespace) -> int:
    _print({"prs": list_prs()})
    return 0


def cmd_pr_close_superseded(args: argparse.Namespace) -> int:
    closed = close_superseded_prs(anchor_ref=args.anchor)
    append_state_event("PR Close Superseded", [f"Anchor: {args.anchor}", f"Closed PRs: {closed}"])
    _print({"anchor": args.anchor, "closed_prs": closed})
    return 0


def cmd_project_list(_: argparse.Namespace) -> int:
    _print({"projects": list_projects()})
    return 0


def cmd_project_add(args: argparse.Namespace) -> int:
    item = add_project(
        slug=args.slug,
        title=args.title,
        local_path=args.local_path,
        release_repo=args.release_repo,
        release_visibility=args.release_visibility,
        release_default_branch=args.release_default_branch,
        status=args.status,
    )
    append_state_event("Project Added", [f"Project: {item['slug']}", f"Release repo: {item['release_repo']}"])
    _print(item)
    return 0


def cmd_project_update(args: argparse.Namespace) -> int:
    updates: dict[str, Any] = {}
    for key in ["title", "local_path", "release_repo", "release_visibility", "release_default_branch", "status"]:
        value = getattr(args, key)
        if value is not None:
            updates[key] = value
    item = update_project_record(args.slug, updates=updates)
    append_state_event("Project Updated", [f"Project: {item['slug']}", f"Status: {item['status']}"])
    _print(item)
    return 0


def cmd_project_scaffold(args: argparse.Namespace) -> int:
    root = scaffold_project(slug=args.slug, title=args.title, base_dir=args.base_dir)
    append_state_event("Project Scaffold", [f"Project: {args.slug}", f"Path: {root}"])
    _print({"slug": args.slug, "path": str(root)})
    return 0


def cmd_release_bootstrap(args: argparse.Namespace) -> int:
    result = bootstrap_release_repo(
        project_slug=args.project,
        visibility=args.visibility,
        default_branch=args.default_branch,
        release_repo=args.release_repo,
    )
    append_state_event(
        "Release Bootstrap",
        [
            f"Project: {result.project}",
            f"Release repo: {result.release_repo}",
            f"Created: {result.created}",
            f"Visibility: {result.visibility}",
        ],
    )
    _print(result.__dict__)
    return 0


def cmd_release_publish(args: argparse.Namespace) -> int:
    result = publish_project_release(project_slug=args.project)
    append_state_event(
        "Release Publish",
        [
            f"Project: {result.project}",
            f"Release repo: {result.release_repo}",
            f"Branch: {result.branch}",
            f"Source head: {result.source_head}",
            f"Release head: {result.release_head}",
            f"Changed files: {result.changed_files}",
        ],
    )
    _print(result.__dict__)
    return 0


def cmd_release_pr(args: argparse.Namespace) -> int:
    result = open_release_pr(
        project_slug=args.project,
        title=args.title,
        body=args.body,
        base=args.base,
        head=args.head,
    )
    append_state_event(
        "Release PR Opened",
        [
            f"Project: {result.project}",
            f"Release repo: {result.release_repo}",
            f"PR: #{result.number}",
            f"URL: {result.url}",
        ],
    )
    _print(result.__dict__)
    return 0


def _read_optional_file(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    return p.read_text(encoding="utf-8")


def cmd_ai_plan(args: argparse.Namespace) -> int:
    extra = _read_optional_file(args.input_file)
    tasks = read_yaml("state/TASKS.yaml")
    prompt = args.prompt or (
        "请基于当前任务队列生成下一阶段 PLAN，要求可执行、可验证、可回滚。\\n\\n"
        f"TASKS:\\n{json.dumps(tasks, ensure_ascii=False, indent=2)}\\n\\n"
        f"EXTRA:\\n{extra}\\n"
    )
    result = run_ai_plan(prompt=prompt, output_path="state/PLAN.md")
    append_state_event(
        "AI Plan",
        [
            f"Model: {result.model}",
            f"Output: {result.output_path}",
            f"Budget spend USD: {result.spend_usd}",
            f"Budget ratio: {result.budget_ratio:.3f}",
            f"Message: {result.message}",
        ],
    )
    _print(result.__dict__)
    if not result.ok and "missing" in result.message.lower():
        return 0
    return 0 if result.ok else 1


def cmd_ai_audit(args: argparse.Namespace) -> int:
    extra = _read_optional_file(args.input_file)
    tasks = read_yaml("state/TASKS.yaml")
    key_results = read_yaml("state/KEY_RESULTS.yaml")
    prompt = args.prompt or (
        "请审计当前工作流状态，重点检查风险、验证覆盖率、审批闭环和回滚安全。\\n\\n"
        f"TASKS:\\n{json.dumps(tasks, ensure_ascii=False, indent=2)}\\n\\n"
        f"KEY_RESULTS:\\n{json.dumps(key_results, ensure_ascii=False, indent=2)}\\n\\n"
        f"EXTRA:\\n{extra}\\n"
    )
    result = run_ai_audit(prompt=prompt)
    append_state_event(
        "AI Audit",
        [
            f"Model: {result.model}",
            f"Output: {result.output_path}",
            f"Budget spend USD: {result.spend_usd}",
            f"Budget ratio: {result.budget_ratio:.3f}",
            f"Message: {result.message}",
        ],
    )
    _print(result.__dict__)
    if not result.ok and "missing" in result.message.lower():
        return 0
    return 0 if result.ok else 1


def cmd_ai_task(args: argparse.Namespace) -> int:
    extra = _read_optional_file(args.input_file)
    task = task_by_id(args.id)
    intent = args.intent
    prompt = args.prompt or (
        "请围绕以下任务输出可执行、可验证、可回滚的工作结果。\\n\\n"
        f"TASK:\\n{json.dumps(task, ensure_ascii=False, indent=2)}\\n\\n"
        f"INTENT:\\n{intent or 'design'}\\n\\n"
        f"EXTRA:\\n{extra}\\n"
    )
    result = run_ai_task(
        task_id=args.id,
        intent=intent,
        prompt=prompt,
        output_path=args.output,
    )
    append_state_event(
        "AI Task",
        [
            f"Task: {args.id}",
            f"Route: {result.route_key}",
            f"Requested model: {result.requested_model}",
            f"Model: {result.model}",
            f"Selection note: {result.selection_note}",
            f"Output: {result.output_path}",
            f"Budget spend USD: {result.spend_usd}",
            f"Budget ratio: {result.budget_ratio:.3f}",
            f"Message: {result.message}",
        ],
    )
    _print(result.__dict__)
    if not result.ok and "missing" in result.message.lower():
        return 0
    return 0 if result.ok else 1


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

    p_sync = sub.add_parser("sync", help="Fetch + pull --rebase from origin for cross-device continuity")
    p_sync.set_defaults(func=cmd_sync)

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

    p_jobs = sub.add_parser("jobs", help="Manage local background jobs")
    jobs_sub = p_jobs.add_subparsers(dest="jobs_cmd", required=True)

    p_jobs_start = jobs_sub.add_parser("start", help="Start a background job")
    p_jobs_start.add_argument("--workdir", default=None, help="Working directory for command")
    p_jobs_start.add_argument("command", nargs=argparse.REMAINDER, help="Command to run in background")
    p_jobs_start.set_defaults(func=cmd_jobs_start)

    p_jobs_list = jobs_sub.add_parser("list", help="List jobs")
    p_jobs_list.set_defaults(func=cmd_jobs_list)

    p_jobs_stop = jobs_sub.add_parser("stop", help="Stop a running job")
    p_jobs_stop.add_argument("--id", required=True)
    p_jobs_stop.add_argument("--force", action="store_true")
    p_jobs_stop.set_defaults(func=cmd_jobs_stop)

    p_jobs_logs = jobs_sub.add_parser("logs", help="Show latest log lines for a job")
    p_jobs_logs.add_argument("--id", required=True)
    p_jobs_logs.add_argument("--lines", type=int, default=80)
    p_jobs_logs.set_defaults(func=cmd_jobs_logs)

    p_task = sub.add_parser("task", help="Task-level role run metadata and execution helpers")
    task_sub = p_task.add_subparsers(dest="task_cmd", required=True)

    p_task_run = task_sub.add_parser("run", help="Run a command under a task role and record run_meta")
    p_task_run.add_argument("--id", required=True, help="Task id like T-0015")
    p_task_run.add_argument("--role", required=True, choices=sorted(TASK_ROLES))
    p_task_run.add_argument("--cmd", required=True, help="Shell command to execute")
    p_task_run.add_argument("--workdir", default=None, help="Working directory for command")
    p_task_run.add_argument("--seed", type=int, default=None, help="Optional reproducibility seed")
    p_task_run.set_defaults(func=cmd_task_run)

    p_kb = sub.add_parser("kb", help="Knowledge-base ingest/chunk/index/query operations")
    kb_sub = p_kb.add_subparsers(dest="kb_cmd", required=True)

    p_kb_ingest = kb_sub.add_parser("ingest", help="Ingest files into KB manifest and index")
    p_kb_ingest.add_argument("--task", help="Optional task id for run_meta binding")
    p_kb_ingest.add_argument("--src", action="append", required=True, help="Source file/dir (repeatable)")
    p_kb_ingest.add_argument("--external-root", help="Optional external root for oversized files")
    p_kb_ingest.add_argument("--purpose", default="background")
    p_kb_ingest.add_argument("--trust-level", default="medium")
    p_kb_ingest.add_argument("--license", default="unknown")
    p_kb_ingest.set_defaults(func=cmd_kb_ingest)

    p_kb_query = kb_sub.add_parser("query", help="Query KB index and return citations")
    p_kb_query.add_argument("--task", help="Optional task id for run_meta binding")
    p_kb_query.add_argument("--q", required=True, help="Query text")
    p_kb_query.add_argument("--top-k", type=int, default=8)
    p_kb_query.add_argument("--purpose")
    p_kb_query.add_argument("--trust-level")
    p_kb_query.add_argument("--license")
    p_kb_query.set_defaults(func=cmd_kb_query)

    p_pr = sub.add_parser("pr", help="Open/update/list/close superseded pull requests via gh CLI")
    pr_sub = p_pr.add_subparsers(dest="pr_cmd", required=True)

    p_pr_open = pr_sub.add_parser("open", help="Open PR from current branch")
    p_pr_open.add_argument("--title", required=True)
    p_pr_open.add_argument("--body", required=True)
    p_pr_open.add_argument("--base")
    p_pr_open.add_argument("--head")
    p_pr_open.add_argument("--draft", action="store_true")
    p_pr_open.set_defaults(func=cmd_pr_open)

    p_pr_update = pr_sub.add_parser("update", help="Update PR title/body/comment")
    p_pr_update.add_argument("--number", type=int, required=True)
    p_pr_update.add_argument("--title")
    p_pr_update.add_argument("--body")
    p_pr_update.add_argument("--comment")
    p_pr_update.set_defaults(func=cmd_pr_update)

    p_pr_list = pr_sub.add_parser("list", help="List PRs tracked by workflow registry")
    p_pr_list.set_defaults(func=cmd_pr_list)

    p_pr_close = pr_sub.add_parser("close-superseded", help="Close open PRs superseded by rollback anchor")
    p_pr_close.add_argument("--anchor", required=True)
    p_pr_close.set_defaults(func=cmd_pr_close_superseded)

    p_project = sub.add_parser("project", help="Manage multi-project registry and local scaffolds")
    project_sub = p_project.add_subparsers(dest="project_cmd", required=True)

    p_project_list = project_sub.add_parser("list", help="List projects from PROJECT_REGISTRY")
    p_project_list.set_defaults(func=cmd_project_list)

    p_project_add = project_sub.add_parser("add", help="Register a project")
    p_project_add.add_argument("--slug", required=True)
    p_project_add.add_argument("--title", required=True)
    p_project_add.add_argument("--local-path", required=True)
    p_project_add.add_argument("--release-repo", required=True)
    p_project_add.add_argument("--release-visibility", default="public")
    p_project_add.add_argument("--release-default-branch", default="main")
    p_project_add.add_argument("--status", default="active")
    p_project_add.set_defaults(func=cmd_project_add)

    p_project_update = project_sub.add_parser("update", help="Update a project by slug")
    p_project_update.add_argument("--slug", required=True)
    p_project_update.add_argument("--title")
    p_project_update.add_argument("--local-path")
    p_project_update.add_argument("--release-repo")
    p_project_update.add_argument("--release-visibility")
    p_project_update.add_argument("--release-default-branch")
    p_project_update.add_argument("--status")
    p_project_update.set_defaults(func=cmd_project_update)

    p_project_scaffold = project_sub.add_parser("scaffold", help="Create project directory scaffold and prompt templates")
    p_project_scaffold.add_argument("--slug", required=True)
    p_project_scaffold.add_argument("--title", required=True)
    p_project_scaffold.add_argument("--base-dir", default="projects")
    p_project_scaffold.set_defaults(func=cmd_project_scaffold)

    p_release = sub.add_parser("release", help="Cross-repo release automation for project exports")
    release_sub = p_release.add_subparsers(dest="release_cmd", required=True)

    p_release_bootstrap = release_sub.add_parser("bootstrap", help="Create/bind release repository for a project")
    p_release_bootstrap.add_argument("--project", required=True)
    p_release_bootstrap.add_argument("--visibility", choices=["public", "private", "internal"], default="public")
    p_release_bootstrap.add_argument("--default-branch", default="main")
    p_release_bootstrap.add_argument("--release-repo")
    p_release_bootstrap.set_defaults(func=cmd_release_bootstrap)

    p_release_publish = release_sub.add_parser("publish", help="Export project directory and push sync branch")
    p_release_publish.add_argument("--project", required=True)
    p_release_publish.set_defaults(func=cmd_release_publish)

    p_release_pr = release_sub.add_parser("pr", help="Open PR in release repository")
    p_release_pr.add_argument("--project", required=True)
    p_release_pr.add_argument("--title", required=True)
    p_release_pr.add_argument("--body", required=True)
    p_release_pr.add_argument("--base")
    p_release_pr.add_argument("--head")
    p_release_pr.set_defaults(func=cmd_release_pr)

    p_ai = sub.add_parser("ai", help="AI-assisted plan/audit with budget guardrails")
    ai_sub = p_ai.add_subparsers(dest="ai_cmd", required=True)

    p_ai_plan = ai_sub.add_parser("plan", help="Generate PLAN.md with Responses API")
    p_ai_plan.add_argument("--prompt", help="Custom prompt override")
    p_ai_plan.add_argument("--input-file", help="Optional file appended into prompt context")
    p_ai_plan.set_defaults(func=cmd_ai_plan)

    p_ai_audit = ai_sub.add_parser("audit", help="Generate AI audit markdown report")
    p_ai_audit.add_argument("--prompt", help="Custom prompt override")
    p_ai_audit.add_argument("--input-file", help="Optional file appended into prompt context")
    p_ai_audit.set_defaults(func=cmd_ai_audit)

    p_ai_task = ai_sub.add_parser("task", help="Generate task-aware AI output with routed model selection")
    p_ai_task.add_argument("--id", required=True, help="Task id like T-0015")
    p_ai_task.add_argument("--intent", choices=["design", "run"], help="Optional task intent for experiment routing")
    p_ai_task.add_argument("--prompt", help="Custom prompt override")
    p_ai_task.add_argument("--input-file", help="Optional file appended into prompt context")
    p_ai_task.add_argument("--output", help="Optional output path override")
    p_ai_task.set_defaults(func=cmd_ai_task)

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
