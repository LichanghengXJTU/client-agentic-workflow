# AI_PROMPTS / 提示词治理

## Prompt Assets
- Role entries:
  - Planner: `prompts/planner.md`
  - Auditor: `prompts/auditor.md`
  - Reflector: `prompts/reflector.md`
  - Retriever: `prompts/retriever.md`
  - Implementer: `prompts/implementer.md`
  - Scribe: `prompts/scribe.md`
  - Critic: `prompts/critic.md`
- Modular registry:
  - Global: `prompts/registry.yaml`
  - Module files: `prompts/modules/*`
- Project overrides:
  - `projects/<slug>/prompts/registry.yaml`
  - `projects/<slug>/prompts/modules/*`
- PR review prompt:
  - `.github/codex/prompts/review.md`

## 管理规则
- 提示词必须版本化（通过 Git 跟踪）。
- 每次重大改动需说明变更原因与预期效果。
- 不得在 prompt 中写入密钥、隐私数据或不可公开信息。
- 项目级 prompt 覆盖全局同 ID 模块（project override > global）。

## Prompt Composer（V2）
- 接口：`workflow/prompt_composer.py::compose_prompt`
- 输出结构：
  - `text`
  - `selected_modules`
  - `dropped_modules`
  - `estimated_tokens`
  - `budget_profile`
  - `response_profile`
  - `project_override_applied`
- 裁剪策略（预算守卫）：
  - `target`: 先删低优先可裁剪模块
  - `soft_limit`: 继续删模块并压缩上下文
  - `hard_limit`: 仅保留必选模块 + 极简上下文

## 执行策略
- `workflow ai plan` 默认 `response_profile=qa_zh`。
- `workflow ai audit` 默认 `response_profile=audit_cn`。
- `workflow ai task` 默认 `response_profile=qa_zh`。
- 可选参数：
  - `--response-profile {qa_zh,paper_en,audit_cn}`
  - `--project <slug>`
  - `--viz {auto,on,off}`
  - `--prompt-budget {high,medium,low}`
- `--prompt` 手工输入优先级最高，提供后将跳过 Prompt Composer。
- 成本受 `state/AI_BUDGET.yaml` 控制：80% 预警，100% 降级模型。

## 严格性基线
- 数学：不跳步推导 + 至少双路径验算（符号与数值/边界/不变量）。
- 代码：可运行代码 + 测试 + 关键中间与最终产物落盘。
- 展示：主文结论 + Appendix 全步骤（layered appendix）。
