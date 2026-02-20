# Reviewer Brief

## 1) 实现内容 / What is implemented
- 完整 CLI：`status/sync/tasks/review-queue/checkpoint/checkpoints/rollback/verify/audit/jobs/pr/ai`
- 安全回档：默认 `rollback/<anchor>-<ts>` + `git revert`，硬回档需要确认短语
- 人类审批闭环：`REVIEW_QUEUE` + `HUMAN_REVIEW_LOG` + Reject 级联重启
- 自动 PR：基于本地 `gh`，支持 open/update/list/close-superseded
- 审计与验证：schema 校验、验证覆盖检查、报告落盘
- Dashboard 六页签：Overview/Tasks/Review Queue/Checkpoints/Audit&Verify/Jobs&AI
- AI 集成：Responses API 入口 + 月预算守卫 + 无 key 优雅降级
- GitHub Actions：CI、手动 Audit、可选 Codex Review

## 2) 最小运行命令 / Quick Start
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m workflow status
python -m workflow verify
python -m workflow audit
streamlit run dashboard/app.py
```

## 3) 验收对照 / Acceptance Checklist
- [x] CLI 核心命令可运行
- [x] Dashboard 可启动并可执行审批/回档/验证/审计
- [x] 审计报告输出到 `artifacts/audit/`
- [x] checkpoint/rollback + schema 校验有测试覆盖
- [x] 文档覆盖 daily usage、审批、回档策略

## 4) 回滚说明 / Rollback Note
- 推荐：
```bash
python -m workflow checkpoints
python -m workflow rollback --mode safe --anchor <checkpoint-or-commit>
```
- 高风险（默认禁用）：
```bash
python -m workflow rollback --mode hard --anchor <ref> --confirm-phrase I_UNDERSTAND_HARD_RESET
```

## 5) Remaining TODO
- 人类执行首次 `RQ-0009` 最终审批
- 在真实研究任务上运行首个完整日循环
- 配置 `OPENAI_API_KEY` 后验证 AI 实际在线调用路径
