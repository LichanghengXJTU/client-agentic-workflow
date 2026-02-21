from __future__ import annotations

from workflow.__main__ import main
from workflow.ai import AICallResult


def _ok_result() -> AICallResult:
    return AICallResult(
        ok=True,
        model="gpt-5.2-pro",
        requested_model="gpt-5.2-pro",
        route_key="pro",
        selection_note="normal",
        output_path="state/PLAN.md",
        text="ok",
        spend_usd=0.0,
        budget_ratio=0.0,
        message="ok",
    )


def test_ai_task_cli_success(monkeypatch) -> None:
    monkeypatch.setattr("workflow.__main__.append_state_event", lambda title, details: None)
    monkeypatch.setattr("workflow.__main__.task_by_id", lambda task_id: {"id": task_id, "type": "code", "title": "demo"})
    monkeypatch.setattr("workflow.__main__.run_ai_task", lambda task_id, intent, prompt, output_path=None: _ok_result())

    rc = main(["ai", "task", "--id", "T-0001", "--prompt", "hello"])
    assert rc == 0


def test_ai_task_cli_task_not_found_returns_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr("workflow.__main__.append_state_event", lambda title, details: None)

    def _missing(task_id: str):
        raise KeyError(f"Task not found: {task_id}")

    monkeypatch.setattr("workflow.__main__.task_by_id", _missing)

    rc = main(["ai", "task", "--id", "T-9999"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "Task not found" in out


def test_ai_task_cli_experiment_default_design(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    monkeypatch.setattr("workflow.__main__.append_state_event", lambda title, details: None)
    monkeypatch.setattr("workflow.__main__.task_by_id", lambda task_id: {"id": task_id, "type": "experiment", "title": "exp"})

    def _fake_run_ai_task(task_id: str, intent: str | None, prompt: str, output_path: str | None = None) -> AICallResult:
        captured["task_id"] = task_id
        captured["intent"] = intent
        captured["prompt"] = prompt
        return _ok_result()

    monkeypatch.setattr("workflow.__main__.run_ai_task", _fake_run_ai_task)

    rc = main(["ai", "task", "--id", "T-0001"])
    assert rc == 0
    assert captured["task_id"] == "T-0001"
    assert captured["intent"] is None
    assert "INTENT" in str(captured["prompt"])
    assert "design" in str(captured["prompt"])
