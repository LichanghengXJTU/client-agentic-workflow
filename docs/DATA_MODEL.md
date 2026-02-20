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
entries: []
```

## Schema Enforcement
- `workflow/schemas.py` 提供 TASKS / KEY_RESULTS 的强校验。
- `python -m workflow audit` 若 schema 不合法会报 P0，并给修复建议。
