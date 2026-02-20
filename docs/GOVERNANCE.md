# GOVERNANCE / 审批与回档治理

## 1. 人类审批优先级
- AI 可提案，Human 有最终裁决权。
- 所有待审事项进入 `state/REVIEW_QUEUE.yaml`。

## 2. 审批动作定义
- Approve: 任务通过，状态变更为 `done`。
- Rework: 任务返工，状态变更为 `blocked`（等待重新执行）。
- Reject: 触发级联重启策略。

## 3. Reject Cascade Restart
Reject 时必须提供 anchor（tag/commit）。系统将：
1. 新建 `rollback/<anchor>-<timestamp>` 分支。
2. 对 `(anchor..HEAD]` 提交做 `git revert`。
3. 将被拒任务标记为 `blocked`，依赖任务重置为 `todo`。
4. 将锚点后不可信关键结论降级为 `proposed`。
5. 自动关闭 superseded PR（若存在）。
6. 写入 `state/HUMAN_REVIEW_LOG.md` 与 `state/STATE.md`。

## 4. 风险分级
- P0: 影响正确性/可回滚性/可追溯性的错误。
- P1: 流程不一致、审计覆盖不足。
- P2: 可读性和效率优化。

## 5. 禁止事项
- 未经明确确认的硬回档/force push。
- 缺失验证就宣称结论“verified”。
- 审批不留痕。

## 6. PR Gate
每个 PR 必须包含：
- 变更摘要
- 验收清单
- 回滚说明
- 如涉及关键结论，附 KEY_RESULTS 更新条目
