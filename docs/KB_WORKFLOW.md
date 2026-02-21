# KB WORKFLOW / 文件库与检索规范

## 1. Scope
- 复用现有目录：`state/` 管理清单，`artifacts/` 管理处理产物，`literature/` 保留人工文献入口。
- 不新增顶层 `knowledge_base/`。

## 2. Core Paths
- 配置：`state/KB_CONFIG.yaml`
- 清单：`state/KB_MANIFEST.yaml`
- chunks：`artifacts/kb/processed/chunks/*.jsonl`
- index：`artifacts/kb/index/inverted.json`、`artifacts/kb/index/chunk_meta.jsonl`
- summaries：`artifacts/kb/summaries/{chunk,doc,corpus}/`

## 3. Ingest
- 命令：`python -m workflow kb ingest --src <path> [--task T-xxxx]`
- 增量规则：`sha256 + size + mtime` 未变化则仅更新 `last_seen_at`。
- 忽略规则：合并 `.gitignore` 与 `KB_CONFIG.ignore_globs`。
- 超大文件：超过 `max_repo_file_mb` 标记 `storage=external`，只保留 pointer。

## 4. Chunk
- 默认策略：`max_chars=1200`，`overlap_chars=200`。
- 最小元数据：`chunk_id/doc_id/line_start/line_end/char_start/char_end/text_sha256/heading`。

## 5. Query
- 命令：`python -m workflow kb query --q "<query>" [--task T-xxxx]`
- 输出：命中列表包含 `score + cite(path#Lx) + source_sha256 + snippet`。
- 检索报告写入：
  - 有 task：`artifacts/tasks/<task_id>/outputs/query-*.yaml`
  - 无 task：`artifacts/kb/query-*.yaml`

## 6. Citation Integrity
- 推荐格式：`path#L<line>`（可扩展范围格式）。
- 校验维度：路径存在、行号有效、`source_sha256` 匹配。
- hash 不匹配时结论应标记 `uncertain`。

## 7. Safety
- 禁止将 `state/AI_SECRETS.local.yaml` 的行级内容作为证据引用。
- 可记录密钥存在性（present/absent），不可记录密钥值。
