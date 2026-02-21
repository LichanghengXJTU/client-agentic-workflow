# WORKFLOW 使用说明 / Daily Playbook

## 1. 安装
```bash
python3 -m pip install -r requirements.txt
```

## 2. 每天开始（双电脑通用）
```bash
python3 -m workflow sync
python3 -m workflow status
```
说明：先同步，再开始工作。另一台电脑也是同样动作。

## 3. 任务管理（TASKS）
```bash
python3 -m workflow tasks list
python3 -m workflow tasks add --title "推导 Bellman 误差上界" --type derivation --priority P0 --owner codex --status in_progress --acceptance "给出可运行验证脚本"
python3 -m workflow tasks update --id T-0001 --status waiting_review
```

## 4. 人类审批（Review Queue）
```bash
python3 -m workflow review-queue sync
python3 -m workflow review-queue list
python3 -m workflow review-queue approve --id RQ-0001 --reviewer human --notes "通过"
python3 -m workflow review-queue rework --id RQ-0001 --reviewer human --notes "补测试"
python3 -m workflow review-queue reject --id RQ-0001 --anchor cp-20260220-1200-demo --reviewer human --notes "基线错误"
```
Reject 会触发安全级联重启（rollback 分支 + revert + 任务重置 + 关闭 superseded PR）。

## 4.5 项目注册（Project Registry）
```bash
python3 -m workflow project list
python3 -m workflow project scaffold --slug rl-gridworld-qlearning --title "RL Gridworld Q-learning"
python3 -m workflow project add --slug rl-gridworld-qlearning --title "RL Gridworld Q-learning" \
  --local-path projects/rl-gridworld-qlearning \
  --release-repo LichanghengXJTU/rl-gridworld-qlearning-release \
  --release-visibility public --release-default-branch main --status active
python3 -m workflow project update --slug rl-gridworld-qlearning --status archived
```

## 4.6 跨库发布（Release Automation）
```bash
python3 -m workflow release bootstrap --project rl-gridworld-qlearning --visibility public
python3 -m workflow release publish --project rl-gridworld-qlearning
python3 -m workflow release pr --project rl-gridworld-qlearning \
  --title "release: rl-gridworld-qlearning sync" --body "sync from source repo"
```
说明：
- `release publish` 仅导出项目目录 `projects/<slug>/`，不会发布整个源仓库。
- 发布 PR 会记录到 `state/PR_REGISTRY.yaml`，并标记 `role: release`。

## 5. 验证与审计
```bash
python3 -m workflow verify
python3 -m workflow audit
```
输出位置：
- 验证报告：`artifacts/test/`
- 审计报告：`artifacts/audit/`

## 6. Checkpoint 与回档
```bash
python3 -m workflow checkpoint --summary "phase-x-stable" --key-result KR-0001
python3 -m workflow checkpoints
python3 -m workflow rollback --mode safe --anchor cp-20260220-1200-demo
```
硬回档仅高级用途（默认禁用）：
```bash
python3 -m workflow rollback --mode hard --anchor <ref> --confirm-phrase I_UNDERSTAND_HARD_RESET
```

## 7. 自动 PR（gh CLI）
```bash
python3 -m workflow pr open --title "feat: xxx" --body "summary"
python3 -m workflow pr list
python3 -m workflow pr close-superseded --anchor <checkpoint-or-commit>
```

## 8. AI plan/audit/task（预算守卫 + 任务路由）
```bash
python3 -m workflow ai plan
python3 -m workflow ai audit
python3 -m workflow ai task --id T-0015 --intent design
python3 -m workflow ai task --id T-0015 --intent run

# Prompt Composer V2 参数
python3 -m workflow ai plan --response-profile qa_zh --project rl-gridworld-qlearning --viz auto --prompt-budget high
python3 -m workflow ai audit --response-profile audit_cn --project rl-gridworld-qlearning --viz on --prompt-budget high
python3 -m workflow ai task --id T-0015 --intent run --response-profile paper_en --project rl-gridworld-qlearning --viz auto --prompt-budget high
```
- 配置：`state/AI_CONFIG.yaml`
- 密钥（本地不入库）：`state/AI_SECRETS.local.yaml` 或 `OPENAI_API_KEY`
- 预算账本：`state/AI_BUDGET.yaml`
- 路由：`plan/audit -> pro`，`task.type -> pro/codex`（`experiment` 支持 `design/run`）。
- 80% 预警，100% 自动降级 `hard_limit_model`（默认 `gpt-5-mini`）。
- 模型不可用时按 route 对应 fallback chain 自动回退。
- Prompt Composer：
  - 全局模块：`prompts/registry.yaml` + `prompts/modules/*`
  - 项目覆盖：`projects/<slug>/prompts/registry.yaml`（同 ID 模块覆盖全局）
  - 手工 `--prompt` 优先级最高，提供时跳过 composer

## 8.5 Task Role Run（run_meta）
```bash
python3 -m workflow task run --id T-0015 --role implementer --cmd "python -m workflow verify"
```
- 任务级 state：`state/tasks/<task_id>/`
- 运行元数据：`artifacts/tasks/<task_id>/runs/<run_id>/run_meta.yaml`

## 8.6 KB Ingest/Query
```bash
python3 -m workflow kb ingest --task T-0015 --src docs --src literature
python3 -m workflow kb query --task T-0015 --q "rollback safety" --top-k 8
```
- 配置：`state/KB_CONFIG.yaml`
- 清单：`state/KB_MANIFEST.yaml`
- 索引：`artifacts/kb/index/`

## 9. Dashboard
```bash
streamlit run dashboard/app.py
```
Tabs:
- Overview
- Intake Center
- Execution Center
- Review Queue
- Checkpoints
- Audit & Verify
- Jobs & AI

Intake Center:
- 输入长文本 prompt + 仓库文件路径 + 可选上传附件
- 自动拆解为结构化 sections，并给 completeness + clarifications
- 一次性创建 `TASKS.yaml` 任务 + `state/tasks/<task_id>/intake.yaml` + `subtasks.yaml`

Execution Center:
- 左侧任务摘要列表，右侧任务/子任务 hero
- 子任务动态流：AI 输出、run_meta、verify/audit 摘要、审批事件
- 子任务审批：Approve/Rework/Reject（Reject 必须 anchor，触发 rollback cascade）
- 聚合相关 PR 摘要与图片产物画廊

## 10. 推荐的每日循环（简单版）
1. `workflow sync` + `workflow status`
2. 在 Intake Center 录入复杂输入并创建任务
3. 在 Execution Center 推进子任务并同步 review queue
4. 审批（approve/rework/reject，subtask 可选 cascade scope）
5. 跑 `verify` + `audit`
6. 创建 checkpoint
7. 需要发布时 `pr open`

## 11. 跨平台说明（macOS/Linux/Windows）
- macOS/Linux: 直接使用本文命令。
- Windows PowerShell: 将 `python3` 改为 `python`，路径分隔符可用 `\\`。
- 后台任务命令（jobs）在 Windows 上可能不支持进程组终止，若 stop 失败可手动结束进程。
