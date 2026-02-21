from __future__ import annotations

from pathlib import Path

from workflow.state_ops import read_yaml
from workflow.task_ops import run_task_command


def test_task_run_records_run_meta_and_index(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_task_command(task_id="T-0015", role="implementer", command="echo task-run-ok")
    assert result.exit_code == 0

    run_meta = read_yaml(result.run_meta_path)
    assert run_meta["task_id"] == "T-0015"
    assert run_meta["role"] == "implementer"
    assert run_meta["command"] == "echo task-run-ok"
    assert "inputs" in run_meta and isinstance(run_meta["inputs"], list)
    assert "outputs" in run_meta and isinstance(run_meta["outputs"], list)
    assert Path(run_meta["logs"]["stdout"]).exists()
    assert Path(run_meta["logs"]["stderr"]).exists()

    run_index = read_yaml("state/tasks/T-0015/run_index.yaml")
    run_ids = [item["run_id"] for item in run_index.get("runs", [])]
    assert result.run_id in run_ids

    worklog = Path("state/tasks/T-0015/worklog.md").read_text(encoding="utf-8")
    assert "implementer: echo task-run-ok" in worklog
