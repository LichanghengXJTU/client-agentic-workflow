# Derivations Workflow / 推导资产化规范

## 规则
- 每个 lemma/theorem 必须有 markdown 推导文件。
- 每个关键推导至少有一个可运行验证脚本。
- 推荐同时有 pytest 用例，便于统一 `workflow verify`。

## 目录建议
- `derivations/examples/*.md`：推导说明
- `derivations/examples/*_check.py`：验证脚本（SymPy/数值对拍）

## 示例
- `derivations/examples/lemma1.md`
- `derivations/examples/lemma1_check.py`
- `tests/test_lemma1.py`
