# Selfhost.3 Adjustments Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/selfhost-3-adjustments/design.md`
**Status**: Draft

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec - confirm before Execute. Guidelines found: `CONTRIBUTING.md` (backend `pytest`, `ruff check .`, `ty`; frontend `npm run lint && npm test`, Vitest + Testing Library via `renderWithProviders` from `@/test/utils`), `backend/pyproject.toml` (pytest asyncio auto, coverage config), `frontend/package.json` scripts.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Backend service / SQL filter (balance, pairing, mapping, bulk) | unit (DB-backed pytest) | All branches; 1:1 to spec ACs; every listed edge case | `backend/tests/test_*.py` | `cd backend && uv run pytest tests/<file> -q` |
| Backend route (FastAPI) | integration (API pytest) | Every route in scope: happy + edge + error (409, 422, 404, permission) | `backend/tests/test_*_api.py` | `cd backend && uv run pytest tests/<file> -q` |
| Backend model / schema / migration | none | - (build gate; migration applied by test DB setup) | - | build gate only |
| Frontend page / component | unit (Vitest + Testing Library) | Each spec AC visible in the UI: happy + error + empty states | `frontend/src/**/*.test.tsx` | `cd frontend && npx vitest run <file>` |
| Docs, frontend api client / types / i18n | none | - (typecheck + i18n parity test) | - | build gate only |

## Gate Check Commands

> Generated from codebase - confirm before Execute.

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After a backend task with unit tests | `cd backend && uv run pytest tests/<task test file> -q` |
| Quick-FE | After a frontend task with unit tests | `cd frontend && npx vitest run <task test file>` |
| Full | After route tasks and tasks touching shared balance/pairing code | `cd backend && uv run pytest -q && uv run ruff check .` |
| Build | After each phase, and for none-layer tasks | Backend: `cd backend && uv run pytest -q && uv run ruff check . && uv run ty check`; Frontend: `cd frontend && npm run typecheck && npm run lint && npm test` |

---

## Execution Plan

Phases run sequentially. Each phase is shippable on its own; Phases 1-2 are the minimum for the release.

### Phase 1: Account fixes (B1, B2)

```
T1 → T2 → T3 → T4 → T5 → T6 → T7
```

### Phase 2: Net-worth notice

```
T8 → T9 → T10 → T11
```

### Phase 3: Saved import mappings (F1)

```
T12 → T13 → T14 → T15 → T16 → T17 → T18 → T19
```

### Phase 4: Bulk ignore (F3)

```
T20 → T21 → T22 → T23 → T24
```

### Phase 5: Transfer pairing (F2, F4)

```
T25 → T26 → T27 → T28 → T29 → T30 → T31 → T32 → T33
```

---

## Task Breakdown

### T1: Reset AccountDialog on every open

**What**: Make create mode reinitialize all fields each time the dialog opens, replacing the `formSource` comparison.
**Where**: `frontend/src/pages/accounts.tsx`
**Depends on**: None
**Reuses**: `form-reset` pattern in `frontend/src/components/form-reset.test.tsx`
**Requirement**: ACC-01

**Tools**:

- MCP: NONE
- Skill: `react-best-practices`

**Done when**:

- [x] Create mode shows defaults after fill→close→reopen and after save→reopen (spec ACC AC 1-3)
- [x] Edit mode still loads the selected account (AC 4)
- [x] New test `frontend/src/pages/accounts-dialog.test.tsx` covers the four ACs
- [x] Gate passes: `cd frontend && npx vitest run src/pages/accounts-dialog.test.tsx`
- [x] Test count: 4 tests pass (no silent deletions)

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `fix(accounts): reset the add-account dialog on every open`

---

### T2: Add the opening-balance floor predicate

**What**: Add `within_opening_floor(cutoff)` to the shared filters.
**Where**: `backend/app/services/_query_filters.py`
**Depends on**: T1
**Reuses**: `is_not_future`, `counts_in_current_balance` style
**Requirement**: BAL-01, BAL-03

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Rows dated before the opening date are excluded when cutoff ≥ opening date; same-day rows included
- [x] Rows dated up to cutoff all included when cutoff < opening date
- [x] Accounts without an opening row are unaffected; with two opening rows the latest date wins
- [x] New test `backend/tests/test_opening_floor.py` covers each case
- [x] Gate passes: `cd backend && uv run pytest tests/test_opening_floor.py -q`
- [x] Test count: 7 tests pass (SPEC_DEVIATION: estimate was 6; the touch-after-import case was added)

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(accounts): add the opening balance floor query filter`

---

### T3: Apply the floor to the accounts list

**What**: Add the floor to `balance_sq` and `prev_balance_sq` in `get_accounts`.
**Where**: `backend/app/services/account_service.py`
**Depends on**: T2
**Reuses**: `within_opening_floor`
**Requirement**: BAL-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Opening 1000 on 10/10 + expense 200 on 05/10 → current balance 1000
- [x] Expense 200 on 15/10 → 800; credit 200 on 15/10 → 1200; same-day expense counts
- [x] Credit-card account follows the same rule
- [x] Connected account fixture returns the same balance as before the change
- [x] Tests added to `backend/tests/test_account_service.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_account_service.py tests/test_accounts_api.py -q`
- [x] Test count: existing + 6 new pass

**Tests**: unit
**Gate**: Quick
**Commit**: `fix(accounts): count only transactions from the opening date in the accounts list balance`

---

### T4: Apply the floor to the account summary

**What**: Add the floor to the manual-account branch of `get_account_summary`.
**Where**: `backend/app/services/account_service.py`
**Depends on**: T3
**Reuses**: `within_opening_floor`
**Requirement**: BAL-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Summary `current_balance` equals the list balance for the same fixture
- [x] Connected accounts still return the provider balance
- [x] Tests added to `backend/tests/test_accounts_api.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_accounts_api.py -q`
- [x] Test count: existing + 3 new pass

**Tests**: integration
**Gate**: Full
**Commit**: `fix(accounts): apply the opening floor to the account summary balance`

---

### T5: Apply the floor to account balance history

**What**: Make `_account_balance_at` and the daily series cutoff-aware.
**Where**: `backend/app/services/account_service.py`
**Depends on**: T4
**Reuses**: `within_opening_floor(cutoff)`
**Requirement**: BAL-02, BAL-03

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] A date before the opening date includes earlier transactions (spec BAL AC 7)
- [x] A date on/after it excludes pre-opening transactions
- [x] The last point of the series equals the account's current balance
- [x] Tests added to `backend/tests/test_account_service.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_account_service.py -q`
- [x] Test count: existing + 4 new pass

**Tests**: unit
**Gate**: Quick
**Commit**: `fix(accounts): apply the opening floor to account balance history`

---

### T6: Apply the floor to dashboard, goal and report snapshots

**What**: Make dashboard `_account_balance_at` honor the floor for manual accounts; connected branch unchanged.
**Where**: `backend/app/services/dashboard_service.py`
**Depends on**: T5
**Reuses**: `within_opening_floor(cutoff)`
**Requirement**: BAL-02, BAL-03

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Snapshot at today excludes pre-opening transactions; snapshot before the opening date includes them
- [x] Connected accounts unchanged at past and current cutoffs
- [x] Dashboard total equals sum of list balances in a mixed fixture
- [x] Tests added to `backend/tests/test_dashboard_service.py`
- [x] Gate passes: `cd backend && uv run pytest -q && uv run ruff check .`
- [x] Test count: full suite passes with 5 new tests

**Tests**: unit
**Gate**: Full
**Commit**: `fix(dashboard): apply the opening floor to account balance snapshots`

---

### T7: Stop name-only edits from moving the opening date

**What**: Send `balance` and `balance_date` from the edit form only when the user changed them.
**Where**: `frontend/src/pages/accounts.tsx`
**Depends on**: T6
**Reuses**: `AccountDialog` submit handler (`accounts.tsx:~735`)
**Requirement**: BAL-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Editing only the name submits a payload without `balance` or `balance_date`
- [x] Changing the balance or date submits both
- [x] Test added to `frontend/src/pages/accounts-dialog.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/pages/accounts-dialog.test.tsx`
- [x] Test count: T1 tests + 3 new pass

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `fix(accounts): keep the opening balance date when only other fields change`

---

### T8: Add the balance-reset schema

**What**: Add `BalanceReset` and `balance_resets` to the report meta schema.
**Where**: `backend/app/schemas/report.py`
**Depends on**: None (phase order)
**Reuses**: `ReportMeta`
**Requirement**: NWN-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `BalanceReset{account_id, account_name, date}` defined; `ReportMeta.balance_resets` defaults to `[]`
- [x] Gate passes: `cd backend && uv run pytest -q && uv run ruff check . && uv run ty check`

**Tests**: none
**Gate**: Build
**Commit**: `feat(reports): add the balance reset field to the report meta`

---

### T9: Detect balance resets in the net-worth report

**What**: Compute accounts whose opening date lies in the window and which have earlier non-ignored transactions; set `meta.balance_resets`.
**Where**: `backend/app/services/report_service.py`
**Depends on**: T8
**Reuses**: `_get_open_accounts`, collection `account_ids` filter
**Requirement**: NWN-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Account with opening 09/10 and a September transaction, window Sep–Oct → listed with date 09/10
- [x] Account with no earlier transactions, or opening outside the window, or only ignored earlier transactions → not listed
- [x] Collection filter limits the list to filtered accounts
- [x] Result is computed with one grouped query (asserted via query-count or single helper call)
- [x] Tests added to `backend/tests/test_report_service.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_report_service.py -q`
- [x] Test count: existing + 6 new pass (SPEC_DEVIATION: estimate was 5; added a leg-requested-twice case)

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(reports): report accounts whose balance was reset inside the net-worth window`

---

### T10: Add the net-worth notice strings and types

**What**: Add `reports.balanceResetNote` keys to all locales and `balance_resets` to the frontend report type.
**Where**: `frontend/src/locales/`
**Depends on**: T9
**Reuses**: `frontend/src/locales/i18n.test.ts` parity checks
**Requirement**: NWN-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Key present with interpolation (`{{account}}`, `{{date}}`) in all 15 locale files, with pt-BR as source text
- [x] `balance_resets` added to the report meta type in `frontend/src/types`
- [x] Gate passes: `cd frontend && npm run typecheck && npx vitest run src/locales`

**Tests**: none
**Gate**: Build
**Commit**: `feat(reports): add balance reset note strings and type`

---

### T11: Render the notice below the net-worth chart

**What**: Show a note listing each reset account and its date under the net-worth chart; hide it when the list is empty.
**Where**: `frontend/src/pages/reports.tsx`
**Depends on**: T10
**Reuses**: `reports.test.tsx` fixtures
**Requirement**: NWN-01

**Tools**:

- MCP: NONE
- Skill: `frontend-design`

**Done when**:

- [x] Note renders with account name and formatted date when `balance_resets` has entries (AC 2)
- [x] No note when the list is empty (AC 3)
- [x] Tests added to `frontend/src/pages/reports.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/pages/reports.test.tsx && npm run lint`
- [x] Test count: existing + 2 new pass

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(reports): explain manual balance updates below the net-worth chart`

---

### T12: Create the ImportMapping model

**What**: Add the `ImportMapping` SQLAlchemy model and register it in `models/__init__`.
**Where**: `backend/app/models/import_mapping.py`
**Depends on**: None (phase order)
**Reuses**: `models/rule.py` conventions
**Requirement**: IMP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Fields as in design (name, name_key, account_id, headers, headers_key, column_mapping, options, last_used_at)
- [x] Unique constraint (user_id, name_key); index (user_id, headers_key)
- [x] Gate passes: `cd backend && uv run pytest -q && uv run ruff check . && uv run ty check`

**Tests**: none
**Gate**: Build
**Commit**: `feat(import): add the import mapping model`

---

### T13: Add migration 097 for import_mappings

**What**: Alembic revision `097` (down `096`) creating the table, FKs (user CASCADE, account SET NULL) and indexes.
**Where**: `backend/alembic/versions/097_import_mappings.py`
**Depends on**: T12
**Reuses**: `096_reconciliation_user_fks_set_null.py` style
**Requirement**: IMP-01

**Tools**:

- MCP: NONE
- Skill: `supabase-postgres-best-practices`

**Done when**:

- [x] `alembic upgrade head` and `downgrade -1` run cleanly on a scratch database
- [x] Gate passes: `cd backend && uv run pytest -q`

**Tests**: none
**Gate**: Build
**Commit**: `feat(import): add the import_mappings migration`

---

### T14: Add the mapping schemas

**What**: Pydantic schemas for create, update, read and match.
**Where**: `backend/app/schemas/import_mapping.py`
**Depends on**: T13
**Reuses**: `schemas/rule.py` style
**Requirement**: IMP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `name` 1..100 stripped; `headers` non-empty list; `column_mapping` dict[str, str]
- [x] Gate passes: `cd backend && uv run ruff check . && uv run ty check`

**Tests**: none
**Gate**: Build
**Commit**: `feat(import): add import mapping schemas`

---

### T15: Implement the mapping service

**What**: CRUD, case-insensitive name uniqueness, header-set hashing, `match(headers)` ordered by `last_used_at`, `touch`.
**Where**: `backend/app/services/import_mapping_service.py`
**Depends on**: T14
**Reuses**: `rule_service` CRUD pattern
**Requirement**: IMP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Duplicate name (any case) raises a conflict error (AC 3); blank/101-char name rejected
- [x] Match is order-insensitive and trim-aware, exact on the set (AC 4); no match returns empty (AC 6)
- [x] Several matches ordered most recently used first (AC 5)
- [x] Operations scoped to the user; other users' mappings invisible (AC 8)
- [x] Deleted account → `account_id` null on read (AC 9)
- [x] Nubank sample headers round-trip (AC 10)
- [x] New test `backend/tests/test_import_mapping_service.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_import_mapping_service.py -q`
- [x] Test count: 14 tests pass (SPEC_DEVIATION: estimate was 9; parametrized name test and per-user/touch/rename/delete cases added)

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(import): add the import mapping service`

---

### T16: Expose the import-mappings API

**What**: Router with list, create, patch, delete, `match` and `touch`; register in `main.py`.
**Where**: `backend/app/api/import_mappings.py`
**Depends on**: T15
**Reuses**: `api/rules.py` dependencies (`current_user`)
**Requirement**: IMP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Happy path, 409 duplicate, 422 invalid name, 404 other user's id, unauthenticated 401
- [x] New test `backend/tests/test_import_mappings_api.py`
- [x] Gate passes: `cd backend && uv run pytest -q && uv run ruff check .`
- [x] Test count: 11 new tests pass (SPEC_DEVIATION: estimate was 8; parametrized name test, match, patch, touch, delete cases)

**Tests**: integration
**Gate**: Full
**Commit**: `feat(import): expose the import mappings API`

---

### T17: Add the mapping API client and types

**What**: Client functions and `ImportMapping` type.
**Where**: `frontend/src/lib/api.ts`
**Depends on**: T16
**Reuses**: existing `transactions` client style
**Requirement**: IMP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `importMappings.list/create/update/remove/match/touch` typed
- [x] Gate passes: `cd frontend && npm run typecheck`

**Tests**: none
**Gate**: Build
**Commit**: `feat(import): add the import mappings client`

---

### T18: Add mapping strings

**What**: i18n keys for save, applied badge, switch, remove, errors, in all locales.
**Where**: `frontend/src/locales/`
**Depends on**: T17
**Reuses**: i18n parity test
**Requirement**: IMP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Keys in all 15 locales; parity test passes
- [x] Gate passes: `cd frontend && npx vitest run src/locales && npm run typecheck`

**Tests**: none
**Gate**: Build
**Commit**: `feat(import): add import mapping strings`

---

### T19: Mapping bar in the import page

**What**: After preview, match headers; apply the match (columns, options, account); show badge with switch/remove; add "Save mapping" with name and current account; touch on successful import.
**Where**: `frontend/src/pages/import.tsx`
**Depends on**: T18
**Reuses**: `csvColumnMapping` state, `handleMappingChange`, `rePreview`
**Requirement**: IMP-01

**Tools**:

- MCP: NONE
- Skill: `frontend-design`

**Done when**:

- [x] Matching file auto-applies and preselects the account, badge reads "Mapping applied: <name>" (AC 4)
- [x] Non-matching file applies nothing and offers saved mappings (AC 6)
- [x] Switch and remove controls work (AC 7); save with duplicate name shows the 409 message (AC 3)
- [x] Tests in new `frontend/src/pages/import-mapping.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/pages/import-mapping.test.tsx && npm run lint && npm run typecheck`
- [x] Test count: 7 tests pass (SPEC_DEVIATION: estimate was 6; the touch-after-import case was added)

**Tests**: unit
**Gate**: Build
**Commit**: `feat(import): save and reapply CSV column mappings`

---

### T20: Add the bulk-ignore request schema

**What**: `BulkIgnoreRequest{transaction_ids (max 100), ignored: bool}`.
**Where**: `backend/app/schemas/transaction.py`
**Depends on**: None (phase order)
**Reuses**: `BulkCategorizeRequest`
**Requirement**: IGN-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `max_length=100` on the list
- [x] Gate passes: `cd backend && uv run ruff check . && uv run ty check`

**Tests**: none
**Gate**: Build
**Commit**: `feat(transactions): add the bulk ignore request schema`

---

### T21: Implement bulk_set_ignored

**What**: Service function setting the explicit state within the workspace and returning the changed count.
**Where**: `backend/app/services/transaction_service.py`
**Depends on**: T20
**Reuses**: `bulk_update_category`
**Requirement**: IGN-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Ignore and un-ignore set the explicit state; count excludes rows already in target state (AC 1, 2, 5)
- [x] Other-workspace IDs untouched and uncounted (AC 4); empty list returns 0
- [x] Pair legs are not cascaded
- [x] New test `backend/tests/test_transactions_bulk_ignore.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_transactions_bulk_ignore.py -q`
- [x] Test count: 6 tests pass

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(transactions): add bulk ignore to the transaction service`

---

### T22: Expose PATCH /transactions/bulk-ignore

**What**: Endpoint under `current_writable_workspace`.
**Where**: `backend/app/api/transactions.py`
**Depends on**: T21
**Reuses**: `bulk_categorize` route
**Requirement**: IGN-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] 200 with `{updated}`; 422 over 100 IDs with no change (AC 3); read-only member rejected (AC 6)
- [x] Route declared before `/{transaction_id}` routes
- [x] Tests added to `backend/tests/test_transactions_bulk_ignore.py`
- [x] Gate passes: `cd backend && uv run pytest -q && uv run ruff check .`
- [x] Test count: existing + 6 new pass (SPEC_DEVIATION: estimate was 5; added a leg-requested-twice case) (SPEC_DEVIATION: estimate was 3; added the exactly-100 boundary and the other-workspace case)

**Tests**: integration
**Gate**: Full
**Commit**: `feat(transactions): expose the bulk ignore endpoint`

---

### T23: Add the bulk-ignore client and strings

**What**: `transactions.bulkIgnore(ids, ignored)` and i18n keys.
**Where**: `frontend/src/lib/api.ts`
**Depends on**: T22
**Reuses**: `bulkCategorize` client
**Requirement**: IGN-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Client typed; locale keys added to all files in the same commit
- [x] Gate passes: `cd frontend && npm run typecheck && npx vitest run src/locales`

**Tests**: none
**Gate**: Build
**Commit**: `feat(transactions): add bulk ignore client and strings`

---

### T24: Bulk ignore actions in the transactions page

**What**: "Ignore" and "Stop ignoring" in the selection bar, with a hint and disabled state above 100 selected.
**Where**: `frontend/src/pages/transactions.tsx`
**Depends on**: T23
**Reuses**: `bulkCategorizeMutation`, `MobileBulkSelectionActions`
**Requirement**: IGN-01

**Tools**:

- MCP: NONE
- Skill: `frontend-design`

**Done when**:

- [x] Both actions call the client with the right state and refresh the list; success toast shows the count
- [x] Actions disabled with hint when more than 100 are selected
- [x] Tests in new `frontend/src/pages/transactions-bulk-ignore.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/pages/transactions-bulk-ignore.test.tsx && npm run lint && npm run typecheck`
- [x] Test count: 4 tests pass

**Tests**: unit
**Gate**: Build
**Commit**: `feat(transactions): ignore many transactions at once`

---

### T25: Extract propose_pairs from detect_transfer_pairs

**What**: Move the pool/neighbour/evaluate/mutual-link decision phase into a non-writing `propose_pairs`; `detect_transfer_pairs` calls it and then writes pairs and suggestions with unchanged behavior.
**Where**: `backend/app/services/transfer_detection_service.py`
**Depends on**: None (phase order)
**Reuses**: existing code moved, not rewritten
**Requirement**: TRF-01, BTR-01

**Tools**:

- MCP: NONE
- Skill: `tactical-ddd`

**Done when**:

- [x] All existing tests pass unchanged: `test_transfer_detection.py`, `test_transfer_matching_rules.py`, `test_transfer_api.py`
- [x] `propose_pairs(restrict_ids=None)` returns mutual `linked` pairs only and writes nothing (TRF AC 1, 2, 5)
- [x] `restrict_ids` limits both legs to the set and reports ambiguous, unmatched and already-linked ids (BTR AC 2-5)
- [x] New tests added to `backend/tests/test_transfer_detection.py`
- [x] Gate passes: `cd backend && uv run pytest -q && uv run ruff check . && uv run ty check`
- [x] Test count: existing + 8 new pass

**Tests**: unit
**Gate**: Full
**Commit**: `refactor(transfers): split pair proposal from linking`

---

### T26: Add apply_pairs

**What**: Revalidate each requested `(a, b)` against current state and link atomically; return `linked` and `skipped`.
**Where**: `backend/app/services/transfer_detection_service.py`
**Depends on**: T25
**Reuses**: `propose_pairs` validation
**Requirement**: TRF-01, BTR-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Valid pairs link and return the count (TRF AC 3, BTR AC 6)
- [x] A leg linked or deleted since preview is skipped and reported (TRF AC 4)
- [x] No suggestions recorded as a side effect (TRF AC 7)
- [x] A forged pair that the rule would not propose is rejected
- [x] Tests added to `backend/tests/test_transfer_detection.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_transfer_detection.py -q`
- [x] Test count: existing + 6 new pass (SPEC_DEVIATION: estimate was 5; added a leg-requested-twice case)

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(transfers): link confirmed pairs after revalidation`

---

### T27: Expose transfer preview and apply endpoints

**What**: `GET /connections/transfers/preview` (read) and `POST /connections/transfers/apply` (write).
**Where**: `backend/app/api/connections.py`
**Depends on**: T26
**Reuses**: `/transfers/detect` route and `current_writable_workspace`
**Requirement**: TRF-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Preview returns pairs with both legs' id, date, account, description, amount and strategy, and writes nothing
- [x] Apply links only the posted pairs; read-only member gets 403 on apply and 200 on preview
- [x] Tests added to `backend/tests/test_transfer_api.py`
- [x] Gate passes: `cd backend && uv run pytest -q && uv run ruff check .`
- [x] Test count: existing + 6 new pass

**Tests**: integration
**Gate**: Full
**Commit**: `feat(transfers): preview and apply the transfer rule on demand`

---

### T28: Expose bulk-transfer preview and confirm endpoints

**What**: `POST /transactions/bulk-transfer/preview` and `POST /transactions/bulk-transfer`, 100-ID cap.
**Where**: `backend/app/api/transactions.py`
**Depends on**: T27
**Reuses**: `propose_pairs(restrict_ids)`, `apply_pairs`
**Requirement**: BTR-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Preview lists pairs plus ambiguous, unmatched and already-linked ids (AC 1-5)
- [x] Confirm links the posted pairs (AC 6); 422 over 100 IDs (AC 7); read-only member rejected (AC 8)
- [x] Tests in new `backend/tests/test_transactions_bulk_transfer.py`
- [x] Gate passes: `cd backend && uv run pytest -q && uv run ruff check .`
- [x] Test count: 10 new tests pass (SPEC_DEVIATION: the 11 in the draft was a stale estimate; 10 cover BTR AC 1-8, the 50-pair cap, the 100-id boundary and workspace scoping)

**Tests**: integration
**Gate**: Full
**Commit**: `feat(transactions): pair selected transactions as transfers`

---

### T29: Add transfer clients, types and strings

**What**: Client functions for the four endpoints, types, and i18n keys.
**Where**: `frontend/src/lib/api.ts`
**Depends on**: T28
**Reuses**: `linkTransfer` client style
**Requirement**: TRF-01, BTR-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Typed clients for preview/apply (rule) and preview/confirm (bulk); locale keys in all files
- [x] Gate passes: `cd frontend && npm run typecheck && npx vitest run src/locales`

**Tests**: none
**Gate**: Build
**Commit**: `feat(transfers): add transfer preview clients and strings`

---

### T30: Shared pair preview table

**What**: Reusable table showing proposed pairs with per-pair checkboxes, totals and an empty state.
**Where**: `frontend/src/components/transfer-pair-preview.tsx`
**Depends on**: T29
**Reuses**: `link-transfer-dialog.tsx` presentation
**Requirement**: TRF-01, BTR-01

**Tools**:

- MCP: NONE
- Skill: `frontend-design`

**Done when**:

- [x] Renders both legs, strategy, selected count; unchecking removes a pair from the confirm set
- [x] Empty state renders
- [x] New test `frontend/src/components/transfer-pair-preview.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/components/transfer-pair-preview.test.tsx`
- [x] Test count: 4 tests pass

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(transfers): add the proposed pairs preview table`

---

### T31: Apply-now action in the transfer rule

**What**: "Apply now" in the transfer rule card opening a dialog with the preview and a confirm button.
**Where**: `frontend/src/components/reconciliation-rules.tsx`
**Depends on**: T30
**Reuses**: `TRANSFER_NODE` section, `TransferPairPreview`
**Requirement**: TRF-01

**Tools**:

- MCP: NONE
- Skill: `frontend-design`

**Done when**:

- [x] Opening the dialog loads the preview and writes nothing
- [x] Confirm sends only the checked pairs and toasts "N linked, M skipped"
- [x] Empty proposal shows the empty state
- [x] Tests added to the existing reconciliation-rules test file, or new `reconciliation-rules-apply.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/components/reconciliation-rules-apply.test.tsx && npm run lint`
- [x] Test count: 4 tests pass

**Tests**: unit
**Gate**: Build
**Commit**: `feat(rules): apply the transfer rule on demand with a preview`

---

### T32: Mark-as-transfer action in the selection bar

**What**: "Mark as transfer" in the bulk bar opening the preview dialog with pairs, ambiguous and unmatched lists; confirm links the checked pairs; disabled above 100 selected.
**Where**: `frontend/src/pages/transactions.tsx`
**Depends on**: T31
**Reuses**: `TransferPairPreview`, bulk mutations pattern
**Requirement**: BTR-01

**Tools**:

- MCP: NONE
- Skill: `frontend-design`

**Done when**:

- [ ] Preview shows pairs and the unmatched/ambiguous/already-linked groups
- [ ] Confirm refreshes the list and toasts the linked count
- [ ] Action disabled with hint above 100 selected
- [ ] Tests in new `frontend/src/pages/transactions-bulk-transfer.test.tsx`
- [ ] Gate passes: `cd frontend && npx vitest run src/pages/transactions-bulk-transfer.test.tsx && npm run lint && npm run typecheck`
- [ ] Test count: 5 tests pass

**Tests**: unit
**Gate**: Build
**Commit**: `feat(transactions): mark many transactions as transfers`

---

### T33: Release docs for selfhost.3

**What**: Document the balance rule change and new features in the deploy/release notes for `0.16.3-selfhost.3`.
**Where**: `docs/deploy/` (release notes file)
**Depends on**: T32
**Reuses**: fork release flow doc from commit `9a1ddff`
**Requirement**: BAL-01

**Tools**:

- MCP: NONE
- Skill: `docs-writer`

**Done when**:

- [ ] Notes explain that balances now ignore transactions dated before the opening balance, with the 1000/05-10/15-10 example
- [ ] Full gates pass: backend `pytest -q && ruff check . && ty check`; frontend `typecheck && lint && test`

**Tests**: none
**Gate**: Build
**Commit**: `docs(deploy): add 0.16.3-selfhost.3 release notes`

---

## Phase Execution Map

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5

Phase 1:  T1 → T2 → T3 → T4 → T5 → T6 → T7
Phase 2:  T8 → T9 → T10 → T11
Phase 3:  T12 → T13 → T14 → T15 → T16 → T17 → T18 → T19
Phase 4:  T20 → T21 → T22 → T23 → T24
Phase 5:  T25 → T26 → T27 → T28 → T29 → T30 → T31 → T32 → T33
```

Execution is strictly sequential. 33 tasks pack into ~5 batches by phase; sub-agent delegation is offered at Execute.
