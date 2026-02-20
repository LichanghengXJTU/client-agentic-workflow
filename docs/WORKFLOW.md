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

## 8. AI plan/audit（预算守卫）
```bash
python3 -m workflow ai plan
python3 -m workflow ai audit
```
- 配置：`state/AI_CONFIG.yaml`
- 密钥（本地不入库）：`state/AI_SECRETS.local.yaml` 或 `OPENAI_API_KEY`
- 预算账本：`state/AI_BUDGET.yaml`
- 80% 预警，100% 自动降级模型。

## 9. Dashboard
```bash
streamlit run dashboard/app.py
```
Tabs:
- Overview
- Tasks
- Review Queue
- Checkpoints
- Audit & Verify
- Jobs & AI

## 10. 推荐的每日循环（简单版）
1. `workflow sync` + `workflow status`
2. 在 Tasks 中推进任务，完成后改为 `waiting_review`
3. 审批（approve/rework/reject）
4. 跑 `verify` + `audit`
5. 创建 checkpoint
6. 需要发布时 `pr open`

## 11. 跨平台说明（macOS/Linux/Windows）
- macOS/Linux: 直接使用本文命令。
- Windows PowerShell: 将 `python3` 改为 `python`，路径分隔符可用 `\\`。
- 后台任务命令（jobs）在 Windows 上可能不支持进程组终止，若 stop 失败可手动结束进程。
