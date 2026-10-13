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

### AD-003
- **Decision**: Bill aggregates (`computed_total`, `paid_amount`, `settled_on`) are stored on `credit_card_bills` and written only by `bill_service.refresh_bills`; bill status, remaining and overpaid amounts are derived at read time.
- **Reason**: The `settlement` accounting mode buckets every card purchase by the date its bill was paid; reading a stored `settled_on` by primary key keeps dashboard, report and budget queries cheap, the same trade AD-002 made for `balance_date`.
- **Trade-off**: Stored values can drift if a write path skips the refresh; AD-004 and the `rebuild-bills` CLI are the guard.
- **Scope**: `backend/app/services/bill_service.py`, `reporting_date_col` in `backend/app/services/_query_filters.py`, migrations `099`/`100`
- **Date**: 2026-10-12
- **Status**: active

### AD-004
- **Decision**: Every write path that creates, changes or deletes a credit-card transaction or a bill payment calls `bill_service.link_account_transactions` or `bill_service.touch` in the same transaction.
- **Reason**: Bills are the anchor for card purchases and payments; a row created outside them breaks the bill totals and the `settlement` mode.
- **Trade-off**: New write paths must remember the call; each existing path has a test asserting the bill after the write.
- **Scope**: `transaction_service`, `import_service`, `connection_service`, `recurring_transaction_service`, `account_service`, `category_service`
- **Date**: 2026-10-12
- **Status**: active (bulk statements and relinking; ORM refreshes are also covered by AD-005)

### AD-005
- **Decision**: A session-level safety net keeps bill aggregates current for every ORM write. A `before_flush` listener on the sync `Session` collects the bills touched by new, changed or deleted `Transaction` rows (old and new `bill_id` / `paid_bill_id`, and the bills of rows whose amount, type, date, account, category, ignore flags, status, source or `transfer_pair_id` changed). A `before_commit` listener refreshes those bills through the single sync implementation behind `refresh_bills`, which runs inside the async greenlet.
- **Reason**: Three verification rounds each found another ORM write path that skipped the explicit refresh (AD-004), most recently the reconciliation transfer accept. A listener covers every ORM path, current and future, in one place.
- **Trade-off**: The listener only refreshes stored aggregates; it does not relink rows to bills (date/account moves still go through `link_account_transactions`). Core bulk `update()`/`delete()` statements bypass ORM events, so the T64 guard test stays and still requires an explicit refresh for them. There is a small extra cost on commits that touch transactions.
- **Scope**: `backend/app/services/bill_service.py` (refresh core + listener registration), every AsyncSession built from `async_session_maker` and the test session
- **Date**: 2026-10-13
- **Status**: active (complements AD-004, which still applies to bulk statements and relinking)

## Handoff

- **Feature**: .specs/features/credit-card-bills
- **Phase / Task**: Done. Verifier round 4 PASS (validation.md, commit 5228ace)
- **Completed**: T1-T78, Verifier rounds 1-4
- **In-progress** (file:line): none
- **Next step**: owner reviews the branch; push and open the PR only with the owner's go-ahead
- **Blockers**: none
- **Uncommitted files**: none
- **Branch**: claude/credit-card-improvements-e85788
