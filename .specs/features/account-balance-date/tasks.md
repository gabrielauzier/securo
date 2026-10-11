# Account Balance Date Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/account-balance-date/design.md`
**Status**: Draft

---

## Test Coverage Matrix

> Same as `.specs/features/selfhost-3-adjustments/tasks.md`. Guidelines found: `CONTRIBUTING.md`, `backend/pyproject.toml`, `frontend/package.json`. `uv` is not installed here: use `backend/.venv/bin/python -m pytest`, `.venv/bin/ruff`, `.venv/bin/ty`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Backend service / SQL filter | unit (DB-backed pytest) | All branches; 1:1 to spec ACs; every listed edge case | `backend/tests/test_*.py` | `cd backend && .venv/bin/python -m pytest tests/<file> -q` |
| Backend route | integration | Happy + edge + error (422) | `backend/tests/test_*_api.py` | same |
| Backend model / schema / migration | none (migration checked on a scratch Postgres) | build gate | - | build gate only |
| Frontend page / component | unit (Vitest + Testing Library) | Each spec AC visible in the UI | `frontend/src/**/*.test.tsx` | `cd frontend && npx vitest run <file>` |
| Frontend types / i18n / docs | none | typecheck + i18n parity test | - | build gate only |

## Gate Check Commands

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | Backend task with unit tests | `cd backend && .venv/bin/python -m pytest tests/<task test file> -q` |
| Quick-FE | Frontend task with unit tests | `cd frontend && npx vitest run <file>` |
| Full | Route tasks and tasks touching shared balance code | `cd backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check .` |
| Build | Phase end and none-layer tasks | Backend: `.venv/bin/python -m pytest -q && .venv/bin/ruff check . && .venv/bin/ty check`; Frontend: `npm run typecheck && npm run lint && npx vitest run` |

---

## Execution Plan

### Phase 1: Stored date and write path

```
T1 → T2 → T3 → T4 → T5
```

### Phase 2: Read path

```
T6 → T7
```

### Phase 3: Interface and docs

```
T8 → T9 → T10
```

---

## Task Breakdown

### T1: Add `balance_date` to the Account model

**What**: Add the nullable `balance_date` column to the model.
**Where**: `backend/app/models/account.py`
**Depends on**: None
**Reuses**: neighbouring `Mapped[Optional[...]]` columns
**Requirement**: ABD-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `balance_date: Mapped[Optional[date]]` (Date, nullable) defined
- [x] Gate passes: Build (backend)

**Tests**: none
**Gate**: Build
**Commit**: `feat(accounts): add the balance date column to the account model`

---

### T2: Migration 098 with backfill

**What**: Alembic revision `098` (down `097`) adding the column and backfilling manual accounts from their latest opening-balance transaction; downgrade drops it.
**Where**: `backend/alembic/versions/098_account_balance_date.py`
**Depends on**: T1
**Reuses**: `097_import_mappings.py` style
**Requirement**: ABD-03

**Tools**:

- MCP: NONE
- Skill: `supabase-postgres-best-practices`

**Done when**:

- [x] Upgrade backfills manual accounts and leaves connected ones and accounts with no opening transaction NULL
- [x] Downgrade drops the column
- [x] Verified on a scratch Postgres (pgvector image) stamped at 097: upgrade, downgrade, upgrade, with accounts seeded before the upgrade; balances compared before and after (scratch container removed afterwards)
- [x] Gate passes: Build (backend)

**Tests**: none
**Gate**: Build
**Commit**: `feat(accounts): add the balance date migration with backfill`

---

### T3: Expose `balance_date` in the account read schema

**What**: Add `balance_date: Optional[date]` to the read model and the serializer.
**Where**: `backend/app/schemas/account.py`
**Depends on**: T2
**Reuses**: `serialize_account` in `account_service.py`
**Requirement**: ABD-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `AccountRead` includes `balance_date`; list and detail responses return it (serializer updated in the same commit)
- [x] Existing account API tests still pass
- [x] Gate passes: Full

**Tests**: integration
**Gate**: Full
**Commit**: `feat(accounts): return the balance date in the account response`

---

### T4: Persist the date on account creation

**What**: Store `balance_date` on create (default today), create the opening transaction only for non-zero balances, ignore the date for connected accounts.
**Where**: `backend/app/services/account_service.py`
**Depends on**: T3
**Reuses**: `create_account`
**Requirement**: ABD-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Create with date D stores D (spec ABD-01 AC1); without a date stores today (AC2)
- [x] Balance 0 with a date stores it and creates no opening transaction (AC3)
- [x] Opening transaction date equals `account.balance_date` for non-zero balances
- [x] Tests in `backend/tests/test_account_service.py` and `test_accounts_api.py` (including 422 on an invalid date)
- [x] Gate passes: `cd backend && .venv/bin/python -m pytest tests/test_account_service.py tests/test_accounts_api.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(accounts): save the balance date when creating an account`

---

### T5: Persist and propagate the date on account update

**What**: On update store the date, keep the opening transaction in step, keep the date when the balance becomes 0, leave it untouched when neither `balance` nor `balance_date` is sent.
**Where**: `backend/app/services/account_service.py`
**Depends on**: T4
**Reuses**: `update_account` balance branch
**Requirement**: ABD-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Date-only update sets `balance_date` and the existing opening transaction date (AC4), including when no opening transaction exists (date stored, no transaction created)
- [x] Non-zero balance without a date keeps the stored date (AC5)
- [x] Balance 0 deletes the opening transaction and keeps the date (AC6)
- [x] Update without `balance`/`balance_date` leaves the date unchanged (AC7)
- [x] Connected account ignores `balance_date` (AC9)
- [x] Account and opening transaction dates equal after every write
- [x] Tests in `backend/tests/test_account_service.py` and `test_accounts_api.py`
- [x] Gate passes: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check .`

**Tests**: integration
**Gate**: Full
**Commit**: `feat(accounts): save the balance date when updating an account`

---

### T6: Read the floor from the account's saved date

**What**: Change `within_opening_floor` to read `Account.balance_date` through a scalar subquery on `accounts`; keep signature and semantics; update fixtures that created opening rows directly to also set `balance_date`.
**Where**: `backend/app/services/_query_filters.py`
**Depends on**: None (phase order)
**Reuses**: the 10 existing call sites (account_service x5, dashboard_service x2 via the helper)
**Requirement**: ABD-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Floor applies for cutoff ≥ `balance_date`, full history for cutoff < `balance_date`, no floor when NULL (spec ABD-02 AC1-3)
- [x] Floor applies with `balance_date` set and no opening transaction (AC4); changing the date changes the next read (AC5)
- [x] Connected accounts unchanged (AC6)
- [x] Every existing floor test still asserts the same expected values (only fixtures changed); any test whose expected outcome must change is reported, not edited
- [x] Tests extended in `backend/tests/test_opening_floor.py` and the per-site tests in `test_account_service.py`, `test_accounts_api.py`, `test_dashboard_service.py`
- [x] Gate passes: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check .`

**Tests**: unit
**Gate**: Full
**Commit**: `refactor(accounts): read the balance floor from the account's saved date`

---

### T7: Base the net-worth notice on the saved date

**What**: `_find_balance_resets` uses `Account.balance_date` instead of the latest opening transaction date.
**Where**: `backend/app/services/report_service.py`
**Depends on**: T6
**Reuses**: current grouped query
**Requirement**: ABD-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Account with `balance_date` in the window and earlier non-ignored transactions is listed with that date (AC7)
- [x] Account with `balance_date` but no opening transaction is listed too
- [x] Connected and NULL-date accounts are not listed; window bounds `(start, end]` kept
- [x] Existing notice tests keep their expected values (fixtures set `balance_date`)
- [x] Tests in `backend/tests/test_report_service.py`
- [x] Gate passes: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/ruff check . && .venv/bin/ty check`

**Tests**: unit
**Gate**: Build
**Commit**: `refactor(reports): base the balance reset notice on the saved date`

---

### T8: Show the saved date and the hint in the account dialog

**What**: Add `balance_date` to the `Account` type; initialize the field from the account in edit mode; add the hint under the field.
**Where**: `frontend/src/pages/accounts.tsx`
**Depends on**: None (phase order)
**Reuses**: `AccountDialog` reset logic and `accounts-dialog.test.tsx`
**Requirement**: ABD-04

**Tools**:

- MCP: NONE
- Skill: `react-best-practices`

**Done when**:

- [x] Edit shows the saved date (ABD-04 AC1); no saved date or create shows today (AC2, AC3)
- [x] Hint renders under the field (AC4)
- [x] Name-only edit still sends no `balance` or `balance_date` (AC5)
- [x] `Account.balance_date: string | null` added in `frontend/src/types/index.ts` in the same commit
- [x] Existing dialog tests pass unchanged; new tests in `frontend/src/pages/accounts-dialog.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/pages/accounts-dialog.test.tsx && npm run typecheck && npm run lint`

**Tests**: unit
**Gate**: Build
**Commit**: `feat(accounts): show the saved balance date when editing an account`

---

### T9: Hint strings in all locales

**What**: Add `accounts.balanceDateHint` to all 15 locale files.
**Where**: `frontend/src/locales/`
**Depends on**: T8
**Reuses**: `frontend/src/locales/i18n.test.ts` parity checks
**Requirement**: ABD-04

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Key present in all 15 files (pt-BR source: "Transações anteriores a esta data não alteram o saldo.")
- [x] Gate passes: `cd frontend && npx vitest run src/locales && npm run typecheck`

**Tests**: none
**Gate**: Build
**Commit**: `feat(accounts): add the balance date hint strings`

---

### T10: Release notes and decision log

**What**: Add the change to the release notes and record AD-002 in STATE.md.
**Where**: `deploy/public/RELEASE-NOTES.md`
**Depends on**: T9
**Reuses**: the existing 0.16.3-selfhost.3 section
**Requirement**: ABD-03

**Tools**:

- MCP: NONE
- Skill: `docs-writer`

**Done when**:

- [x] Notes explain: the date is saved on the account, balances do not change after upgrade, migration `098`, the hint in the dialog
- [x] `.specs/STATE.md` has AD-002 (supersedes the storage part of AD-001; AD-001 status `superseded by AD-002` only for storage, keep the rule text)
- [x] Full Build gates pass (backend and frontend)

**Tests**: none
**Gate**: Build
**Commit**: `docs(deploy): document the saved balance date in the release notes`

---

## Phase Execution Map

```
Phase 1 → Phase 2 → Phase 3

Phase 1:  T1 → T2 → T3 → T4 → T5
Phase 2:  T6 → T7
Phase 3:  T8 → T9 → T10
```

10 tasks in 3 phases: packed as 2 batches (Phase 1 = 5 tasks; Phases 2+3 = 5 tasks).

---

## Verification Fixes

Findings from `validation.md` (iteration 1).

### F1: Zero-balance create must not add a floor (CRITICAL gap 1)

**What**: Per the owner decision, create stores a date only when the request carries one or the balance is non-zero; otherwise `balance_date` stays NULL. Spec updated first.
**Where**: `spec.md`, `backend/app/services/account_service.py`, `backend/tests/test_account_service.py`, `backend/tests/test_accounts_api.py`
**Requirement**: ABD-01 AC2/AC3/AC10, ABD-02 AC8

**Done when**:

- [x] spec.md updated (ABD-01 AC2/AC3/AC10, ABD-02 AC8, assumptions, edge case) and validate_spec exits 0
- [x] Balance-0 create without a date leaves `balance_date` NULL; explicit date with balance 0 stores it; non-zero without a date stores today
- [x] API regression: balance-0 account, 1000 credit 30 days ago + 10 debit today gives balance 990
- [x] Gate passes: backend pytest, ruff, ty

**Commit**: `fix(accounts): leave the balance date empty on a zero-balance create`

### F2: Create dialog sends a date only when it matters (CRITICAL gap 1, frontend)

**What**: The create payload carries `balance_date` only when the user changed the date or the balance is non-zero.
**Where**: `frontend/src/pages/accounts.tsx`, `frontend/src/pages/accounts-dialog.test.tsx`
**Requirement**: ABD-04 AC7

**Done when**:

- [x] Balance 0 with an untouched date sends no `balance_date`; a changed date or a non-zero balance sends the date shown
- [x] Edit-mode payload rules unchanged
- [x] Gate passes: `cd frontend && npx vitest run src/pages/accounts-dialog.test.tsx && npm run typecheck && npm run lint`

**Commit**: `fix(accounts): send the balance date on create only when it matters`

### F3: Automated test for the migration 098 backfill (WARNING 2)

**What**: Run the real `upgrade()`/`downgrade()` of migration 098 against sqlite with seeded accounts.
**Where**: `backend/tests/test_account_balance_date_migration.py`
**Requirement**: ABD-03 AC1-AC3

**Done when**:

- [x] Latest opening date wins; one opening row; no opening row stays NULL; connected stays NULL; downgrade drops the column
- [x] Mutants killed (max to min, dropped connection filter, dropped source filter)
- [x] Gate passes: `pytest tests/test_account_balance_date_migration.py`, ruff, ty

**Commit**: `test(accounts): cover the balance date backfill migration`

### F4: Edge-case and connected-guard coverage (WARNING 3, SUGGESTION 4)

**What**: Pin that a bank-connected account with a stored `balance_date` is not listed as a balance reset. The reworded sequential-write edge case is covered by `test_sequential_writes_keep_account_and_opening_dates_equal`, added with F1.
**Where**: `backend/tests/test_report_service.py`
**Requirement**: ABD-01 AC9, ABD-02 AC6/AC7

**Done when**:

- [x] A connected account with a non-NULL `balance_date` is not listed by `_find_balance_resets` (mutant dropping the `connection_id` guard is killed)
- [x] Sequential writes keep account and opening dates equal after each write
- [x] Gate passes: backend pytest, ruff, ty

**Commit**: `test(reports): keep connected accounts out of the balance reset notice`
