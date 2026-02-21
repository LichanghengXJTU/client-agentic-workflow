from __future__ import annotations

from workflow.citation_ops import canonical_cite, file_sha256, validate_cite


def test_validate_cite_with_hash_and_line() -> None:
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = root / "sample.txt"
        path.write_text("line1\nline2\nline3\n", encoding="utf-8")

        cite = canonical_cite("sample.txt", 2)
        ok, msg = validate_cite(cite, source_sha256=file_sha256(path), cwd=root)
        assert ok, msg


def test_validate_cite_fails_on_invalid_line() -> None:
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = root / "sample.txt"
        path.write_text("line1\nline2\n", encoding="utf-8")

        ok, _ = validate_cite("sample.txt#L5", cwd=root)
        assert not ok


def test_validate_cite_fails_on_hash_mismatch() -> None:
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = root / "sample.txt"
        path.write_text("line1\nline2\n", encoding="utf-8")

        ok, _ = validate_cite("sample.txt#L1", source_sha256="sha256:deadbeef", cwd=root)
        assert not ok
