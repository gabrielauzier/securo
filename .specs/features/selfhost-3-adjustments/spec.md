# Selfhost.3 Adjustments Specification

PRD: `.specs/prd/v0.16.3-selfhost.2-ajustes.md` · Target release: `0.16.3-selfhost.3`

## Problem Statement

The first production week of `0.16.3-selfhost.2` exposed two account bugs and four manual-work gaps. A new-account dialog reopens with the previous account's data; transactions dated before an account's opening balance still change that balance; CSV column mappings must be redone on every import; transfer pairing only runs on sync/import events; and transactions can only be ignored or turned into transfers one at a time.

## Goals

- [ ] Account balance equals opening balance plus transactions dated on/after the opening date, for every account type.
- [ ] The new-account dialog always opens with default values.
- [ ] Re-importing a known CSV layout needs zero mapping interactions.
- [ ] Transfer pairing runs on demand with a preview; bulk ignore/transfer act on up to 100 transactions per request.

## Out of Scope

| Feature | Reason |
| ------- | ------ |
| Net-worth variance set→out (original report item) | Discarded at triage: correct behavior |
| Horizontal scroll on import preview table | Discarded at triage |
| Sharing import mappings across users/workspaces | Mappings are per user |
| Mapping for OFX/QIF/CAMT | Already structured formats |
| Changing historical report series to apply the opening floor before the opening date | Decision: history keeps pre-opening transactions |
| Rewriting the reconciliation engine | F2/F4 reuse it as is |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| Opening-date comparison | `Transaction.date >= opening date` (same day counts) | Stated by owner | y |
| Opening balance row identity | The account's `source="opening_balance"` transaction; its `date` is the opening date | Existing model, no new column | y |
| Balance at a past cutoff | At cutoff `c`: if `c <` opening date, all transactions `<= c` count; else only transactions with `date >= opening date` and `<= c` count | Keeps historical series intact before the opening date while the current balance honors the floor | n (derived from owner's "keep historical series" decision) |
| Connected accounts | Rule applies uniformly; no-op in practice because the synthetic opening row is dated one day before the oldest counted transaction | Verified in `sync_opening_balance_for_connected_account` | y |
| "Last update date" shown in the report notice | Date of the account's opening-balance transaction | No separate balance-updated timestamp exists | y |
| Notice trigger | Open account in scope whose opening date falls in `(window start, window end]` and which has at least one non-ignored transaction dated before it | Divergence only exists then | y |
| Mapping match | Exact match of the CSV header set (order-insensitive, trimmed, case-sensitive) against the user's saved mappings | Avoids false positives | y |
| Several saved mappings match one file | Apply the most recently used; others stay selectable | Deterministic | n |
| Mapping name uniqueness | Unique per user, case-insensitive | Owner asked for named mappings | y |
| Bulk limit | 100 transaction IDs per request; above that → HTTP 422 | Owner decision | y |
| Bulk ignore semantics | Sets an explicit state; does not toggle | Avoids inverting mixed selections | y |
| Bulk ignore on transfer legs | Updates only the selected rows; does not cascade to the pair | Matches existing single toggle (`toggle_ignore_transaction`) | y |
| F2 scope | All unpaired transactions of the workspace, using the workspace's transfer rule; only mutual (`linked`) pairs are proposed | Same certainty bar as automatic pairing | y |
| F2 "suggested" pairs | Not applied by F2; remain in the existing suggestions queue | Out of the PRD | y |
| F4 pairing universe | Only the selected transactions; window/amount tolerance from the transfer rule | Owner decision | y |
| Permissions | Mutating endpoints require `current_writable_workspace`; previews are read-gated | Existing convention | y |
| Bulk-transfer preview gate | `POST /transactions/bulk-transfer/preview` requires write access, unlike the rule-wide `GET` preview which is read-gated | It is a POST (body carries up to 100 ids) and `test_write_permission_coverage` requires every POST to be write-gated; viewers cannot bulk-select-to-mark anyway | y |
| Rule-wide apply revalidation | `apply_pairs` revalidates posted pairs only against the posted ids (`restrict_ids`), not against the whole workspace | Same code path as the bulk flow, whose universe is the selection; stale legs (linked/deleted) are still skipped | y |
| Mapping destination account | A supplied `account_id` on create/update must belong to a workspace the user is a member of or manages; otherwise HTTP 404 `Account not found` (nothing stored, never 500); `null` clears it | Same 404-for-inaccessible convention as the accounts API; reuses `account_service.get_account` per user workspace | y |
| Account detail running-balance walk | When the chart window spans the opening date, the in-window running balance can differ from `current_balance` because the walk adds every in-window row; the summary seed and `current_balance` follow the floor. Accepted for this release | The account-detail walk (`frontend/src/pages/account-detail.tsx`) is a presentation of rows; `current_balance` remains authoritative | n |

**Open questions:** none - all resolved or logged above.

---

## User Stories

### P1: New-account dialog opens clean ⭐ MVP

**User Story**: As a user, I want the add-account dialog to open with default values so that I do not create an account with the previous account's data.

**Why P1**: Data-entry error on every second account created.

**Acceptance Criteria**:

1. WHEN the add-account dialog opens in create mode THEN the system SHALL show empty name and display name, type `checking`, balance `0`, the user's currency, today's date as balance date, and empty credit-card fields.
2. WHEN the dialog is closed after a successful save and reopened in create mode THEN the system SHALL show the default values.
3. WHEN the dialog is closed without saving and reopened in create mode THEN the system SHALL show the default values.
4. WHEN the dialog opens in edit mode THEN the system SHALL show the selected account's values.

**Independent Test**: Open dialog, fill fields, close, reopen: all fields default.

---

### P1: Opening balance is a floor for account balance ⭐ MVP

**User Story**: As a user, I want an account balance entered on a date to be affected only by transactions from that date onward so that older entries do not distort it.

**Why P1**: Wrong balances contaminate dashboard, goals and net worth.

**Acceptance Criteria**:

1. WHILE an account has an opening-balance transaction dated D, the account's current balance SHALL equal the opening amount plus the signed sum of counted transactions dated on or after D and up to today.
2. WHEN a transaction dated before D exists THEN the system SHALL keep it visible in the transaction list and SHALL exclude it from the account's current balance.
3. WHEN a transaction is dated exactly D THEN the system SHALL include it in the balance.
4. WHEN the opening balance date or amount is edited THEN the system SHALL recompute which transactions count on the next balance read.
5. WHILE an account has no opening-balance transaction the system SHALL sum all counted transactions as today.
6. The system SHALL apply the floor to the accounts list balance, `previous_balance`, the account detail summary, the account balance history, and dashboard, goals and report snapshots taken at a cutoff on or after D.
7. WHEN a report snapshot cutoff is earlier than D THEN the system SHALL include all counted transactions dated up to that cutoff.
8. WHERE an account is bank-connected the system SHALL return the same balance as before this change.
9. WHERE an account is a credit card the system SHALL apply the same floor to its balance.

**Independent Test**: Opening 1000 on 10/10; expense 200 on 05/10 → balance 1000; expense 200 on 15/10 → 800; credit 200 on 15/10 → 1200.

---

### P1: Net-worth notice for manual balance resets

**User Story**: As a user, I want the net-worth chart to tell me when a jump comes from a manually set balance so that I do not read it as real wealth change.

**Why P1**: Direct consequence of the floor rule; avoids the confusion reported in production.

**Acceptance Criteria**:

1. WHEN the net-worth report window contains an in-scope account's opening date and that account has non-ignored transactions dated before it THEN the report response SHALL list that account with its name and opening date.
2. WHEN the response lists at least one account THEN the net-worth page SHALL render a note below the chart naming each account and stating that the variation comes from a manually updated balance on the listed date.
3. IF no account meets the condition THEN the system SHALL return an empty list and SHALL NOT render the note.
4. WHERE a collection filter limits accounts the system SHALL consider only the filtered accounts.

**Independent Test**: Account with opening on 09/10 and a September transaction, window Sep–Oct → note names the account and 09/10.

---

### P1: Saved CSV import mappings

**User Story**: As a user, I want to save a CSV column mapping with a name and a target account so that the next import of the same layout needs no setup.

**Why P1**: Repeated every statement import.

**Acceptance Criteria**:

1. WHEN a CSV preview has a column mapping or split-column setup THEN the system SHALL offer "Save mapping" requiring a non-empty name (max 100 characters).
2. WHEN a mapping is saved THEN the system SHALL store, for the current user, the name, destination account, header set, field→column map, date format, flip-amount flag and inflow/outflow columns.
3. IF the name already exists for the user (case-insensitive) THEN the system SHALL reject the save with HTTP 409 and a message.
4. WHEN a CSV is uploaded and its header set exactly equals a saved mapping's header set THEN the system SHALL apply that mapping, preselect its destination account and show "Mapping applied: <name>".
5. WHEN several saved mappings match THEN the system SHALL apply the most recently used one and list the others for selection.
6. WHEN no saved mapping matches THEN the system SHALL apply nothing and SHALL let the user pick any saved mapping manually.
7. WHEN a saved mapping is applied THEN the system SHALL let the user adjust it, switch to another, or remove the applied mapping before importing.
8. WHEN a user lists, renames or deletes mappings THEN the system SHALL operate only on that user's mappings.
9. IF the destination account no longer exists THEN the system SHALL apply the mapping without preselecting an account.
10. WHERE the file is the Nubank layout `Data,Valor,Identificador,Descrição` the saved mapping SHALL map date=Data, amount=Valor, external id=Identificador, description=Descrição.

**Independent Test**: Save mapping for the Nubank sample, re-upload it: preview shows parsed rows and the badge with no manual selection.

---

### P2: Bulk ignore

**User Story**: As a user, I want to ignore or un-ignore many transactions at once.

**Why P2**: Convenience; single toggle already exists.

**Acceptance Criteria**:

1. WHEN the user chooses "Ignore" on a selection THEN the system SHALL set `is_ignored=true` on every selected transaction of the workspace.
2. WHEN the user chooses "Stop ignoring" THEN the system SHALL set `is_ignored=false` on every selected transaction of the workspace.
3. IF the request holds more than 100 IDs THEN the system SHALL reject it with HTTP 422 and change nothing.
4. IF an ID belongs to another workspace THEN the system SHALL leave it untouched and SHALL NOT count it.
5. WHEN the operation completes THEN the system SHALL return the number of rows whose state changed.
6. The bulk-ignore endpoint SHALL require write access to the workspace.

**Independent Test**: Select 3 mixed transactions, Ignore → all ignored, response `updated` = number that were not ignored.

---

### P2: Manual transfer pairing with preview

**User Story**: As a user, I want to run the transfer rule on demand and review the pairs first.

**Why P2**: Fixes history without waiting for a sync.

**Acceptance Criteria**:

1. WHEN the user opens the transfer rule's apply action THEN the system SHALL return the proposed pairs without writing any data.
2. Each proposed pair SHALL carry both legs' id, date, account, description and amount, and the matching strategy.
3. WHEN the user confirms a chosen set of proposed pairs THEN the system SHALL link only those pairs, atomically, and return the number linked.
4. IF a confirmed pair's leg was linked or deleted since the preview THEN the system SHALL skip that pair and report it as skipped.
5. WHEN the rule has every strategy disabled THEN the system SHALL return an empty proposal.
6. The apply endpoint SHALL require write access; the preview endpoint SHALL require read access.
7. WHEN the user applies pairs THEN the system SHALL NOT create suggestions as a side effect.

**Independent Test**: Two unpaired mirrored legs → preview lists one pair; apply links them.

---

### P2: Bulk "mark as transfer"

**User Story**: As a user, I want to select transactions and let the system pair them as transfers.

**Why P2**: Removes per-pair manual linking.

**Acceptance Criteria**:

1. WHEN the user chooses "Mark as transfer" on a selection THEN the system SHALL propose pairs among the selected transactions only, using the transfer rule's window and amount tolerance.
2. A proposed pair SHALL consist of two selected, unpaired transactions on different accounts, opposite types, with matching amount per the rule and dates within the rule window.
3. IF a selected transaction has more than one valid counterpart THEN the system SHALL NOT pair it and SHALL report it as ambiguous.
4. IF a selected transaction has no counterpart in the selection THEN the system SHALL report it as unmatched.
5. IF a selected transaction already belongs to a transfer pair THEN the system SHALL report it as already linked and leave it untouched.
6. WHEN the user confirms THEN the system SHALL link the proposed pairs atomically and return the linked count.
7. IF the selection holds more than 100 IDs THEN the system SHALL reject it with HTTP 422.
8. The confirm endpoint SHALL require write access.

**Independent Test**: Select a debit and a credit of the same amount on two accounts plus one stray row → 1 pair, 1 unmatched.

---

## Edge Cases

- IF an account has two `opening_balance` rows THEN the system SHALL use the latest date as D.
- WHEN the opening balance transaction is deleted THEN the system SHALL fall back to summing all counted transactions.
- IF a mapping name is blank or over 100 characters THEN the system SHALL reject it with HTTP 422.
- IF the uploaded file has no header row THEN the system SHALL apply no saved mapping.
- IF bulk ignore receives an empty list THEN the system SHALL return `updated` = 0.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| ACC-01 | P1: New-account dialog opens clean | Phase 1 | Done |
| BAL-01 | P1: Opening balance is a floor | Phase 1 | In progress |
| BAL-02 | P1: Opening balance is a floor | Phase 1 | In progress |
| BAL-03 | P1: Opening balance is a floor | Phase 1 | In progress |
| NWN-01 | P1: Net-worth notice | T8-T11 | Done |
| IMP-01 | P1: Saved CSV import mappings | T12-T19 | Done |
| IGN-01 | P2: Bulk ignore | T20-T24 | Done |
| TRF-01 | P2: Manual transfer pairing | T25-T31 | Done |
| BTR-01 | P2: Bulk mark as transfer | T25-T32 | Done |

**Mapping:** ACC-01 = story 1 ACs 1-4; BAL-01 = ACs 1-5, 8-9 (core rule); BAL-02 = AC 6 (all balance read sites); BAL-03 = AC 7 (cutoff semantics); NWN-01 = notice ACs 1-4; IMP-01 = mapping ACs 1-10; IGN-01 = ignore ACs 1-6; TRF-01 = pairing ACs 1-7; BTR-01 = bulk transfer ACs 1-8.

**Coverage:** 9 total, 0 mapped to tasks, 9 unmapped ⚠️ (until tasks are approved)

---

## Success Criteria

- [ ] Opening 1000 on 10/10 with an earlier 200 expense shows 1000; a later 200 expense shows 800.
- [ ] Reopening the add-account dialog never shows previous values.
- [ ] A saved Nubank mapping applies with zero clicks on the second import.
- [ ] Bulk operations act on 100 transactions in one request.
