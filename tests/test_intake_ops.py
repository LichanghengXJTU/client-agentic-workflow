from __future__ import annotations

from pathlib import Path

from workflow.intake_ops import (
    parse_intake_prompt,
    resolve_prompt_contract,
    save_task_intake,
    score_intake_completeness,
)
from workflow.state_ops import read_yaml


def test_parse_and_score_intake_prompt() -> None:
    contract = resolve_prompt_contract(task_type="code", project_slug=None)
    raw = """
# 核心任务
实现 dashboard 双中心

# 需要提供的文件
- dashboard/app.py
- workflow/review_ops.py

# 工作流程
- Plan
- Do
- Check
- Act

回答方式: 先结论后细节
验收标准:
- pytest 通过
- verify 通过
"""
    sections = parse_intake_prompt(raw, contract)
    completeness = score_intake_completeness(sections, contract)

    assert sections["core_task"]
    assert "dashboard/app.py" in sections["required_files"]
    assert sections["response_style"]
    assert completeness["score"] > 0.5


def test_save_task_intake_writes_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    payload = {
        "raw_prompt": "核心任务: 补测试",
        "project_slug": "demo",
        "sections": {
            "core_task": "补测试",
            "required_files": ["tests/test_x.py"],
            "workflow": ["Plan", "Do"],
            "response_style": "qa_zh",
            "acceptance": ["pytest 通过"],
            "constraints": [],
            "deliverables": ["test report"],
            "visualization": "none",
        },
        "completeness": {"missing_required": [], "score": 1.0},
    }
    intake_path = save_task_intake(task_id="T-9999", payload=payload, uploads=[("spec.txt", b"hello")])

    assert Path(intake_path).exists()
    data = read_yaml(intake_path)
    assert data["task_id"] == "T-9999"
    assert data["project_slug"] == "demo"
    assert data["raw_prompt_ref"]
    assert Path(data["raw_prompt_ref"]).exists()
    assert len(data["attachments"]) == 1
    assert Path(data["attachments"][0]["path"]).exists()
    assert data["attachments"][0]["sha256"].startswith("sha256:")
