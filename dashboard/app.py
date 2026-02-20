from __future__ import annotations

from pathlib import Path

import streamlit as st
import yaml

from dashboard.components import git_write_guard, section_header, status_badge
from workflow.audit import run_audit
from workflow.checkpoint import create_checkpoint, list_checkpoints
from workflow.git_ops import get_status
from workflow.review_ops import apply_review_action
from workflow.rollback import HARD_CONFIRM_PHRASE, rollback
from workflow.state_ops import (
    load_review_queue,
    load_tasks,
    save_tasks,
    sync_review_queue_from_tasks,
)
from workflow.verify import run_verify

st.set_page_config(page_title="Agentic Workflow Dashboard", layout="wide")
st.title("Agentic Workflow Dashboard / 审批与审计面板")


def _latest_audit_report() -> Path | None:
    base = Path("artifacts/audit")
    if not base.exists():
        return None
    files = sorted(base.glob("*.md"), key=lambda p: p.name)
    return files[-1] if files else None


def _render_overview() -> None:
    section_header("Overview", "仓库状态 / Checkpoint / 任务统计 / 最新审计")
    status = get_status()
    checkpoints = list_checkpoints()
    tasks = load_tasks()

    todo = len([t for t in tasks if t.get("status") == "todo"])
    in_progress = len([t for t in tasks if t.get("status") == "in_progress"])
    waiting_review = len([t for t in tasks if t.get("status") == "waiting_review"])
    done = len([t for t in tasks if t.get("status") == "done"])

    c1, c2 = st.columns(2)
    with c1:
        status_badge("Branch", status.branch)
        status_badge("HEAD", status.head[:12])
        status_badge("Dirty Files", str(status.dirty_count))
    with c2:
        if checkpoints:
            latest = checkpoints[0]
            status_badge("Latest Checkpoint", latest["tag"])
            status_badge("Checkpoint Commit", latest["commit"][:12])
        else:
            status_badge("Latest Checkpoint", "none")

    st.markdown("### TASKS Stats")
    st.write(
        {
            "todo": todo,
            "in_progress": in_progress,
            "waiting_review": waiting_review,
            "done": done,
            "total": len(tasks),
        }
    )

    latest_audit = _latest_audit_report()
    st.markdown("### Latest Audit")
    if latest_audit:
        st.code(str(latest_audit), language="text")
    else:
        st.info("No audit report yet.")


def _render_tasks() -> None:
    section_header("Tasks", "查看 / 新增 / 编辑 / 保存 TASKS.yaml")
    tasks = load_tasks()

    st.markdown("### Current TASKS")
    st.dataframe(tasks, use_container_width=True)

    st.markdown("### 新增任务 / Add Task")
    with st.form("add_task_form"):
        title = st.text_input("Title")
        task_type = st.selectbox("Type", ["derivation", "code", "writing", "literature", "experiment", "meta"])
        priority = st.selectbox("Priority", ["P0", "P1", "P2"])
        owner = st.selectbox("Owner", ["codex", "chatgpt", "human"])
        status = st.selectbox("Status", ["todo", "in_progress", "waiting_review", "done", "blocked"])
        acceptance = st.text_area("Acceptance (one per line)")
        evidence = st.text_area("Evidence (one per line)")
        verification = st.text_area("Verification (one per line)")
        depends_on = st.text_area("Depends On task IDs (one per line)")
        submitted = st.form_submit_button("Add Task")
        if submitted and title.strip():
            new_id = f"T-{(len(tasks)+1):04d}"
            tasks.append(
                {
                    "id": new_id,
                    "title": title.strip(),
                    "type": task_type,
                    "priority": priority,
                    "owner": owner,
                    "status": status,
                    "acceptance": [x.strip() for x in acceptance.splitlines() if x.strip()],
                    "evidence": [x.strip() for x in evidence.splitlines() if x.strip()],
                    "verification": [x.strip() for x in verification.splitlines() if x.strip()],
                    "depends_on": [x.strip() for x in depends_on.splitlines() if x.strip()],
                    "created_at": "2026-02-20",
                    "updated_at": "2026-02-20",
                }
            )
            save_tasks(tasks)
            st.success(f"Task added: {new_id}")

    st.markdown("### 编辑并保存 / Edit-and-save")
    yaml_text = st.text_area("TASKS.yaml content", value=yaml.safe_dump({"tasks": tasks}, allow_unicode=True, sort_keys=False), height=280)
    if st.button("Save TASKS.yaml"):
        parsed = yaml.safe_load(yaml_text) or {}
        save_tasks(parsed.get("tasks", []))
        st.success("TASKS.yaml saved.")


def _render_review_queue() -> None:
    section_header("Review Queue", "人类审批：Approve / Rework / Reject")

    if st.button("Sync from TASKS waiting_review"):
        items = sync_review_queue_from_tasks()
        st.success(f"Synced {len(items)} review items.")

    items = load_review_queue()
    if not items:
        st.info("Review queue is empty.")
        return

    for item in items:
        with st.expander(f"{item['id']} | {item['task_id']} | {item['title']} | status={item.get('status')}"):
            reviewer = st.text_input("Reviewer", value="human", key=f"reviewer_{item['id']}")
            notes = st.text_input("Notes", value="", key=f"notes_{item['id']}")
            anchor = st.text_input("Reject Anchor (checkpoint tag or commit)", value="", key=f"anchor_{item['id']}")
            c1, c2, c3 = st.columns(3)
            if c1.button("Approve", key=f"approve_{item['id']}"):
                result = apply_review_action(item["id"], reviewer, "Approve", notes)
                st.success(f"Approved {item['id']} -> task {result.task['id']} done")
            if c2.button("Rework", key=f"rework_{item['id']}"):
                result = apply_review_action(item["id"], reviewer, "Rework", notes)
                st.warning(f"Rework {item['id']} -> task {result.task['id']} blocked")
            if c3.button("Reject", key=f"reject_{item['id']}"):
                if not anchor.strip():
                    st.error("Reject requires anchor checkpoint/commit.")
                else:
                    result = apply_review_action(item["id"], reviewer, "Reject", notes, anchor=anchor.strip())
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
    command_preview = f"python -m workflow checkpoint --summary \"{summary}\""
    allow_checkpoint = git_write_guard("create_checkpoint", command_preview)
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
    rb_preview = f"python -m workflow rollback --mode safe --anchor {anchor}"
    allow_rb = git_write_guard("safe_rollback", rb_preview)
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
    hard_preview = f"python -m workflow rollback --mode hard --anchor {hard_anchor} --confirm-phrase {HARD_CONFIRM_PHRASE}"
    allow_hard = git_write_guard("hard_rollback", hard_preview, phrase_required=HARD_CONFIRM_PHRASE)
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
        st.session_state["verify_result"] = result
        if result.ok:
            st.success(f"Verify PASS, report: {result.report_path}")
        else:
            st.error(f"Verify FAIL, report: {result.report_path}")

    if c2.button("Run Audit"):
        result = run_audit()
        st.session_state["audit_result"] = result
        if result.p0 == 0:
            st.success(f"Audit completed, report: {result.report_path}")
        else:
            st.error(f"Audit found P0={result.p0}, report: {result.report_path}")

    latest = _latest_audit_report()
    if latest and latest.exists():
        st.markdown("### Latest Audit Report Content")
        st.text(latest.read_text(encoding="utf-8"))


def _render_jobs_ai() -> None:
    section_header("Jobs & AI", "后台任务与 AI 计划/审计（后续命令可直接接入）")
    st.info(
        "Jobs 与 AI 命令已在 CLI 规划中。当前面板先保留入口位，"
        "下一阶段将接入 `workflow jobs` 与 `workflow ai` 的可视化控制。"
    )


def main() -> None:
    tabs = st.tabs(["Overview", "Tasks", "Review Queue", "Checkpoints", "Audit & Verify", "Jobs & AI"])
    with tabs[0]:
        _render_overview()
    with tabs[1]:
        _render_tasks()
    with tabs[2]:
        _render_review_queue()
    with tabs[3]:
        _render_checkpoints()
    with tabs[4]:
        _render_audit_verify()
    with tabs[5]:
        _render_jobs_ai()


if __name__ == "__main__":
    main()
