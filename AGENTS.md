# AGENTS Constitution

## Scope
This repository implements an auditable, verifiable, and rollback-safe Codex/ChatGPT/GitHub workflow.

## Severity Levels
- P0: Incorrect key result, missing verification for critical conclusion, unsafe rollback violation, schema corruption.
- P1: Workflow behavior mismatch, missing audit fields, approval traceability gap.
- P2: Documentation clarity, UX quality, non-blocking improvements.

## Hard Rules
- No fabrication. Mark uncertainty explicitly.
- Every critical conclusion must be written to `state/KEY_RESULTS.yaml` with evidence + verification.
- Mathematical derivations and key conclusions require executable validation (symbolic, numerical, dual-implementation, or invariant test).
- Unsafe destructive operations (`reset --hard`, force push) are forbidden by default.

## Mandatory Sync On Changes
- Update `state/STATE.md` for snapshot handoff.
- Update `state/KEY_RESULTS.yaml` when new conclusions are introduced.
- Generate `artifacts/audit/*` when audits are run.

## PR Requirements
- Change summary
- Acceptance checklist mapping
- Rollback note

## Execution Loop
- Plan -> Do -> Check -> Act
