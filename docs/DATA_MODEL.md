# DATA MODEL / 数据模型说明

## TASKS.yaml
```yaml
tasks:
  - id: "T-0001"
    title: "..."
    type: "derivation|code|writing|literature|experiment|meta"
    priority: "P0|P1|P2"
    owner: "codex|chatgpt|human"
    status: "todo|in_progress|waiting_review|done|blocked"
    acceptance: ["..."]
    evidence: ["path/to/file"]
    verification: ["pytest::...", "python derivations/..._check.py"]
    depends_on: ["T-0000"]
    created_at: "YYYY-MM-DD"
    updated_at: "YYYY-MM-DD"
```

## KEY_RESULTS.yaml
```yaml
results:
  - id: "KR-0001"
    statement: "可验证结论"
    status: "proposed|verified|deprecated"
    confidence: "low|medium|high"
    evidence: ["GUIDE.md#...", "tests/test_x.py::test_y"]
    verification: ["python -m workflow verify", "python derivations/examples/lemma1_check.py"]
    related_tasks: ["T-0001"]
    first_seen_commit: "<hash|TBD>"
    last_confirmed_commit: "<hash|TBD>"
    checkpoint_tags: ["cp-..."]
```

## REVIEW_QUEUE.yaml
```yaml
items:
  - id: "RQ-0001"
    task_id: "T-0001"
    title: "..."
    status: "pending|approve|rework|reject"
    scope: "task|subtask"  # optional, default task
    subtask_id: "ST-001"   # required when scope=subtask
    cascade_scope: "self_only|downstream|all"
    cascade_advice_ref: "artifacts/tasks/T-0017/ai/cascade-advice-....yaml"
    created_at: "YYYY-MM-DD"
    updated_at: "YYYY-MM-DD"
```

## PR_REGISTRY.yaml
```yaml
prs:
  - number: 12
    state: "OPEN|CLOSED|MERGED"
    role: "source|release"
    repo: "owner/repo"
    head_ref: "bootstrap/agentic-workflow"
    base_ref: "main"
    head_sha: "..."
    url: "https://github.com/..."
    created_at: "..."
    updated_at: "..."
```

## PROJECT_REGISTRY.yaml
```yaml
projects:
  - id: "P-0001"
    slug: "rl-gridworld-qlearning"
    title: "RL Gridworld Q-learning"
    local_path: "projects/rl-gridworld-qlearning"
    release_repo: "LichanghengXJTU/rl-gridworld-qlearning-release"
    release_visibility: "public|private|internal"
    release_default_branch: "main"
    status: "active|archived|draft"
    created_at: "YYYY-MM-DD"
    updated_at: "YYYY-MM-DD"
```

## JOBS.yaml
```yaml
jobs:
  - id: "J-0001"
    command: "python3 -m workflow verify"
    pid: 12345
    status: "running|stopped|exited"
    log_path: "artifacts/test/job-J-0001.log"
    workdir: "."
    started_at: "..."
    updated_at: "..."
```

## AI_BUDGET.yaml
```yaml
monthly_budget_usd: 2000.0
alert_threshold: 0.8
hard_limit_threshold: 1.0
current_month: "YYYY-MM"
spend_usd: 0.0
entries:
  - time: "YYYY-MM-DDTHH:MM:SS"
    task_type: "plan|audit|task:code|task:derivation|..."
    route_key: "pro|codex"
    requested_model: "gpt-5.2-pro"
    model: "gpt-5.2-pro|gpt-5-pro|..."
    fallback_hops: 0
    selection_note: "normal|hard_limit_reached_downgraded|..."
    input_tokens: 0
    output_tokens: 0
    cached_tokens: 0
    cost_usd: 0.0
    note: "selection note mirror for backward compatibility"
```

## AI_CONFIG.yaml (v2)
```yaml
version: 2
models:
  pro: "gpt-5.2-pro"
  codex: "gpt-5.2-codex"
routing:
  plan: "pro"
  audit: "pro"
  task_type:
    code: "codex"
    derivation: "pro"
    writing: "pro"
    literature: "pro"
    meta: "pro"
    experiment:
      design: "pro"
      run: "codex"
fallback_chains:
  pro: ["gpt-5.2-pro", "gpt-5-pro", "gpt-5.2", "gpt-5.1", "gpt-5", "gpt-5-mini"]
  codex: ["gpt-5.2-codex", "gpt-5.1-codex-max", "gpt-5.1-codex", "gpt-5-codex", "gpt-5.2", "gpt-5-mini"]
effort_by_route:
  pro: "xhigh"
  codex: "xhigh"
  hard_limit: "high"
hard_limit_model: "gpt-5-mini"
prompting:
  default_response_profile:
    plan: "qa_zh"
    audit: "audit_cn"
    task: "qa_zh"
  default_budget_profile: "high"
  budget_profiles:
    high:
      target_tokens: 12000
      soft_limit_tokens: 18000
      hard_limit_tokens: 24000
    medium:
      target_tokens: 8000
      soft_limit_tokens: 12000
      hard_limit_tokens: 16000
    low:
      target_tokens: 5000
      soft_limit_tokens: 8000
      hard_limit_tokens: 12000
  viz_policy:
    auto_on_commands: ["audit"]
    auto_on_task_types: ["experiment"]
  math_rigor_default: "strict"
  step_visibility: "layered_appendix"
  artifact_contract: "full_evidence_pack"
```

## state/tasks/<task_id>/brief.yaml
```yaml
task_id: "T-0015"
title: "..."
owner: "codex|human"
goal: "一句话目标"
success_criteria: ["..."]
scope_in: []
scope_out: []
constraints: []
long_inputs:
  - input_id: "IN-001"
    path: "artifacts/tasks/T-0015/inputs/spec-v1.md"
    source: "repo|external"
    sha256: "sha256:..."
assumptions:
  - id: "ASM-001"
    text: "..."
    status: "open|resolved"
    tag: "uncertain"
```

## state/tasks/<task_id>/intake.yaml
```yaml
task_id: "T-0017"
project_slug: "rl-gridworld-qlearning"
raw_prompt_ref: "artifacts/tasks/T-0017/inputs/intake-20260222-120001.md"
sections:
  core_task: "..."
  required_files: ["workflow/ai.py", "docs/WORKFLOW.md"]
  workflow: ["Plan", "Do", "Check", "Act"]
  response_style: "qa_zh"
  acceptance: ["..."]
  constraints: ["..."]
  deliverables: ["..."]
  visualization: "auto|required|none"
completeness:
  missing_required: []
  score: 0.0
attachments:
  - path: "artifacts/tasks/T-0017/inputs/uploads/.../spec.pdf"
    sha256: "sha256:..."
```

## state/tasks/<task_id>/subtasks.yaml
```yaml
task_id: "T-0017"
subtasks:
  - id: "ST-001"
    title: "..."
    objective: "..."
    owner: "planner|retriever|implementer|critic|scribe|human"
    priority: "P0|P1|P2"
    status: "todo|in_progress|waiting_review|done|blocked"
    depends_on: ["ST-000"]
    prompt_contract:
      core_task: "..."
      required_files: []
      workflow: []
      response_style: "qa_zh"
      deliverables: []
      verification: []
    latest_summary: "..."
    latest_event_at: "2026-02-22T12:00:00"
    review_history:
      - time: "2026-02-22T12:00:00"
        reviewer: "human"
        action: "Rework|Reject|Approve"
        notes: "..."
        scope: "self_only|downstream|all"
```

## PROMPT_CONTRACTS.yaml
```yaml
version: 1
default_contract:
  required_sections:
    - core_task
    - required_files
    - workflow
    - response_style
    - acceptance
    - constraints
    - deliverables
  sections:
    core_task:
      label: "核心任务"
      aliases: ["core task", "核心任务", "任务目标", "goal"]
      kind: "text"
task_type_overrides: {}
project_overrides: {}
```

## state/tasks/<task_id>/evidence_map.yaml
```yaml
task_id: "T-0015"
claims:
  - claim_id: "CL-001"
    statement: "可审计结论"
    linked_key_results: ["KR-0009"]
    confidence: "low|medium|high"
    evidence:
      - cite: "docs/WORKFLOW.md#L54"
        source_sha256: "sha256:..."
        note: "..."
    verification:
      - command: "python -m workflow verify"
        run_id: "RUN-20260221-100001"
    status: "proposed|verified|rejected"
```

## artifacts/tasks/<task_id>/runs/<run_id>/run_meta.yaml
```yaml
run_id: "RUN-20260221-100001"
task_id: "T-0015"
role: "planner|retriever|implementer|critic|scribe"
started_at: "2026-02-21T10:00:01"
ended_at: "2026-02-21T10:01:08"
command: "python -m workflow kb query --task T-0015 --q workflow"
args: ["--task", "T-0015"]
workdir: "."
environment:
  python: "3.13.7"
  platform: "Darwin-arm64"
  key_presence:
    OPENAI_API_KEY: "present|absent"
seed: 42
inputs:
  - path: "state/tasks/T-0015/brief.yaml"
    sha256: "sha256:..."
outputs:
  - path: "artifacts/tasks/T-0015/outputs/query-20260221-100108.yaml"
    sha256: "sha256:..."
exit_code: 0
logs:
  stdout: "artifacts/tasks/T-0015/runs/RUN-20260221-100001/stdout.log"
  stderr: "artifacts/tasks/T-0015/runs/RUN-20260221-100001/stderr.log"
```

## KB_CONFIG.yaml
```yaml
external_roots: ["/Volumes/workflow-kb"]
ignore_globs: ["**/.git/**", "**/.venv/**", "**/__pycache__/**"]
max_repo_file_mb: 20
chunk_policy:
  default_max_chars: 1200
  default_overlap_chars: 200
```

## KB_MANIFEST.yaml
```yaml
documents:
  - doc_id: "DOC-7f3ab2"
    source_uri: "file://literature/notes/2026-foo.md"
    local_path: "literature/notes/2026-foo.md"
    collected_at: "2026-02-21T10:20:00"
    version: "git:8e03dc5b"
    purpose: "background|policy|derivation|experiment"
    trust_level: "low|medium|high"
    license: "MIT|CC-BY|unknown"
    storage: "repo|external"
    external_root: ""
    size_bytes: 18342
    sha256: "sha256:..."
    status: "active|deprecated"
    processed:
      chunks_path: "artifacts/kb/processed/chunks/DOC-7f3ab2.jsonl"
      doc_summary_path: "artifacts/kb/summaries/doc/DOC-7f3ab2.yaml"
      index_refs:
        - "artifacts/kb/index/inverted.json"
```

## Schema Enforcement
- `workflow/schemas.py` 提供 TASKS / KEY_RESULTS 的强校验。
- `python -m workflow audit` 若 schema 不合法会报 P0，并给修复建议。

## GitHub Runtime Facts（非 schema 字段）
- 仓库 `visibility` 与 `defaultBranchRef` 属于 GitHub 托管平台运行态事实，不是本仓库 YAML schema 强制字段。
- 文档中提到的模型版本与仓库可见性状态是快照描述；模型真值来源为 `state/AI_CONFIG.yaml`，仓库状态真值来源为 `gh repo view ... --json ...`。
- 建议将关键可见性结论写入 `state/KEY_RESULTS.yaml`，并在 `state/STATE.md` 留存执行前后快照。
