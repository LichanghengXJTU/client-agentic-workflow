from __future__ import annotations

from pathlib import Path

from workflow.ai import run_ai_plan
from workflow.state_ops import atomic_write_yaml, read_yaml


class _FakeUsage:
    def __init__(self) -> None:
        self.input_tokens = 100
        self.output_tokens = 50
        self.cached_tokens = 0


class _FakeResponse:
    def __init__(self) -> None:
        self.output_text = "Generated plan"
        self.usage = _FakeUsage()


def test_ai_plan_missing_key_creates_pending_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()
    (tmp_path / "artifacts" / "audit").mkdir(parents=True)

    atomic_write_yaml(
        tmp_path / "state" / "AI_BUDGET.yaml",
        {
            "monthly_budget_usd": 2000.0,
            "alert_threshold": 0.8,
            "hard_limit_threshold": 1.0,
            "current_month": "2026-02",
            "spend_usd": 0.0,
            "entries": [],
        },
    )

    result = run_ai_plan(prompt="hello", output_path="state/PLAN.md")
    assert not result.ok
    assert result.route_key == "pro"
    assert result.requested_model == "gpt-5.2-pro"
    assert "OPENAI_API_KEY" in result.text
    assert (tmp_path / "state" / "PLAN.md").exists()

    budget = read_yaml(tmp_path / "state" / "AI_BUDGET.yaml")
    assert budget["entries"]
    assert budget["entries"][-1]["route_key"] == "pro"


def test_ai_plan_hard_limit_downgrades_model_to_gpt_5_mini(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()

    atomic_write_yaml(
        tmp_path / "state" / "AI_BUDGET.yaml",
        {
            "monthly_budget_usd": 2000.0,
            "alert_threshold": 0.8,
            "hard_limit_threshold": 1.0,
            "current_month": "2026-02",
            "spend_usd": 2000.0,
            "entries": [],
        },
    )

    monkeypatch.setattr("workflow.ai._api_key", lambda: "fake-key")
    monkeypatch.setattr("workflow.ai._invoke_responses_api", lambda api_key, model, prompt, effort: _FakeResponse())

    result = run_ai_plan(prompt="build plan", output_path="state/PLAN.md")
    assert result.ok
    assert result.route_key == "pro"
    assert result.requested_model == "gpt-5-mini"
    assert result.model == "gpt-5-mini"
    assert "hard_limit_reached_downgraded" in result.selection_note

    budget = read_yaml(tmp_path / "state" / "AI_BUDGET.yaml")
    assert budget["entries"]
    entry = budget["entries"][-1]
    assert entry["requested_model"] == "gpt-5-mini"
    assert entry["route_key"] == "pro"
    assert entry["fallback_hops"] == 0
