from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .state_ops import load_project_registry, save_project_registry, today_str


@dataclass
class ProjectRegistryResult:
    id: str
    slug: str
    title: str
    local_path: str
    release_repo: str
    release_visibility: str
    release_default_branch: str
    status: str


PROJECT_PROMPT_TEMPLATES: dict[str, str] = {
    "prompt-01-initiation.md": (
        "# Prompt-01 Initiation\n\n"
        "Create project scaffold and register 5 tasks (scaffold, implementation, verify-audit, "
        "release automation, final review)."
    ),
    "prompt-02-derivation.md": (
        "# Prompt-02 Derivation\n\n"
        "Write Q-learning update and Bellman relation in project derivations, and add a runnable check script."
    ),
    "prompt-03-experiment.md": (
        "# Prompt-03 Experiment\n\n"
        "Implement deterministic Gridworld tabular Q-learning with fixed seed and save artifacts."
    ),
    "prompt-04-ai-plan.md": (
        "# Prompt-04 AI Plan\n\n"
        "Generate actionable next-step plan from current TASKS and project files; highlight missing evidence/verifications."
    ),
    "prompt-05-ai-audit.md": (
        "# Prompt-05 AI Audit\n\n"
        "Audit P0/P1/P2 risks for task state, key-result traceability, approval loop, and rollback safety."
    ),
}


def _next_project_id(items: list[dict[str, Any]]) -> str:
    nums: list[int] = []
    for item in items:
        pid = str(item.get("id", ""))
        if not pid.startswith("P-"):
            continue
        tail = pid.split("-", maxsplit=1)[1]
        if tail.isdigit():
            nums.append(int(tail))
    return f"P-{(max(nums) + 1 if nums else 1):04d}"


def list_projects() -> list[dict[str, Any]]:
    return load_project_registry()


def project_by_slug(slug: str) -> dict[str, Any]:
    projects = load_project_registry()
    for item in projects:
        if item.get("slug") == slug:
            return item
    raise KeyError(f"Project not found by slug: {slug}")


def add_project(
    slug: str,
    title: str,
    local_path: str,
    release_repo: str,
    release_visibility: str = "public",
    release_default_branch: str = "main",
    status: str = "active",
) -> dict[str, Any]:
    projects = load_project_registry()
    if any(item.get("slug") == slug for item in projects):
        raise ValueError(f"Project slug already exists: {slug}")

    today = today_str()
    item = {
        "id": _next_project_id(projects),
        "slug": slug,
        "title": title,
        "local_path": local_path,
        "release_repo": release_repo,
        "release_visibility": release_visibility,
        "release_default_branch": release_default_branch,
        "status": status,
        "created_at": today,
        "updated_at": today,
    }
    projects.append(item)
    save_project_registry(projects)
    return item


def update_project(slug: str, updates: dict[str, Any]) -> dict[str, Any]:
    projects = load_project_registry()
    for item in projects:
        if item.get("slug") != slug:
            continue
        item.update(updates)
        item["updated_at"] = today_str()
        save_project_registry(projects)
        return item
    raise KeyError(f"Project not found by slug: {slug}")


def scaffold_project(slug: str, title: str, base_dir: str = "projects") -> Path:
    root = Path(base_dir) / slug
    (root / "prompts").mkdir(parents=True, exist_ok=True)
    (root / "derivations").mkdir(parents=True, exist_ok=True)
    (root / "experiments").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(parents=True, exist_ok=True)

    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(
            "\n".join(
                [
                    f"# {title}",
                    "",
                    f"- Slug: `{slug}`",
                    "- Purpose: auditable RL workflow demo with Gridworld Q-learning.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    for name, content in PROJECT_PROMPT_TEMPLATES.items():
        prompt_path = root / "prompts" / name
        if not prompt_path.exists():
            prompt_path.write_text(content + "\n", encoding="utf-8")

    return root
