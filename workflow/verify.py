from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


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
