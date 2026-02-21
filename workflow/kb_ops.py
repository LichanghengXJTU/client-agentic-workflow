from __future__ import annotations

import fnmatch
import json
import re
import shlex
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .citation_ops import canonical_cite, file_sha256
from .git_ops import current_head
from .state_ops import atomic_write_yaml, read_yaml
from .task_ops import record_task_run, scaffold_task_record

KB_CONFIG_PATH = Path("state") / "KB_CONFIG.yaml"
KB_MANIFEST_PATH = Path("state") / "KB_MANIFEST.yaml"
KB_CHUNKS_DIR = Path("artifacts") / "kb" / "processed" / "chunks"
KB_CHUNK_SUMMARY_DIR = Path("artifacts") / "kb" / "summaries" / "chunk"
KB_DOC_SUMMARY_DIR = Path("artifacts") / "kb" / "summaries" / "doc"
KB_CORPUS_SUMMARY_DIR = Path("artifacts") / "kb" / "summaries" / "corpus"
KB_INDEX_DIR = Path("artifacts") / "kb" / "index"

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")


@dataclass
class KBIngestResult:
    report_path: str
    manifest_path: str
    documents_total: int
    ingested: int
    updated: int
    skipped: int


@dataclass
class KBQueryResult:
    report_path: str
    hits: list[dict[str, Any]]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _default_kb_config() -> dict[str, Any]:
    return {
        "external_roots": ["/Volumes/workflow-kb"],
        "ignore_globs": ["**/.git/**", "**/.venv/**", "**/__pycache__/**"],
        "max_repo_file_mb": 20,
        "chunk_policy": {"default_max_chars": 1200, "default_overlap_chars": 200},
    }


def load_kb_config(path: str | Path = KB_CONFIG_PATH) -> dict[str, Any]:
    data = read_yaml(path)
    if not data:
        return _default_kb_config()
    merged = _default_kb_config()
    merged.update({k: v for k, v in data.items() if k != "chunk_policy"})
    cp = dict(merged.get("chunk_policy", {}))
    cp.update(data.get("chunk_policy", {}))
    merged["chunk_policy"] = cp
    return merged


def load_kb_manifest(path: str | Path = KB_MANIFEST_PATH) -> dict[str, Any]:
    data = read_yaml(path)
    if not data:
        return {"documents": []}
    data.setdefault("documents", [])
    return data


def save_kb_manifest(data: dict[str, Any], path: str | Path = KB_MANIFEST_PATH) -> None:
    atomic_write_yaml(path, data)


def _safe_rel_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return path.resolve().as_posix()


def _read_gitignore_patterns(root: Path) -> list[str]:
    path = root / ".gitignore"
    if not path.exists():
        return []
    patterns: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if line.endswith("/"):
            line = f"{line}**"
        patterns.append(line.lstrip("./"))
    return patterns


def _should_ignore(rel_path: str, gitignore_patterns: list[str], extra_globs: list[str]) -> bool:
    merged = [*gitignore_patterns, *extra_globs]
    normalized = rel_path.lstrip("./")
    for pattern in merged:
        p = pattern.lstrip("./")
        if fnmatch.fnmatch(normalized, p):
            return True
    return False


def _iter_source_files(sources: list[str], root: Path, gitignore_patterns: list[str], extra_globs: list[str]) -> list[Path]:
    discovered: list[Path] = []
    seen: set[str] = set()
    for source in sources:
        start = Path(source)
        if not start.exists():
            continue
        candidates = [start] if start.is_file() else [p for p in start.rglob("*") if p.is_file()]
        for path in candidates:
            rel = _safe_rel_path(path, root)
            if _should_ignore(rel, gitignore_patterns, extra_globs):
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            discovered.append(path)
    return sorted(discovered)


def _repo_version() -> str:
    try:
        return f"git:{current_head()[:8]}"
    except Exception:
        return "untracked"


def _source_uri(path: Path) -> str:
    return f"file://{path.resolve().as_posix()}"


def _doc_id_from_sha(sha256_value: str, local_path: str) -> str:
    import hashlib

    raw = f"{sha256_value}:{local_path}".encode("utf-8")
    return f"DOC-{hashlib.sha1(raw).hexdigest()[:8]}"


def _text_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text.splitlines()


def _line_offsets(lines: list[str]) -> list[int]:
    offsets: list[int] = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    return offsets


def _chunk_lines(path_rel: str, lines: list[str], max_chars: int, overlap_chars: int) -> list[dict[str, Any]]:
    if not lines:
        return []
    offsets = _line_offsets(lines)
    chunks: list[dict[str, Any]] = []
    start_idx = 0
    heading = ""
    idx = 0
    chunk_no = 1

    while idx < len(lines):
        line = lines[idx]
        hm = _HEADING_RE.match(line)
        if hm:
            heading = hm.group(1).strip()

        end_idx = idx
        size = 0
        while end_idx < len(lines):
            probe = len(lines[end_idx]) + (1 if end_idx > idx else 0)
            if size + probe > max_chars and end_idx > idx:
                break
            size += probe
            end_idx += 1

        chosen_end = max(end_idx - 1, idx)
        text = "\n".join(lines[idx : chosen_end + 1])
        line_start = idx + 1
        line_end = chosen_end + 1
        char_start = offsets[idx]
        char_end = offsets[chosen_end] + len(lines[chosen_end])
        chunks.append(
            {
                "chunk_id": f"CHK-{chunk_no:04d}",
                "source_path": path_rel,
                "ordinal": chunk_no,
                "line_start": line_start,
                "line_end": line_end,
                "char_start": char_start,
                "char_end": char_end,
                "heading": heading,
                "text_sha256": file_sha256_from_text(text),
                "text": text,
            }
        )
        chunk_no += 1

        if chosen_end >= len(lines) - 1:
            break

        back_chars = 0
        back_idx = chosen_end
        while back_idx > idx and back_chars < overlap_chars:
            back_chars += len(lines[back_idx]) + 1
            back_idx -= 1
        idx = max(start_idx, back_idx + 1)
        start_idx = idx

    return chunks


def file_sha256_from_text(text: str) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def _doc_summary(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    snippet = " ".join(chunk["text"].strip().replace("\n", " ")[:180] for chunk in chunks[:3]).strip()
    key_points = [chunk["heading"] for chunk in chunks if chunk.get("heading")][:3]
    return {"summary": snippet or "(empty)", "key_points": key_points, "open_risks": []}


def _tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


def _rebuild_index(manifest: dict[str, Any]) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    doc_by_id = {doc.get("doc_id"): doc for doc in manifest.get("documents", []) if isinstance(doc, dict)}
    inverted: dict[str, set[str]] = {}
    chunk_meta: list[dict[str, Any]] = []

    for chunk_path in sorted(KB_CHUNKS_DIR.glob("*.jsonl")):
        for chunk in _read_jsonl(chunk_path):
            doc = doc_by_id.get(chunk.get("doc_id"), {})
            chunk_id = str(chunk.get("chunk_id"))
            cite = canonical_cite(str(chunk.get("source_path", "")), int(chunk.get("line_start", 1)))
            entry = {
                "chunk_id": chunk_id,
                "doc_id": chunk.get("doc_id"),
                "source_path": chunk.get("source_path"),
                "line_start": chunk.get("line_start"),
                "line_end": chunk.get("line_end"),
                "cite": cite,
                "source_sha256": doc.get("sha256", ""),
                "purpose": doc.get("purpose", "background"),
                "trust_level": doc.get("trust_level", "medium"),
                "license": doc.get("license", "unknown"),
                "heading": chunk.get("heading", ""),
                "snippet": str(chunk.get("text", ""))[:240],
            }
            chunk_meta.append(entry)

            seen_terms = set(_tokenize(str(chunk.get("text", ""))))
            for term in seen_terms:
                inverted.setdefault(term, set()).add(chunk_id)

    normalized = {term: sorted(values) for term, values in inverted.items()}
    return normalized, chunk_meta


def _write_index(inverted: dict[str, list[str]], chunk_meta: list[dict[str, Any]]) -> None:
    KB_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    (KB_INDEX_DIR / "inverted.json").write_text(json.dumps(inverted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_jsonl(KB_INDEX_DIR / "chunk_meta.jsonl", chunk_meta)


def ingest_kb_sources(
    sources: list[str],
    task_id: str | None = None,
    external_root: str | None = None,
    purpose: str = "background",
    trust_level: str = "medium",
    license_name: str = "unknown",
) -> KBIngestResult:
    root = Path.cwd()
    config = load_kb_config()
    manifest = load_kb_manifest()
    existing_docs = {
        str(item.get("local_path")): item
        for item in manifest.get("documents", [])
        if isinstance(item, dict) and item.get("local_path")
    }

    gitignore_patterns = _read_gitignore_patterns(root)
    files = _iter_source_files(
        sources=sources,
        root=root,
        gitignore_patterns=gitignore_patterns,
        extra_globs=list(config.get("ignore_globs", [])),
    )

    KB_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    KB_CHUNK_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    KB_DOC_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    KB_CORPUS_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    max_repo_file_mb = int(config.get("max_repo_file_mb", 20))
    max_bytes = max_repo_file_mb * 1024 * 1024
    now = _now_iso()
    repo_version = _repo_version()

    ingested = 0
    updated = 0
    skipped = 0
    refreshed_docs: list[dict[str, Any]] = []

    for path in files:
        rel = _safe_rel_path(path, root)
        stat = path.stat()
        sha = file_sha256(path)
        existing = existing_docs.get(rel, {})
        unchanged = (
            bool(existing)
            and existing.get("sha256") == sha
            and int(existing.get("size_bytes", -1)) == stat.st_size
            and float(existing.get("mtime_epoch", -1.0)) == float(stat.st_mtime)
        )

        doc_id = str(existing.get("doc_id") or _doc_id_from_sha(sha, rel))
        storage = "external" if stat.st_size > max_bytes else "repo"
        effective_external_root = external_root or (config.get("external_roots", [""])[0] if storage == "external" else "")
        entry = {
            "doc_id": doc_id,
            "source_uri": _source_uri(path),
            "local_path": rel,
            "collected_at": existing.get("collected_at", now),
            "last_seen_at": now,
            "version": repo_version,
            "purpose": existing.get("purpose", purpose),
            "trust_level": existing.get("trust_level", trust_level),
            "license": existing.get("license", license_name),
            "storage": storage,
            "external_root": effective_external_root,
            "size_bytes": stat.st_size,
            "mtime_epoch": float(stat.st_mtime),
            "sha256": sha,
            "status": existing.get("status", "active"),
            "processed": existing.get("processed", {}),
        }

        if unchanged:
            skipped += 1
            refreshed_docs.append(entry)
            continue

        lines = _text_lines(path)
        is_binary_like = "\x00" in "\n".join(lines[:50])
        if storage == "repo" and not is_binary_like:
            chunk_policy = config.get("chunk_policy", {})
            max_chars = int(chunk_policy.get("default_max_chars", 1200))
            overlap = int(chunk_policy.get("default_overlap_chars", 200))
            chunks = _chunk_lines(path_rel=rel, lines=lines, max_chars=max_chars, overlap_chars=overlap)
            for chunk in chunks:
                chunk["doc_id"] = doc_id
            chunk_path = KB_CHUNKS_DIR / f"{doc_id}.jsonl"
            _write_jsonl(chunk_path, chunks)

            chunk_summaries = [
                {"chunk_id": item["chunk_id"], "summary": item["text"].replace("\n", " ")[:180]} for item in chunks
            ]
            _write_jsonl(KB_CHUNK_SUMMARY_DIR / f"{doc_id}.jsonl", chunk_summaries)
            doc_summary = _doc_summary(chunks)
            atomic_write_yaml(
                KB_DOC_SUMMARY_DIR / f"{doc_id}.yaml",
                {
                    "doc_id": doc_id,
                    "summary": doc_summary["summary"],
                    "key_points": doc_summary["key_points"],
                    "open_risks": doc_summary["open_risks"],
                },
            )
            entry["processed"] = {
                "chunks_path": chunk_path.as_posix(),
                "doc_summary_path": (KB_DOC_SUMMARY_DIR / f"{doc_id}.yaml").as_posix(),
                "index_refs": [
                    (KB_INDEX_DIR / "inverted.json").as_posix(),
                    (KB_INDEX_DIR / "chunk_meta.jsonl").as_posix(),
                ],
            }
        else:
            entry["processed"] = {
                "chunks_path": "",
                "doc_summary_path": "",
                "index_refs": [],
            }

        if existing:
            updated += 1
        else:
            ingested += 1
        refreshed_docs.append(entry)

    untouched = [doc for lp, doc in existing_docs.items() if lp not in {d["local_path"] for d in refreshed_docs}]
    manifest["documents"] = sorted([*untouched, *refreshed_docs], key=lambda item: str(item.get("doc_id", "")))
    save_kb_manifest(manifest)

    inverted, chunk_meta = _rebuild_index(manifest)
    _write_index(inverted, chunk_meta)
    corpus_summary = "\n".join(
        [
            "# Corpus Summary",
            "",
            f"- Time: {now}",
            f"- Documents: {len(manifest.get('documents', []))}",
            f"- Chunks indexed: {len(chunk_meta)}",
        ]
    )
    (KB_CORPUS_SUMMARY_DIR / "latest.md").write_text(corpus_summary + "\n", encoding="utf-8")

    report_payload = {
        "time": now,
        "sources": sources,
        "documents_total": len(manifest.get("documents", [])),
        "ingested": ingested,
        "updated": updated,
        "skipped": skipped,
        "manifest_path": KB_MANIFEST_PATH.as_posix(),
    }
    if task_id:
        scaffold_task_record(task_id=task_id)
        report_path = Path("artifacts") / "tasks" / task_id / "outputs" / f"ingest-{_timestamp()}.yaml"
    else:
        report_path = Path("artifacts") / "kb" / f"ingest-{_timestamp()}.yaml"
    atomic_write_yaml(report_path, report_payload)

    if task_id:
        ingest_args = ["--task", task_id]
        for src in sources:
            ingest_args.extend(["--src", src])
        if external_root:
            ingest_args.extend(["--external-root", external_root])
        ingest_args.extend(["--purpose", purpose, "--trust-level", trust_level, "--license", license_name])
        record_task_run(
            task_id=task_id,
            role="retriever",
            command=shlex.join([sys.executable, "-m", "workflow", "kb", "ingest", *ingest_args]),
            args=ingest_args,
            workdir=".",
            seed=None,
            inputs=[KB_CONFIG_PATH, KB_MANIFEST_PATH],
            outputs=[report_path],
            exit_code=0,
            stdout=json.dumps(report_payload, ensure_ascii=False),
            stderr="",
            add_worklog=True,
        )

    return KBIngestResult(
        report_path=report_path.as_posix(),
        manifest_path=KB_MANIFEST_PATH.as_posix(),
        documents_total=len(manifest.get("documents", [])),
        ingested=ingested,
        updated=updated,
        skipped=skipped,
    )


def query_kb(
    query: str,
    task_id: str | None = None,
    top_k: int = 8,
    purpose: str | None = None,
    trust_level: str | None = None,
    license_name: str | None = None,
) -> KBQueryResult:
    inverted_path = KB_INDEX_DIR / "inverted.json"
    chunk_meta_path = KB_INDEX_DIR / "chunk_meta.jsonl"
    if not inverted_path.exists() or not chunk_meta_path.exists():
        hits: list[dict[str, Any]] = []
    else:
        inverted = json.loads(inverted_path.read_text(encoding="utf-8"))
        chunk_meta = _read_jsonl(chunk_meta_path)
        meta_by_chunk = {item.get("chunk_id"): item for item in chunk_meta}

        tokens = _tokenize(query)
        scores: dict[str, int] = {}
        for token in tokens:
            for chunk_id in inverted.get(token, []):
                scores[chunk_id] = scores.get(chunk_id, 0) + 1

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        hits = []
        for chunk_id, score in ranked:
            meta = meta_by_chunk.get(chunk_id)
            if not meta:
                continue
            if purpose and meta.get("purpose") != purpose:
                continue
            if trust_level and meta.get("trust_level") != trust_level:
                continue
            if license_name and meta.get("license") != license_name:
                continue
            hits.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": meta.get("doc_id"),
                    "score": score,
                    "cite": meta.get("cite"),
                    "source_sha256": meta.get("source_sha256"),
                    "snippet": meta.get("snippet"),
                    "heading": meta.get("heading"),
                }
            )
            if len(hits) >= max(top_k, 1):
                break

    payload = {"time": _now_iso(), "query": query, "top_k": top_k, "hits": hits}
    if task_id:
        scaffold_task_record(task_id=task_id)
        report_path = Path("artifacts") / "tasks" / task_id / "outputs" / f"query-{_timestamp()}.yaml"
    else:
        report_path = Path("artifacts") / "kb" / f"query-{_timestamp()}.yaml"
    atomic_write_yaml(report_path, payload)

    if task_id:
        query_args = ["--task", task_id, "--q", query, "--top-k", str(top_k)]
        if purpose:
            query_args.extend(["--purpose", purpose])
        if trust_level:
            query_args.extend(["--trust-level", trust_level])
        if license_name:
            query_args.extend(["--license", license_name])
        record_task_run(
            task_id=task_id,
            role="retriever",
            command=shlex.join([sys.executable, "-m", "workflow", "kb", "query", *query_args]),
            args=query_args,
            workdir=".",
            seed=None,
            inputs=[KB_MANIFEST_PATH, inverted_path, chunk_meta_path],
            outputs=[report_path],
            exit_code=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="",
            add_worklog=True,
        )

    return KBQueryResult(report_path=report_path.as_posix(), hits=hits)
