from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .state_ops import AI_BUDGET_PATH, AI_CONFIG_PATH, atomic_write_yaml, read_yaml


@dataclass
class AICallResult:
    ok: bool
    model: str
    output_path: str
    text: str
    spend_usd: float
    budget_ratio: float
    message: str


def _load_local_secrets() -> dict[str, Any]:
    path = Path("state/AI_SECRETS.local.yaml")
    if not path.exists():
        return {}
    return read_yaml(path)


def _load_ai_config() -> dict[str, Any]:
    cfg = read_yaml(AI_CONFIG_PATH)
    if not cfg:
        cfg = {
            "default_model": "gpt-5",
            "low_cost_model": "gpt-4.1-mini",
            "reasoning_effort": "high",
            "price_per_1m_input_usd": 10.0,
            "price_per_1m_output_usd": 30.0,
            "price_per_1m_cached_input_usd": 2.5,
        }
    return cfg


def _load_budget() -> dict[str, Any]:
    current_month = datetime.now().strftime("%Y-%m")
    budget = read_yaml(AI_BUDGET_PATH)
    if not budget:
        budget = {
            "monthly_budget_usd": 2000.0,
            "alert_threshold": 0.8,
            "hard_limit_threshold": 1.0,
            "current_month": current_month,
            "spend_usd": 0.0,
            "entries": [],
        }
    elif budget.get("current_month") != current_month:
        budget["current_month"] = current_month
        budget["spend_usd"] = 0.0
        budget["entries"] = []
    return budget


def _save_budget(data: dict[str, Any]) -> None:
    atomic_write_yaml(AI_BUDGET_PATH, data)


def _api_key() -> str | None:
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key
    local = _load_local_secrets()
    key = local.get("openai_api_key")
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None


def _extract_output_text(response: Any) -> str:
    txt = getattr(response, "output_text", None)
    if isinstance(txt, str) and txt.strip():
        return txt

    output = getattr(response, "output", [])
    chunks: list[str] = []
    for item in output:
        content = getattr(item, "content", [])
        for block in content:
            if getattr(block, "type", "") in {"output_text", "text"}:
                text = getattr(block, "text", "")
                if text:
                    chunks.append(text)
    return "\n".join(chunks).strip()


def _usage_tokens(response: Any) -> tuple[int, int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0, 0

    in_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    out_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cached_tokens = int(getattr(usage, "cached_tokens", 0) or 0)
    return in_tokens, out_tokens, cached_tokens


def _estimate_cost_usd(config: dict[str, Any], in_tokens: int, out_tokens: int, cached_tokens: int) -> float:
    in_rate = float(config.get("price_per_1m_input_usd", 10.0))
    out_rate = float(config.get("price_per_1m_output_usd", 30.0))
    cache_rate = float(config.get("price_per_1m_cached_input_usd", 2.5))
    cost = (in_tokens / 1_000_000) * in_rate + (out_tokens / 1_000_000) * out_rate + (cached_tokens / 1_000_000) * cache_rate
    return round(cost, 6)


def _select_model(task_type: str, config: dict[str, Any], budget: dict[str, Any]) -> tuple[str, str]:
    default_model = str(config.get("default_model", "gpt-5"))
    low_model = str(config.get("low_cost_model", "gpt-4.1-mini"))

    monthly_budget = float(budget.get("monthly_budget_usd", 2000.0))
    spend = float(budget.get("spend_usd", 0.0))
    ratio = (spend / monthly_budget) if monthly_budget > 0 else 0.0

    preferred = default_model if task_type in {"plan", "audit"} else low_model

    if ratio >= float(budget.get("hard_limit_threshold", 1.0)) and preferred == default_model:
        return low_model, "hard_limit_reached_downgraded"
    if ratio >= float(budget.get("alert_threshold", 0.8)) and preferred == default_model:
        return preferred, "alert_threshold_reached"
    return preferred, "normal"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_missing_key_text(task_type: str) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    return (
        f"# AI {task_type.capitalize()} (Pending)\n\n"
        f"- Time: {now}\n"
        "- OPENAI_API_KEY is set: no\n"
        "- Action: skipped remote AI call, please provide API key in env or state/AI_SECRETS.local.yaml\n"
    )


def _invoke_responses_api(api_key: str, model: str, prompt: str, effort: str) -> Any:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    return client.responses.create(
        model=model,
        reasoning={"effort": effort},
        input=prompt,
    )


def _record_budget_entry(
    task_type: str,
    model: str,
    in_tokens: int,
    out_tokens: int,
    cached_tokens: int,
    cost_usd: float,
    note: str,
) -> tuple[float, float]:
    budget = _load_budget()
    budget["spend_usd"] = round(float(budget.get("spend_usd", 0.0)) + cost_usd, 6)
    budget.setdefault("entries", []).append(
        {
            "time": datetime.now().isoformat(timespec="seconds"),
            "task_type": task_type,
            "model": model,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "cached_tokens": cached_tokens,
            "cost_usd": cost_usd,
            "note": note,
        }
    )
    _save_budget(budget)

    monthly_budget = float(budget.get("monthly_budget_usd", 2000.0))
    ratio = (float(budget.get("spend_usd", 0.0)) / monthly_budget) if monthly_budget > 0 else 0.0
    return float(budget.get("spend_usd", 0.0)), ratio


def run_ai_plan(prompt: str, output_path: str = "state/PLAN.md") -> AICallResult:
    return _run_ai_task(task_type="plan", prompt=prompt, output_path=output_path)


def run_ai_audit(prompt: str, output_path: str | None = None) -> AICallResult:
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        output_path = f"artifacts/audit/ai-{ts}.md"
    return _run_ai_task(task_type="audit", prompt=prompt, output_path=output_path)


def _run_ai_task(task_type: str, prompt: str, output_path: str) -> AICallResult:
    config = _load_ai_config()
    budget = _load_budget()
    model, selection_note = _select_model(task_type, config, budget)

    key = _api_key()
    out_path = Path(output_path)

    if not key:
        text = _build_missing_key_text(task_type)
        _write_text(out_path, text)
        spend, ratio = _record_budget_entry(task_type, model, 0, 0, 0, 0.0, "missing_api_key")
        return AICallResult(
            ok=False,
            model=model,
            output_path=str(out_path),
            text=text,
            spend_usd=spend,
            budget_ratio=ratio,
            message="OPENAI_API_KEY missing; generated pending report.",
        )

    response = _invoke_responses_api(
        api_key=key,
        model=model,
        prompt=prompt,
        effort=str(config.get("reasoning_effort", "high")),
    )
    text = _extract_output_text(response)

    if task_type == "plan":
        rendered = (
            "# PLAN (AI Generated)\n\n"
            f"- Time: {datetime.now().isoformat(timespec='seconds')}\n"
            f"- Model: {model}\n"
            f"- Selection note: {selection_note}\n"
            f"- OPENAI_API_KEY is set: yes\n\n"
            "## Input Summary\n"
            f"{prompt[:1000]}\n\n"
            "## Output\n"
            f"{text}\n"
        )
    else:
        rendered = (
            "# AI Audit Report\n\n"
            f"- Time: {datetime.now().isoformat(timespec='seconds')}\n"
            f"- Model: {model}\n"
            f"- Selection note: {selection_note}\n"
            f"- OPENAI_API_KEY is set: yes\n\n"
            "## Input Summary\n"
            f"{prompt[:1000]}\n\n"
            "## Output\n"
            f"{text}\n"
        )

    _write_text(out_path, rendered)

    in_tokens, out_tokens, cached_tokens = _usage_tokens(response)
    cost_usd = _estimate_cost_usd(config, in_tokens, out_tokens, cached_tokens)
    spend, ratio = _record_budget_entry(task_type, model, in_tokens, out_tokens, cached_tokens, cost_usd, selection_note)

    return AICallResult(
        ok=True,
        model=model,
        output_path=str(out_path),
        text=rendered,
        spend_usd=spend,
        budget_ratio=ratio,
        message="ok",
    )
