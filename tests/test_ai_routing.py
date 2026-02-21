from __future__ import annotations

from pathlib import Path

from workflow.ai import default_ai_config_v2, resolve_route, run_ai_plan, run_ai_task
from workflow.state_ops import atomic_write_yaml


class _FakeUsage:
    def __init__(self) -> None:
        self.input_tokens = 50
        self.output_tokens = 20
        self.cached_tokens = 0


class _FakeResponse:
    def __init__(self) -> None:
        self.output_text = "ok"
        self.usage = _FakeUsage()


def test_resolve_route_matrix() -> None:
    cfg = default_ai_config_v2()

    assert resolve_route("plan", None, None, cfg)[0] == "pro"
    assert resolve_route("audit", None, None, cfg)[0] == "pro"
    assert resolve_route("code", None, "T-1", cfg)[0] == "codex"
    assert resolve_route("derivation", None, "T-1", cfg)[0] == "pro"
    assert resolve_route("writing", None, "T-1", cfg)[0] == "pro"
    assert resolve_route("literature", None, "T-1", cfg)[0] == "pro"
    assert resolve_route("meta", None, "T-1", cfg)[0] == "pro"
    assert resolve_route("experiment", "design", "T-1", cfg)[0] == "pro"
    assert resolve_route("experiment", "run", "T-1", cfg)[0] == "codex"


def test_legacy_config_is_compatible(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()

    atomic_write_yaml(
        tmp_path / "state" / "AI_CONFIG.yaml",
        {
            "default_model": "gpt-5",
            "low_cost_model": "gpt-4.1-mini",
            "reasoning_effort": "high",
            "price_per_1m_input_usd": 10.0,
            "price_per_1m_output_usd": 30.0,
            "price_per_1m_cached_input_usd": 2.5,
        },
    )
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

    monkeypatch.setattr("workflow.ai._api_key", lambda: "fake-key")
    monkeypatch.setattr("workflow.ai._invoke_responses_api", lambda api_key, model, prompt, effort: _FakeResponse())

    result = run_ai_plan(prompt="legacy", output_path="state/PLAN.md")
    assert result.ok
    assert result.requested_model == "gpt-5"
    assert result.route_key == "pro"


def test_run_ai_task_routes_by_task_type_and_intent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()

    atomic_write_yaml(
        tmp_path / "state" / "TASKS.yaml",
        {
            "tasks": [
                {"id": "T-0001", "type": "code"},
                {"id": "T-0002", "type": "derivation"},
                {"id": "T-0003", "type": "writing"},
                {"id": "T-0004", "type": "literature"},
                {"id": "T-0005", "type": "meta"},
                {"id": "T-0006", "type": "experiment"},
            ]
        },
    )
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

    monkeypatch.setattr("workflow.ai._api_key", lambda: "fake-key")
    monkeypatch.setattr("workflow.ai._invoke_responses_api", lambda api_key, model, prompt, effort: _FakeResponse())

    result_code = run_ai_task(task_id="T-0001", prompt="code", intent=None)
    result_derivation = run_ai_task(task_id="T-0002", prompt="derivation", intent=None)
    result_writing = run_ai_task(task_id="T-0003", prompt="writing", intent=None)
    result_literature = run_ai_task(task_id="T-0004", prompt="literature", intent=None)
    result_meta = run_ai_task(task_id="T-0005", prompt="meta", intent=None)
    result_exp_design = run_ai_task(task_id="T-0006", prompt="exp-design", intent=None)
    result_exp_run = run_ai_task(task_id="T-0006", prompt="exp-run", intent="run")

    assert result_code.route_key == "codex"
    assert result_derivation.route_key == "pro"
    assert result_writing.route_key == "pro"
    assert result_literature.route_key == "pro"
    assert result_meta.route_key == "pro"
    assert result_exp_design.route_key == "pro"
    assert result_exp_run.route_key == "codex"

    assert result_code.requested_model == "gpt-5.2-codex"
    assert result_derivation.requested_model == "gpt-5.2-pro"
    assert result_writing.requested_model == "gpt-5.2-pro"
    assert result_literature.requested_model == "gpt-5.2-pro"
    assert result_meta.requested_model == "gpt-5.2-pro"
    assert result_exp_design.requested_model == "gpt-5.2-pro"
    assert result_exp_run.requested_model == "gpt-5.2-codex"
