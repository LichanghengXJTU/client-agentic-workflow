from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .state_ops import read_yaml


VALID_RESPONSE_PROFILES = {"qa_zh", "paper_en", "audit_cn"}
VALID_BUDGET_PROFILES = {"high", "medium", "low"}
VALID_VIZ_MODES = {"auto", "on", "off"}


@dataclass
class ComposedPrompt:
    text: str
    selected_modules: list[str]
    dropped_modules: list[str]
    estimated_tokens: int
    budget_profile: str
    response_profile: str
    project_override_applied: bool


@dataclass
class _Segment:
    segment_id: str
    text: str
    required: bool
    priority: int
    order: int
    kind: str


def default_prompting_config() -> dict[str, Any]:
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


def normalize_prompting_config(ai_config: dict[str, Any]) -> dict[str, Any]:
    base = default_prompting_config()
    incoming = ai_config.get("prompting") if isinstance(ai_config, dict) else None
    if not isinstance(incoming, dict):
        return base

    merged = default_prompting_config()

    incoming_defaults = incoming.get("default_response_profile")
    if isinstance(incoming_defaults, str):
        merged["default_response_profile"] = {
            "plan": incoming_defaults,
            "audit": incoming_defaults,
            "task": incoming_defaults,
        }
    elif isinstance(incoming_defaults, dict):
        merged["default_response_profile"].update(
            {
                key: str(value)
                for key, value in incoming_defaults.items()
                if key in {"plan", "audit", "task"} and isinstance(value, str)
            }
        )

    if isinstance(incoming.get("default_budget_profile"), str):
        merged["default_budget_profile"] = str(incoming["default_budget_profile"])

    incoming_budget_profiles = incoming.get("budget_profiles")
    if isinstance(incoming_budget_profiles, dict):
        for profile_name, profile_cfg in incoming_budget_profiles.items():
            if not isinstance(profile_cfg, dict):
                continue
            current = dict(merged["budget_profiles"].get(profile_name, {}))
            current.update(
                {
                    key: int(value)
                    for key, value in profile_cfg.items()
                    if key in {"target_tokens", "soft_limit_tokens", "hard_limit_tokens"} and isinstance(value, int)
                }
            )
            if current:
                merged["budget_profiles"][profile_name] = current

    incoming_viz = incoming.get("viz_policy")
    if isinstance(incoming_viz, dict):
        merged["viz_policy"].update(incoming_viz)

    for key in ["math_rigor_default", "step_visibility", "artifact_contract"]:
        if isinstance(incoming.get(key), str):
            merged[key] = incoming[key]

    return merged


def _estimate_tokens(text: str) -> int:
    # Lightweight estimator to avoid depending on model tokenizer locally.
    return max(1, len(text) // 4)


def _normalize_profile(command: str, response_profile: str | None, prompting_cfg: dict[str, Any]) -> str:
    candidate = response_profile or str(prompting_cfg["default_response_profile"].get(command, "qa_zh"))
    if candidate not in VALID_RESPONSE_PROFILES:
        return "qa_zh"
    return candidate


def _normalize_budget(prompt_budget: str | None, prompting_cfg: dict[str, Any]) -> str:
    candidate = prompt_budget or str(prompting_cfg.get("default_budget_profile", "high"))
    if candidate not in VALID_BUDGET_PROFILES:
        return "high"
    return candidate


def _effective_viz(
    *,
    command: str,
    task_type: str | None,
    viz: str | None,
    prompting_cfg: dict[str, Any],
) -> bool:
    resolved = (viz or "auto").strip().lower()
    if resolved not in VALID_VIZ_MODES:
        resolved = "auto"
    if resolved == "on":
        return True
    if resolved == "off":
        return False

    viz_policy = prompting_cfg.get("viz_policy", {})
    auto_on_commands = {str(item) for item in viz_policy.get("auto_on_commands", []) if isinstance(item, str)}
    auto_on_task_types = {str(item) for item in viz_policy.get("auto_on_task_types", []) if isinstance(item, str)}
    return command in auto_on_commands or (task_type or "") in auto_on_task_types


def _load_registry(path: Path) -> list[dict[str, Any]]:
    data = read_yaml(path)
    modules = data.get("modules", [])
    return modules if isinstance(modules, list) else []


def _module_applies(
    module: dict[str, Any],
    *,
    command: str,
    task_type: str | None,
    response_profile: str,
    viz_enabled: bool,
) -> bool:
    commands = module.get("commands", ["plan", "audit", "task"])
    if not isinstance(commands, list):
        return False
    command_set = {str(item) for item in commands}
    if command not in command_set and "all" not in command_set:
        return False

    profiles = module.get("profiles")
    if isinstance(profiles, list):
        profile_set = {str(item) for item in profiles}
        if response_profile not in profile_set and "all" not in profile_set:
            return False

    task_types = module.get("task_types")
    if command == "task" and isinstance(task_types, list):
        task_set = {str(item) for item in task_types}
        if (task_type or "") not in task_set and "all" not in task_set:
            return False

    viz_setting = str(module.get("viz", "any"))
    if viz_setting == "on" and not viz_enabled:
        return False
    if viz_setting == "off" and viz_enabled:
        return False
    return True


def _load_module_text(root: Path, path_value: str) -> str:
    module_path = Path(path_value)
    if not module_path.is_absolute():
        module_path = root / module_path
    if not module_path.exists():
        return f"[missing module file: {path_value}]"
    return module_path.read_text(encoding="utf-8").strip()


def _render_segments(segments: list[_Segment]) -> str:
    lines: list[str] = []
    for seg in sorted(segments, key=lambda item: (item.order, -item.priority, item.segment_id)):
        if seg.kind == "module":
            lines.extend([f"## Module `{seg.segment_id}`", seg.text, ""])
        else:
            lines.extend([f"## Context `{seg.segment_id}`", seg.text, ""])
    return "\n".join(lines).strip()


def _compress_text(text: str, ratio: float, hard_cap_chars: int) -> str:
    if len(text) <= hard_cap_chars:
        return text
    truncated = text[: max(256, int(len(text) * ratio))]
    if len(truncated) > hard_cap_chars:
        truncated = truncated[:hard_cap_chars]
    return truncated + "\n\n[truncated_by_prompt_budget]"


def compose_prompt(
    *,
    command: str,
    task_type: str | None,
    intent: str | None,
    context_blocks: list[dict[str, Any]] | None,
    ai_config: dict[str, Any] | None,
    response_profile: str | None,
    project_slug: str | None,
    viz: str | None,
    prompt_budget: str | None,
    root: str | Path | None = None,
) -> ComposedPrompt:
    repo_root = Path(root) if root else Path.cwd()
    prompting_cfg = normalize_prompting_config(ai_config or {})
    resolved_profile = _normalize_profile(command, response_profile, prompting_cfg)
    resolved_budget = _normalize_budget(prompt_budget, prompting_cfg)
    viz_enabled = _effective_viz(command=command, task_type=task_type, viz=viz, prompting_cfg=prompting_cfg)

    global_registry = _load_registry(repo_root / "prompts" / "registry.yaml")
    module_by_id: dict[str, dict[str, Any]] = {}
    for raw in global_registry:
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            module_by_id[str(raw["id"])] = dict(raw)

    project_override_applied = False
    if project_slug:
        project_registry_path = repo_root / "projects" / project_slug / "prompts" / "registry.yaml"
        if project_registry_path.exists():
            for raw in _load_registry(project_registry_path):
                if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
                    continue
                module_id = str(raw["id"])
                if module_id in module_by_id:
                    project_override_applied = True
                module_by_id[module_id] = dict(raw)

    module_segments: list[_Segment] = []
    selected_modules: list[str] = []
    for module in module_by_id.values():
        if not _module_applies(
            module,
            command=command,
            task_type=task_type,
            response_profile=resolved_profile,
            viz_enabled=viz_enabled,
        ):
            continue
        module_id = str(module["id"])
        module_text = _load_module_text(repo_root, str(module.get("path", "")))
        module_segments.append(
            _Segment(
                segment_id=module_id,
                text=module_text,
                required=bool(module.get("required", False)),
                priority=int(module.get("priority", 50)),
                order=int(module.get("order", 100)),
                kind="module",
            )
        )
        selected_modules.append(module_id)

    context_segments: list[_Segment] = []
    for idx, block in enumerate(context_blocks or []):
        if not isinstance(block, dict):
            continue
        name = str(block.get("name", f"context_{idx+1}"))
        text = str(block.get("text", "")).strip()
        if not text:
            continue
        context_segments.append(
            _Segment(
                segment_id=name,
                text=text,
                required=bool(block.get("required", True)),
                priority=int(block.get("priority", 40)),
                order=int(block.get("order", 1000 + idx)),
                kind="context",
            )
        )

    all_segments = module_segments + context_segments
    dropped: list[str] = []

    budgets = prompting_cfg.get("budget_profiles", {})
    budget_cfg = budgets.get(resolved_budget, budgets.get("high", {}))
    target_tokens = int(budget_cfg.get("target_tokens", 12000))
    soft_limit = int(budget_cfg.get("soft_limit_tokens", 18000))
    hard_limit = int(budget_cfg.get("hard_limit_tokens", 24000))

    def _render_with_meta(segments: list[_Segment], dropped_modules: list[str]) -> tuple[str, int]:
        body = _render_segments(segments)
        meta = [
            "[PromptComposerMeta]",
            f"command={command}",
            f"task_type={task_type or command}",
            f"intent={intent or 'design'}",
            f"response_profile={resolved_profile}",
            f"budget_profile={resolved_budget}",
            f"viz={'on' if viz_enabled else 'off'}",
            "selected_modules=" + ",".join(sorted({seg.segment_id for seg in segments if seg.kind == "module"})),
            "dropped_modules=" + ",".join(dropped_modules),
            "[/PromptComposerMeta]",
            "",
            body,
        ]
        text = "\n".join(meta).strip()
        return text, _estimate_tokens(text)

    rendered_text, estimated_tokens = _render_with_meta(all_segments, dropped)

    # Stage 1: drop lowest-priority optional modules above target.
    if estimated_tokens > target_tokens:
        drop_candidates = sorted(
            [seg for seg in all_segments if seg.kind == "module" and not seg.required],
            key=lambda seg: (seg.priority, -seg.order),
        )
        for seg in drop_candidates:
            all_segments = [item for item in all_segments if item.segment_id != seg.segment_id]
            if seg.segment_id not in dropped:
                dropped.append(seg.segment_id)
            rendered_text, estimated_tokens = _render_with_meta(all_segments, dropped)
            if estimated_tokens <= target_tokens:
                break

    # Stage 2: continue dropping optional modules and compress context for soft limit.
    if estimated_tokens > soft_limit:
        drop_candidates = sorted(
            [seg for seg in all_segments if seg.kind == "module" and not seg.required],
            key=lambda seg: (seg.priority, -seg.order),
        )
        for seg in drop_candidates:
            all_segments = [item for item in all_segments if item.segment_id != seg.segment_id]
            if seg.segment_id not in dropped:
                dropped.append(seg.segment_id)
        compressed_segments: list[_Segment] = []
        for seg in all_segments:
            if seg.kind == "context":
                compressed_segments.append(
                    _Segment(
                        segment_id=seg.segment_id,
                        text=_compress_text(seg.text, ratio=0.6, hard_cap_chars=4000),
                        required=seg.required,
                        priority=seg.priority,
                        order=seg.order,
                        kind=seg.kind,
                    )
                )
            else:
                compressed_segments.append(seg)
        all_segments = compressed_segments
        rendered_text, estimated_tokens = _render_with_meta(all_segments, dropped)

    # Stage 3: hard limit guard keeps only required modules + minimal context.
    if estimated_tokens > hard_limit:
        all_segments = [seg for seg in all_segments if seg.required]
        compressed_segments = []
        for seg in all_segments:
            if seg.kind == "context":
                compressed_segments.append(
                    _Segment(
                        segment_id=seg.segment_id,
                        text=_compress_text(seg.text, ratio=0.35, hard_cap_chars=1800),
                        required=seg.required,
                        priority=seg.priority,
                        order=seg.order,
                        kind=seg.kind,
                    )
                )
            else:
                compressed_segments.append(seg)
        all_segments = compressed_segments
        rendered_text, estimated_tokens = _render_with_meta(all_segments, dropped)

    final_selected_modules = sorted({seg.segment_id for seg in all_segments if seg.kind == "module"})
    return ComposedPrompt(
        text=rendered_text,
        selected_modules=final_selected_modules,
        dropped_modules=dropped,
        estimated_tokens=estimated_tokens,
        budget_profile=resolved_budget,
        response_profile=resolved_profile,
        project_override_applied=project_override_applied,
    )
