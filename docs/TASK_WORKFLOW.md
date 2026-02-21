# TASK WORKFLOW / 任务级结构化协作规范

## 1. Goal
- 在不新增顶层并行体系的前提下，为每个任务提供可审计、可复现、可交接的结构化记录。
- 所有任务级结构默认落在 `state/tasks/<task_id>/` 与 `artifacts/tasks/<task_id>/`。

## 2. Required Files
- `state/tasks/<task_id>/brief.yaml`
- `state/tasks/<task_id>/intake.yaml`（输入中心落盘）
- `state/tasks/<task_id>/subtasks.yaml`（子任务编排）
- `state/tasks/<task_id>/worklog.md`
- `state/tasks/<task_id>/evidence_map.yaml`
- `state/tasks/<task_id>/notes.md`
- `state/tasks/<task_id>/handoff.yaml`
- `state/tasks/<task_id>/run_index.yaml`

## 3. PDCA Worklog
- Plan/Do/Check/Act 统一记录在 `worklog.md` 表格中。
- 每条记录必须包含至少一项证据路径或验证指针。
- Intake Center 侧输入（长文本 + 文件路径 + 上传附件）需落盘到 `intake.yaml`，并给出 completeness 评分。

## 4. Role Handoff
- 五角色：Planner / Retriever / Implementer / Critic / Scribe。
- 交接状态：`accepted|rework|rejected`，`accepted` 必须包含 `accepted_at`。
- 子任务 owner 默认映射上述角色，也可由 `human` 接管。

## 4.5 Subtask Review & Cascade
- 审批粒度支持 task-level 与 subtask-level。
- subtask-level 审批进入 `state/REVIEW_QUEUE.yaml`，并标记 `scope: subtask` + `subtask_id`。
- `Rework/Reject` 先生成 cascade 建议（`self_only|downstream|all`），再由人工确认执行。
- `Reject` 必须提供 rollback anchor，触发安全级联（rollback branch + git revert + KR 降级 + superseded PR 关闭）。

## 5. Evidence Rules
- `evidence_map.yaml` 中每个 claim 必须定义 `claim_id`、`statement`、`confidence`、`status`。
- 引用必须采用 `path#Lx` 形式，并可附 `source_sha256` 做稳定性校验。
- 无法验证的引用必须标记 `uncertain`，不得进入 verified 结论。

## 6. Run Metadata
- 所有角色执行动作建议经 `workflow task run` 记录 `run_meta.yaml`。
- `run_meta` 必须记录 `command/args/environment/seed/inputs/outputs/exit_code`。

## 7. Guardrails
- 禁止凭空编造证据引用。
- 禁止在任务产物中记录密钥内容；仅允许存在性路径引用。
- 任务完成后应同步 `state/STATE.md`，如产生关键结论则同步 `state/KEY_RESULTS.yaml`。
