from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .state_ops import (
    load_prompt_contracts,
    read_yaml,
    save_task_intake_data,
    task_state_dir,
)

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_KEY_VALUE_RE = re.compile(r"^\s*([A-Za-z0-9_\-\u4e00-\u9fff\s]{2,60})\s*[:：]\s*(.*)$")
_LIST_SPLIT_RE = re.compile(r"[;,，、]")
_PATH_HINT_RE = re.compile(r"[A-Za-z0-9_./\\-]+\.[A-Za-z0-9]{1,8}")


def _now_ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _normalize_text(value: str) -> str:
    return value.strip()


def _to_list(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    rows: list[str] = []
    for line in str(value).splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("- "):
            text = text[2:].strip()
        if text.startswith("* "):
            text = text[2:].strip()
        if text:
            rows.append(text)
    if not rows:
        rows = [x.strip() for x in _LIST_SPLIT_RE.split(str(value)) if x.strip()]
    return rows


def _section_kind(contract: dict[str, Any], section_id: str) -> str:
    section_map = contract.get("sections", {})
    section = section_map.get(section_id, {}) if isinstance(section_map, dict) else {}
    return str(section.get("kind", "text"))


def resolve_prompt_contract(task_type: str, project_slug: str | None = None) -> dict[str, Any]:
    contracts = load_prompt_contracts()
    default_contract = dict(contracts.get("default_contract", {}))

    task_type_overrides = contracts.get("task_type_overrides", {})
    if isinstance(task_type_overrides, dict) and isinstance(task_type_overrides.get(task_type), dict):
        default_contract.update(task_type_overrides[task_type])

    project_overrides = contracts.get("project_overrides", {})
    if project_slug and isinstance(project_overrides, dict) and isinstance(project_overrides.get(project_slug), dict):
        default_contract.update(project_overrides[project_slug])

    default_contract.setdefault("sections", {})
    default_contract.setdefault("required_sections", [])
    return default_contract


def _build_alias_map(contract: dict[str, Any]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for section_id, raw in contract.get("sections", {}).items():
        if not isinstance(raw, dict):
            continue
        alias_map[section_id.lower()] = section_id
        label = raw.get("label")
        if isinstance(label, str) and label.strip():
            alias_map[label.strip().lower()] = section_id
        aliases = raw.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str) and alias.strip():
                    alias_map[alias.strip().lower()] = section_id
    return alias_map


def _match_section(name: str, alias_map: dict[str, str]) -> str | None:
    normalized = name.strip().lower()
    if normalized in alias_map:
        return alias_map[normalized]

    for alias, section_id in alias_map.items():
        if alias and alias in normalized:
            return section_id
    return None


def _init_sections(contract: dict[str, Any]) -> dict[str, Any]:
    sections: dict[str, Any] = {}
    for section_id in contract.get("sections", {}):
        kind = _section_kind(contract, section_id)
        if kind == "list":
            sections[section_id] = []
        elif kind == "enum":
            choices = contract.get("sections", {}).get(section_id, {}).get("choices", ["auto"])
            sections[section_id] = str(choices[0] if choices else "auto")
        else:
            sections[section_id] = ""
    sections.setdefault("visualization", "auto")
    return sections


def parse_intake_prompt(raw_text: str, contract: dict[str, Any]) -> dict[str, Any]:
    text = str(raw_text or "")
    sections = _init_sections(contract)
    alias_map = _build_alias_map(contract)
    current_section: str | None = None

    for line in text.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            matched = _match_section(heading.group(1), alias_map)
            if matched:
                current_section = matched
            continue

        kv = _KEY_VALUE_RE.match(line)
        if kv:
            matched = _match_section(kv.group(1), alias_map)
            if matched:
                current_section = matched
                value = kv.group(2).strip()
                if value:
                    kind = _section_kind(contract, matched)
                    if kind == "list":
                        sections[matched].extend(_to_list(value))
                    elif kind == "enum":
                        choices = contract.get("sections", {}).get(matched, {}).get("choices", [])
                        lowered = value.lower()
                        sections[matched] = lowered if lowered in choices else "auto"
                    else:
                        sections[matched] = f"{sections[matched]}\n{value}".strip()
                continue

        if not current_section:
            continue

        kind = _section_kind(contract, current_section)
        if kind == "list":
            items = _to_list(line)
            sections[current_section].extend(items)
        elif kind == "enum":
            lowered = line.strip().lower()
            choices = contract.get("sections", {}).get(current_section, {}).get("choices", [])
            if lowered in choices:
                sections[current_section] = lowered
        else:
            value = line.strip()
            if value:
                sections[current_section] = f"{sections[current_section]}\n{value}".strip()

    # Fallback extraction for common sections.
    if not sections.get("core_task"):
        sections["core_task"] = text.strip()[:1000]

    if not sections.get("required_files"):
        sections["required_files"] = sorted({x for x in _PATH_HINT_RE.findall(text) if "/" in x or "\\" in x})

    for key, value in list(sections.items()):
        kind = _section_kind(contract, key)
        if kind == "list":
            dedup: list[str] = []
            seen: set[str] = set()
            for item in _to_list(value):
                if item in seen:
                    continue
                seen.add(item)
                dedup.append(item)
            sections[key] = dedup
        elif kind == "text":
            sections[key] = _normalize_text(str(value))

    if sections.get("visualization") not in {"auto", "required", "none"}:
        sections["visualization"] = "auto"

    return sections


def score_intake_completeness(parsed_sections: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    required_sections = [str(item) for item in contract.get("required_sections", []) if isinstance(item, str)]
    missing: list[str] = []

    for section in required_sections:
        value = parsed_sections.get(section)
        is_missing = False
        if isinstance(value, list):
            is_missing = len([x for x in value if str(x).strip()]) == 0
        else:
            is_missing = not str(value or "").strip()
        if is_missing:
            missing.append(section)

    if not required_sections:
        score = 1.0
    else:
        score = round((len(required_sections) - len(missing)) / len(required_sections), 3)

    return {
        "missing_required": missing,
        "score": score,
    }


def build_clarification_suggestions(parsed_sections: dict[str, Any], completeness: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    missing = set(completeness.get("missing_required", []))

    if "core_task" in missing:
        suggestions.append("补一句可执行目标：一句话说明要产出什么、如何判断完成。")
    if "required_files" in missing:
        suggestions.append("补全输入文件路径：至少给出核心代码/文档路径，避免模型盲猜。")
    if "workflow" in missing:
        suggestions.append("补流程：按 Plan/Do/Check/Act 给出关键步骤。")
    if "acceptance" in missing:
        suggestions.append("补验收标准：至少 2 条可验证标准（命令或测试）。")
    if "response_style" in missing:
        suggestions.append("指定回答方式：例如‘先结论后细节，输出中英文双语’。")

    if parsed_sections.get("visualization") == "required":
        suggestions.append("可视化为必需：请明确需要图表类型和对应数据来源。")

    if not suggestions:
        suggestions.append("输入信息已较完整，可直接创建任务并进入子任务拆解。")
    return suggestions


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _extract_upload(upload: Any) -> tuple[str, bytes] | None:
    if upload is None:
        return None
    if hasattr(upload, "name") and hasattr(upload, "getvalue"):
        try:
            return str(upload.name), bytes(upload.getvalue())
        except Exception:
            return None
    if isinstance(upload, tuple) and len(upload) == 2:
        name, content = upload
        if isinstance(name, str) and isinstance(content, (bytes, bytearray)):
            return name, bytes(content)
    if isinstance(upload, dict):
        name = upload.get("name")
        content = upload.get("content")
        if isinstance(name, str) and isinstance(content, (bytes, bytearray)):
            return name, bytes(content)
    return None


def save_task_intake(task_id: str, payload: dict[str, Any], uploads: list[Any] | None = None) -> str:
    uploads = uploads or []
    state_dir = task_state_dir(task_id)
    state_dir.mkdir(parents=True, exist_ok=True)

    inputs_dir = Path("artifacts") / "tasks" / task_id / "inputs"
    uploads_dir = inputs_dir / "uploads" / _now_ts()
    inputs_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    raw_prompt = str(payload.get("raw_prompt", "")).strip()
    raw_prompt_ref = ""
    if raw_prompt:
        raw_path = inputs_dir / f"intake-{_now_ts()}.md"
        raw_path.write_text(raw_prompt + "\n", encoding="utf-8")
        raw_prompt_ref = raw_path.as_posix()

    attachments: list[dict[str, str]] = []
    for item in uploads:
        parsed = _extract_upload(item)
        if not parsed:
            continue
        name, content = parsed
        safe_name = Path(name).name
        target = uploads_dir / safe_name
        target.write_bytes(content)
        attachments.append({"path": target.as_posix(), "sha256": _sha256_bytes(content)})

    for extra in payload.get("attachments", []):
        if not isinstance(extra, dict):
            continue
        p = extra.get("path")
        if isinstance(p, str) and p.strip():
            extra_item = {"path": p.strip(), "sha256": str(extra.get("sha256", ""))}
            attachments.append(extra_item)

    intake_data = {
        "task_id": task_id,
        "project_slug": str(payload.get("project_slug", "")).strip() or None,
        "raw_prompt_ref": raw_prompt_ref,
        "sections": payload.get("sections", {}),
        "completeness": payload.get("completeness", {}),
        "attachments": attachments,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    save_task_intake_data(task_id, intake_data)
    return (state_dir / "intake.yaml").as_posix()


def _load_local_api_key() -> str | None:
    env = os.getenv("OPENAI_API_KEY")
    if env:
        return env
    local = read_yaml("state/AI_SECRETS.local.yaml")
    key = local.get("openai_api_key") if isinstance(local, dict) else None
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None


def generate_ai_clarification_suggestions(raw_text: str, missing_required: list[str]) -> dict[str, Any]:
    key = _load_local_api_key()
    if not key:
        return {
            "ok": False,
            "uncertain": True,
            "suggestions": ["OPENAI_API_KEY 缺失，已回退规则建议。"],
            "note": "missing_api_key",
        }

    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        prompt = (
            "你是任务澄清助手。根据用户输入补充3-6条最重要澄清问题或补充信息建议。"
            "\n要求：每条一行，聚焦可执行性、验收、输入文件。"
            f"\nmissing_required={missing_required}\n\nraw:\n{raw_text[:4000]}"
        )
        response = client.responses.create(
            model="gpt-5-mini",
            reasoning={"effort": "low"},
            input=prompt,
        )
        text = getattr(response, "output_text", "") or ""
        rows = [x.strip("- ").strip() for x in text.splitlines() if x.strip()]
        return {
            "ok": True,
            "uncertain": False,
            "suggestions": rows[:8],
            "note": "ai_generated",
        }
    except Exception as exc:  # pragma: no cover - network and key dependent
        return {
            "ok": False,
            "uncertain": True,
            "suggestions": [f"AI 建议生成失败，已回退规则建议：{exc}"],
            "note": "ai_error",
        }
