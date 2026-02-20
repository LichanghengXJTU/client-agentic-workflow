# DECISIONS (ADR)

## ADR-0001: Safe Rollback By Default
- Date: 2026-02-20
- Status: Accepted
- Decision: Reject/human rollback defaults to `rollback/<ref>` branch + `git revert`, not hard history rewrite.

## ADR-0002: Reject Cascade Restart
- Date: 2026-02-21
- Status: Accepted
- Decision: Reject 必须提供 anchor，并触发任务状态级联重置与 superseded PR 关闭。

## ADR-0003: AI Budget Guardrails
- Date: 2026-02-21
- Status: Accepted
- Decision: AI 月预算默认 2000 USD；80% 预警；100% 降级高成本模型。
