from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .citation_ops import validate_cite
from .kb_ops import KB_INDEX_DIR, query_kb
from .state_ops import read_yaml


@dataclass
class VerifyStep:
    name: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass
class VerifyResult:
    ok: bool
    steps: list[VerifyStep] = field(default_factory=list)
    report_path: Path | None = None


def _run(cmd: list[str], cwd: str | Path | None = None) -> VerifyStep:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return VerifyStep(
        name=" ".join(cmd),
        command=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
    )


def _discover_derivation_checks(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("*_check.py"))


def _discover_project_derivation_checks(root: Path) -> list[Path]:
    projects_root = root / "projects"
    if not projects_root.exists():
        return []
    return sorted(projects_root.rglob("derivations/*_check.py"))


def _verify_task_records(root: Path) -> VerifyStep:
    task_root = root / "state" / "tasks"
    if not task_root.exists():
        return VerifyStep(
            name="verify_task_records",
            command=["verify_task_records"],
            returncode=0,
            stdout="No state/tasks/ directory; skipped task record validation.",
            stderr="",
        )

    required = ["brief.yaml", "worklog.md", "evidence_map.yaml", "handoff.yaml", "run_index.yaml"]
    missing: list[str] = []
    for task_dir in sorted(path for path in task_root.iterdir() if path.is_dir()):
        for name in required:
            if not (task_dir / name).exists():
                missing.append(f"{task_dir.as_posix()}/{name}")
    if missing:
        return VerifyStep(
            name="verify_task_records",
            command=["verify_task_records"],
            returncode=1,
            stdout="",
            stderr="Missing task records:\n" + "\n".join(missing),
        )
    return VerifyStep(
        name="verify_task_records",
        command=["verify_task_records"],
        returncode=0,
        stdout="Task record structure looks complete.",
        stderr="",
    )


def _verify_citations(root: Path) -> VerifyStep:
    task_root = root / "state" / "tasks"
    if not task_root.exists():
        return VerifyStep(
            name="verify_citations",
            command=["verify_citations"],
            returncode=0,
            stdout="No task evidence maps found; skipped citation validation.",
            stderr="",
        )

    invalid: list[str] = []
    for evidence_map_path in sorted(task_root.glob("*/evidence_map.yaml")):
        data = read_yaml(evidence_map_path)
        for idx, claim in enumerate(data.get("claims", [])):
            if not isinstance(claim, dict):
                continue
            for eidx, evidence in enumerate(claim.get("evidence", [])):
                if not isinstance(evidence, dict):
                    continue
                cite = evidence.get("cite")
                if not isinstance(cite, str) or not cite:
                    continue
                ok, msg = validate_cite(cite, source_sha256=evidence.get("source_sha256"), cwd=root)
                if not ok:
                    invalid.append(f"{evidence_map_path.as_posix()} claims[{idx}] evidence[{eidx}]: {msg}")

    if invalid:
        return VerifyStep(
            name="verify_citations",
            command=["verify_citations"],
            returncode=1,
            stdout="",
            stderr="\n".join(invalid),
        )
    return VerifyStep(
        name="verify_citations",
        command=["verify_citations"],
        returncode=0,
        stdout="Citation checks passed.",
        stderr="",
    )


def _verify_kb_query_smoke(root: Path) -> VerifyStep:
    inverted = root / KB_INDEX_DIR / "inverted.json"
    chunk_meta = root / KB_INDEX_DIR / "chunk_meta.jsonl"
    if not inverted.exists() or not chunk_meta.exists():
        return VerifyStep(
            name="verify_kb_query_smoke",
            command=["verify_kb_query_smoke"],
            returncode=0,
            stdout="KB index not found; skipped query smoke test.",
            stderr="",
        )

    prev_cwd = Path.cwd()
    try:
        if root != prev_cwd:
            import os

            os.chdir(root)
        result = query_kb(query="workflow", task_id=None, top_k=1)
    finally:
        if Path.cwd() != prev_cwd:
            import os

            os.chdir(prev_cwd)
    if not result.hits:
        return VerifyStep(
            name="verify_kb_query_smoke",
            command=["verify_kb_query_smoke"],
            returncode=1,
            stdout="",
            stderr="KB query returned no hits.",
        )
    return VerifyStep(
        name="verify_kb_query_smoke",
        command=["verify_kb_query_smoke"],
        returncode=0,
        stdout=f"KB query smoke hit: {result.hits[0].get('cite', '')}",
        stderr="",
    )


def _verify_replay(root: Path) -> VerifyStep:
    candidates = sorted((root / "artifacts" / "tasks").glob("*/runs/*/run_meta.yaml"), reverse=True)
    for run_meta_path in candidates:
        data = read_yaml(run_meta_path)
        command = data.get("command", "")
        workdir = str(data.get("workdir", "."))
        if not isinstance(command, str) or not command.strip():
            continue
        if "workflow kb query" not in command:
            continue
        resolved_cwd = Path(workdir)
        if not resolved_cwd.is_absolute():
            resolved_cwd = (root / resolved_cwd).resolve()
        proc = subprocess.run(command, shell=True, cwd=resolved_cwd, capture_output=True, text=True)  # noqa: S602
        return VerifyStep(
            name="verify_replay",
            command=[command],
            returncode=proc.returncode,
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
        )

    return VerifyStep(
        name="verify_replay",
        command=["verify_replay"],
        returncode=0,
        stdout="No replayable run_meta command found; skipped replay.",
        stderr="",
    )


def run_verify(cwd: str | Path | None = None) -> VerifyResult:
    root = Path(cwd) if cwd else Path.cwd()
    steps: list[VerifyStep] = []

    tests_dir = root / "tests"
    if tests_dir.exists() and any(tests_dir.rglob("test_*.py")):
        steps.append(_run([sys.executable, "-m", "pytest", "-q"], cwd=root))
    else:
        steps.append(
            VerifyStep(
                name="pytest",
                command=[sys.executable, "-m", "pytest", "-q"],
                returncode=0,
                stdout="No tests found under tests/.",
                stderr="",
            )
        )

    for script in _discover_derivation_checks(root / "derivations"):
        steps.append(_run([sys.executable, str(script)], cwd=root))

    for script in _discover_project_derivation_checks(root):
        steps.append(_run([sys.executable, str(script)], cwd=root))

    steps.append(_verify_task_records(root))
    steps.append(_verify_citations(root))
    steps.append(_verify_kb_query_smoke(root))
    steps.append(_verify_replay(root))

    ok = all(step.returncode == 0 for step in steps)

    ts = datetime.now().strftime("%Y%m%d-%H%M")
    report = root / "artifacts" / "test" / f"verify-{ts}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Verify Report",
        "",
        f"- Time: {datetime.now().isoformat(timespec='seconds')}",
        f"- Overall: {'PASS' if ok else 'FAIL'}",
        "",
        "## Steps",
    ]
    for step in steps:
        lines.extend(
            [
                f"### {step.name}",
                f"- Return code: {step.returncode}",
                "- Stdout:",
                "```text",
                step.stdout or "",
                "```",
                "- Stderr:",
                "```text",
                step.stderr or "",
                "```",
                "",
            ]
        )
    report.write_text("\n".join(lines), encoding="utf-8")

    return VerifyResult(ok=ok, steps=steps, report_path=report)
