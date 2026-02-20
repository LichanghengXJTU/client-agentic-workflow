from __future__ import annotations

from workflow.schemas import validate_key_results_data, validate_tasks_data


def test_tasks_schema_valid() -> None:
    data = {
        "tasks": [
            {
                "id": "T-0001",
                "title": "Build workflow",
                "type": "code",
                "priority": "P0",
                "owner": "codex",
                "status": "todo",
                "acceptance": ["works"],
                "evidence": ["docs/WORKFLOW.md"],
                "verification": ["python -m workflow audit"],
                "depends_on": [],
                "created_at": "2026-02-20",
                "updated_at": "2026-02-20",
            }
        ]
    }
    ok, issues = validate_tasks_data(data)
    assert ok
    assert not issues


def test_tasks_schema_invalid_enum_and_date() -> None:
    data = {
        "tasks": [
            {
                "id": "BAD",
                "title": "",
                "type": "invalid",
                "priority": "HIGH",
                "owner": "bot",
                "status": "running",
                "acceptance": "bad",
                "evidence": [],
                "verification": [],
                "depends_on": [],
                "created_at": "2026/02/20",
                "updated_at": "today",
            }
        ]
    }
    ok, issues = validate_tasks_data(data)
    assert not ok
    paths = {issue.path for issue in issues}
    assert "tasks[0].id" in paths
    assert "tasks[0].type" in paths
    assert "tasks[0].created_at" in paths


def test_key_results_schema_valid() -> None:
    data = {
        "results": [
            {
                "id": "KR-0001",
                "statement": "x+y= y+x",
                "status": "verified",
                "confidence": "high",
                "evidence": ["GUIDE.md#..."],
                "verification": ["python derivations/examples/lemma1_check.py"],
                "related_tasks": ["T-0001"],
                "first_seen_commit": "abc123",
                "last_confirmed_commit": "abc123",
                "checkpoint_tags": ["cp-20260220-1200-lemma"],
            }
        ]
    }
    ok, issues = validate_key_results_data(data)
    assert ok
    assert not issues


def test_key_results_schema_invalid() -> None:
    data = {
        "results": [
            {
                "id": "K-1",
                "statement": "",
                "status": "ok",
                "confidence": "sure",
                "evidence": [],
                "verification": [],
                "related_tasks": [],
                "first_seen_commit": "",
                "last_confirmed_commit": "",
                "checkpoint_tags": [],
            }
        ]
    }
    ok, issues = validate_key_results_data(data)
    assert not ok
    paths = {issue.path for issue in issues}
    assert "results[0].id" in paths
    assert "results[0].status" in paths
    assert "results[0].confidence" in paths
