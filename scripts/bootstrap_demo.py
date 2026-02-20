from __future__ import annotations

from workflow.state_ops import (
    atomic_write_yaml,
    today_str,
)


def main() -> None:
    today = today_str()

    tasks = {
        "tasks": [
            {
                "id": "T-0001",
                "title": "建立 workflow 最小闭环",
                "type": "meta",
                "priority": "P0",
                "owner": "codex",
                "status": "waiting_review",
                "acceptance": ["status/audit/verify 可运行", "dashboard 可启动"],
                "evidence": ["docs/WORKFLOW.md"],
                "verification": ["python -m workflow verify", "python -m workflow audit"],
                "depends_on": [],
                "created_at": today,
                "updated_at": today,
            },
            {
                "id": "T-0002",
                "title": "完成 lemma1 推导与符号验证",
                "type": "derivation",
                "priority": "P1",
                "owner": "codex",
                "status": "todo",
                "acceptance": ["SymPy 脚本通过", "pytest 用例通过"],
                "evidence": ["derivations/examples/lemma1.md"],
                "verification": ["python derivations/examples/lemma1_check.py", "python -m pytest -q tests/test_lemma1.py"],
                "depends_on": ["T-0001"],
                "created_at": today,
                "updated_at": today,
            },
        ]
    }

    key_results = {
        "results": [
            {
                "id": "KR-0001",
                "statement": "(a+b)^2 = a^2 + 2ab + b^2 在符号层面验证通过。",
                "status": "verified",
                "confidence": "high",
                "evidence": [
                    "derivations/examples/lemma1.md",
                    "tests/test_lemma1.py::test_lemma1_symbolic_verification_script",
                ],
                "verification": [
                    "python derivations/examples/lemma1_check.py",
                    "python -m pytest -q tests/test_lemma1.py",
                ],
                "related_tasks": ["T-0002"],
                "first_seen_commit": "TBD",
                "last_confirmed_commit": "TBD",
                "checkpoint_tags": [],
            }
        ]
    }

    atomic_write_yaml("state/TASKS.yaml", tasks)
    atomic_write_yaml("state/KEY_RESULTS.yaml", key_results)
    print("Demo TASKS and KEY_RESULTS generated.")


if __name__ == "__main__":
    main()
