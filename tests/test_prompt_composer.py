from __future__ import annotations

from workflow.prompt_composer import compose_prompt


def test_compose_prompt_loads_global_modules() -> None:
    result = compose_prompt(
        command="plan",
        task_type="plan",
        intent=None,
        context_blocks=[{"name": "TASKS", "text": "{}", "required": True, "order": 1000}],
        ai_config={},
        response_profile="qa_zh",
        project_slug=None,
        viz="off",
        prompt_budget="high",
    )
    assert "core.governance" in result.selected_modules
    assert "output.qa_zh" in result.selected_modules
    assert result.project_override_applied is False


def test_compose_prompt_project_override_applies() -> None:
    result = compose_prompt(
        command="task",
        task_type="experiment",
        intent="run",
        context_blocks=[{"name": "TASK", "text": '{"id":"T-0011"}', "required": True, "order": 1000}],
        ai_config={},
        response_profile="paper_en",
        project_slug="rl-gridworld-qlearning",
        viz="on",
        prompt_budget="high",
    )
    assert result.project_override_applied is True
    assert "project.rl.scope" in result.selected_modules
    assert "math.strict_derivation" in result.selected_modules


def test_compose_prompt_profile_switches_output_module() -> None:
    result = compose_prompt(
        command="task",
        task_type="derivation",
        intent="design",
        context_blocks=[{"name": "TASK", "text": '{"id":"T-derivation"}', "required": True, "order": 1000}],
        ai_config={},
        response_profile="paper_en",
        project_slug=None,
        viz="off",
        prompt_budget="high",
    )
    assert "output.paper_en" in result.selected_modules
    assert "output.qa_zh" not in result.selected_modules


def test_compose_prompt_budget_trimming_keeps_required_modules() -> None:
    large_context = "x" * 120_000
    result = compose_prompt(
        command="plan",
        task_type="plan",
        intent=None,
        context_blocks=[{"name": "TASKS", "text": large_context, "required": True, "order": 1000}],
        ai_config={},
        response_profile="qa_zh",
        project_slug=None,
        viz="off",
        prompt_budget="low",
    )
    assert "core.governance" in result.selected_modules
    assert result.estimated_tokens <= 12_000
    assert result.dropped_modules


def test_compose_prompt_high_budget_enforces_hard_limit() -> None:
    large_context = "y" * 300_000
    result = compose_prompt(
        command="audit",
        task_type="audit",
        intent=None,
        context_blocks=[{"name": "TASKS", "text": large_context, "required": True, "order": 1000}],
        ai_config={},
        response_profile="audit_cn",
        project_slug=None,
        viz="on",
        prompt_budget="high",
    )
    assert result.budget_profile == "high"
    assert result.estimated_tokens <= 24_000
