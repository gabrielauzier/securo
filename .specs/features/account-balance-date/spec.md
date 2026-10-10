# Account Balance Date Specification

Plan: `.specs/features/account-balance-date/plan.md` · Builds on `.specs/features/selfhost-3-adjustments/` (AD-001)

## Problem Statement

The "balance date" chosen in the add/edit account dialog is not stored on the account. It exists only as the date of the synthetic `opening_balance` transaction, which is deleted when the balance is 0, cannot be edited alone when no such transaction exists, is not shown when editing, and is re-read through a correlated subquery on every balance query. The owner wants the chosen date saved on the account and used as the cutoff for summing transactions everywhere a balance is shown.

## Goals

- [ ] The date chosen by the user is persisted on the account and shown again when editing.
- [ ] Every balance read uses the stored date as the floor, with no subquery on transactions.
- [ ] Existing accounts keep showing the same balances after the upgrade.

## Out of Scope

| Feature | Reason |
| ------- | ------ |
| User-defined balance date on bank-connected accounts | Provider stays the source of the balance (owner decision) |
| Applying the floor to the running-balance walk in account detail (F10 residual) | Deferred to a follow-up |
| Changing historical report series before the balance date | Decision of the previous release (AD-001) |
| Replacing the synthetic `opening_balance` transaction with another model | It keeps carrying the balance amount |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| Where the date lives | New nullable column `accounts.balance_date` (DATE) | Survives balance 0, date-only edits and re-creation of the synthetic row | y |
| `NULL` meaning | No floor (sum every countable transaction) | Matches pre-B2 behavior for accounts with no opening date | y |
| Saldo 0 with a chosen date | Date is saved and the floor applies; no opening transaction is created | Owner approved the proposal (Q1) | y |
| Edit without touching the date | The stored date is kept; it changes only when the user changes it | Owner approved (Q2) | y |
| Backfill | Manual accounts get the latest `opening_balance` transaction date; others stay NULL | Same date the floor uses today, so displayed balances do not change (Q3) | y |
| Bank-connected accounts | `balance_date` stays NULL and is ignored | Owner approved (Q4) | y |
| Future date | Accepted; the floor takes effect when the date arrives (a cutoff before it reads full history) | Owner approved (Q5) | y |
| Account vs opening transaction | The account is the source of truth; every write updates both in the same commit | Avoids drift | y |
| Create with no date sent | Default is today (`app_today()`) | Current behavior | y |
| Floor read path | `within_opening_floor(cutoff)` keeps its signature and reads `Account.balance_date` through a correlated scalar subquery on `accounts` (no new joins in callers) | Smallest change for the 10 existing call sites | y |

**Open questions:** none - all resolved or logged above.

---

## User Stories

### P1: Save the balance date on the account ⭐ MVP

**User Story**: As a user, I want the balance date I choose to be saved with the account so that it keeps meaning even when the balance is zero or I change only the date.

**Why P1**: Fixes the root cause of the lost date and enables the rest.

**Acceptance Criteria**:

1. WHEN a manual account is created with a balance date D THEN the system SHALL store `balance_date = D` on the account.
2. WHEN a manual account is created without a balance date THEN the system SHALL store `balance_date` as today's date.
3. WHEN a manual account is created with balance 0 and a date D THEN the system SHALL store `balance_date = D` and SHALL NOT create an opening-balance transaction.
4. WHEN a manual account is updated with a new balance date D THEN the system SHALL store `balance_date = D` and SHALL set the existing opening-balance transaction's date to D.
5. WHEN a manual account is updated with a balance (non-zero) and no date THEN the system SHALL keep the stored `balance_date` and SHALL create or update the opening-balance transaction dated at that stored date (today if the account has none).
6. WHEN a manual account is updated to balance 0 THEN the system SHALL delete the opening-balance transaction and SHALL keep `balance_date`.
7. WHEN a manual account is updated without `balance` and `balance_date` THEN the system SHALL leave `balance_date` unchanged.
8. The account read model SHALL include `balance_date` (null when unset).
9. WHERE the account is bank-connected the system SHALL keep `balance_date` null and SHALL ignore a `balance_date` sent in a write.

**Independent Test**: Create an account with balance 0 and a date; read it back: the date is returned.

---

### P1: Balance reads use the stored date as the floor ⭐ MVP

**User Story**: As a user, I want every balance shown for an account to sum only transactions from the saved date onward.

**Why P1**: The point of the change.

**Acceptance Criteria**:

1. WHILE an account has `balance_date` D the system SHALL count, in the accounts-list balance and `previous_balance`, the account summary current balance and window opening balance, the balance history, and dashboard, goal and report snapshots, only transactions dated on or after D when the cutoff is on or after D.
2. WHEN the cutoff is before D THEN the system SHALL include every countable transaction up to the cutoff.
3. WHILE `balance_date` is null the system SHALL sum every countable transaction.
4. WHILE an account has `balance_date` D and no opening-balance transaction the system SHALL still apply the floor (balance 0 at D).
5. WHEN `balance_date` changes THEN the next balance read SHALL reflect the new floor.
6. WHERE the account is bank-connected the system SHALL return the same balances as before this change.
7. The net-worth balance-reset notice SHALL be based on `Account.balance_date` (accounts whose `balance_date` lies in the report window and that have earlier non-ignored transactions) and SHALL show that date.

**Independent Test**: Balance date 10/10, expense on 05/10: balance unchanged; expense on 15/10: balance moves.

---

### P1: Existing accounts keep their balances after the upgrade ⭐ MVP

**User Story**: As an operator, I want the upgrade to keep today's balances unchanged.

**Acceptance Criteria**:

1. WHEN the migration runs THEN the system SHALL set `balance_date` of each manual account that has opening-balance transactions to the latest such date.
2. WHEN the migration runs THEN the system SHALL leave `balance_date` null for bank-connected accounts and for manual accounts with no opening-balance transaction.
3. WHEN the migration is downgraded THEN the system SHALL drop the column without error.

**Independent Test**: Seed accounts, run the migration, compare balances before and after.

---

### P2: The edit dialog shows and explains the saved date

**User Story**: As a user, I want the edit dialog to show the saved balance date and tell me what it does.

**Acceptance Criteria**:

1. WHEN the edit dialog opens for a manual account with a `balance_date` THEN the system SHALL show that date in the "Data do saldo" field.
2. WHEN the edit dialog opens for a manual account with no `balance_date` THEN the system SHALL show today's date.
3. WHEN the create dialog opens THEN the system SHALL show today's date.
4. The dialog SHALL show a hint under the field that transactions before this date do not change the balance.
5. WHEN the user changes only the account name THEN the system SHALL NOT send `balance` or `balance_date`.
6. The hint SHALL exist in all supported locales.

**Independent Test**: Open edit for an account with date 10/10: the field shows 10/10.

---

## Edge Cases

- IF `balance_date` is sent as an invalid date THEN the system SHALL reject it with HTTP 422.
- WHEN two requests update the same account concurrently THEN the last committed write SHALL win and the account and its opening transaction SHALL still carry the same date.
- WHEN the opening-balance transaction exists with a different date than the account THEN the system SHALL treat the account's `balance_date` as authoritative.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| ABD-01 | P1: Save the balance date on the account | Phase 1 (T1-T5) | Done |
| ABD-02 | P1: Balance reads use the stored date as the floor | - | Pending |
| ABD-03 | P1: Existing accounts keep their balances after the upgrade | - | Pending |
| ABD-04 | P2: The edit dialog shows and explains the saved date | - | Pending |

**Coverage:** 4 total, 0 mapped to tasks, 4 unmapped ⚠️ (until tasks are approved)

---

## Success Criteria

- [ ] Account created with balance 0 and a date returns that date, and the floor applies.
- [ ] Balances of existing accounts are identical before and after the migration.
- [ ] Editing an account shows the stored date.
