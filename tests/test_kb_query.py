from __future__ import annotations

from pathlib import Path

from workflow.citation_ops import validate_cite
from workflow.kb_ops import ingest_kb_sources, query_kb


def test_kb_query_returns_citations(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "policy.md").write_text("# Ops\nreject triggers rollback branch and revert.\n", encoding="utf-8")

    ingest_kb_sources(sources=["docs"])
    result = query_kb(query="rollback revert", top_k=5)

    assert result.hits
    first = result.hits[0]
    assert "#L" in first["cite"]
    ok, msg = validate_cite(first["cite"], source_sha256=first["source_sha256"], cwd=tmp_path)
    assert ok, msg


def test_kb_query_task_bound_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "workflow.md").write_text("workflow verify workflow audit\n", encoding="utf-8")

    ingest_kb_sources(sources=["docs"])
    result = query_kb(query="workflow", task_id="T-0015", top_k=1)

    assert Path(result.report_path).exists()
    assert Path("state/tasks/T-0015/run_index.yaml").exists()
