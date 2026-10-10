# STATE

## Decisions

### AD-001
- **Decision**: An account's balance is derived from its `opening_balance` transaction and counts only transactions dated on or after it; the rule lives in `within_opening_floor` in `backend/app/services/_query_filters.py`.
- **Reason**: Entries older than a manually set balance must not distort it, and the floor is derived at query time so editing the opening date is immediately correct with no migration or drift.
- **Trade-off**: Every balance read site must adopt the shared predicate; historical report series before the opening date still include earlier transactions, so a manual update can cause a visible jump (flagged by a note).
- **Scope**: account_service, dashboard_service, report_service, any future balance read
- **Date**: 2026-10-10
- **Status**: active

## Handoff

- **Feature**: .specs/features/selfhost-3-adjustments
- **Phase / Task**: Phase 1 / T1
- **Completed**: none
- **In-progress** (file:line): none
- **Next step**: dispatch batch worker 1 (Phase 1)
- **Blockers**: none
- **Uncommitted files**: .gitignore, frontend/package-lock.json (pre-existing, not ours; never stage them)
- **Branch**: feat/selfhost-3-adjustments
