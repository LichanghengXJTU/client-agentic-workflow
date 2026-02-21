from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from typing import Any

import streamlit as st

# Streamlit executes apps as scripts, so the project root may not be on sys.path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.components import (  # noqa: E402
    activity_event_card,
    git_write_guard,
    image_gallery,
    section_header,
    status_badge,
    subtask_card,
)
from workflow.activity_ops import extract_task_images, list_task_activity, match_task_prs  # noqa: E402
from workflow.ai import run_ai_audit, run_ai_plan, run_ai_task  # noqa: E402
from workflow.audit import run_audit  # noqa: E402
from workflow.checkpoint import create_checkpoint, list_checkpoints  # noqa: E402
from workflow.git_ops import get_status  # noqa: E402
from workflow.intake_ops import (  # noqa: E402
    build_clarification_suggestions,
    generate_ai_clarification_suggestions,
    parse_intake_prompt,
    resolve_prompt_contract,
    save_task_intake,
    score_intake_completeness,
)
from workflow.jobs import list_jobs, start_job, stop_job, tail_job_log  # noqa: E402
from workflow.review_ops import apply_review_action  # noqa: E402
from workflow.rollback import HARD_CONFIRM_PHRASE, rollback  # noqa: E402
from workflow.state_ops import (  # noqa: E402
    add_task,
    append_state_event,
    atomic_write_yaml,
    load_project_registry,
    load_review_queue,
    load_task_subtasks,
    load_tasks,
    read_yaml,
    sync_review_queue_from_tasks,
    task_by_id,
    task_state_dir,
)
from workflow.subtask_ops import (  # noqa: E402
    ensure_subtasks,
    suggest_cascade_scope,
    sync_review_queue_from_subtasks,
    update_subtask_status,
)
from workflow.task_ops import scaffold_task_record  # noqa: E402
from workflow.verify import run_verify  # noqa: E402

st.set_page_config(page_title="Agentic Workflow Dashboard", layout="wide")
st.title("Agentic Workflow Dashboard / 输入输出集成中心")


def _latest_report(base: str, pattern: str = "*.md") -> Path | None:
    root = Path(base)
    if not root.exists():
        return None
    files = sorted(root.glob(pattern), key=lambda p: p.name)
    return files[-1] if files else None


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text).splitlines() if line.strip()]


def _dedup(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _update_brief_from_intake(task_id: str, task: dict[str, Any], intake_payload: dict[str, Any]) -> None:
    brief_path = task_state_dir(task_id) / "brief.yaml"
    brief = read_yaml(brief_path)
    sections = intake_payload.get("sections", {}) if isinstance(intake_payload, dict) else {}
    if not brief:
        brief = {
            "task_id": task_id,
            "title": task.get("title", ""),
            "owner": task.get("owner", "codex"),
            "goal": "",
            "success_criteria": [],
            "scope_in": [],
            "scope_out": [],
            "constraints": [],
            "long_inputs": [],
            "assumptions": [],
        }

    brief["title"] = task.get("title", brief.get("title", ""))
    brief["owner"] = task.get("owner", brief.get("owner", "codex"))
    brief["goal"] = sections.get("core_task", brief.get("goal", ""))
    brief["success_criteria"] = sections.get("acceptance", brief.get("success_criteria", []))
    brief["scope_in"] = sections.get("required_files", brief.get("scope_in", []))
    brief["constraints"] = sections.get("constraints", brief.get("constraints", []))

    long_inputs = brief.get("long_inputs", [])
    if not isinstance(long_inputs, list):
        long_inputs = []
    raw_prompt_ref = intake_payload.get("raw_prompt_ref")
    if isinstance(raw_prompt_ref, str) and raw_prompt_ref.strip():
        long_inputs.append(
            {
                "input_id": f"IN-{datetime.now().strftime('%H%M%S')}",
                "path": raw_prompt_ref,
                "source": "repo",
                "sha256": "",
            }
        )
    brief["long_inputs"] = long_inputs

    assumptions = brief.get("assumptions", [])
    if not isinstance(assumptions, list):
        assumptions = []
    missing_required = intake_payload.get("completeness", {}).get("missing_required", [])
    if missing_required:
        assumptions.append(
            {
                "id": f"ASM-{datetime.now().strftime('%H%M%S')}",
                "text": f"uncertain: intake missing sections {missing_required}",
                "status": "open",
                "tag": "uncertain",
            }
        )
    brief["assumptions"] = assumptions

    atomic_write_yaml(brief_path, brief)


def _task_summary_rows(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task in tasks:
        tid = str(task.get("id", ""))
        sub_data = load_task_subtasks(tid)
        subtasks = sub_data.get("subtasks", []) if isinstance(sub_data, dict) else []
        waiting = len([x for x in subtasks if isinstance(x, dict) and x.get("status") == "waiting_review"])

        ai_dir = Path("artifacts") / "tasks" / tid / "ai"
        latest_model = ""
        latest_summary = ""
        if ai_dir.exists():
            reports = sorted(ai_dir.glob("*.md"))
            if reports:
                content = reports[-1].read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines()[:30]:
                    if line.startswith("- Model:"):
                        latest_model = line.split(":", maxsplit=1)[1].strip()
                        break
                latest_summary = " ".join(content.splitlines()[10:18])[:80]

        rows.append(
            {
                "task_id": tid,
                "title": task.get("title", ""),
                "status": task.get("status", ""),
                "subtasks": len(subtasks),
                "pending_subtask_reviews": waiting,
                "latest_model": latest_model,
                "latest_summary": latest_summary,
            }
        )
    return rows


def _render_overview() -> None:
    section_header("Overview", "仓库状态 / 任务摘要 / 最新验证与审计")
    status = get_status()
    checkpoints = list_checkpoints()
    tasks = load_tasks()
    queue = load_review_queue()

    c1, c2, c3 = st.columns(3)
    with c1:
        status_badge("Branch", status.branch)
        status_badge("HEAD", status.head[:12])
        status_badge("Dirty Files", str(status.dirty_count))
    with c2:
        if checkpoints:
            latest = checkpoints[0]
            status_badge("Latest Checkpoint", latest["tag"])
            status_badge("Commit", latest["commit"][:12])
        else:
            status_badge("Latest Checkpoint", "none")
    with c3:
        subtask_pending = len([x for x in queue if str(x.get("scope", "task")) == "subtask" and x.get("status") == "pending"])
        task_pending = len([x for x in queue if str(x.get("scope", "task")) != "subtask" and x.get("status") == "pending"])
        status_badge("Pending Task Reviews", str(task_pending))
        status_badge("Pending Subtask Reviews", str(subtask_pending))
        status_badge("Total Tasks", str(len(tasks)))

    st.markdown("### Task Execution Snapshot")
    st.dataframe(_task_summary_rows(tasks), use_container_width=True)

    latest_verify = _latest_report("artifacts/test", "verify-*.md")
    latest_audit = _latest_report("artifacts/audit", "*.md")
    c4, c5 = st.columns(2)
    with c4:
        st.markdown("### Latest Verify")
        if latest_verify:
            st.code(str(latest_verify), language="text")
        else:
            st.info("No verify report yet.")
    with c5:
        st.markdown("### Latest Audit")
        if latest_audit:
            st.code(str(latest_audit), language="text")
        else:
            st.info("No audit report yet.")


def _render_intake_center() -> None:
    section_header("Intake Center", "长文本输入 + 结构化拆解 + 一次性建任务")
    projects = load_project_registry()
    project_options = [""] + [str(item.get("slug")) for item in projects if item.get("slug")]

    title = st.text_input("Task Title", key="intake_title")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        task_type = st.selectbox("Task Type", ["derivation", "code", "writing", "literature", "experiment", "meta"], key="intake_type")
    with c2:
        priority = st.selectbox("Priority", ["P0", "P1", "P2"], key="intake_priority")
    with c3:
        owner = st.selectbox("Owner", ["codex", "chatgpt", "human"], key="intake_owner")
    with c4:
        project_slug = st.selectbox("Project (optional)", options=project_options, key="intake_project")

    raw_prompt = st.text_area(
        "Raw Prompt / Long Context",
        height=240,
        key="intake_raw_prompt",
        placeholder="在这里粘贴长文本：背景、目标、依赖、限制、输出风格、验收标准...",
    )
    repo_files = st.text_area(
        "Repo File Paths (one per line)",
        height=120,
        key="intake_repo_paths",
        placeholder="例如:\nworkflow/ai.py\ndocs/WORKFLOW.md",
    )
    uploads = st.file_uploader("Optional Uploads", accept_multiple_files=True)

    analyze = st.button("Analyze Intake")
    ai_suggest = st.button("Generate AI Clarification Suggestions")
    create = st.button("Create Task + Intake + Subtasks")

    preview = st.session_state.get("intake_preview", {})
    if analyze:
        contract = resolve_prompt_contract(task_type=task_type, project_slug=project_slug or None)
        sections = parse_intake_prompt(raw_prompt, contract)
        sections["required_files"] = _dedup(list(sections.get("required_files", [])) + _split_lines(repo_files))
        completeness = score_intake_completeness(sections, contract)
        st.session_state["intake_preview"] = {
            "contract": contract,
            "sections": sections,
            "completeness": completeness,
        }
        preview = st.session_state["intake_preview"]

    if preview:
        st.markdown("### Parsed Sections")
        st.json(preview.get("sections", {}), expanded=False)
        st.markdown("### Completeness")
        st.write(preview.get("completeness", {}))

        st.markdown("### Clarification Suggestions (Rule-based)")
        for tip in build_clarification_suggestions(preview.get("sections", {}), preview.get("completeness", {})):
            st.write(f"- {tip}")

        if ai_suggest:
            result = generate_ai_clarification_suggestions(
                raw_text=raw_prompt,
                missing_required=list(preview.get("completeness", {}).get("missing_required", [])),
            )
            st.session_state["intake_ai_suggestions"] = result

        ai_result = st.session_state.get("intake_ai_suggestions")
        if isinstance(ai_result, dict):
            st.markdown("### Clarification Suggestions (AI)")
            st.caption(f"note={ai_result.get('note', '')} | uncertain={ai_result.get('uncertain', False)}")
            for tip in ai_result.get("suggestions", []):
                st.write(f"- {tip}")

    if create:
        if not title.strip():
            st.error("Task title is required.")
            return

        contract = resolve_prompt_contract(task_type=task_type, project_slug=project_slug or None)
        sections = parse_intake_prompt(raw_prompt, contract)
        sections["required_files"] = _dedup(list(sections.get("required_files", [])) + _split_lines(repo_files))
        completeness = score_intake_completeness(sections, contract)

        task = add_task(
            title=title.strip(),
            task_type=task_type,
            priority=priority,
            owner=owner,
            status="todo",
            acceptance=list(sections.get("acceptance", [])) or ["补充验收标准"],
            evidence=list(sections.get("required_files", [])),
            verification=[],
            depends_on=[],
        )
        task_id = str(task.get("id"))
        scaffold_task_record(task_id=task_id, title=title.strip(), owner=owner)

        intake_payload = {
            "task_id": task_id,
            "project_slug": project_slug or None,
            "raw_prompt": raw_prompt,
            "sections": sections,
            "completeness": completeness,
            "attachments": [],
        }
        intake_path = save_task_intake(task_id=task_id, payload=intake_payload, uploads=uploads)
        intake_file = read_yaml(intake_path)

        ensure_subtasks(task_id=task_id, lazy=True)
        _update_brief_from_intake(task_id=task_id, task=task, intake_payload=intake_file)
        append_state_event(
            "Intake Created",
            [
                f"Task: {task_id}",
                f"Type: {task_type}",
                f"Project: {project_slug or '-'}",
                f"Intake path: {intake_path}",
                f"Completeness score: {completeness.get('score', 0.0)}",
                f"Missing required: {completeness.get('missing_required', [])}",
            ],
        )
        st.success(f"Created {task_id} with intake and default subtasks.")


def _find_subtask_review_item(task_id: str, subtask_id: str) -> dict[str, Any] | None:
    items = load_review_queue()
    candidates = [
        item
        for item in items
        if str(item.get("scope", "task")) == "subtask"
        and str(item.get("task_id", "")) == task_id
        and str(item.get("subtask_id", "")) == subtask_id
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: str(x.get("updated_at", x.get("created_at", ""))), reverse=True)
    return candidates[0]


def _render_execution_center() -> None:
    section_header("Execution Center", "任务输出中心：子任务动态流 / 审批 / PR / 图片")
    tasks = load_tasks()
    if not tasks:
        st.info("No tasks available. Create one in Intake Center first.")
        return

    rows = _task_summary_rows(tasks)
    task_ids = [row["task_id"] for row in rows]

    c_left, c_right = st.columns([1, 2])
    with c_left:
        selected_task_id = st.selectbox("Select Task", options=task_ids, key="exec_task_id")
        if st.button("Refresh Selected Task (lazy migration)"):
            ensure_subtasks(selected_task_id, lazy=True)
            st.success(f"Task {selected_task_id} refreshed.")

        st.markdown("### Task List")
        st.dataframe(rows, use_container_width=True)

    with c_right:
        task = task_by_id(selected_task_id)
        subtasks = ensure_subtasks(selected_task_id, lazy=True)
        intake_data = read_yaml(task_state_dir(selected_task_id) / "intake.yaml")

        st.markdown(f"## {selected_task_id} | {task.get('title', '')}")
        a1, a2, a3, a4 = st.columns(4)
        with a1:
            status_badge("Task Status", str(task.get("status", "")))
        with a2:
            status_badge("Owner", str(task.get("owner", "")))
        with a3:
            status_badge("Priority", str(task.get("priority", "")))
        with a4:
            status_badge("Type", str(task.get("type", "")))

        with st.expander("Intake Snapshot", expanded=False):
            if intake_data:
                st.json(intake_data, expanded=False)
            else:
                st.info("No intake.yaml yet. This task is running in legacy mode.")

        if not subtasks:
            st.warning("No subtasks defined.")
            return

        st.markdown("### Subtasks")
        selected_subtask_id = st.radio(
            "Pick a subtask",
            options=[str(item.get("id")) for item in subtasks],
            format_func=lambda sid: next(
                (
                    f"{item.get('id')} | {item.get('title')} | status={item.get('status')}"
                    for item in subtasks
                    if item.get("id") == sid
                ),
                sid,
            ),
            key=f"subtask_select_{selected_task_id}",
        )
        selected_subtask = next(item for item in subtasks if str(item.get("id")) == selected_subtask_id)
        subtask_card(selected_subtask, selected=True)

        st.markdown("#### Quick Subtask Status")
        q1, q2, q3, q4 = st.columns(4)
        if q1.button("Set todo", key=f"set_todo_{selected_task_id}_{selected_subtask_id}"):
            update_subtask_status(selected_task_id, selected_subtask_id, "todo")
            st.rerun()
        if q2.button("Set in_progress", key=f"set_prog_{selected_task_id}_{selected_subtask_id}"):
            update_subtask_status(selected_task_id, selected_subtask_id, "in_progress")
            st.rerun()
        if q3.button("Set waiting_review", key=f"set_wait_{selected_task_id}_{selected_subtask_id}"):
            update_subtask_status(selected_task_id, selected_subtask_id, "waiting_review")
            st.rerun()
        if q4.button("Set done", key=f"set_done_{selected_task_id}_{selected_subtask_id}"):
            update_subtask_status(selected_task_id, selected_subtask_id, "done")
            st.rerun()

        st.markdown("### Dynamic Flow")
        events = list_task_activity(task_id=selected_task_id, subtask_id=selected_subtask_id, limit=200)
        if not events:
            st.info("No activity yet for this subtask/task.")
        else:
            for event in events:
                activity_event_card(event)

        st.markdown("### Subtask Review Panel")
        if st.button("Sync Review Queue from Subtasks", key=f"sync_subtask_queue_{selected_task_id}"):
            items = sync_review_queue_from_subtasks(task_id=selected_task_id)
            st.success(f"Synced review queue items: {len(items)}")
            st.rerun()

        review_item = _find_subtask_review_item(selected_task_id, selected_subtask_id)
        if not review_item:
            st.info("No subtask review item yet. Set status=waiting_review and sync queue.")
        else:
            st.write({
                "review_id": review_item.get("id"),
                "status": review_item.get("status"),
                "scope": review_item.get("scope", "task"),
                "subtask_id": review_item.get("subtask_id"),
            })
            reviewer = st.text_input("Reviewer", value="human", key=f"exec_reviewer_{selected_task_id}_{selected_subtask_id}")
            notes = st.text_area("Review Notes", value="", key=f"exec_notes_{selected_task_id}_{selected_subtask_id}")
            anchor = st.text_input(
                "Reject Anchor (required for Reject)",
                value="",
                key=f"exec_anchor_{selected_task_id}_{selected_subtask_id}",
            )

            advice_key = f"cascade_advice_{selected_task_id}_{selected_subtask_id}"
            if st.button("Analyze Cascade Scope", key=f"analyze_cascade_{selected_task_id}_{selected_subtask_id}"):
                advice = suggest_cascade_scope(
                    task_id=selected_task_id,
                    subtask_id=selected_subtask_id,
                    action="Rework",
                    reviewer_note=notes,
                )
                st.session_state[advice_key] = advice

            advice_payload = st.session_state.get(advice_key, {})
            suggested_scope = str(advice_payload.get("suggested_scope", "downstream"))
            if advice_payload:
                st.caption(
                    "Cascade suggestion: "
                    f"scope={advice_payload.get('suggested_scope')} "
                    f"confidence={advice_payload.get('confidence')} "
                    f"uncertain={advice_payload.get('uncertain')}"
                )
                st.code(str(advice_payload.get("artifact_path", "")), language="text")
                st.write({
                    "affected_subtasks": advice_payload.get("affected_subtasks", []),
                    "reason": advice_payload.get("reason", ""),
                })

            scope_options = ["self_only", "downstream", "all"]
            default_index = scope_options.index(suggested_scope) if suggested_scope in scope_options else 1
            cascade_scope = st.selectbox(
                "Cascade Scope",
                options=scope_options,
                index=default_index,
                key=f"exec_scope_{selected_task_id}_{selected_subtask_id}",
            )

            b1, b2, b3 = st.columns(3)
            if b1.button("Approve", key=f"exec_ap_{selected_task_id}_{selected_subtask_id}"):
                result = apply_review_action(
                    review_id=str(review_item.get("id")),
                    reviewer=reviewer,
                    action="Approve",
                    notes=notes,
                    cascade_scope=cascade_scope,
                )
                st.success(f"Approved: task {result.task['id']} -> {result.task['status']}")
                st.rerun()
            if b2.button("Rework", key=f"exec_rw_{selected_task_id}_{selected_subtask_id}"):
                result = apply_review_action(
                    review_id=str(review_item.get("id")),
                    reviewer=reviewer,
                    action="Rework",
                    notes=notes,
                    cascade_scope=cascade_scope,
                )
                st.warning(f"Rework applied: task {result.task['id']} -> {result.task['status']}")
                st.rerun()
            if b3.button("Reject", key=f"exec_rj_{selected_task_id}_{selected_subtask_id}"):
                if not anchor.strip():
                    st.error("Reject requires anchor checkpoint/commit.")
                else:
                    result = apply_review_action(
                        review_id=str(review_item.get("id")),
                        reviewer=reviewer,
                        action="Reject",
                        notes=notes,
                        anchor=anchor.strip(),
                        cascade_scope=cascade_scope,
                    )
                    st.error(
                        f"Rejected: branch={result.rollback_branch}, reverted={result.reverted_count}, "
                        f"closed_prs={result.closed_prs}"
                    )
                    st.rerun()

        st.markdown("### Related PRs")
        prs = match_task_prs(selected_task_id)
        if prs:
            rows_pr = [
                {
                    "repo": item.get("repo", ""),
                    "number": item.get("number", ""),
                    "state": item.get("state", ""),
                    "title": item.get("title", ""),
                    "role": item.get("role", ""),
                    "updated_at": item.get("updated_at", ""),
                    "match_reason": item.get("match_reason", ""),
                    "uncertain": item.get("uncertain", False),
                    "url": item.get("url", ""),
                }
                for item in prs
            ]
            st.dataframe(rows_pr, use_container_width=True)
        else:
            st.info("No related PR found for this task.")

        st.markdown("### Image Gallery")
        image_gallery(extract_task_images(selected_task_id, selected_subtask_id))


def _render_review_queue() -> None:
    section_header("Review Queue", "统一审批队列：task + subtask")
    c1, c2 = st.columns(2)
    if c1.button("Sync from TASKS waiting_review"):
        items = sync_review_queue_from_tasks()
        st.success(f"Synced task-scope review items: {len(items)}")
    if c2.button("Sync from SUBTASKS waiting_review"):
        items = sync_review_queue_from_subtasks()
        st.success(f"Synced mixed review items: {len(items)}")

    items = load_review_queue()
    if not items:
        st.info("Review queue is empty.")
        return

    for item in items:
        scope = str(item.get("scope", "task"))
        subtask_hint = f" | subtask={item.get('subtask_id')}" if scope == "subtask" else ""
        with st.expander(
            f"{item.get('id')} | {item.get('task_id')} | scope={scope}{subtask_hint} | status={item.get('status')}"
        ):
            reviewer = st.text_input("Reviewer", value="human", key=f"reviewer_{item['id']}")
            notes = st.text_input("Notes", value="", key=f"notes_{item['id']}")
            anchor = st.text_input("Reject Anchor (checkpoint tag or commit)", value="", key=f"anchor_{item['id']}")
            cascade_scope = st.selectbox(
                "Cascade Scope (subtask only)",
                options=["downstream", "self_only", "all"],
                key=f"scope_{item['id']}",
            )
            c3, c4, c5 = st.columns(3)
            if c3.button("Approve", key=f"approve_{item['id']}"):
                result = apply_review_action(item["id"], reviewer, "Approve", notes, cascade_scope=cascade_scope)
                st.success(f"Approved {item['id']} -> task {result.task['id']} {result.task['status']}")
            if c4.button("Rework", key=f"rework_{item['id']}"):
                result = apply_review_action(item["id"], reviewer, "Rework", notes, cascade_scope=cascade_scope)
                st.warning(f"Rework {item['id']} -> task {result.task['id']} {result.task['status']}")
            if c5.button("Reject", key=f"reject_{item['id']}"):
                if not anchor.strip():
                    st.error("Reject requires anchor checkpoint/commit.")
                else:
                    result = apply_review_action(
                        item["id"],
                        reviewer,
                        "Reject",
                        notes,
                        anchor=anchor.strip(),
                        cascade_scope=cascade_scope,
                    )
                    st.error(
                        f"Rejected {item['id']}, rollback branch={result.rollback_branch}, "
                        f"reverted={result.reverted_count}, closed_prs={result.closed_prs}"
                    )


def _render_checkpoints() -> None:
    section_header("Checkpoints", "创建 checkpoint / 安全回档")
    checkpoints = list_checkpoints()
    st.dataframe(checkpoints, use_container_width=True)

    st.markdown("### Create Checkpoint")
    summary = st.text_input("Summary", value="manual checkpoint")
    message = st.text_input("Commit message (optional)", value="")
    key_results = st.text_input("Related KEY_RESULTS IDs (comma separated)", value="")
    allow_checkpoint = git_write_guard("create_checkpoint", f"python -m workflow checkpoint --summary \"{summary}\"")
    if st.button("Create checkpoint"):
        if not allow_checkpoint:
            st.error("Please confirm git write operation first.")
        else:
            result = create_checkpoint(
                summary=summary,
                commit_message=message or None,
                related_key_results=[x.strip() for x in key_results.split(",") if x.strip()],
            )
            st.success(f"Checkpoint created: {result.tag} @ {result.snapshot_commit[:8]}")

    st.markdown("### Safe Rollback")
    options = [c["tag"] for c in checkpoints]
    anchor = st.selectbox("Anchor checkpoint", options=options if options else [""], index=0)
    allow_rb = git_write_guard("safe_rollback", f"python -m workflow rollback --mode safe --anchor {anchor}")
    if st.button("Run safe rollback"):
        if not anchor:
            st.error("No checkpoint available.")
        elif not allow_rb:
            st.error("Please confirm git write operation first.")
        else:
            result = rollback(anchor_ref=anchor, mode="safe")
            st.success(f"Rollback done on {result.branch}, reverted={result.reverted_count}")

    st.markdown("### Hard Rollback (Advanced)")
    hard_anchor = st.text_input("Hard rollback anchor")
    allow_hard = git_write_guard(
        "hard_rollback",
        f"python -m workflow rollback --mode hard --anchor {hard_anchor} --confirm-phrase {HARD_CONFIRM_PHRASE}",
        phrase_required=HARD_CONFIRM_PHRASE,
    )
    if st.button("Run hard rollback"):
        if not hard_anchor.strip():
            st.error("Please input anchor ref")
        elif not allow_hard:
            st.error("Hard rollback confirmation failed")
        else:
            result = rollback(anchor_ref=hard_anchor.strip(), mode="hard", confirm_phrase=HARD_CONFIRM_PHRASE)
            st.success(f"Hard rollback completed to {result.anchor_ref}")


def _render_audit_verify() -> None:
    section_header("Audit & Verify", "运行验证与审计")
    c1, c2 = st.columns(2)
    if c1.button("Run Verify"):
        result = run_verify()
        if result.ok:
            st.success(f"Verify PASS, report: {result.report_path}")
        else:
            st.error(f"Verify FAIL, report: {result.report_path}")

    if c2.button("Run Audit"):
        result = run_audit()
        if result.p0 == 0:
            st.success(f"Audit completed, report: {result.report_path}")
        else:
            st.error(f"Audit found P0={result.p0}, report: {result.report_path}")

    latest = _latest_report("artifacts/audit", "*.md")
    if latest and latest.exists():
        st.markdown("### Latest Audit Report Content")
        st.text(latest.read_text(encoding="utf-8"))


def _render_jobs_ai() -> None:
    section_header("Jobs & AI", "后台任务管理 + AI Plan/Audit/Task")

    st.markdown("### Jobs")
    with st.form("job_start_form"):
        cmd = st.text_input("Command", value="python3 -m workflow verify")
        workdir = st.text_input("Workdir (optional)", value="")
        submitted = st.form_submit_button("Start Job")
        if submitted:
            result = start_job(command=cmd, workdir=workdir or None)
            st.success(f"Started {result.id} pid={result.pid}")

    jobs = list_jobs()
    st.dataframe(jobs, use_container_width=True)
    if jobs:
        selected = st.selectbox("Select Job", options=[j["id"] for j in jobs], key="job_select")
        c1, c2 = st.columns(2)
        if c1.button("Show Job Logs"):
            st.code(tail_job_log(selected, lines=120), language="text")
        if c2.button("Stop Job"):
            item = stop_job(selected)
            st.warning(f"Job {item['id']} -> {item['status']}")

    st.markdown("### AI Plan / Audit")
    extra = st.text_area("Extra Context", value="", height=120)
    c3, c4 = st.columns(2)
    if c3.button("Run AI Plan"):
        result = run_ai_plan(prompt=extra or "Generate actionable PLAN.md for current repo state.")
        if result.ok:
            st.success(f"AI plan generated: {result.output_path} | model={result.model}")
        else:
            st.warning(f"AI plan pending: {result.output_path} | {result.message}")

    if c4.button("Run AI Audit"):
        result = run_ai_audit(prompt=extra or "Audit current workflow state with risk prioritization.")
        if result.ok:
            st.success(f"AI audit generated: {result.output_path} | model={result.model}")
        else:
            st.warning(f"AI audit pending: {result.output_path} | {result.message}")

    st.markdown("### AI Task (Task-aware Routing)")
    tasks = load_tasks()
    task_ids = [str(item.get("id")) for item in tasks if isinstance(item, dict) and item.get("id")]
    if not task_ids:
        st.info("No task available. Please create task first in Intake Center.")
        return

    with st.form("ai_task_form"):
        selected_task = st.selectbox("Task ID", options=task_ids)
        intent_choice = st.selectbox("Intent", options=["(default: design)", "design", "run"])
        task_output = st.text_input("Output path (optional)", value="")
        task_extra = st.text_area("Task Prompt / Extra Context", value="", height=120)
        submitted = st.form_submit_button("Run AI Task")
        if submitted:
            intent = None if intent_choice.startswith("(default") else intent_choice
            result = run_ai_task(
                task_id=selected_task,
                intent=intent,
                prompt=task_extra,
                output_path=task_output or None,
            )
            if result.ok:
                st.success(
                    f"AI task generated: {result.output_path} | route={result.route_key} | "
                    f"requested={result.requested_model} | model={result.model}"
                )
            else:
                st.warning(
                    f"AI task pending: {result.output_path} | route={result.route_key} | "
                    f"requested={result.requested_model} | {result.message}"
                )


def main() -> None:
    tabs = st.tabs(
        [
            "Overview",
            "Intake Center",
            "Execution Center",
            "Review Queue",
            "Checkpoints",
            "Audit & Verify",
            "Jobs & AI",
        ]
    )
    with tabs[0]:
        _render_overview()
    with tabs[1]:
        _render_intake_center()
    with tabs[2]:
        _render_execution_center()
    with tabs[3]:
        _render_review_queue()
    with tabs[4]:
        _render_checkpoints()
    with tabs[5]:
        _render_audit_verify()
    with tabs[6]:
        _render_jobs_ai()


if __name__ == "__main__":
    main()
