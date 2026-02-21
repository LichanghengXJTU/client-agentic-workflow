from __future__ import annotations

from pathlib import Path

from workflow.kb_ops import ingest_kb_sources, load_kb_manifest


def test_kb_ingest_is_incremental(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "note.md").write_text("# Title\nrollback safety check\n", encoding="utf-8")

    result_1 = ingest_kb_sources(sources=["docs"])
    assert result_1.documents_total == 1
    assert result_1.ingested == 1

    manifest_1 = load_kb_manifest()
    assert len(manifest_1["documents"]) == 1
    doc = manifest_1["documents"][0]
    assert doc["local_path"] == "docs/note.md"
    assert Path(doc["processed"]["chunks_path"]).exists()
    assert Path("artifacts/kb/index/inverted.json").exists()

    result_2 = ingest_kb_sources(sources=["docs"])
    assert result_2.documents_total == 1
    assert result_2.skipped >= 1


def test_kb_ingest_task_bound_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "algo.md").write_text("Bellman backup with deterministic policy.\n", encoding="utf-8")

    result = ingest_kb_sources(sources=["docs"], task_id="T-0015")
    assert Path(result.report_path).exists()
    assert Path("state/tasks/T-0015/run_index.yaml").exists()
