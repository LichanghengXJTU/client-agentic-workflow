from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

SHA256_PREFIX = "sha256:"
_CITE_RE = re.compile(r"^(?P<path>.+)#L(?P<start>\d+)(?:-L?(?P<end>\d+))?$")


@dataclass
class CitationRef:
    path: str
    line_start: int
    line_end: int


def normalize_sha256(value: str) -> str:
    raw = value.strip()
    if raw.startswith(SHA256_PREFIX):
        return raw
    return f"{SHA256_PREFIX}{raw}"


def file_sha256(path: str | Path) -> str:
    p = Path(path)
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    return f"{SHA256_PREFIX}{digest}"


def parse_cite(cite: str) -> CitationRef:
    m = _CITE_RE.match(cite.strip())
    if not m:
        raise ValueError(f"Invalid cite format: {cite!r}. Expected `<path>#L<line>` or `<path>#L<start>-L<end>`.")

    start = int(m.group("start"))
    end = int(m.group("end") or start)
    if start <= 0 or end <= 0 or end < start:
        raise ValueError(f"Invalid cite line range in {cite!r}.")
    return CitationRef(path=m.group("path"), line_start=start, line_end=end)


def canonical_cite(path: str | Path, line_start: int, line_end: int | None = None) -> str:
    if line_start <= 0:
        raise ValueError("line_start must be positive.")
    if line_end is None or line_end == line_start:
        return f"{Path(path).as_posix()}#L{line_start}"
    if line_end < line_start:
        raise ValueError("line_end must be >= line_start.")
    return f"{Path(path).as_posix()}#L{line_start}-L{line_end}"


def validate_cite(cite: str, source_sha256: str | None = None, cwd: str | Path | None = None) -> tuple[bool, str]:
    try:
        ref = parse_cite(cite)
    except ValueError as exc:
        return False, str(exc)

    root = Path(cwd) if cwd else Path.cwd()
    file_path = root / ref.path
    if not file_path.exists():
        return False, f"Cited file does not exist: {ref.path}"
    if not file_path.is_file():
        return False, f"Cited path is not a file: {ref.path}"

    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if ref.line_end > len(lines):
        return False, f"Cited line out of range: {cite} (max {len(lines)})"

    if source_sha256:
        expected = normalize_sha256(source_sha256)
        actual = file_sha256(file_path)
        if actual != expected:
            return False, f"source_sha256 mismatch for {ref.path}"

    return True, "ok"


def extract_cited_text(cite: str, cwd: str | Path | None = None) -> str:
    ref = parse_cite(cite)
    root = Path(cwd) if cwd else Path.cwd()
    file_path = root / ref.path
    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[ref.line_start - 1 : ref.line_end])
