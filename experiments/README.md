# Experiments Workflow / 仿真实验规范

每个实验建议包含：
- 实验目标（Goal）
- 参数与随机种子（Config + Seed）
- 运行命令（Reproduce Command）
- 输出路径（Artifacts Path）
- 对应任务 ID 与关键结论 ID

结果建议落盘到 `artifacts/` 并在 `state/KEY_RESULTS.yaml` 建立引用。
