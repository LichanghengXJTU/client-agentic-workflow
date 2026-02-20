from __future__ import annotations

import time
from pathlib import Path

from workflow.jobs import list_jobs, start_job, stop_job, tail_job_log


def test_jobs_start_list_stop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()

    job = start_job("python3 -c \"import time; print('hello'); time.sleep(5)\"")
    assert job.id.startswith("J-")

    jobs = list_jobs()
    assert any(item["id"] == job.id for item in jobs)

    stopped = stop_job(job.id, force=False)
    assert stopped["status"] in {"stopped", "exited"}

    logs = tail_job_log(job.id)
    # log may be empty if process was terminated before flush, so only assert type
    assert isinstance(logs, str)

    # Ensure process termination settles
    time.sleep(0.2)
