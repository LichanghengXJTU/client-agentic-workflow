# AI_PROMPTS / 提示词治理

## Prompt Files
- Planner: `prompts/planner.md`
- Auditor: `prompts/auditor.md`
- Reflector: `prompts/reflector.md`
- Retriever: `prompts/retriever.md`
- Implementer: `prompts/implementer.md`
- Scribe: `prompts/scribe.md`
- Critic: `prompts/critic.md`

## 管理规则
- 提示词必须版本化（通过 Git 跟踪）。
- 每次重大改动需说明变更原因与预期效果。
- 不得在 prompt 中写入密钥、隐私数据或不可公开信息。

## 执行策略
- `workflow ai plan` 使用 planner 风格（高推理）。
- `workflow ai audit` 使用 auditor 风格（风险优先）。
- 成本受 `state/AI_BUDGET.yaml` 控制：80% 预警，100% 降级模型。
