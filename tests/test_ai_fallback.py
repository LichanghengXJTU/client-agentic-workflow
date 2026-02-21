from __future__ import annotations

from pathlib import Path

import pytest

from workflow.ai import run_ai_plan
from workflow.state_ops import atomic_write_yaml, read_yaml


class _FakeUsage:
    def __init__(self) -> None:
        self.input_tokens = 10
        self.output_tokens = 10
        self.cached_tokens = 0


class _FakeResponse:
    def __init__(self) -> None:
        self.output_text = "ok"
        self.usage = _FakeUsage()


class _FakeApiError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def _setup_budget(tmp_path: Path) -> None:
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


def test_fallback_hits_next_model_on_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()
    _setup_budget(tmp_path)

    monkeypatch.setattr("workflow.ai._api_key", lambda: "fake-key")

    def _invoke(api_key: str, model: str, prompt: str, effort: str):
        if model == "gpt-5.2-pro":
            raise _FakeApiError(404, "model not found")
        assert model == "gpt-5-pro"
        return _FakeResponse()

    monkeypatch.setattr("workflow.ai._invoke_responses_api", _invoke)

    result = run_ai_plan(prompt="fallback", output_path="state/PLAN.md")
    assert result.ok
    assert result.requested_model == "gpt-5.2-pro"
    assert result.model == "gpt-5-pro"
    assert "fallback_applied" in result.selection_note

    budget = read_yaml(tmp_path / "state" / "AI_BUDGET.yaml")
    assert budget["entries"][-1]["fallback_hops"] == 1


def test_fallback_hits_next_model_on_403(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()
    _setup_budget(tmp_path)

    monkeypatch.setattr("workflow.ai._api_key", lambda: "fake-key")

    def _invoke(api_key: str, model: str, prompt: str, effort: str):
        if model == "gpt-5.2-pro":
            raise _FakeApiError(403, "permission denied")
        assert model == "gpt-5-pro"
        return _FakeResponse()

    monkeypatch.setattr("workflow.ai._invoke_responses_api", _invoke)

    result = run_ai_plan(prompt="fallback", output_path="state/PLAN.md")
    assert result.ok
    assert result.model == "gpt-5-pro"
    assert "fallback_applied" in result.selection_note


def test_retry_429_then_success_without_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()
    _setup_budget(tmp_path)

    monkeypatch.setattr("workflow.ai._api_key", lambda: "fake-key")

    calls = {"n": 0}

    def _invoke(api_key: str, model: str, prompt: str, effort: str):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _FakeApiError(429, "rate limit")
        return _FakeResponse()

    monkeypatch.setattr("workflow.ai._invoke_responses_api", _invoke)

    result = run_ai_plan(prompt="retry", output_path="state/PLAN.md")
    assert result.ok
    assert result.model == "gpt-5.2-pro"
    assert "fallback_applied" not in result.selection_note
    assert calls["n"] == 3


def test_retry_500_then_success_without_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()
    _setup_budget(tmp_path)

    monkeypatch.setattr("workflow.ai._api_key", lambda: "fake-key")

    calls = {"n": 0}

    def _invoke(api_key: str, model: str, prompt: str, effort: str):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _FakeApiError(500, "server error")
        return _FakeResponse()

    monkeypatch.setattr("workflow.ai._invoke_responses_api", _invoke)

    result = run_ai_plan(prompt="retry", output_path="state/PLAN.md")
    assert result.ok
    assert result.model == "gpt-5.2-pro"
    assert "fallback_applied" not in result.selection_note
    assert calls["n"] == 3


def test_retryable_error_exhausted_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()
    _setup_budget(tmp_path)

    monkeypatch.setattr("workflow.ai._api_key", lambda: "fake-key")
    monkeypatch.setattr("workflow.ai._invoke_responses_api", lambda api_key, model, prompt, effort: (_ for _ in ()).throw(_FakeApiError(429, "rate limit")))

    with pytest.raises(_FakeApiError):
        run_ai_plan(prompt="retry", output_path="state/PLAN.md")
