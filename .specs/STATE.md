# STATE

## Decisions

### AD-001
- **Decision**: An account's balance is derived from its `opening_balance` transaction and counts only transactions dated on or after it; the rule lives in `within_opening_floor` in `backend/app/services/_query_filters.py`.
- **Reason**: Entries older than a manually set balance must not distort it, and the floor is derived at query time so editing the opening date is immediately correct with no migration or drift.
- **Trade-off**: Every balance read site must adopt the shared predicate; historical report series before the opening date still include earlier transactions, so a manual update can cause a visible jump (flagged by a note).
- **Scope**: account_service, dashboard_service, report_service, any future balance read
- **Date**: 2026-10-10
- **Status**: superseded by AD-002 (storage detail only; the floor rule itself is unchanged and still holds)

### AD-002
- **Decision**: An account's balance floor is read from `accounts.balance_date` (user-chosen, saved with the account); the `opening_balance` transaction mirrors it.
- **Reason**: The date chosen in the dialog was only the date of the synthetic opening transaction, so it vanished at balance 0, could not be edited alone and was not shown on edit; a column on the account keeps it and replaces the correlated subquery on `transactions` with a primary-key lookup on `accounts`.
- **Trade-off**: The account and its opening transaction must be written together (`create_account` / `update_account` keep them equal); fixtures that insert an opening row directly must also set `balance_date`.
- **Scope**: `within_opening_floor` (`backend/app/services/_query_filters.py`), `_find_balance_resets` (`report_service.py`), `account_service` create/update, migration `098`, the account dialog
- **Date**: 2026-10-10
- **Status**: active

## Handoff

- **Feature**: .specs/features/account-balance-date
- **Phase / Task**: Done (T1-T10 + verification fixes F1-F6), validation.md PASS
- **Completed**: T1-T10, F1-F6
- **In-progress** (file:line): none
- **Next step**: owner reviews the branch and opens the PR (not pushed yet); it is stacked on feat/selfhost-3-adjustments (PR #2), so merge #2 first or target that branch
- **Blockers**: none
- **Uncommitted files**: .gitignore, frontend/package-lock.json (pre-existing, not ours)
- **Branch**: feat/account-balance-date
