# PLAN

## Current Phase
- Final validation and reviewer handoff

## Focus
1. 运行 verify + audit，确认 P0=0。
2. 创建 checkpoint 并准备 PR-ready 描述。
3. 由 human 对 `RQ-0009` 做最终审批。

## Acceptance Checklist
- [ ] `python -m workflow status` 正常
- [ ] `python -m workflow verify` 正常
- [ ] `python -m workflow audit` 正常且 P0=0
- [ ] `streamlit run dashboard/app.py` 可启动
- [ ] `docs/WORKFLOW.md` 可指导日常使用

## Risks
- 若未配置 GitHub remote，则自动 PR 无法执行。
- 若未配置 API key，AI 子命令仅生成 pending 报告。
