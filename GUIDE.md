# GUIDE / Long-Running Guidebook

## 1. Workflow Principles
- 目标：构建可审计、可验证、可回档的日常研究与工程工作流。
- 方法：所有关键产出必须落盘（state/docs/artifacts）。
- 节奏：Plan -> Do -> Check -> Act。

## 2. Mathematical Derivation Assets
- 推导规则见 `derivations/README.md`。
- 示例推导：`derivations/examples/lemma1.md`
- 示例验证脚本：`derivations/examples/lemma1_check.py`
- 示例测试：`tests/test_lemma1.py`

## 3. Literature and Citation Assets
- 阅读流程见 `literature/README.md`
- 笔记目录：`literature/notes/`
- 引用库：`literature/references.bib`

## 4. Experiment and Simulation Assets
- 规范见 `experiments/README.md`
- 建议每个实验提供参数记录、随机种子、复现实验入口。

## 5. Engineering and CI Assets
- CLI 入口：`python -m workflow ...`
- Dashboard：`streamlit run dashboard/app.py`
- CI/Audit Actions：`.github/workflows/`

## 6. Audit and Governance
- 审计命令：`python -m workflow audit`
- 验证命令：`python -m workflow verify`
- 人类审批队列：`state/REVIEW_QUEUE.yaml`
- 审批日志：`state/HUMAN_REVIEW_LOG.md`
