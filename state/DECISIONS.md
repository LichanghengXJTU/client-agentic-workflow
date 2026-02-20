# DECISIONS (ADR)

## ADR-0001: Safe Rollback By Default
- Date: 2026-02-20
- Status: Accepted
- Decision: Reject/human rollback defaults to `rollback/<ref>` branch + `git revert`, not hard history rewrite.
