# AGENTS Constitution / AI协作宪法

## 1. Purpose
本仓库用于构建并长期维护一个可审计（Auditable）、可验证（Verifiable）、可回档（Rollback-safe）的研究与工程协作系统。

## 2. Severity Levels
- P0: 错误关键结论、无验证的关键推导、破坏回档安全、schema 损坏、审批记录缺失。
- P1: 行为与文档不一致、审计盲区、审批队列/任务状态不一致。
- P2: 可读性、易用性、非阻塞改进。

## 3. Non-negotiable Rules
- 不允许编造。任何不确定信息必须明确标注 `uncertain`。
- 每条关键结论必须写入 `state/KEY_RESULTS.yaml`，并附 evidence + verification。
- 数学推导必须至少有一种可运行验证：SymPy、数值对拍、双实现、边界/不变量测试。
- 默认禁止破坏性历史重写（`git reset --hard`、force push）。
- Reject 默认触发安全级联：rollback 分支 + git revert + 任务状态重启。

## 4. Mandatory Sync After Changes
每次完成实质性改动，至少检查并更新：
- `state/STATE.md`（当前快照/交接上下文）
- `state/KEY_RESULTS.yaml`（若产生/修改关键结论）
- `artifacts/audit/`（若执行审计）
- `state/HUMAN_REVIEW_LOG.md`（若发生审批动作）

## 5. PR Requirements
每个 PR 必须包含：
- 变更摘要（What changed）
- 验收标准对照（Acceptance checklist）
- 回滚说明（Rollback note）

## 6. Fixed Execution Loop (PDCA)
所有任务按统一结构执行与记录：
1. Plan: 明确目标、约束、验收标准。
2. Do: 实施并产出可追溯证据。
3. Check: 运行 verify/audit/tests，确认结果可复核。
4. Act: 根据审阅结论推进、返工或回档。

## 7. Governance for Human-in-the-loop
- 人类审批为一等公民：所有待审项进入 `state/REVIEW_QUEUE.yaml`。
- 审批动作仅三种：Approve / Rework / Reject。
- Reject 需要 anchor（checkpoint/tag/commit），并记录原因与回档路径。
