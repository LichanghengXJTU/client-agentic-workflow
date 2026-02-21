from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .state_ops import AI_BUDGET_PATH, AI_CONFIG_PATH, atomic_write_yaml, read_yaml, task_by_id


MAX_RETRY_PER_MODEL = 2


@dataclass
class AICallResult:
    ok: bool
    model: str
    requested_model: str
    route_key: str
    selection_note: str
    output_path: str
    text: str
    spend_usd: float
    budget_ratio: float
    message: str


def _default_prompting_config() -> dict[str, Any]:
    return {
        "default_response_profile": {
            "plan": "qa_zh",
            "audit": "audit_cn",
            "task": "qa_zh",
        },
        "default_budget_profile": "high",
        "budget_profiles": {
            "high": {"target_tokens": 12000, "soft_limit_tokens": 18000, "hard_limit_tokens": 24000},
            "medium": {"target_tokens": 8000, "soft_limit_tokens": 12000, "hard_limit_tokens": 16000},
            "low": {"target_tokens": 5000, "soft_limit_tokens": 8000, "hard_limit_tokens": 12000},
        },
        "viz_policy": {
            "auto_on_commands": ["audit"],
            "auto_on_task_types": ["experiment"],
        },
        "math_rigor_default": "strict",
        "step_visibility": "layered_appendix",
        "artifact_contract": "full_evidence_pack",
    }


def default_ai_config_v2() -> dict[str, Any]:
    return {
        "version": 2,
        "models": {
            "pro": "gpt-5.2-pro",
            "codex": "gpt-5.2-codex",
        },
        "routing": {
            "plan": "pro",
            "audit": "pro",
            "task_type": {
                "code": "codex",
                "derivation": "pro",
                "writing": "pro",
                "literature": "pro",
                "meta": "pro",
                "experiment": {
                    "design": "pro",
                    "run": "codex",
                },
            },
        },
        "fallback_chains": {
            "pro": ["gpt-5.2-pro", "gpt-5-pro", "gpt-5.2", "gpt-5.1", "gpt-5", "gpt-5-mini"],
            "codex": ["gpt-5.2-codex", "gpt-5.1-codex-max", "gpt-5.1-codex", "gpt-5-codex", "gpt-5.2", "gpt-5-mini"],
        },
        "effort_by_route": {
            "pro": "xhigh",
            "codex": "xhigh",
            "hard_limit": "high",
        },
        "hard_limit_model": "gpt-5-mini",
        "price_per_1m_input_usd": 10.0,
        "price_per_1m_output_usd": 30.0,
        "price_per_1m_cached_input_usd": 2.5,
        "prompting": _default_prompting_config(),
        "notes": "Do not store API key here. Put key in state/AI_SECRETS.local.yaml or OPENAI_API_KEY env.",
    }


def _load_local_secrets() -> dict[str, Any]:
    path = Path("state/AI_SECRETS.local.yaml")
    if not path.exists():
        return {}
    return read_yaml(path)


def _normalize_ai_config(cfg: dict[str, Any]) -> dict[str, Any]:
    base = default_ai_config_v2()
    if not cfg:
        return base

    # v2 shape
    if isinstance(cfg.get("routing"), dict):
        merged = default_ai_config_v2()
        merged.update(
            {
                k: v
                for k, v in cfg.items()
                if k not in {"models", "routing", "fallback_chains", "effort_by_route", "prompting"}
            }
        )

        incoming_models = cfg.get("models")
        if isinstance(incoming_models, dict):
            merged["models"].update(incoming_models)

        incoming_fallback = cfg.get("fallback_chains")
        if isinstance(incoming_fallback, dict):
            merged["fallback_chains"].update(incoming_fallback)

        incoming_effort = cfg.get("effort_by_route")
        if isinstance(incoming_effort, dict):
            merged["effort_by_route"].update(incoming_effort)

        incoming_prompting = cfg.get("prompting")
        if isinstance(incoming_prompting, dict):
            merged_prompting = _default_prompting_config()

            incoming_defaults = incoming_prompting.get("default_response_profile")
            if isinstance(incoming_defaults, str):
                merged_prompting["default_response_profile"] = {
                    "plan": incoming_defaults,
                    "audit": incoming_defaults,
                    "task": incoming_defaults,
                }
            elif isinstance(incoming_defaults, dict):
                merged_prompting["default_response_profile"].update(
                    {
                        key: str(value)
                        for key, value in incoming_defaults.items()
                        if key in {"plan", "audit", "task"} and isinstance(value, str)
                    }
                )

            if isinstance(incoming_prompting.get("default_budget_profile"), str):
                merged_prompting["default_budget_profile"] = str(incoming_prompting["default_budget_profile"])

            incoming_budget_profiles = incoming_prompting.get("budget_profiles")
            if isinstance(incoming_budget_profiles, dict):
                for profile_name, profile_cfg in incoming_budget_profiles.items():
                    if not isinstance(profile_cfg, dict):
                        continue
                    current = dict(merged_prompting["budget_profiles"].get(profile_name, {}))
                    current.update(
                        {
                            key: int(value)
                            for key, value in profile_cfg.items()
                            if key in {"target_tokens", "soft_limit_tokens", "hard_limit_tokens"} and isinstance(value, int)
                        }
                    )
                    if current:
                        merged_prompting["budget_profiles"][profile_name] = current

            incoming_viz = incoming_prompting.get("viz_policy")
            if isinstance(incoming_viz, dict):
                merged_prompting["viz_policy"].update(incoming_viz)

            for key in ["math_rigor_default", "step_visibility", "artifact_contract"]:
                if isinstance(incoming_prompting.get(key), str):
                    merged_prompting[key] = incoming_prompting[key]

            merged["prompting"] = merged_prompting

        incoming_routing = cfg.get("routing")
        if isinstance(incoming_routing, dict):
            for key, value in incoming_routing.items():
                if key == "task_type" and isinstance(value, dict):
                    merged["routing"]["task_type"].update(value)
                else:
                    merged["routing"][key] = value
        return merged

    # legacy shape fallback
    legacy_default = str(cfg.get("default_model", "gpt-5"))
    legacy_low = str(cfg.get("low_cost_model", "gpt-4.1-mini"))
    legacy_effort = str(cfg.get("reasoning_effort", "high"))

    base["models"]["pro"] = legacy_default
    base["models"]["codex"] = legacy_default
    base["hard_limit_model"] = legacy_low
    base["effort_by_route"]["pro"] = legacy_effort
    base["effort_by_route"]["codex"] = legacy_effort
    base["effort_by_route"]["hard_limit"] = "high"

    for rate_key in [
        "price_per_1m_input_usd",
        "price_per_1m_output_usd",
        "price_per_1m_cached_input_usd",
    ]:
        if rate_key in cfg:
            base[rate_key] = cfg[rate_key]

    if "notes" in cfg:
        base["notes"] = cfg["notes"]
    return base


def _load_ai_config() -> dict[str, Any]:
    return _normalize_ai_config(read_yaml(AI_CONFIG_PATH))


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


def _budget_ratio(budget: dict[str, Any]) -> float:
    monthly_budget = float(budget.get("monthly_budget_usd", 2000.0))
    spend = float(budget.get("spend_usd", 0.0))
    return (spend / monthly_budget) if monthly_budget > 0 else 0.0


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


def resolve_route(task_type: str, intent: str | None, task_id: str | None, config: dict[str, Any]) -> tuple[str, str]:
    routing = config.get("routing", {})

    if task_type in {"plan", "audit"}:
        return str(routing.get(task_type, "pro")), "normal"

    task_routes = routing.get("task_type", {})
    route_cfg = task_routes.get(task_type)
    if isinstance(route_cfg, str):
        return route_cfg, "normal"

    if isinstance(route_cfg, dict):
        resolved_intent = (intent or "design").strip().lower() or "design"
        if resolved_intent not in {"design", "run"}:
            resolved_intent = "design"
        note = "experiment_intent_defaulted_design" if task_type == "experiment" and not intent else "normal"
        return str(route_cfg.get(resolved_intent, route_cfg.get("design", "pro"))), note

    return "pro", "route_fallback_default"


def _select_target(
    *,
    task_type: str,
    intent: str | None,
    task_id: str | None,
    config: dict[str, Any],
    budget: dict[str, Any],
) -> tuple[str, str, str, str]:
    route_key, route_note = resolve_route(task_type=task_type, intent=intent, task_id=task_id, config=config)

    models = config.get("models", {})
    requested_model = str(models.get(route_key, "gpt-5.2-pro"))
    effort = str(config.get("effort_by_route", {}).get(route_key, "xhigh"))

    ratio = _budget_ratio(budget)
    alert_threshold = float(budget.get("alert_threshold", 0.8))
    hard_threshold = float(budget.get("hard_limit_threshold", 1.0))

    selection_note = "normal"
    if ratio >= alert_threshold:
        selection_note = "alert_threshold_reached"

    if ratio >= hard_threshold:
        requested_model = str(config.get("hard_limit_model", "gpt-5-mini"))
        effort = str(config.get("effort_by_route", {}).get("hard_limit", "high"))
        selection_note = "hard_limit_reached_downgraded"

    if route_note != "normal":
        selection_note = f"{selection_note}|{route_note}"

    return route_key, requested_model, effort, selection_note


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_missing_key_text(
    *,
    task_type: str,
    route_key: str,
    requested_model: str,
    selection_note: str,
    task_id: str | None,
) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    task_line = f"- Task ID: {task_id}\n" if task_id else ""
    return (
        f"# AI {task_type.capitalize()} (Pending)\n\n"
        f"- Time: {now}\n"
        f"- Route: {route_key}\n"
        f"- Requested model: {requested_model}\n"
        f"- Selection note: {selection_note}\n"
        f"{task_line}"
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


def _error_status_code(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status

    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status
    return None


def _is_retryable_error(exc: Exception) -> bool:
    status = _error_status_code(exc)
    if status in {429, 500, 502, 503, 504}:
        return True
    name = type(exc).__name__.lower()
    return "timeout" in name or "connection" in name


def _is_model_unavailable_error(exc: Exception) -> bool:
    status = _error_status_code(exc)
    message = str(exc).lower()

    if status in {403, 404}:
        return True

    if status == 400:
        keys = [
            "model",
            "does not exist",
            "not found",
            "not available",
            "not supported",
            "permission",
            "access",
            "unsupported",
        ]
        return any(token in message for token in keys)

    return False


def _build_model_chain(
    *,
    route_key: str,
    requested_model: str,
    config: dict[str, Any],
    hard_limited: bool,
) -> list[str]:
    if hard_limited:
        return [requested_model]

    chain_raw = config.get("fallback_chains", {}).get(route_key, [])
    chain: list[str] = [requested_model]
    if isinstance(chain_raw, list):
        chain.extend(str(item) for item in chain_raw if isinstance(item, str))

    dedup: list[str] = []
    seen: set[str] = set()
    for model in chain:
        if not model or model in seen:
            continue
        seen.add(model)
        dedup.append(model)
    return dedup or [requested_model]


def invoke_with_fallback(
    *,
    api_key: str,
    prompt: str,
    effort: str,
    model_chain: list[str],
) -> tuple[Any, str, int, str]:
    visited: list[str] = []

    for model in model_chain:
        visited.append(model)
        retry_count = 0
        while True:
            try:
                response = _invoke_responses_api(api_key=api_key, model=model, prompt=prompt, effort=effort)
                hops = max(0, len(visited) - 1)
                note = "normal" if hops == 0 else f"fallback_applied:{'->'.join(visited)}"
                return response, model, hops, note
            except Exception as exc:  # pragma: no cover - exercised via tests with monkeypatch
                if _is_retryable_error(exc) and retry_count < MAX_RETRY_PER_MODEL:
                    retry_count += 1
                    continue
                if _is_model_unavailable_error(exc):
                    break
                raise

    chain_text = " -> ".join(model_chain)
    raise RuntimeError(f"All models failed in fallback chain: {chain_text}")


def _record_budget_entry(
    task_type: str,
    model: str,
    in_tokens: int,
    out_tokens: int,
    cached_tokens: int,
    cost_usd: float,
    note: str,
    *,
    route_key: str,
    requested_model: str,
    fallback_hops: int,
    selection_note: str,
) -> tuple[float, float]:
    budget = _load_budget()
    budget["spend_usd"] = round(float(budget.get("spend_usd", 0.0)) + cost_usd, 6)
    budget.setdefault("entries", []).append(
        {
            "time": datetime.now().isoformat(timespec="seconds"),
            "task_type": task_type,
            "route_key": route_key,
            "requested_model": requested_model,
            "model": model,
            "fallback_hops": fallback_hops,
            "selection_note": selection_note,
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


def _render_ai_report(
    *,
    task_type: str,
    route_key: str,
    model: str,
    requested_model: str,
    selection_note: str,
    prompt: str,
    text: str,
    task_id: str | None = None,
    intent: str | None = None,
) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    title_map = {
        "plan": "# PLAN (AI Generated)",
        "audit": "# AI Audit Report",
    }
    title = title_map.get(task_type, "# AI Task Report")
    task_block = ""
    if task_id:
        task_block = f"- Task ID: {task_id}\n- Intent: {intent or 'design'}\n"

    return (
        f"{title}\n\n"
        f"- Time: {now}\n"
        f"- Route: {route_key}\n"
        f"- Requested model: {requested_model}\n"
        f"- Model: {model}\n"
        f"- Selection note: {selection_note}\n"
        f"{task_block}"
        "- OPENAI_API_KEY is set: yes\n\n"
        "## Input Summary\n"
        f"{prompt[:1000]}\n\n"
        "## Output\n"
        f"{text}\n"
    )


def run_ai_plan(prompt: str, output_path: str = "state/PLAN.md") -> AICallResult:
    return _run_ai_request(task_type="plan", prompt=prompt, output_path=output_path)


def run_ai_audit(prompt: str, output_path: str | None = None) -> AICallResult:
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        output_path = f"artifacts/audit/ai-{ts}.md"
    return _run_ai_request(task_type="audit", prompt=prompt, output_path=output_path)


def run_ai_task(
    *,
    task_id: str,
    intent: str | None = None,
    prompt: str,
    output_path: str | None = None,
) -> AICallResult:
    task = task_by_id(task_id)
    task_type = str(task.get("type", "meta"))
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = f"artifacts/tasks/{task_id}/ai/ai-{ts}.md"

    resolved_intent = intent
    if task_type == "experiment" and not resolved_intent:
        resolved_intent = "design"

    final_prompt = prompt or (
        "请基于以下任务给出可执行且可验证的实施内容，输出应包含检查点与风险控制。\n\n"
        f"TASK:\n{json.dumps(task, ensure_ascii=False, indent=2)}\n\n"
        f"INTENT: {resolved_intent or 'design'}\n"
    )

    return _run_ai_request(
        task_type=task_type,
        prompt=final_prompt,
        output_path=output_path,
        task_id=task_id,
        intent=resolved_intent,
        budget_task_type=f"task:{task_type}",
    )


def _run_ai_request(
    *,
    task_type: str,
    prompt: str,
    output_path: str,
    task_id: str | None = None,
    intent: str | None = None,
    budget_task_type: str | None = None,
) -> AICallResult:
    config = _load_ai_config()
    budget = _load_budget()

    route_key, requested_model, effort, selection_note = _select_target(
        task_type=task_type,
        intent=intent,
        task_id=task_id,
        config=config,
        budget=budget,
    )

    hard_limited = selection_note.startswith("hard_limit_reached_downgraded")
    model_chain = _build_model_chain(
        route_key=route_key,
        requested_model=requested_model,
        config=config,
        hard_limited=hard_limited,
    )

    key = _api_key()
    out_path = Path(output_path)
    task_type_for_budget = budget_task_type or task_type

    if not key:
        text = _build_missing_key_text(
            task_type=task_type,
            route_key=route_key,
            requested_model=requested_model,
            selection_note=selection_note,
            task_id=task_id,
        )
        _write_text(out_path, text)
        spend, ratio = _record_budget_entry(
            task_type_for_budget,
            requested_model,
            0,
            0,
            0,
            0.0,
            "missing_api_key",
            route_key=route_key,
            requested_model=requested_model,
            fallback_hops=0,
            selection_note=selection_note,
        )
        return AICallResult(
            ok=False,
            model=requested_model,
            requested_model=requested_model,
            route_key=route_key,
            selection_note=selection_note,
            output_path=str(out_path),
            text=text,
            spend_usd=spend,
            budget_ratio=ratio,
            message="OPENAI_API_KEY missing; generated pending report.",
        )

    response, final_model, fallback_hops, fallback_note = invoke_with_fallback(
        api_key=key,
        prompt=prompt,
        effort=effort,
        model_chain=model_chain,
    )
    text = _extract_output_text(response)

    final_selection_note = selection_note if fallback_note == "normal" else f"{selection_note}|{fallback_note}"
    rendered = _render_ai_report(
        task_type=task_type,
        route_key=route_key,
        model=final_model,
        requested_model=requested_model,
        selection_note=final_selection_note,
        prompt=prompt,
        text=text,
        task_id=task_id,
        intent=intent,
    )
    _write_text(out_path, rendered)

    in_tokens, out_tokens, cached_tokens = _usage_tokens(response)
    cost_usd = _estimate_cost_usd(config, in_tokens, out_tokens, cached_tokens)
    spend, ratio = _record_budget_entry(
        task_type_for_budget,
        final_model,
        in_tokens,
        out_tokens,
        cached_tokens,
        cost_usd,
        final_selection_note,
        route_key=route_key,
        requested_model=requested_model,
        fallback_hops=fallback_hops,
        selection_note=final_selection_note,
    )

    return AICallResult(
        ok=True,
        model=final_model,
        requested_model=requested_model,
        route_key=route_key,
        selection_note=final_selection_note,
        output_path=str(out_path),
        text=rendered,
        spend_usd=spend,
        budget_ratio=ratio,
        message="ok",
    )
