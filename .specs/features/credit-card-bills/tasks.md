# Credit Card Bills Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/credit-card-bills/design.md`
**Status**: Approved (2026-10-12) · In Progress

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec - confirm before Execute. Guidelines found: `CONTRIBUTING.md` (backend `pytest`, `ruff check .`, `ty`; frontend `npm run lint && npm test`, Vitest + Testing Library via `renderWithProviders` from `@/test/utils`), `backend/pyproject.toml` (pytest asyncio auto), `backend/tests/conftest.py` (SQLite in-memory; `postgres_sessions` fixture for PostgreSQL-only checks), `frontend/package.json` scripts, `frontend/src/locales/i18n.test.ts` (locale key parity).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Backend pure domain (business days, period math, status) | unit | All branches; 1:1 to spec ACs; every listed edge case and every 2026-2028 holiday | `backend/tests/test_*.py` | `cd backend && uv run pytest tests/<file> -q` |
| Backend service / SQL filter (bills, payments, matching, settlement) | unit (DB-backed pytest) | All branches; 1:1 to spec ACs; every listed edge case | `backend/tests/test_*.py` | `cd backend && uv run pytest tests/<file> -q` |
| Backend data migration | unit (migration test) | Backfill result on fixture data; idempotency; frozen math equals live math 2024-2028 | `backend/tests/test_*_migration.py` | `cd backend && uv run pytest tests/<file> -q` |
| Backend route (FastAPI) | integration (API pytest) | Every route in scope: happy + edge + error (404, 409, 422, viewer 403) | `backend/tests/test_*_api.py` | `cd backend && uv run pytest tests/<file> -q` |
| Backend model / schema-only migration | none | - (build gate; tables created by test DB setup) | - | build gate only |
| Frontend page / component | unit (Vitest + Testing Library) | Each spec AC visible in the UI: happy + error + empty states | `frontend/src/**/*.test.tsx` | `cd frontend && npx vitest run <file>` |
| Frontend api client / types, docs | none | - (typecheck; i18n parity test) | - | build gate only |

## Gate Check Commands

> Approved 2026-10-12. Local toolchain: `uv` is not on PATH here; run backend commands with the main checkout venv `/Volumes/MacOnlySSD/dev/personal/securo/backend/.venv/bin/` (`python -m pytest`, `ruff`, `ty`), which resolves this worktree's `app` package.

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After a backend task with unit tests | `cd backend && uv run pytest tests/<task test file> -q` |
| Quick-FE | After a frontend task with unit tests | `cd frontend && npx vitest run <task test file>` |
| Full | After route tasks and tasks touching shared filters or write paths | `cd backend && uv run pytest -q && uv run ruff check .` |
| Build | After each phase, and for none-layer tasks | Backend: `cd backend && uv run pytest -q && uv run ruff check . && uv run ty check`; Frontend: `cd frontend && npm run typecheck && npm run lint && npm test` |

---

## Execution Plan

Phases run sequentially. Phases 1-4 deliver the P1 stories (bills, import linking, payments) and are releasable on their own.

### Phase 1: Domain foundation

```
T1 → T2 → T3 → T4 → T5
```

### Phase 2: Write paths and backfill

```
T6 → T7 → T8 → T9 → T10 → T11 → T12
```

### Phase 3: Bills API

```
T13 → T14 → T15
```

### Phase 4: Bill payments

```
T16 → T17 → T18 → T19 → T20 → T21
```

### Phase 5: Payment matching

```
T22 → T23 → T24 → T25 → T26 → T27 → T28 → T52
```

### Phase 6: Settlement mode (backend)

```
T29 → T30 → T31 → T32 → T33 → T34 → T35 → T36 → T37
```

### Phase 7: Frontend foundations

```
T53 → T38 → T39 → T40 → T41 → T54
```

### Phase 8: Frontend payments

```
T42 → T43 → T44 → T45
```

### Phase 9: Frontend bills and consolidated page

```
T46 → T47 → T48 → T49 → T50 → T51
```

### Phase 10: Verification fixes (round 1)

```
T55 → T56 → T57 → T58 → T59 → T60
```

### Phase 11: Round 2 fixes and backend adjustments

```
T61 → T62 → T63 → T64 → T65 → T66
```

### Phase 12: Remaining refresh paths and frontend adjustments

```
T73 → T74 → T67 → T68 → T69 → T70 → T71 → T72
```

---

## Task Breakdown

### T1: Brazilian business-day calendar

**What**: Add `easter_sunday`, `br_national_holidays`, `is_business_day` and `next_business_day`.
**Where**: `backend/app/core/business_days.py`
**Depends on**: None
**Reuses**: none (standard library)
**Requirement**: BDAY-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Every holiday listed in the spec Assumptions is returned for 2026, 2027 and 2028, with Easter on 2026-04-05, 2027-03-28, 2028-04-16
- [x] `next_business_day(2026-09-12) == 2026-09-14` (Saturday) and `next_business_day(2026-09-07) == 2026-09-08` (holiday)
- [x] A business day returns itself
- [x] New test `backend/tests/test_business_days.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_business_days.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): add the brazilian business-day calendar`

---

### T2: Bill period math

**What**: Add `BillPeriod`, `bill_period_for` and `bill_period_for_month`.
**Where**: `backend/app/services/credit_card_service.py`
**Depends on**: T1
**Reuses**: `_clamp_day`, rules of `compute_effective_date`
**Requirement**: BILL-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Spec P1 AC 2, 3, 4 and the close-day-equals-due-day edge case pass with the exact dates
- [x] A purchase on the close day belongs to the next period (BIMP AC 3)
- [x] `bill_period_for(d).nominal_due_date == compute_effective_date(d)` for every day of 2026 with close 5/due 12 and close 28/due 5
- [x] New test `backend/tests/test_bill_period.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_bill_period.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): compute the full bill period for a date`

---

### T3: Bill schema migration and models

**What**: Migration `099` and model changes from the design Data Models (bill columns, partial unique index, `transactions.paid_bill_id`, `transactions.bill_payment_pair`, `categories.is_bill_payment`, `bill_payment_dismissals`); existing bills get `source='provider'`, period columns from cycle math and `declared_total = total_amount`.
**Where**: `backend/alembic/versions/099_credit_card_bills_v2.py` (models in `backend/app/models/`)
**Depends on**: T2
**Reuses**: `098_account_balance_date.py` style
**Requirement**: BILL-01

**Tools**:

- MCP: NONE
- Skill: `supabase-postgres-best-practices`

**Done when**:

- [x] `alembic upgrade head` and `downgrade -1` run on PostgreSQL
- [x] `backend/scripts/check_migration_chain.py` passes
- [x] Partial index declared with `postgresql_where` and `sqlite_where`
- [x] Gate passes: Build (backend)

**Tests**: none
**Gate**: Build
**Commit**: `feat(bills): extend the bill schema for every card`

---

### T4: Bill aggregates and status

**What**: Add `get_or_create_bill`, `refresh_bills`, `bill_status` and `bill_amounts` per the design aggregate rules.
**Where**: `backend/app/services/bill_service.py`
**Depends on**: T3
**Reuses**: `account_service.get_account`
**Requirement**: BILL-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] P1 AC 1, 5, 6 pass; every status of the precedence table has a test, including zero-target bill (`open` before close, `paid` after)
- [x] Computed total excludes opening balance, ignored rows, `is_bill_payment`/`is_ignored` categories and the card leg of a payment pair
- [x] `settled_on` is the date of the payment that reaches target; NULL below target; `close_date` when target ≤ 0
- [x] Concurrent `get_or_create_bill` keeps one bill (PostgreSQL test with `postgres_sessions`)
- [x] New test `backend/tests/test_bill_service.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_bill_service.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): store bill aggregates and derive status`

---

### T5: Link card transactions to bills

**What**: Add `link_account_transactions`, `relink_account` and `touch`.
**Where**: `backend/app/services/bill_service.py`
**Depends on**: T4
**Reuses**: `bill_period_for`, `refresh_bills`
**Requirement**: BILL-01, BILL-03, BIMP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BIMP AC 1, 2, 3, 4, 8 pass at service level; card without close/due day returns `LinkSummary(0, 0)` (P1 AC 13)
- [x] Rows linked to a provider bill are not moved; no auto bill is created for a month covered by a provider bill
- [x] `relink_account` moves rows of bills without payments and leaves bills with payments unchanged (P1 AC 12)
- [x] `touch` refreshes both `bill_id` and `paid_bill_id` bills
- [x] New test `backend/tests/test_bill_linking.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_bill_linking.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): link card transactions to their bill`

---

### T6: Backfill bills on upgrade

**What**: Data migration `100` with frozen period/holiday math: creates `auto` bills for configured cards, links unlinked rows, fills aggregates.
**Where**: `backend/alembic/versions/100_credit_card_bills_backfill.py`
**Depends on**: None (phase order)
**Reuses**: `backend/tests/test_account_balance_date_migration.py` pattern
**Requirement**: BILL-04

**Tools**:

- MCP: NONE
- Skill: `supabase-postgres-best-practices`

**Done when**:

- [x] P1 Independent Test scenario passes through the migration function
- [x] Running the backfill twice yields the same bills and links (P1 AC 14)
- [x] Provider bills and their links unchanged (P1 AC 15)
- [x] Frozen math equals live `bill_period_for` for every day 2024-2028 (two cycle configs)
- [x] New test `backend/tests/test_credit_card_bills_backfill_migration.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_credit_card_bills_backfill_migration.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): backfill bills for existing card transactions`

---

### T7: rebuild-bills CLI

**What**: Add `python -m app.cli rebuild-bills [--workspace <id>]` that runs `link_account_transactions` and `refresh_bills` for every card.
**Where**: `backend/app/cli.py`
**Depends on**: T6
**Reuses**: `generate_recurring` command shape
**Requirement**: BILL-04

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Corrupted aggregates (test sets wrong `paid_amount`) are corrected; prints counts
- [x] New test `backend/tests/test_cli_rebuild_bills.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_cli_rebuild_bills.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): add the rebuild-bills repair command`

---

### T8: Link bills on import

**What**: Call `link_account_transactions` after card imports and add `bills_linked` / `bills_created` to the import result.
**Where**: `backend/app/services/import_service.py`
**Depends on**: T7
**Reuses**: `import_transactions` result
**Requirement**: BIMP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BIMP Independent Test passes (3 linked, bills 2026-09/10/11)
- [x] Re-importing the same CSV creates no bill (BIMP AC 7)
- [x] New test `backend/tests/test_import_bills.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `feat(bills): link imported card transactions to bills`

---

### T9: Bill hooks in transaction CRUD

**What**: Call `link_account_transactions` / `touch` from `create_transaction`, `update_transaction`, `create_transfer`, `create_transfer_counterpart`, `toggle_ignore_transaction`, `bulk_set_ignored`, `bulk_update_category`, `delete_transaction` and `bulk_delete_transactions`; replace `_resync_bill_link_from_override` for non-provider bills.
**Where**: `backend/app/services/transaction_service.py`
**Depends on**: T8
**Reuses**: existing service functions
**Requirement**: BIMP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] One test per listed function asserting bill links and aggregates after the call (AD-004)
- [x] BIMP AC 4 (override) and AC 5 (date/account change relinks) pass
- [x] Deleting a linked payment recomputes the bill (edge case)
- [x] New test `backend/tests/test_transaction_bill_hooks.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `feat(bills): keep bills current on transaction changes`

---

### T10: Bill hook in recurring generation

**What**: Link generated card rows to bills.
**Where**: `backend/app/services/recurring_transaction_service.py`
**Depends on**: T9
**Reuses**: `link_account_transactions`
**Requirement**: BIMP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] A recurring charge generated on a card lands on its bill
- [x] New test `backend/tests/test_recurring_bills.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_recurring_bills.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): link recurring card charges to bills`

---

### T11: Bill hook in provider sync

**What**: After sync, run `link_account_transactions` for card accounts and fill new columns on provider bills.
**Where**: `backend/app/services/connection_service.py`
**Depends on**: T10
**Reuses**: `_sync_credit_card_bills`
**Requirement**: BIMP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Provider bills get `source='provider'`, period and effective due date; existing tests in `backend/tests/test_providers_pluggy_bills.py` stay green
- [x] Synced rows without a provider bill join an auto bill
- [x] New test `backend/tests/test_sync_bills.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `feat(bills): link synced card transactions to bills`

---

### T12: Relink on cycle change

**What**: Call `relink_account` when `statement_close_day` or `payment_due_day` changes, and reject incompatible close/due day combinations.
**Where**: `backend/app/services/account_service.py`
**Depends on**: T11
**Reuses**: `_recompute_effective_dates` trigger point
**Requirement**: BILL-03

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] P1 AC 12 passes through `update_account`
- [x] Create and update reject close/due day combinations that map two consecutive closes to the same reference month (checked over 48 months including a leap year) with HTTP 422 `incompatible_cycle_days`; 5/12, 28/5 and 10/10 accepted (spec edge case, owner decision 2026-10-12)
- [x] New test `backend/tests/test_account_cycle_relink.py`
- [x] Gate passes: Build (backend)

**Tests**: unit
**Gate**: Build
**Commit**: `feat(bills): relink bills when the card cycle changes`

---

### T13: Bills read API

**What**: New router with `GET /credit-card-bills` (filters `reference_month`, `account_id`) and `GET /credit-card-bills/{id}`; extend `CreditCardBillRead` (new fields, status, amounts, payments) also used by `GET /accounts/{id}/bills`.
**Where**: `backend/app/api/credit_card_bills.py`
**Depends on**: None (phase order)
**Reuses**: `backend/app/api/accounts.py` router conventions
**Requirement**: BILL-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Filters return the right bills; other workspace → 404; viewer can read
- [x] `GET /accounts/{id}/bills` returns the new fields without breaking existing tests
- [x] New test `backend/tests/test_credit_card_bills_api.py`
- [x] Gate passes: Full

**Tests**: integration
**Gate**: Full
**Commit**: `feat(bills): expose bills with status and amounts`

---

### T14: Manual bill management service

**What**: Add `create_manual_bill`, `update_bill`, `delete_bill`.
**Where**: `backend/app/services/bill_service.py`
**Depends on**: T13
**Reuses**: `link_account_transactions`, `refresh_bills`
**Requirement**: BILL-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] P1 AC 7, 9, 11 pass; AC 8 raises a conflict; AC 10 raises on provider dates; negative declared total rejected
- [x] New test `backend/tests/test_bill_manual.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_bill_manual.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): create, edit and delete bills manually`

---

### T15: Manual bill API

**What**: `POST`, `PATCH`, `DELETE /credit-card-bills` endpoints, write-gated.
**Where**: `backend/app/api/credit_card_bills.py`
**Depends on**: T14
**Reuses**: T13 router
**Requirement**: BILL-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] 201/409/422/404/204 paths and viewer 403 covered; `test_write_permission_coverage` passes
- [x] Tests added to `backend/tests/test_credit_card_bills_api.py`
- [x] Gate passes: Build (backend)

**Tests**: integration
**Gate**: Build
**Commit**: `feat(bills): add the manual bill endpoints`

---

### T16: Exclude bill payments from P/L

**What**: `counts_as_pnl` excludes rows with `paid_bill_id` and rows in `is_bill_payment` categories.
**Where**: `backend/app/services/_query_filters.py`
**Depends on**: None (phase order)
**Reuses**: `counts_as_pnl`
**Requirement**: BPAY-01, BPAY-03

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BPAY AC 2 and AC 13 pass for dashboard totals, category spending, reports and budgets in `cash` and `accrual`
- [x] New test `backend/tests/test_bill_payment_pnl.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `feat(bills): leave bill payments out of income and expenses`

---

### T17: Bill-payment category flag

**What**: `is_bill_payment` in category schemas and `update_category`; refresh workspace bills when it or `is_ignored` changes.
**Where**: `backend/app/services/category_service.py`
**Depends on**: T16
**Reuses**: `treat_as_transfer` handling
**Requirement**: BPAY-03

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Flag readable/writable through `/categories`; toggling it refreshes bill totals
- [x] New test `backend/tests/test_category_bill_payment.py`
- [x] Gate passes: Full

**Tests**: integration
**Gate**: Full
**Commit**: `feat(categories): flag categories as bill payments`

---

### T18: Link and unlink payments

**What**: `validate_payment`, `link_payment`, `unlink_payment` (without pairing).
**Where**: `backend/app/services/bill_payment_service.py`
**Depends on**: T17
**Reuses**: `refresh_bills`
**Requirement**: BPAY-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BPAY AC 1, 5, 6, 7, 8, 10, 11, 12 and the zero/negative and closed-card edge cases pass
- [x] New test `backend/tests/test_bill_payment_service.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_bill_payment_service.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): link payments to bills`

---

### T19: Pair the payment with the card credit

**What**: `find_card_credit`; `link_payment` pairs it and sets `bill_payment_pair`, else returns `needs_counterpart`; `unlink_payment` unpairs only marked pairs.
**Where**: `backend/app/services/bill_payment_service.py`
**Depends on**: T18
**Reuses**: `link_existing_as_transfer`, `unlink_transfer_pair`, `_widest_window`
**Requirement**: BPAY-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BPAY AC 3, 4, 9 pass; a pair made by the user before linking is not removed on unlink
- [x] Computed total ignores the paired card credit
- [x] New test `backend/tests/test_bill_payment_pairing.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_bill_payment_pairing.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): pair bill payments with the card credit`

---

### T20: Payment API

**What**: `POST /credit-card-bills/{id}/payments` and `DELETE /credit-card-bills/payments/{transaction_id}`.
**Where**: `backend/app/api/credit_card_bills.py`
**Depends on**: T19
**Reuses**: T13 router
**Requirement**: BPAY-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BPAY Independent Test passes through the API; 404/409/422 and viewer 403 covered
- [x] Tests added to `backend/tests/test_credit_card_bills_api.py`
- [x] Gate passes: Full

**Tests**: integration
**Gate**: Full
**Commit**: `feat(bills): add the bill payment endpoints`

---

### T21: Payment fields on transactions

**What**: Transactions list/detail return `paid_bill` (id, card name, reference month) and `needs_counterpart`.
**Where**: `backend/app/services/transaction_service.py`
**Depends on**: T20
**Reuses**: transaction serialization
**Requirement**: BPAY-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Linked payment exposes its bill; unlinked returns null
- [x] New test `backend/tests/test_transactions_bill_fields_api.py`
- [x] Gate passes: Build (backend)

**Tests**: integration
**Gate**: Build
**Commit**: `feat(bills): show the paid bill on transactions`

---

### T22: Payment candidates

**What**: `eligible_payments` and `candidates_for` with the window, amount rules and ranking.
**Where**: `backend/app/services/bill_match_service.py`
**Depends on**: None (phase order)
**Reuses**: bill period columns
**Requirement**: BMATCH-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BMATCH AC 3, 5, 12, 13, 15 pass
- [x] New test `backend/tests/test_bill_match_candidates.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_bill_match_candidates.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): find candidate bills for a payment`

---

### T23: Propose, auto-match and apply

**What**: `propose_matches`, `run_auto_match`, `apply_matches`.
**Where**: `backend/app/services/bill_match_service.py`
**Depends on**: T22
**Reuses**: `link_payment`
**Requirement**: BMATCH-01, BMATCH-03

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BMATCH AC 4, 6 (both ambiguity directions), 11 (per-pair failure) pass
- [x] New test `backend/tests/test_bill_match_apply.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_bill_match_apply.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): match payments to bills automatically`

---

### T24: Dismissed suggestions

**What**: `dismiss` and `has_suggestion`; proposals skip dismissed pairs.
**Where**: `backend/app/services/bill_match_service.py`
**Depends on**: T23
**Reuses**: `bill_payment_dismissals`
**Requirement**: BMATCH-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BMATCH AC 9 passes; `has_suggestion` true only for undismissed suggestion pairs
- [x] New test `backend/tests/test_bill_match_dismiss.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_bill_match_dismiss.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): remember dismissed payment suggestions`

---

### T25: Auto-match after import

**What**: Run `run_auto_match` after any import; add `payments_matched` to the import result.
**Where**: `backend/app/services/import_service.py`
**Depends on**: T24
**Reuses**: T8 hook
**Requirement**: BMATCH-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BMATCH Independent Test passes; card import that creates a bill matches an existing payment (AC 7)
- [x] New test `backend/tests/test_import_bill_match.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `feat(bills): match bill payments after import`

---

### T26: Auto-match after manual entry

**What**: Run `run_auto_match` after `create_transaction` and `update_transaction` on non-card debits.
**Where**: `backend/app/services/transaction_service.py`
**Depends on**: T25
**Reuses**: T9 hooks
**Requirement**: BMATCH-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Manually entered reference payment links automatically
- [x] Tests added to `backend/tests/test_transaction_bill_hooks.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `feat(bills): match bill payments on manual entry`

---

### T27: Auto-match after sync

**What**: Run `run_auto_match` at the end of a provider sync.
**Where**: `backend/app/services/connection_service.py`
**Depends on**: T26
**Reuses**: T11 hook
**Requirement**: BMATCH-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Synced checking payment links to its bill
- [x] Tests added to `backend/tests/test_sync_bills.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `feat(bills): match bill payments after sync`

---

### T28: Matching API and list indicator

**What**: `GET /payment-candidates`, `GET /payment-matches/preview`, `POST /payment-matches/apply`, `POST /payment-suggestions/dismiss`; transactions list returns `bill_payment_suggestion`.
**Where**: `backend/app/api/credit_card_bills.py`
**Depends on**: T27
**Reuses**: T13 router, `has_suggestion`
**Requirement**: BMATCH-02, BMATCH-03

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BMATCH AC 8, 10, 14 (API side) pass; preview writes nothing; write routes gated
- [x] Tests added to `backend/tests/test_credit_card_bills_api.py`
- [x] Gate passes: Build (backend)

**Tests**: integration
**Gate**: Build
**Commit**: `feat(bills): add the payment matching endpoints`

---

### T52: Refresh bills after automatic transfer pairing

**What**: `transfer_detection_service.apply_pairs` and the sync/import detection path call `bill_service.touch` for the paired rows, so a card credit paired automatically leaves the bill's computed total current (AD-004 gap found in B3).
**Where**: `backend/app/services/transfer_detection_service.py`
**Depends on**: T28
**Reuses**: `bill_service.touch`
**Requirement**: BPAY-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] A card credit paired by `apply_pairs` and by `detect_transfer_pairs` is excluded from the bill's computed total right after pairing
- [x] New test `backend/tests/test_transfer_pairing_bills.py`
- [x] Gate passes: Build (backend)

**Tests**: unit
**Gate**: Build
**Commit**: `fix(bills): refresh bills after automatic transfer pairing`

---

### T29: Accept the settlement mode

**What**: Admin setting whitelist accepts `settlement`; `get_credit_card_accounting_mode` returns it.
**Where**: `backend/app/api/admin.py`
**Depends on**: None (phase order)
**Reuses**: setting whitelist
**Requirement**: BREP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BREP AC 1 passes; invalid value → 422
- [x] Tests added to `backend/tests/test_credit_card_accounting_mode.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_credit_card_accounting_mode.py -q`

**Tests**: integration
**Gate**: Quick
**Commit**: `feat(bills): add the settlement accounting mode setting`

---

### T30: Settlement date filters

**What**: `reporting_date_col` settlement branch, `is_recognized`, `is_bill_projected`.
**Where**: `backend/app/services/_query_filters.py`
**Depends on**: T29
**Reuses**: `reporting_date_col`
**Requirement**: BREP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Expression returns payment date, effective due date, today for overdue, and purchase date without bill (BREP AC 2, 3, 4, 9)
- [x] `cash`/`accrual` expressions unchanged (regression test on compiled SQL)
- [x] New test `backend/tests/test_settlement_filters.py`
- [x] Gate passes: `cd backend && uv run pytest tests/test_settlement_filters.py -q`

**Tests**: unit
**Gate**: Quick
**Commit**: `feat(bills): bucket card purchases by bill payment date`

---

### T31: Settlement in dashboard realized totals

**What**: Monthly totals and category spending add `is_recognized(mode)`.
**Where**: `backend/app/services/dashboard_service.py`
**Depends on**: T30
**Reuses**: `reporting_date_col`
**Requirement**: BREP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BREP AC 5, 7, 8 pass
- [x] New test `backend/tests/test_dashboard_settlement.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `feat(bills): count paid bills in dashboard expenses`

---

### T32: Settlement projections

**What**: `_get_settlement_projections` feeding projected totals and category `projected`.
**Where**: `backend/app/services/dashboard_service.py`
**Depends on**: T31
**Reuses**: `_get_forecast_transactions` loops
**Requirement**: BREP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BREP AC 3, 4, 6 pass
- [x] Tests added to `backend/tests/test_dashboard_settlement.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `feat(bills): project unpaid bills as future expenses`

---

### T33: Open bills balance

**What**: "Faturas de cartão em aberto" uses remaining amounts of unpaid bills in `settlement`.
**Where**: `backend/app/services/dashboard_service.py`
**Depends on**: T32
**Reuses**: `bill_amounts`
**Requirement**: BREP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BREP AC 11 passes; other modes unchanged
- [x] Tests added to `backend/tests/test_dashboard_settlement.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `feat(bills): show remaining open bills on the dashboard`

---

### T34: Settlement in reports

**What**: Income/expenses and cash-flow reports apply `is_recognized` and settlement projections.
**Where**: `backend/app/services/report_service.py`
**Depends on**: T33
**Reuses**: T30 filters
**Requirement**: BREP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] AC 5 bill reports in September only, realized when paid and projected when not
- [x] New test `backend/tests/test_report_settlement.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `feat(bills): apply the settlement mode to reports`

---

### T35: Settlement in budgets

**What**: Budget actuals follow the active mode, including `settlement`.
**Where**: `backend/app/services/budget_service.py`
**Depends on**: T34
**Reuses**: T30 filters
**Requirement**: BREP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Budget actual for Mercado in September = 600.00 only after the bill is paid
- [x] New test `backend/tests/test_budget_settlement.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `feat(bills): apply the settlement mode to budgets`

---

### T36: Mode-aware split adjustments

**What**: `owner_split_offset_pnl` and `viewer_shared_pnl` bucket by `reporting_date_col(mode)` and `is_recognized`; callers pass the mode.
**Where**: `backend/app/services/_query_filters.py`
**Depends on**: T35
**Reuses**: T30 filters
**Requirement**: BREP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] A split card purchase offsets in the same month the purchase is recognized in each mode (BREP AC 10)
- [x] New test `backend/tests/test_split_offsets_mode.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `fix(dashboard): bucket split offsets by the accounting mode`

---

### T37: Reporting fields on transactions

**What**: List rows return `reporting_date` and `is_bill_projected`; the list period filter uses the settlement date in `settlement`.
**Where**: `backend/app/services/transaction_service.py`
**Depends on**: T36
**Reuses**: `reporting_date_col`
**Requirement**: BREP-01, BREP-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `user_pnl_only` list for September in `settlement` contains paid purchases with `reporting_date = 2026-09-14` and unpaid ones with `is_bill_projected = true`
- [x] `cash` list unchanged; bill view (`bill_id` filter) unchanged
- [x] New test `backend/tests/test_transactions_reporting_fields_api.py`
- [x] Gate passes: Build (backend)

**Tests**: integration
**Gate**: Build
**Commit**: `feat(bills): return the reporting date on transactions`

---

### T53: Exclude bill payments from forecast rows

**What**: `dashboard_service._counts_as_user_pnl_row` matches `counts_as_user_pnl`: it also drops rows with `paid_bill_id` and rows in `is_bill_payment` categories, so a pending "Pagamento de fatura" never adds to projected expenses (gap found in B5).
**Where**: `backend/app/services/dashboard_service.py`
**Depends on**: None (phase order)
**Reuses**: `counts_as_user_pnl`
**Requirement**: BPAY-03

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] A pending debit in an `is_bill_payment` category does not change projected expenses (BPAY AC 13), in every mode
- [x] New test `backend/tests/test_forecast_bill_payment.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `fix(bills): leave bill payments out of projected expenses`

---

### T38: Frontend types and API client

**What**: Types for bills, payments, candidates, proposals, new transaction and category fields; `creditCardBills` API client.
**Where**: `frontend/src/lib/api.ts` (types in `frontend/src/types/index.ts`)
**Depends on**: T53
**Reuses**: `accounts.bills` client
**Requirement**: BILL-01, BPAY-01, BMATCH-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Typecheck passes
- [x] Gate passes: Build (frontend)

**Tests**: none
**Gate**: Build
**Commit**: `feat(bills): add the bills api client`

---

### T39: Admin mode selector

**What**: Third radio option "Na liquidação da fatura" with description for each mode.
**Where**: `frontend/src/pages/admin/settings.tsx`
**Depends on**: T38
**Reuses**: existing radio block
**Requirement**: BREP-01

**Tools**:

- MCP: NONE
- Skill: `react-best-practices`

**Done when**:

- [x] BREP AC 16: selecting `settlement` saves it; current value shown; keys in every locale
- [x] New test `frontend/src/pages/admin/settings-accounting-mode.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/pages/admin/settings-accounting-mode.test.tsx`

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(bills): add the settlement mode to admin settings`

---

### T40: Bill-payment toggle on categories

**What**: Toggle "Pagamento de fatura" on the category form.
**Where**: `frontend/src/pages/categories.tsx`
**Depends on**: T39
**Reuses**: `treat_as_transfer` toggle
**Requirement**: BPAY-03

**Tools**:

- MCP: NONE
- Skill: `react-best-practices`

**Done when**:

- [x] Toggle saves `is_bill_payment`; keys in every locale
- [x] New test `frontend/src/pages/categories-bill-payment.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/pages/categories-bill-payment.test.tsx`

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(categories): toggle the bill payment flag`

---

### T41: Drill-down reporting date layout

**What**: Main date = `reporting_date`, extra line "Lançada em <date> · <card>" in `accrual`/`settlement`, projected badge for `is_bill_projected`, sort by main date.
**Where**: `frontend/src/components/transaction-drill-down.tsx`
**Depends on**: T40
**Reuses**: `ProjectedTransactionBadge`
**Requirement**: BREP-02

**Tools**:

- MCP: NONE
- Skill: `react-best-practices`

**Done when**:

- [x] BREP AC 12-15 pass, including the PRD Google example (12/11 main, "Lançada em 11/10/2026 · Cartão de Crédito Nubank")
- [x] Tests added to `frontend/src/components/transaction-drill-down.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/components/transaction-drill-down.test.tsx`

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(dashboard): show the recognition date of card purchases`

---

### T54: Open bills value on the dashboard

**What**: In `settlement`, the dashboard "Faturas de cartão em aberto" shows `open_bills_remaining_primary` from the summary instead of summing card balances; other modes unchanged.
**Where**: `frontend/src/pages/dashboard.tsx`
**Depends on**: T41
**Reuses**: existing `creditCardBalance` block
**Requirement**: BREP-01

**Tools**:

- MCP: NONE
- Skill: `react-best-practices`

**Done when**:

- [x] BREP AC 11 visible: settlement shows the API value; cash/accrual keep the card-balance sum; hidden when 0
- [x] Tests added to `frontend/src/pages/dashboard.test.tsx`
- [x] Gate passes: Build (frontend)

**Tests**: unit
**Gate**: Build
**Commit**: `feat(dashboard): show remaining open bills in settlement mode`

---

### T42: Bill status badge

**What**: Badge with color and text for each status, plus effective-due tooltip "Vencimento original <date> (<weekday>)".
**Where**: `frontend/src/components/credit-card/bill-status-badge.tsx`
**Depends on**: None (phase order)
**Reuses**: badge components
**Requirement**: BILL-01

**Tools**:

- MCP: NONE
- Skill: `accessibility`

**Done when**:

- [x] Five statuses render distinct text; tooltip only when effective ≠ nominal
- [x] New test `frontend/src/components/credit-card/bill-status-badge.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/components/credit-card/bill-status-badge.test.tsx`

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(bills): add the bill status badge`

---

### T43: Link-bill dialog

**What**: "Vincular a fatura" dialog: candidates first with reason, other unpaid bills, confirm, `needs_counterpart` follow-up.
**Where**: `frontend/src/components/link-bill-dialog.tsx`
**Depends on**: T42
**Reuses**: `LinkTransferDialog`
**Requirement**: BMATCH-02, BPAY-01

**Tools**:

- MCP: NONE
- Skill: `accessibility`

**Done when**:

- [x] BMATCH AC 8 rendering, confirm calls the link endpoint, 409/422 messages shown, counterpart action offered when flagged
- [x] New test `frontend/src/components/link-bill-dialog.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/components/link-bill-dialog.test.tsx`

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(bills): add the link to bill dialog`

---

### T44: Transactions page wiring

**What**: Action bar button "Vincular a fatura" (one eligible debit selected), row indicator "Possível pagamento de fatura" with confirm/dismiss, "Pagamento da fatura <card> <month>" label with unlink.
**Where**: `frontend/src/pages/transactions.tsx`
**Depends on**: T43
**Reuses**: `BulkIconButton`, mobile action menu
**Requirement**: BMATCH-02, BPAY-01

**Tools**:

- MCP: NONE
- Skill: `react-best-practices`

**Done when**:

- [x] BMATCH AC 14 and the unlink flow pass; button disabled for credits and card rows
- [x] New test `frontend/src/pages/transactions-bill-payment.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/pages/transactions-bill-payment.test.tsx`

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(bills): link bill payments from the transactions list`

---

### T45: Bulk match preview dialog

**What**: "Aplicar match de pagamentos" dialog with a checkbox per proposal; entry in the transactions page actions menu.
**Where**: `frontend/src/components/bill-match-apply-dialog.tsx`
**Depends on**: T44
**Reuses**: `TransferApplyDialog`
**Requirement**: BMATCH-03

**Tools**:

- MCP: NONE
- Skill: `accessibility`

**Done when**:

- [x] BMATCH AC 10, 11 pass in the UI; empty state shown
- [x] New test `frontend/src/components/bill-match-apply-dialog.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/components/bill-match-apply-dialog.test.tsx`

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(bills): preview and apply payment matches in bulk`

---

### T46: Bill details on account detail

**What**: Account detail bill header shows status badge, effective due date, computed vs declared total and payments; edit declared total; create manual bill.
**Where**: `frontend/src/pages/account-detail.tsx`
**Depends on**: None (phase order)
**Reuses**: existing bill navigation
**Requirement**: BILL-02

**Tools**:

- MCP: NONE
- Skill: `react-best-practices`

**Done when**:

- [x] P1 AC 7, 9 flows work in the UI; provider bills hide date edit; existing `account-detail-cycle.test.tsx` green
- [x] New test `frontend/src/pages/account-detail-bills.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/pages/account-detail-bills.test.tsx src/pages/account-detail-cycle.test.tsx`

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(bills): manage bills from the card account page`

---

### T47: Move a transaction to another bill

**What**: Transaction dialog lists the card's bills for the override instead of a free date.
**Where**: `frontend/src/components/transaction-dialog.tsx`
**Depends on**: T46
**Reuses**: `effective_bill_date` field
**Requirement**: BILL-02

**Tools**:

- MCP: NONE
- Skill: `react-best-practices`

**Done when**:

- [x] Picking a bill saves its due date as override; option to clear
- [x] Tests added to `frontend/src/components/transaction-dialog.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/components/transaction-dialog.test.tsx`

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(bills): move a card transaction to another bill`

---

### T48: Bill summary card

**What**: Summary card (targets, paid, remaining, next effective due, limit, available with shared-limit rule) extracted for reuse.
**Where**: `frontend/src/components/credit-card/bill-summary-card.tsx`
**Depends on**: T47
**Reuses**: account detail summary rendering
**Requirement**: BVIEW-01

**Tools**:

- MCP: NONE
- Skill: `react-composition-patterns`

**Done when**:

- [x] BVIEW AC 5 figures, shared limit counted once
- [x] New test `frontend/src/components/credit-card/bill-summary-card.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/components/credit-card/bill-summary-card.test.tsx`

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(bills): add the bill summary card`

---

### T49: Consolidated credit card page

**What**: `/accounts/credit-cards` page with card selector (`?account=`), reference-month navigation, summary, bills list and transactions list.
**Where**: `frontend/src/pages/credit-cards.tsx`
**Depends on**: T48
**Reuses**: `bill-summary-card`, `bill-status-badge`, month stepper
**Requirement**: BVIEW-01

**Tools**:

- MCP: NONE
- Skill: `frontend-design`

**Done when**:

- [x] BVIEW AC 2-10 pass; keys in every locale
- [x] New test `frontend/src/pages/credit-cards.test.tsx`
- [x] Gate passes: `cd frontend && npx vitest run src/pages/credit-cards.test.tsx`

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(bills): add the consolidated credit card page`

---

### T50: Route and navigation

**What**: Route `/accounts/credit-cards` (static, before `/accounts/:id`), sub-item under Accounts in `nav-items`, command palette entry.
**Where**: `frontend/src/lib/nav-items.ts` (route in `frontend/src/App.tsx`, palette in `frontend/src/components/command-palette.tsx`)
**Depends on**: T49
**Reuses**: `nav-accounts` entry
**Requirement**: BVIEW-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] BVIEW AC 1 and AC 11 (375 px, no horizontal scroll) verified in the browser preview (orchestrator, 2026-10-13: document width 375 at 375 px; tables scroll inside their own container)
- [x] `frontend/src/pages/pages.contract.test.ts` updated for the new page
- [x] Gate passes: Build (frontend)

**Tests**: unit
**Gate**: Build
**Commit**: `feat(bills): link the credit card page in the navigation`

---

### T51: Release notes

**What**: Release notes for `0.16.3-selfhost.4`: migrations `099`/`100`, backup before upgrade, the settlement mode, the `rebuild-bills` command, the holiday list.
**Where**: `deploy/public/RELEASE-NOTES.md`
**Depends on**: T50
**Reuses**: previous release notes format
**Requirement**: BILL-04, BREP-01

**Tools**:

- MCP: NONE
- Skill: `docs-writer`

**Done when**:

- [x] Notes cover every migration and operator action
- [x] Gate passes: Build (backend and frontend)

**Tests**: none
**Gate**: Build
**Commit**: `docs(deploy): write the 0.16.3-selfhost.4 release notes`


---

### T55: Refresh bills when an import is undone

**What**: `DELETE /api/import-logs/{id}` collects the bill ids of the rows it deletes (`bill_service.collect_bill_ids`) and refreshes them after the delete (Verifier gap 1).
**Where**: `backend/app/api/import_logs.py`
**Depends on**: None (phase order)
**Reuses**: `collect_bill_ids`, `refresh_bills`
**Requirement**: BILL-01, BPAY-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Undoing a card import drops the bill's computed total to the remaining rows
- [x] Undoing a checking import that holds a linked payment drops `paid_amount`, clears `settled_on` and the bill status leaves `paid`
- [x] New test `backend/tests/test_import_undo_bills.py`
- [x] Gate passes: Full

**Tests**: integration
**Gate**: Full
**Commit**: `fix(bills): refresh bills when an import is undone`

---

### T56: Refresh bills when an account with payments is deleted

**What**: `account_service.delete_account` collects the bills paid by rows of the account before deleting and refreshes them after (Verifier gap 2).
**Where**: `backend/app/services/account_service.py`
**Depends on**: T55
**Reuses**: `collect_bill_ids`, `refresh_bills`
**Requirement**: BPAY-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Deleting a checking account holding a linked payment drops the bill's `paid_amount` and status
- [x] Deleting a card account deletes its bills and leaves its former payments unlinked (`paid_bill_id` null), asserted on PostgreSQL with `postgres_sessions` (Verifier gap 3, spec edge case)
- [x] New test `backend/tests/test_account_delete_bills.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `fix(bills): refresh bills when an account is deleted`

---

### T57: Refresh paid bills after sync duplicate cleanup

**What**: The sync twin/phantom cleanup (`connection_service.py` ~l.1645) collects bill ids (both `bill_id` and `paid_bill_id`) of rows it deletes and refreshes them (Verifier gap 5).
**Where**: `backend/app/services/connection_service.py`
**Depends on**: T56
**Reuses**: `collect_bill_ids`, `refresh_bills`
**Requirement**: BPAY-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] A linked non-card payment removed by the cleanup no longer counts in its bill's `paid_amount`
- [x] Tests added to `backend/tests/test_sync_bills.py`
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `fix(bills): refresh paid bills after sync duplicate cleanup`

---

### T58: Close the backend spec-precision gaps

**What**: The concurrent creation test asserts that rows of both concurrent batches link to the single surviving bill (Verifier gap 4, spec edge case).
**Where**: `backend/tests/test_bill_service.py`
**Depends on**: T57
**Reuses**: existing `postgres_sessions` test
**Requirement**: BILL-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Assertion on both batches' `bill_id` equal to the one bill id added (test created by this feature, so no owner approval needed)
- [x] Gate passes: `cd backend && $V/python -m pytest tests/test_bill_service.py -q` with `POSTGRES_TEST_URL`

**Tests**: unit
**Gate**: Quick
**Commit**: `test(bills): assert both concurrent batches join the same bill`

---

### T59: Same bill figures on both pages

**What**: A frontend test renders the account detail bill panel and the consolidated page for the same bill fixture and asserts equal target, paid, remaining, status and effective due date (BVIEW AC 8, Verifier gap 4).
**Where**: `frontend/src/pages/credit-cards-consistency.test.tsx`
**Depends on**: T58
**Reuses**: fixtures in `credit-cards.test.tsx`, `account-detail-bills.test.tsx`
**Requirement**: BVIEW-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Both renders show the same five figures for one bill
- [x] Gate passes: `cd frontend && npx vitest run src/pages/credit-cards-consistency.test.tsx`

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `test(bills): compare bill figures across both pages`

---

### T60: Keep the description visible next to bill badges

**What**: In the transactions list, the paid-bill pill and the "possible bill payment" badge shrink and truncate instead of hiding the description; the description keeps at least its first words visible and nothing overflows into the Category column (browser check finding, desktop and 375 px).
**Where**: `frontend/src/components/bill-payment-row-badge.tsx`
**Depends on**: T59
**Reuses**: truncation classes used by other row badges
**Requirement**: BPAY-01, BMATCH-02

**Tools**:

- MCP: NONE
- Skill: `frontend-design`

**Done when**:

- [x] Pill uses a short label (card display name + `MMM/yy`) with the full text in a tooltip/title; badge and pill have `min-w-0`/`truncate`/max width so the description is never fully hidden
- [x] Test asserts the full label is available as accessible text/title and the description text is still rendered
- [x] Tests added to `frontend/src/components/bill-payment-row-badge.test.tsx`
- [x] Gate passes: Build (frontend); orchestrator re-checks in the browser

**Tests**: unit
**Gate**: Build
**Commit**: `fix(bills): keep transaction descriptions visible next to bill badges`


---

### T61: Refresh bills when a category is deleted with reassignment

**What**: When a category is deleted and its rows move to another category (bulk `UPDATE transactions SET category_id`, `category_service.py` ~l.411-448), refresh the bills of the moved rows (Verifier round 2 gap 1, AD-004).
**Where**: `backend/app/services/category_service.py`
**Depends on**: None (phase order)
**Reuses**: `bill_service.collect_bill_ids`, `refresh_bills`
**Requirement**: BILL-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] A card purchase moved from an `is_ignored` category to a normal one raises the bill's `computed_total` (0.00 → 100.00), and the reverse lowers it
- [x] New test `backend/tests/test_category_delete_bills.py` that fails before the fix
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `fix(bills): refresh bills when a deleted category reassigns rows`

---

### T62: Refresh bills when rules are applied

**What**: `rule_service.apply_single_rule` and `apply_all_rules` refresh the bills of every row they change (category or `is_ignored`) before commit (Verifier round 2 gap 2, AD-004).
**Where**: `backend/app/services/rule_service.py`
**Depends on**: T61
**Reuses**: `bill_service.touch`
**Requirement**: BILL-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] An `ignore` rule matching a card purchase drops `computed_total` (100.00 → 0.00) through both entry points
- [x] A categorize rule into an `is_bill_payment` category removes a payment from P/L and refreshes its bill
- [x] New test `backend/tests/test_rule_apply_bills.py` that fails before the fix
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `fix(bills): refresh bills when rules are applied`

---

### T63: Refresh bills for upgraded recurring placeholders

**What**: Import `touch`es the `upgraded_placeholders` ids after rules run on them (`import_service.py` ~l.1016-1047, Verifier round 2 gap 3).
**Where**: `backend/app/services/import_service.py`
**Depends on**: T62
**Reuses**: `bill_service.touch`
**Requirement**: BILL-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] An upgraded placeholder that a rule marks ignored leaves its bill total updated
- [x] Tests added to `backend/tests/test_import_bills.py` (feature-created file)
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `fix(bills): refresh bills for upgraded recurring placeholders`

---

### T64: Guard test for AD-004

**What**: A test scans `backend/app/services/` and `backend/app/api/` for bulk `update(Transaction)` / `delete(Transaction)` statements and for writes to `category_id`, `is_ignored`, `bill_id`, `paid_bill_id` via core statements, and fails when a module contains one without calling `bill_service` (allow-list with a reason per entry).
**Where**: `backend/tests/test_ad004_guard.py`
**Depends on**: T63
**Reuses**: `ast` / text scan of the source tree
**Requirement**: BILL-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Guard passes on the current tree and fails when the refresh call is removed from T61's or T62's path (checked once, not committed)
- [x] Every allow-list entry has a one-line reason
- [x] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `test(bills): guard bulk transaction writes against stale bills`

---

### T65: Projected purchase count per category

**What**: Category spending in `settlement` returns `projected_count` per category (number of `is_bill_projected` card rows counted in `projected`); 0 elsewhere.
**Where**: `backend/app/services/dashboard_service.py`
**Depends on**: T64
**Reuses**: `_get_settlement_projections`
**Requirement**: ADJ-04

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Two unpaid purchases in Compras give `projected_count = 2`; paid ones are not counted; `cash`/`accrual` return 0
- [x] Schema field optional with default 0
- [x] New test `backend/tests/test_dashboard_projected_count.py`
- [x] Gate passes: Full

**Tests**: integration
**Gate**: Full
**Commit**: `feat(dashboard): count projected card purchases per category`

---

### T66: Available credit honors the balance date

**What**: The account detail `available_credit` equals `credit_limit − amount owed`, using the same floored current balance as the accounts list (AD-001/AD-002). Find why `serialize_account` / `get_account` differs from `get_accounts` and fix at the source.
**Where**: `backend/app/services/account_service.py`
**Depends on**: T65
**Reuses**: balance used by `get_accounts`
**Requirement**: ADJ-05

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] A card with an opening balance and older transactions shows the same owed amount in list and detail, and `available_credit = limit − owed`
- [x] New test `backend/tests/test_card_available_credit.py` that fails before the fix
- [x] Gate passes: Build (backend)

**Tests**: integration
**Gate**: Build
**Commit**: `fix(accounts): compute available credit from the floored balance`

---

### T73: Refresh other users' bills when a user is deleted

**What**: `admin_service.delete_user` collects the bills paid by the user's rows that belong to accounts of other users (shared workspace) and refreshes them after the delete; remove its entry from the T64 guard allow-list (G1 note).
**Where**: `backend/app/services/admin_service.py`
**Depends on**: None (phase order)
**Reuses**: `collect_bill_ids`, `refresh_bills`
**Requirement**: BPAY-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Deleting user A whose payment paid user B's card bill drops that bill's `paid_amount` and status
- [ ] `delete_user` no longer allow-listed in `backend/tests/test_ad004_guard.py` (feature-created file)
- [ ] New test `backend/tests/test_delete_user_bills.py` that fails before the fix
- [ ] Gate passes: Full

**Tests**: unit
**Gate**: Full
**Commit**: `fix(bills): refresh shared bills when a user is deleted`

---

### T74: Account create returns the floored balance

**What**: `POST /api/accounts` returns the account through `get_serialized_account`, so a new card with an opening balance reports its real `current_balance` and `available_credit` (G1 note, same cause as T66).
**Where**: `backend/app/api/accounts.py`
**Depends on**: T73
**Reuses**: `account_service.get_serialized_account`
**Requirement**: ADJ-05

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Creating a card with balance owed 300 and limit 1000 returns `current_balance` -300 (card sign convention as in the list) and `available_credit` 700
- [ ] Tests added to `backend/tests/test_card_available_credit.py`
- [ ] Gate passes: Build (backend)

**Tests**: integration
**Gate**: Build
**Commit**: `fix(accounts): return the computed balance when creating an account`

---

### T67: Bill-payment badge on categories

**What**: Categories list shows a "Pagamento de fatura" badge for `is_bill_payment`, like the Transferências/Ignorado badges.
**Where**: `frontend/src/pages/categories.tsx`
**Depends on**: T74
**Reuses**: existing transfer/ignored badges
**Requirement**: ADJ-01

**Tools**:

- MCP: NONE
- Skill: react-best-practices

**Done when**:

- [ ] Badge shown only for flagged categories; keys in every locale
- [ ] Tests added to `frontend/src/pages/categories-bill-payment.test.tsx`
- [ ] Gate passes: Quick-FE

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(categories): show the bill payment badge in the list`

---

### T68: Projected count badge on Spending by Category

**What**: Dashboard "Gastos por Categoria" shows "(N previstas)" next to categories with `projected_count > 0` in `settlement`.
**Where**: `frontend/src/pages/dashboard.tsx`
**Depends on**: T67
**Reuses**: `projected_count` from T65
**Requirement**: ADJ-04

**Tools**:

- MCP: NONE
- Skill: react-best-practices

**Done when**:

- [ ] Badge text uses plural rules (1 prevista / 2 previstas); hidden when 0
- [ ] Tests added to `frontend/src/pages/dashboard.test.tsx` (append only)
- [ ] Gate passes: Quick-FE

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(dashboard): show projected purchase counts per category`

---

### T69: Settlement dates in the transactions list

**What**: In `settlement`, card rows with a bill show the reporting date with "Paga em" (bill paid) or "Pagar até" (otherwise) and a second line "Lançada em <date>", plus the "Prevista" badge when `is_bill_projected`; desktop and mobile rows; other modes unchanged.
**Where**: `frontend/src/pages/transactions.tsx`
**Depends on**: T68
**Reuses**: drill-down row layout (T41), `ProjectedTransactionBadge`
**Requirement**: ADJ-02

**Tools**:

- MCP: NONE
- Skill: react-best-practices

**Done when**:

- [ ] ADJ AC 2, 3, 4 and the spec Independent Test (Petz Digital: "Pagar até 13/10/2026", "Lançada em 05/09/2026", Prevista)
- [ ] Backend already returns `reporting_date`/`is_bill_projected`; add the bill paid state to the row if missing (smallest change, documented)
- [ ] New test `frontend/src/pages/transactions-settlement-dates.test.tsx`
- [ ] Gate passes: Quick-FE

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(transactions): show bill dates for card rows in settlement mode`

---

### T70: Bill info in the transaction dialog

**What**: Card transactions with a bill show read-only: bill (card + reference month) and "Quitada em <date>" or "Não quitada · vence em <effective due>".
**Where**: `frontend/src/components/transaction-dialog.tsx`
**Depends on**: T69
**Reuses**: `creditCardBills.get`, `BillStatusBadge`
**Requirement**: ADJ-03

**Tools**:

- MCP: NONE
- Skill: react-best-practices

**Done when**:

- [ ] ADJ AC 5 for paid and unpaid bills; nothing shown for non-card rows
- [ ] Tests added to `frontend/src/components/transaction-dialog.test.tsx` (append only)
- [ ] Gate passes: Quick-FE

**Tests**: unit
**Gate**: Quick-FE
**Commit**: `feat(bills): show the bill and settlement date on card transactions`

---

### T71: Payment links open the payment

**What**: Payment entries in `BillDetailsCard` and on the credit cards page link to `/transactions?highlight=<payment id>` scoped to the payment's month instead of the paying account.
**Where**: `frontend/src/components/credit-card/bill-details-card.tsx`
**Depends on**: T70
**Reuses**: `highlight` handling in `transactions.tsx`
**Requirement**: ADJ-06

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] ADJ AC 8 on both pages
- [ ] Tests updated only in feature-created files (`account-detail-bills.test.tsx`, `credit-cards.test.tsx`)
- [ ] Gate passes: Build (frontend)

**Tests**: unit
**Gate**: Build
**Commit**: `fix(bills): open the payment transaction from a bill`

---

### T72: Release notes for the adjustments

**What**: Release notes cover ADJ items, the inverted-sign CSV guidance (use "inverter sinal" in the saved card mapping), and the bill-refresh fixes.
**Where**: `deploy/public/RELEASE-NOTES.md`
**Depends on**: T71
**Reuses**: T51 notes
**Requirement**: ADJ-07

**Tools**:

- MCP: NONE
- Skill: docs-writer

**Done when**:

- [ ] Notes updated in Portuguese
- [ ] Gate passes: Build (backend and frontend)

**Tests**: none
**Gate**: Build
**Commit**: `docs(deploy): document the credit card adjustments`
---

## Phase Execution Map

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 8 → Phase 9

Phase 1:  T1 → T2 → T3 → T4 → T5
Phase 2:  T6 → T7 → T8 → T9 → T10 → T11 → T12
Phase 3:  T13 → T14 → T15
Phase 4:  T16 → T17 → T18 → T19 → T20 → T21
Phase 5:  T22 → T23 → T24 → T25 → T26 → T27 → T28 → T52
Phase 6:  T29 → T30 → T31 → T32 → T33 → T34 → T35 → T36 → T37
Phase 7:  T53 → T38 → T39 → T40 → T41 → T54
Phase 8:  T42 → T43 → T44 → T45
Phase 9:  T46 → T47 → T48 → T49 → T50 → T51
Phase 10: T55 → T56 → T57 → T58 → T59 → T60
Phase 11: T61 → T62 → T63 → T64 → T65 → T66
Phase 12: T73 → T74 → T67 → T68 → T69 → T70 → T71 → T72
```

Batches (~7 tasks, whole phases): B1 = Phase 1 (5), B2 = Phase 2 (7), B3 = Phases 3-4 (9), B4 = Phase 5 (8), B5 = Phase 6 (9), B6 = Phase 7 (6), B7 = Phase 8 (4), B8 = Phase 9 (6).

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T3: schema migration + models | 1 migration + model columns it creates | ⚠️ Cohesive (schema change cannot be split from its models) |
| T9: hooks in transaction CRUD | 1 file, 9 call sites of one helper | ⚠️ Cohesive (AD-004 single concern) |
| T38: types + api client | 2 files, one contract | ⚠️ Cohesive |
| T50: route + nav + palette | 3 small wiring edits | ⚠️ Cohesive |
| All other tasks | 1 file, 1 concern | ✅ Granular |

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| ---- | ---------------------- | ------------- | ------ |
| T1 | None | start of Phase 1 | ✅ Match |
| T2-T5 | previous task | chain | ✅ Match |
| T6 | None (phase order) | start of Phase 2 (after Phase 1) | ✅ Match |
| T7-T12 | previous task | chain | ✅ Match |
| T13 | None (phase order) | start of Phase 3 | ✅ Match |
| T14-T15 | previous task | chain | ✅ Match |
| T16 | None (phase order) | start of Phase 4 | ✅ Match |
| T17-T21 | previous task | chain | ✅ Match |
| T22 | None (phase order) | start of Phase 5 | ✅ Match |
| T23-T28 | previous task | chain | ✅ Match |
| T52 | T28 | chain (end of Phase 5) | ✅ Match |
| T29 | None (phase order) | start of Phase 6 | ✅ Match |
| T30-T37 | previous task | chain | ✅ Match |
| T53 | None (phase order) | start of Phase 7 | ✅ Match |
| T38 | T53 | chain | ✅ Match |
| T39-T41 | previous task | chain | ✅ Match |
| T54 | T41 | chain (end of Phase 7) | ✅ Match |
| T42 | None (phase order) | start of Phase 8 | ✅ Match |
| T43-T45 | previous task | chain | ✅ Match |
| T46 | None (phase order) | start of Phase 9 | ✅ Match |
| T47-T51 | previous task | chain | ✅ Match |

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | --------------------------- | --------------- | --------- | ------ |
| T1, T2 | Backend pure domain | unit | unit | ✅ OK |
| T3 | Model / schema-only migration | none | none | ✅ OK |
| T4, T5, T7-T12, T14, T16, T18, T19, T22-T27, T30-T36, T52, T53 | Backend service / SQL filter | unit | unit | ✅ OK |
| T6 | Backend data migration | unit | unit | ✅ OK |
| T13, T15, T17, T20, T21, T28, T29, T37 | Backend route (and its service) | integration | integration | ✅ OK |
| T38 | Frontend api client / types | none | none | ✅ OK |
| T39-T49, T54 | Frontend page / component | unit | unit | ✅ OK |
| T50 | Frontend wiring (route/nav) | unit | unit (contract test) | ✅ OK |
| T51 | Docs | none | none | ✅ OK |

## Requirement Coverage

| Requirement | Tasks |
| ----------- | ----- |
| BILL-01 | T2, T3, T4, T5, T13, T38, T42 |
| BILL-02 | T14, T15, T46, T47 |
| BILL-03 | T5, T12 |
| BILL-04 | T6, T7, T51 |
| BIMP-01 | T5, T8, T9, T10, T11 |
| BPAY-01 | T16, T18, T20, T21, T38, T43, T44 |
| BPAY-02 | T19, T52 |
| BPAY-03 | T16, T17, T40, T53 |
| BDAY-01 | T1 |
| BMATCH-01 | T22, T23, T25, T26, T27 |
| BMATCH-02 | T24, T28, T38, T43, T44 |
| BMATCH-03 | T23, T28, T45 |
| BREP-01 | T29-T37, T39, T51, T54 |
| BREP-02 | T37, T41 |
| BVIEW-01 | T48, T49, T50 |
| ADJ-01 | T67 |
| ADJ-02 | T69 |
| ADJ-03 | T70 |
| ADJ-04 | T65, T68 |
| ADJ-05 | T66, T74 |
| ADJ-06 | T71 |
| ADJ-07 | T72 |
