# README 文件级附录（中文 + English Terms）

> 本附录是 `README.md` 的深度索引，聚焦“文件职责、实现入口、输入输出、状态副作用、测试映射”。

## 1. 适用范围
- 适用仓库：`client-agentic-workflow`
- 主文档：`README.md`
- 目标：让评审者可以从“描述 -> 文件 -> 测试 -> 产物”快速穿透。

## 2. 核心文件逐项说明清单

格式：`Path | Role | Key Symbols | Inputs | Outputs | State Side Effects | Tests`

| Path | Role | Key Symbols | Inputs | Outputs | State Side Effects | Tests |
|---|---|---|---|---|---|---|
| `workflow/__main__.py` | CLI 路由入口 | `build_parser`, `cmd_*` | CLI args | JSON stdout, dispatch to modules | 调用 state/event 写入 | `tests/test_*` 间接覆盖 |
| `workflow/state_ops.py` | 状态读写与原子落盘 | `read_yaml`, `atomic_write_yaml`, `add_task`, `update_task` | state yaml/md | updated yaml/md | `state/*.yaml`, `state/STATE.md`, `state/HUMAN_REVIEW_LOG.md` | `tests/test_review_queue_flow.py`, `tests/test_task_run_meta.py` |
| `workflow/schemas.py` | schema 校验层 | `validate_tasks_data`, `validate_key_results_data`, `validate_project_registry_data`, `validate_kb_manifest_data` | yaml dict | issues list | 无直接副作用 | `tests/test_state_schema.py`, `tests/test_project_registry.py` |
| `workflow/audit.py` | 审计聚合器 | `run_audit`, `_required_file_checks`, `_evidence_map_schema`, `_run_meta_completeness` | repo state + git metadata | `AuditResult`, markdown report | `artifacts/audit/*.md` | `tests/test_audit_report.py` |
| `workflow/verify.py` | 运行时验证器 | `run_verify`, `_verify_task_records`, `_verify_citations`, `_verify_kb_query_smoke`, `_verify_replay` | tests, derivation scripts, task/kb data | `VerifyResult`, markdown report | `artifacts/test/verify-*.md` | 间接由全量测试验证 |
| `workflow/checkpoint.py` | checkpoint 快照管理 | `create_checkpoint`, `list_checkpoints` | summary, key results refs | tag/commit metadata | `state/CHECKPOINTS.md`, `state/STATE.md`, `state/KEY_RESULTS.yaml` | `tests/test_checkpoint_rollback.py` |
| `workflow/rollback.py` | rollback 执行 | `safe_rollback`, `hard_rollback`, `rollback` | anchor + mode | `RollbackResult` | git branch/commits changed | `tests/test_checkpoint_rollback.py` |
| `workflow/review_ops.py` | 审批编排与 reject cascade | `apply_review_action`, `_dependency_reset`, `_mark_key_results_after_anchor` | review id/action/anchor | `ReviewActionResult` | tasks/results/review log/state updates | `tests/test_review_queue_flow.py`, `tests/test_reject_cascade.py` |
| `workflow/git_ops.py` | git 抽象层 | `_run_git`, `get_status`, `commits_after`, `is_ancestor` | git refs | parsed git metadata | git operations | `tests/test_workflow_git_ops.py` |
| `workflow/jobs.py` | 后台任务管理 | `start_job`, `stop_job`, `list_jobs`, `tail_job_log` | command/workdir | job records + logs | `state/JOBS.yaml`, `artifacts/test/job-*.log` | `tests/test_jobs.py` |
| `workflow/task_ops.py` | task-level run_meta 记录 | `scaffold_task_record`, `record_task_run`, `run_task_command` | task id/role/command | run_meta + run index | `state/tasks/*`, `artifacts/tasks/*` | `tests/test_task_run_meta.py` |
| `workflow/citation_ops.py` | 引用解析与 hash 校验 | `parse_cite`, `validate_cite`, `file_sha256` | cite string, optional sha | validation result | 无直接副作用 | `tests/test_citation_validity.py` |
| `workflow/kb_ops.py` | KB ingest/query 引擎 | `ingest_kb_sources`, `query_kb` | source paths, query text | ingest/query yaml reports | `state/KB_MANIFEST.yaml`, `artifacts/kb/*`, task run_meta | `tests/test_kb_ingest.py`, `tests/test_kb_query.py` |
| `workflow/pr_ops.py` | source PR 自动化 | `open_pr`, `update_pr`, `close_superseded_prs` | gh + git context | pr entry data | `state/PR_REGISTRY.yaml` | `tests/test_reject_cascade.py`（间接） |
| `workflow/project_ops.py` | project registry 管理 | `add_project`, `update_project`, `scaffold_project` | slug/title/release metadata | project entry + scaffold files | `state/PROJECT_REGISTRY.yaml`, `projects/<slug>/` | `tests/test_project_registry.py` |
| `workflow/release_ops.py` | cross-repo release automation | `bootstrap_release_repo`, `publish_project_release`, `open_release_pr` | project slug, repo settings | release metadata | release repo pushes + `state/PR_REGISTRY.yaml` | `tests/test_release_ops.py` |
| `workflow/ai.py` | AI 调用与预算守卫 + 任务路由 | `run_ai_plan`, `run_ai_audit`, `run_ai_task`, `resolve_route`, `invoke_with_fallback` | prompt/task + budget + api key | plan/audit/task markdown, budget updates | `state/AI_BUDGET.yaml`, `state/PLAN.md`, `artifacts/audit/ai-*.md`, `artifacts/tasks/*/ai/*.md` | `tests/test_ai_budget.py`, `tests/test_ai_routing.py`, `tests/test_ai_fallback.py` |
| `workflow/prompt_composer.py` | Prompt Composer（模块化拼装 + 预算裁剪） | `compose_prompt`, `normalize_prompting_config`, `default_prompting_config` | command/task context + AI config + project override | composed prompt package + module selection metadata | 无直接 state 改写 | `tests/test_prompt_composer.py`, `tests/test_ai_cli.py` |
| `dashboard/app.py` | Streamlit UI 主入口 | `_render_*`, `main` | state + workflow module calls | web UI actions | 触发 workflow 副作用 | `tests/test_dashboard_smoke.py` |
| `dashboard/components.py` | UI 组件封装 | `git_write_guard`, `status_badge` | UI interaction | guarded actions | 无直接 state 改写 | `tests/test_dashboard_smoke.py`（导入级） |
| `docs/WORKFLOW.md` | 日常命令手册 | command playbook | user intent | operational guidance | 无 | 文档审计间接覆盖 |
| `docs/DATA_MODEL.md` | 数据模型契约 | YAML schema docs | model requirements | contract reference | 无 | `workflow/schemas.py` + tests 对齐 |
| `docs/GOVERNANCE.md` | 治理规则文档 | reject cascade policy | governance decisions | policy reference | 无 | `workflow/review_ops.py` 行为对齐 |
| `docs/TASK_WORKFLOW.md` | 任务级协作规范 | role/handoff/evidence rules | task collaboration | rules reference | 无 | `workflow/task_ops.py`, `workflow/audit.py` 对齐 |
| `docs/KB_WORKFLOW.md` | KB 流程规范 | ingest/query/citation rules | kb operations | rules reference | 无 | `workflow/kb_ops.py`, `workflow/citation_ops.py` 对齐 |
| `docs/AI_PROMPTS.md` | prompt 治理规则 | module registry + override policy | AI workflow governance | prompt policy | 无 | 审计 required files 检查 |
| `state/TASKS.yaml` | 任务台账 | `tasks[*]` | human/agent updates | task state | 驱动 review queue / execution | schema + audit checks |
| `state/KEY_RESULTS.yaml` | 关键结论台账 | `results[*]` | validated claims | KR history | checkpoint tags / status downgrade | schema + audit + review cascade |
| `state/REVIEW_QUEUE.yaml` | 审批队列 | `items[*]` | waiting_review tasks | review actions | task status transitions | `tests/test_review_queue_flow.py` |
| `state/PROJECT_REGISTRY.yaml` | 项目注册表 | `projects[*]` | project lifecycle ops | registry entries | release automation source of truth | `tests/test_project_registry.py` |
| `state/PR_REGISTRY.yaml` | PR 跟踪表 | `prs[*]` | pr/release actions | pr records | source/release PR auditability | `tests/test_release_ops.py` |
| `state/KB_MANIFEST.yaml` | KB 文档清单 | `documents[*]` | ingest process | doc metadata | drives index/query quality | `tests/test_kb_ingest.py`, audit checks |
| `state/KB_CONFIG.yaml` | KB 配置 | chunk policy/ignore rules | kb ingest | config baseline | affects ingest behavior | `tests/test_kb_ingest.py`（间接） |
| `state/STATE.md` | 可读快照日志 | `append_state_event` outputs | workflow actions | timeline narrative | accumulates audit trail | 人工审查 + audit required files |
| `state/HUMAN_REVIEW_LOG.md` | 审批留痕 | review table rows | human actions | immutable-like log rows | compliance evidence | `tests/test_review_queue_flow.py` |
| `tests/test_checkpoint_rollback.py` | 回档机制回归 | checkpoint + safe/hard rollback checks | temp git repo | assertions | none | self |
| `tests/test_reject_cascade.py` | Reject 级联回归 | task reset + KR downgrade + rollback branch | temp repo + state fixtures | assertions | none | self |
| `tests/test_kb_ingest.py` | KB ingest 回归 | incremental ingest + task bound outputs | docs fixtures | assertions | none | self |
| `tests/test_kb_query.py` | KB query 回归 | citation validity + task bound query output | docs fixtures | assertions | none | self |
| `tests/test_task_run_meta.py` | run_meta 完整性回归 | command execution + index/worklog updates | temp cwd | assertions | none | self |
| `tests/test_rl_gridworld_qlearning.py` | RL 实验回归 | reproducibility + metrics threshold + artifact outputs | project module | assertions | none | self |
| `.github/workflows/ci.yml` | CI pipeline | pytest gate | push/pr events | test results | GitHub Actions artifacts/logs | platform-level |
| `.github/workflows/audit.yml` | Manual audit action | workflow audit execution | workflow_dispatch | audit artifacts upload | GitHub Actions | platform-level |
| `.github/workflows/codex-review.yml` | Optional AI review action | conditional OpenAI key usage | PR events | review action run | GitHub PR comments/logs | platform-level |

## 3. `workflow/` 深度映射
### 3.1 CLI Surface（`python -m workflow`）
- `status`, `sync`
- `tasks list/add/update`
- `review-queue sync/list/approve/rework/reject`
- `checkpoint`, `checkpoints`, `rollback`
- `verify`, `audit`
- `jobs start/list/stop/logs`
- `task run`
- `kb ingest/query`
- `pr open/update/list/close-superseded`
- `project list/add/update/scaffold`
- `release bootstrap/publish/pr`
- `ai plan/audit/task`

### 3.2 关键数据流
1. `task run` -> `task_ops.record_task_run` -> `run_meta.yaml + run_index.yaml + worklog.md`。
2. `kb ingest` -> `KB_MANIFEST + chunks + index + summaries`，可绑定 task 生成 run_meta。
3. `kb query` -> `hits(cite+sha+snippet)`，可绑定 task 生成 outputs + run_meta。
4. `review reject` -> `dependency reset + safe rollback + KR downgrade + close superseded PR`。

## 4. `state/` 数据模型索引
### 4.1 `TASKS.yaml`
- 任务生命周期：`todo -> in_progress -> waiting_review -> done`，异常可转 `blocked`。
- 最小证据字段：`acceptance`, `evidence`, `verification`。

### 4.2 `KEY_RESULTS.yaml`
- `status`: `proposed|verified|deprecated`。
- `confidence`: `low|medium|high`。
- 要求：每条 KR 需可追溯 `evidence + verification + related_tasks`。

### 4.3 `KB_MANIFEST.yaml`
- 每条文档记录需含：`doc_id/source_uri/local_path/sha256/processed.*`。
- audit 会检查 schema 完整性与字段合法性。

### 4.4 `state/tasks/<task_id>/`
- `brief.yaml`：任务定义。
- `worklog.md`：PDCA 轨迹。
- `evidence_map.yaml`：claim/evidence/verification 映射。
- `handoff.yaml`：角色交接。
- `run_index.yaml`：run 元数据索引。

## 5. `tests/` 覆盖矩阵（功能 -> 风险）

| Test File | 覆盖功能 | 主要风险点 |
|---|---|---|
| `tests/test_state_schema.py` | TASKS/KR schema | 数据结构漂移导致 audit 失真 |
| `tests/test_audit_report.py` | audit report 结构 | 审计报告缺段或不可读 |
| `tests/test_checkpoint_rollback.py` | checkpoint/rollback | 回档不可用或 hard rollback 误触发 |
| `tests/test_review_queue_flow.py` | review queue action flow | 审批状态写入不一致 |
| `tests/test_reject_cascade.py` | reject cascade | 任务未重置、KR 未降级、回退失败 |
| `tests/test_jobs.py` | background jobs | 僵尸进程/状态不一致 |
| `tests/test_ai_budget.py` | AI budget guardrails | 预算超限策略失效 |
| `tests/test_ai_routing.py` | AI 路由矩阵与 legacy 兼容 | 任务类型路由错误或旧配置不兼容 |
| `tests/test_ai_fallback.py` | AI fallback/retry 策略 | 模型不可用无法回退或重试行为错误 |
| `tests/test_ai_cli.py` | `workflow ai task` CLI 行为 | 参数解析/错误返回/默认 intent 语义偏差 |
| `tests/test_project_registry.py` | project registry + scaffold | 多项目记录损坏 |
| `tests/test_release_ops.py` | release automation | 跨库发布链路断裂 |
| `tests/test_task_run_meta.py` | run_meta persistence | 运行证据不可追溯 |
| `tests/test_citation_validity.py` | citation parsing/validation | 引用不可验证或 hash 失配 |
| `tests/test_kb_ingest.py` | KB incremental ingest | 重复入库、清单错误 |
| `tests/test_kb_query.py` | KB query + citation output | 检索无引用或引用错误 |
| `tests/test_lemma1.py` | derivation verification | 推导无可执行证明 |
| `tests/test_rl_gridworld_qlearning.py` | RL reproducibility/thresholds | 实验不可复现或回归退化 |
| `tests/test_workflow_git_ops.py` | git utility functions | 状态感知失效 |
| `tests/test_dashboard_smoke.py` | dashboard importability | UI 入口无法启动 |

## 6. `artifacts/` 全量索引（当前仓库快照）

说明：以下为当前 `artifacts/` 的完整文件列表，按类型分组展示，不做裁剪。

### 6.1 artifacts/audit（审计报告）
- `artifacts/audit/20260221-0027.md`
- `artifacts/audit/20260221-0034.md`
- `artifacts/audit/20260221-0049.md`
- `artifacts/audit/20260221-0051.md`
- `artifacts/audit/20260221-0054.md`
- `artifacts/audit/20260221-0159.md`
- `artifacts/audit/20260221-0311.md`
- `artifacts/audit/20260221-0318.md`
- `artifacts/audit/20260221-0449.md`
- `artifacts/audit/20260221-0450.md`
- `artifacts/audit/20260221-0451.md`
- `artifacts/audit/20260221-0454.md`
- `artifacts/audit/20260221-0455.md`
- `artifacts/audit/20260221-0456.md`
- `artifacts/audit/20260221-1738.md`
- `artifacts/audit/20260221-2034.md`
- `artifacts/audit/20260221-2038.md`
- `artifacts/audit/ai-20260221-0044.md`
- `artifacts/audit/ai-20260221-0316.md`
- `artifacts/audit/pr-ready-brief.md`

### 6.2 artifacts/test（verify 报告）
- `artifacts/test/verify-20260221-0034.md`
- `artifacts/test/verify-20260221-0051.md`
- `artifacts/test/verify-20260221-0054.md`
- `artifacts/test/verify-20260221-0159.md`
- `artifacts/test/verify-20260221-0202.md`
- `artifacts/test/verify-20260221-0310.md`
- `artifacts/test/verify-20260221-0318.md`
- `artifacts/test/verify-20260221-0449.md`
- `artifacts/test/verify-20260221-0450.md`
- `artifacts/test/verify-20260221-0451.md`
- `artifacts/test/verify-20260221-0453.md`
- `artifacts/test/verify-20260221-0456.md`
- `artifacts/test/verify-20260221-1738.md`
- `artifacts/test/verify-20260221-2034.md`
- `artifacts/test/verify-20260221-2038.md`

### 6.3 artifacts/kb/index（倒排索引）
- `artifacts/kb/index/chunk_meta.jsonl`
- `artifacts/kb/index/inverted.json`

### 6.4 artifacts/kb/processed/chunks（chunk 数据）
- `artifacts/kb/processed/chunks/DOC-0556811c.jsonl`
- `artifacts/kb/processed/chunks/DOC-0f2ff4a4.jsonl`
- `artifacts/kb/processed/chunks/DOC-14dcdf16.jsonl`
- `artifacts/kb/processed/chunks/DOC-38159754.jsonl`
- `artifacts/kb/processed/chunks/DOC-3b24d521.jsonl`
- `artifacts/kb/processed/chunks/DOC-85e276f6.jsonl`
- `artifacts/kb/processed/chunks/DOC-b76f66e4.jsonl`
- `artifacts/kb/processed/chunks/DOC-d5a222b2.jsonl`
- `artifacts/kb/processed/chunks/DOC-dcdcf99a.jsonl`
- `artifacts/kb/processed/chunks/DOC-def6e824.jsonl`
- `artifacts/kb/processed/chunks/DOC-ef3bfead.jsonl`
- `artifacts/kb/processed/chunks/DOC-fa16fb47.jsonl`

### 6.5 artifacts/kb/summaries/chunk（chunk 摘要）
- `artifacts/kb/summaries/chunk/DOC-0556811c.jsonl`
- `artifacts/kb/summaries/chunk/DOC-0f2ff4a4.jsonl`
- `artifacts/kb/summaries/chunk/DOC-14dcdf16.jsonl`
- `artifacts/kb/summaries/chunk/DOC-38159754.jsonl`
- `artifacts/kb/summaries/chunk/DOC-3b24d521.jsonl`
- `artifacts/kb/summaries/chunk/DOC-85e276f6.jsonl`
- `artifacts/kb/summaries/chunk/DOC-b76f66e4.jsonl`
- `artifacts/kb/summaries/chunk/DOC-d5a222b2.jsonl`
- `artifacts/kb/summaries/chunk/DOC-dcdcf99a.jsonl`
- `artifacts/kb/summaries/chunk/DOC-def6e824.jsonl`
- `artifacts/kb/summaries/chunk/DOC-ef3bfead.jsonl`
- `artifacts/kb/summaries/chunk/DOC-fa16fb47.jsonl`

### 6.6 artifacts/kb/summaries/doc（doc 摘要）
- `artifacts/kb/summaries/doc/DOC-0556811c.yaml`
- `artifacts/kb/summaries/doc/DOC-0f2ff4a4.yaml`
- `artifacts/kb/summaries/doc/DOC-14dcdf16.yaml`
- `artifacts/kb/summaries/doc/DOC-38159754.yaml`
- `artifacts/kb/summaries/doc/DOC-3b24d521.yaml`
- `artifacts/kb/summaries/doc/DOC-85e276f6.yaml`
- `artifacts/kb/summaries/doc/DOC-b76f66e4.yaml`
- `artifacts/kb/summaries/doc/DOC-d5a222b2.yaml`
- `artifacts/kb/summaries/doc/DOC-dcdcf99a.yaml`
- `artifacts/kb/summaries/doc/DOC-def6e824.yaml`
- `artifacts/kb/summaries/doc/DOC-ef3bfead.yaml`
- `artifacts/kb/summaries/doc/DOC-fa16fb47.yaml`

### 6.7 artifacts/kb/summaries/corpus（corpus 摘要）
- `artifacts/kb/summaries/corpus/latest.md`

### 6.8 artifacts/kb（query 报告）
- `artifacts/kb/query-20260221-045032.yaml`
- `artifacts/kb/query-20260221-045111.yaml`
- `artifacts/kb/query-20260221-045137.yaml`
- `artifacts/kb/query-20260221-045337.yaml`
- `artifacts/kb/query-20260221-045356.yaml`
- `artifacts/kb/query-20260221-045605.yaml`
- `artifacts/kb/query-20260221-173825.yaml`
- `artifacts/kb/query-20260221-203403.yaml`
- `artifacts/kb/query-20260221-203445.yaml`
- `artifacts/kb/query-20260221-203810.yaml`

### 6.9 artifacts/tasks/T-0015/outputs（任务输出）
- `artifacts/tasks/T-0015/outputs/ingest-20260221-045018.yaml`
- `artifacts/tasks/T-0015/outputs/query-20260221-045023.yaml`
- `artifacts/tasks/T-0015/outputs/query-20260221-045104.yaml`
- `artifacts/tasks/T-0015/outputs/query-20260221-045130.yaml`
- `artifacts/tasks/T-0015/outputs/query-20260221-045137.yaml`
- `artifacts/tasks/T-0015/outputs/query-20260221-045338.yaml`
- `artifacts/tasks/T-0015/outputs/query-20260221-045356.yaml`
- `artifacts/tasks/T-0015/outputs/query-20260221-045605.yaml`
- `artifacts/tasks/T-0015/outputs/query-20260221-173825.yaml`
- `artifacts/tasks/T-0015/outputs/query-20260221-203403.yaml`
- `artifacts/tasks/T-0015/outputs/query-20260221-203445.yaml`
- `artifacts/tasks/T-0015/outputs/query-20260221-203810.yaml`

### 6.10 artifacts/tasks/T-0015/runs/*（run_meta + logs）
- `artifacts/tasks/T-0015/runs/RUN-20260221-045011755757/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045011755757/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045011755757/stdout.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045018277484/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045018277484/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045018277484/stdout.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045023280669/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045023280669/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045023280669/stdout.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045104226899/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045104226899/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045104226899/stdout.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045130813155/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045130813155/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045130813155/stdout.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045137904489/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045137904489/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045137904489/stdout.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045338004336/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045338004336/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045338004336/stdout.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045338037268/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045338037268/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045338037268/stdout.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045356758860/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045356758860/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045356758860/stdout.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045605228354/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045605228354/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-045605228354/stdout.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-173825584102/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-173825584102/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-173825584102/stdout.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-203403708173/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-203403708173/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-203403708173/stdout.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-203445143105/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-203445143105/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-203445143105/stdout.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-203810117071/run_meta.yaml`
- `artifacts/tasks/T-0015/runs/RUN-20260221-203810117071/stderr.log`
- `artifacts/tasks/T-0015/runs/RUN-20260221-203810117071/stdout.log`

### 6.11 artifacts/experiments/rl-gridworld-qlearning（实验产物）
- `artifacts/experiments/rl-gridworld-qlearning/q_table.npy`
- `artifacts/experiments/rl-gridworld-qlearning/report.md`
- `artifacts/experiments/rl-gridworld-qlearning/summary.json`
- `artifacts/experiments/rl-gridworld-qlearning/training_trace.csv`

## 7. 使用建议（Reviewer 快速路径）
1. 先看 `README.md` 的 Architecture 与核心机制章节。
2. 再看本附录第 2 节（核心文件矩阵）锁定实现入口。
3. 如需证据复核，直接跳到第 6 节对应 artifacts 文件。
4. 如需风险评估，优先看 `workflow/audit.py` + `tests/test_reject_cascade.py` + `tests/test_task_run_meta.py`。

## 8. 维护策略
- 当新增核心模块时，必须同步更新本附录第 2 节。
- 当新增 artifacts 类型时，必须扩展第 6 节分组。
- 建议在 CI 中增加“附录索引更新检查”防止文档漂移。
