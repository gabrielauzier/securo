# Account Balance Date Validation

**Date**: 2026-10-11
**Spec**: `.specs/features/account-balance-date/spec.md` (updated by the owner decision: ABD-01 AC2/AC3/AC10, ABD-02 AC8, ABD-04 AC7)
**Diff range**: `f56667f..HEAD` (HEAD = 8e97364, branch `feat/account-balance-date`; includes fix commits 6f8f480, b27f50e, f2e3463, 3f85588, 82c7afd, 8e97364)
**Verifier**: fresh independent sub-agent, iteration 4 (final, authorized by the owner beyond three; scoped re-verification of 8e97364; author != verifier); real working tree untouched (`git status --porcelain` identical before and after: only the pre-existing `.gitignore` and `frontend/package-lock.json`, plus this file)

**Result**: PASS

Reason (iteration 4): the iteration-3 blocker N7 is closed. ABD-01 AC13 (future date accepted, reads before it see full history) is pinned at service and HTTP level and the former survivors M11 and M13 are now killed, as are M8, M10 and M12. 15 further backend mutants were run: 11 killed, and 4 survivors are all outside P0 write rules, floor, backfill and the zero-balance create regression (credit-card-only effective_date and serializer gating, untouched import path). No uncovered AC, no CRITICAL gap. All 34 ACs/edge cases have file:line evidence.

---

## Iteration History

| Iteration | Verdict | Notes |
| --------- | ------- | ----- |
| 1 | FAIL | CRITICAL G1 (balance-0 create floored history), G2 backfill untested, G3 sequential-write edge untested, G4 R3 survivor |
| 2 | FAIL | G1 fixed and verified end to end; G2, G3, G4 closed; new gap N1 (update with `balance: 0` plus a date untested, mutant U13 survives) |
| 3 | FAIL | N1 closed by 82c7afd (AC11/AC12, U13 killed); new gap N7: the "future date accepted" edge case is untested on create/update (mutants M11, M13 survive); code verified correct |
| 4 | PASS | N7 closed by 8e97364 (AC13 tests; M11, M13, M8, M10, M12 killed); 15 new mutants, 11 killed, 4 survivors outside P0 (SUGGESTIONs N10-N12); full gate green |

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1-T10 | Done | unchanged from iteration 1 |
| F1 zero-balance create leaves NULL | Done | `account_service.py:268-278` |
| F2 create dialog sends date only when it matters | Done | `accounts.tsx:744-761` |
| F3 migration 098 automated test | Done | `tests/test_account_balance_date_migration.py` |
| F4 connected guard + sequential edge | Done | `test_report_service.py:3012`, `test_account_service.py:303` |
| F5 zero-balance update with a date (AC11/AC12) | Done | `test_account_service.py:252,276,298`; `test_accounts_api.py:1240,1261,1285` |

---

## Iteration-1 Gap Re-check (item 1)

| Check | Result | Evidence |
| ----- | ------ | -------- |
| (a) Backend create rule | OK | `account_service.py:268-278`: explicit date wins; else non-zero balance -> `app_today()`; else NULL. Explicit `balance_date: null` goes through `model_fields_set` but `data.balance_date` is `None` either way, so the `model_fields_set` check is redundant (equivalent, see Sensor note). Tests: `test_account_service.py:238` (date D + 300 -> D), `:252` (no date + 300 -> today), `:262` (0 + D -> D, no opening), `:278` (0, no date -> None, no opening), `:290` (0, explicit None -> None) |
| (b) Frontend create payload | OK | `accounts.tsx:749-761`: `sendDate = account ? balanceTouched : dateChanged \|\| balanceValue !== 0`; `balance` always sent on create. Tests `accounts-dialog.test.tsx:175` (0, untouched -> no `balance_date`), `:183` (0, date changed -> sent, not today), `:198` (250, untouched -> today); `:101`, `:156` |
| (c) Regression test real and discriminating | OK | `test_accounts_api.py:1110` `test_zero_balance_account_without_date_counts_imported_history`: balance 0, no date, 1000 credit 30 days ago + 10 debit today -> list balance `== 990` and detail `balance_date is None`. With create mutated to store today for zero balance the test FAILS (also `:1096`). |
| (c) End-to-end CSV import probe (scratch, not committed) | OK | Scratch test at HEAD: `POST /api/accounts` balance 0 (once with no date, once with explicit `balance_date: null`) -> `balance_date` null; `POST /api/transactions/import` with a 1000 credit (30 days ago) and a 10 debit (today) -> `imported == 2`; list `current_balance == 990.0`, `balance_date` null, `/summary` `current_balance == 990.0`. Under the zero->today mutant both variants fail. Control: balance 100 created without a date (floor today) + imported old credit -> balance stays 100 (floor applies, as intended). `grep` over `backend/app`: `import_service.py` and `api/import_transactions.py` do not reference `balance_date` or `opening_balance`; they neither set nor depend on it. |
| (d) Migration 098 backfill test | OK | `tests/test_account_balance_date_migration.py` runs the real `upgrade()`/`downgrade()` on SQLite: latest opening (`:91` `2025-06-20`), single opening, no opening -> None, connected with an opening row -> None, downgrade drops the column. Mutants re-run: max->min, dropped `connection_id IS NULL`, dropped `source` filter, backfill no-op: all KILLED |
| (e) R3 guard test | OK | `test_report_service.py:3012` connected account with `balance_date` set and earlier history -> `balance_resets == []`; mutant dropping the `connection_id` guard KILLED |
| (f) Sequential-write edge | OK | `test_account_service.py:303`: after `update(balance 200, date first)` and after `update(date second)`, account and opening dates are equal each time; mutants U2, U4, U6, U7, U9, U11 are killed by it |

---

## Test-Edit Integrity Review (item 2)

`git diff f56667f..HEAD` and `git diff d4f7b38..HEAD` on every pre-existing test:

| File | Change | Judgment |
| ---- | ------ | -------- |
| `test_account_service.py` (`_add_txn`, +7 lines) | opening-source rows also set the owner's `balance_date` (`max(...)`, manual accounts only) | Fixture only, mirrors what the service does; no assertion touched |
| `test_account_service.py` ~l.278 | iteration-1 test `..._without_date_stores_today` renamed to `..._leaves_it_null`; expected `balance_date == app_today()` became `is None` | Required by the owner decision (ABD-01 AC10); the test was itself added in this feature, `_opening_of(...) is None` kept. Not a weakening |
| `test_dashboard_service.py` (`_add_txn`), `test_opening_floor.py` (`_tx`), `test_report_service.py` (`_seed_reset_account`) | same fixture mirroring of the opening date onto `balance_date` | Fixture only; zero removed lines in all three files; AD-002 trade-off |
| `test_dashboard_api.py` (`test_balance_date_parameter_overrides_default_cutoff`) | account creation JSON gains `"balance_date": today-60d`; no assertion changed | Was needed in iteration 1; under the owner decision the unchanged fixture would also pass, so the explicit date is now vestigial (harmless, SUGGESTION to revert) |
| `test_accounts_api.py` | additions only; no removed line vs `f56667f`; iteration-2 diff adds two tests | OK |
| `accounts-dialog.test.tsx` ~l.96-106, ~l.151-166 | `expect(payload.balance_date).toBe(today)` replaced by `expect(payload).not.toHaveProperty('balance_date')` (balance-0, untouched date) | Required by ABD-04 AC7. Not weakened: `balance`, `currency`, card fields still asserted, and the non-zero / changed-date cases are asserted exactly in the new `describe` (`:159-206`, today asserted with `toBe(todayString())`) |
| `dashboard.test.tsx` | `balance_date: null` added to the `Account` factory | Type fixture only |

No test removed; no assertion weakened. Test counts only went up (backend 4394 -> 4433 passed, frontend 957 -> 967).

---

## Spec-Anchored Acceptance Criteria (item 3)

Evidence-or-zero. Line numbers are current at HEAD.

### ABD-01 Save the balance date on the account

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| AC1 create with D | `balance_date = D` | `test_account_service.py:238` `account.balance_date == chosen`, opening `.date == chosen`; HTTP `test_accounts_api.py:1066` `resp.json()["balance_date"] == chosen.isoformat()` | Covered |
| AC2 create, no date, non-zero | today, opening dated today | `test_account_service.py:252` `balance_date == app_today()`, opening `.date == app_today()`; HTTP `test_accounts_api.py:1082` `== _app_today().isoformat()` | Covered |
| AC3 balance 0 + D | `balance_date = D`, no opening tx | `test_account_service.py:262` `balance_date == chosen`, `_opening_of(...) is None`; HTTP floor `test_accounts_api.py:959` `approx(-50.0)` | Covered |
| AC11 update balance 0 + D | `balance_date = D`; opening tx deleted if present | Service `test_account_service.py:252` (existing opening, 500 at D-20, update 0 + D-4): `updated.balance_date == new_date`, `_opening_of(...) is None`. `:276` (NULL date, no opening): `balance_date == new_date`, `_opening_of is None`. PATCH `test_accounts_api.py:1240` (existing opening): `resp.json()["balance_date"] == new_day.isoformat()`, `_opening_tx_count == 0`. `:1261` (NULL date, no opening): same assertions, precondition `created.json()["balance_date"] is None` | Covered (U13 killed by `:252`) |
| AC12 update `balance_date` null | stored date unchanged (no-op) | Service `test_account_service.py:298`: `AccountUpdate(balance_date=None)` -> `updated.balance_date == stored`, opening date `== stored`. PATCH `test_accounts_api.py:1285`: `json={"balance_date": None}` -> 200, `balance_date == stored.isoformat()` | Covered |
| AC13 future date | stored as given on create and update; reads with a cutoff before it include all transactions to the cutoff | Service `test_account_service.py:252` create (balance 300, D=today+5): `account.balance_date == future` and opening `.date == future`; `:266` update (date-only to today+5): `updated.balance_date == future`, opening `.date == future`; `:285` read: balance 0 + future date, credit 100 three days ago, `current_balance == approx(100.0)` (floor inactive). HTTP `test_accounts_api.py:1082` POST returns `balance_date == future`; `:1098` PATCH returns it and the opening row `.date == future`; `:1127` summary and list `current_balance == approx(100.0)`. Killing M11, M13 (clamp to today) and the read test pins the cutoff-before-D clause | Covered |
| AC10 balance 0, no date | NULL, no opening tx | `test_account_service.py:278` `balance_date is None`, `_opening_of is None`; `:290` explicit None same; HTTP `test_accounts_api.py:1096` `balance_date is None` | Covered |
| AC4 update with new D | account = D and opening tx date = D | `test_account_service.py:426` `opening.date == new_date`; `:470`, `:559`, `:303`; HTTP `test_accounts_api.py:1159` PATCH returns the new date and opening moved | Covered (nonzero and date-only; zero balance + date: see AC11) |
| AC5 balance (non-zero), no date | keep stored date, opening dated at it; today if none | `test_account_service.py:504` `balance_date == stored`, opening `== stored`; `:524` existing opening; `:544` null -> `app_today()` | Covered |
| AC6 update to balance 0 | opening deleted, date kept | `test_account_service.py:601` `_opening_of(...) is None`, `updated.balance_date == stored` | Covered |
| AC7 neither field | unchanged | `test_account_service.py:619` date and opening date `== stored`; HTTP `test_accounts_api.py:1189` | Covered |
| AC8 read model | `balance_date` in list and detail, null when unset | `test_accounts_api.py:1030` list and detail `is None`; `:1046` list and detail `== stored.isoformat()` | Covered |
| AC9 connected | stays NULL, sent date ignored | `test_account_service.py:638` `updated.balance_date is None` after sending a date; `test_opening_floor.py:206` connected `balance_date is None`; `test_report_service.py:3012` | Covered |

### ABD-02 Balance reads use the stored date as the floor

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| AC1 floor at every read site | rows on/after D count when cutoff >= D | `test_opening_floor.py:59` excluded before D, `:74` D itself included; per site (all 7 call sites mutated, see Sensor): list `test_account_service.py:1830`, previous_balance `:1941`, history `:2006`, summary current `test_accounts_api.py:807`, window opening `:876`, dashboard `test_dashboard_service.py:1253`, total by currency `:1307` | Covered |
| AC2 cutoff < D | all rows up to cutoff | `test_opening_floor.py:85`, `:165` | Covered |
| AC3 NULL | no floor | `test_opening_floor.py:99`, `:177` | Covered |
| AC8 NULL, any date counts (imported history) | full history in balance | `test_accounts_api.py:1110` `== Decimal("990")`; scratch import probe 990 | Covered |
| AC4 date, no opening tx | floor still applies | `test_opening_floor.py:151`; `test_dashboard_service.py:1257` `approx(-100.0)`; `test_accounts_api.py:959` `approx(-50.0)` | Covered |
| AC5 date change | next read reflects it | `test_opening_floor.py:188`; `test_accounts_api.py:959` PATCH then `approx(-250.0)` | Covered |
| AC6 connected unchanged | same balances | `test_opening_floor.py:206`; `test_dashboard_service.py:172`, `:231`, `:281` connected balance cases | Covered |
| AC7 reset notice from `Account.balance_date` | listed with that date, earlier non-ignored history required | `test_report_service.py:3044` `[(id, saved.isoformat())]` with no opening row; `:3067` NULL -> `[]`; `:3089` ignored-only -> `[]`; window bounds `:2865`, `:2889`; opening day `:2911`; opening rows not history `:2956`; connected `:2978`, `:3012` | Covered |

### ABD-03 Existing accounts keep their balances after the upgrade

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| AC1 backfill latest opening date (manual) | `max(opening date)` | `test_account_balance_date_migration.py:91` `dates["manual-two"] == "2025-06-20"` (two openings plus a later non-opening row), `:92` `manual-one == "2025-03-05"` | Covered (automated) |
| AC2 NULL for connected and manual without opening | NULL | same test `:93` `manual-none is None`, `:94` `connected is None` (connected carries an opening row) | Covered (automated) |
| AC3 downgrade drops column | no error | `test_account_balance_date_migration.py:104` `"balance_date" not in columns` | Covered (automated) |

Residual note: the test runs the real migration module against SQLite with a minimal schema, not Postgres; the `DATE` DDL and the correlated UPDATE are portable. The Postgres run remains the worker's earlier manual evidence. Not a gap.

### ABD-04 The edit dialog shows and explains the saved date

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| AC1 edit with date | field shows it | `accounts-dialog.test.tsx:317` text matches `/2023/`, day 7, month 3 for `'2023-03-07'` | Covered |
| AC2 edit without date | today | `:325` current year, not 2023 | Covered (year level, see S3) |
| AC3 create | today | `:331` current year; payload exact `:198-205` `toBe(todayString())` | Covered |
| AC4 hint | text under the field | `:336` `getByText(t('accounts.balanceDateHint'))` | Covered |
| AC5 name-only | no `balance`/`balance_date` | `:263`, `:341` `not.toHaveProperty(...)`, `:232` | Covered |
| AC7 create payload | 0 + untouched -> not sent; changed date or non-zero -> sent shown | `:175` `not.toHaveProperty('balance_date')`; `:183` changed date sent and `not.toBe(todayString())`; `:198` `balance 250`, `balance_date toBe(todayString())`; `:101`, `:156` | Covered |
| AC6 all locales | key in every locale | `locales/i18n.test.ts` parity (all 15 files carry the key) | Covered |

### Edge cases

| Edge case | `file:line` + assertion | Result |
| --------- | ----------------------- | ------ |
| Invalid date -> 422 | `test_accounts_api.py:1153` create `== 422`; `:1221` patch `== 422`, stored date kept | Covered |
| Two sequential writes -> same date after each | `test_account_service.py:303` account and opening `== first`, then `== second` | Covered |
| Opening tx drifted -> account authoritative | `test_account_service.py:580` after balance update both `== stored`; floor `test_opening_floor.py:151` (no opening at all) | Covered |

**Spec-precision flags**: (P1) resolved by AC11 (balance 0 plus D stores D, deletes the opening tx); matches `account_service.py:408-409,450-451`. (P2) resolved by AC12 (explicit null is a documented no-op); matches `update_data.pop(..., None)` plus `if balance_date:`, tested at service and PATCH level, so it hides no defect. (P3, open, does not block) ABD-01 AC9 defines no create-path behavior for connected accounts (connected accounts are never created through `create_account`).

**Status**: 100% of spec items (4 stories, 34 ACs/edge cases including AC11, AC12, AC13) have file:line evidence; 0 uncovered ACs. The "Future date accepted" edge case (spec.md:36) is now AC13 and covered at write level (N7 closed).

---

## Discrimination Sensor (item 4)

Scratch git worktree at HEAD (`/Volumes/MacOnlySSD/tmp-verifier6`, removed afterwards), original file restored after each mutant, every pattern required to match exactly once (confirmed the mutant was applied). Backend set: account_service, accounts_api, opening_floor, dashboard_service, dashboard_api, report_service, migration tests. Frontend: `accounts-dialog.test.tsx`.

| # | File | Mutation | Result (first failing test) |
| - | ---- | -------- | --------------------------- |
| C1 | `account_service.py` create | non-zero without date -> NULL | Killed (`test_create_account_with_balance`) |
| C2 | create | zero without date -> today (the iteration-1 regression) | Killed (`test_create_account_zero_balance_without_date_leaves_it_null`; also `test_accounts_api.py:1110` and `:1096`, and the e2e import probe) |
| C3 | create | explicit date ignored at balance 0 | Killed (`..._keeps_the_date_without_opening`) |
| C4 | create | opening tx dated today, not the account date | Killed (`test_create_account_with_balance_date`) |
| C5 | create | explicit date honoured only at balance 0 | Killed (`test_create_account_with_balance_date`) |
| U1 | update | balance 0 clears `balance_date` | Killed (`test_update_balance_to_zero_keeps_the_balance_date`) |
| U2 | update | date-only update does not move the opening tx | Killed (`test_sequential_writes_keep_account_and_opening_dates_equal`) |
| U3 | update | non-zero update with no stored date: no today fallback | Killed (`test_update_balance_on_account_with_no_date_stores_today`) |
| U4 | update | provided date not stored on the account | Killed (`test_sequential_writes_...`) |
| U5 | update | fallback date not persisted on the account | Killed (`test_update_balance_on_account_with_no_date_stores_today`) |
| U6 | update | balance update does not realign the existing opening date | Killed (`test_sequential_writes_...`) |
| U7 | update | date-only branch removed (`or balance_date`) | Killed (`test_sequential_writes_...`) |
| U9 | update | date ignored when `balance` is also in the payload | Killed (`test_sequential_writes_...`) |
| U11 | update | non-zero update ignores stored date, uses today | Killed (`test_sequential_writes_...`) |
| U12 | update | connected account honours `balance_date` | Killed (`test_update_connected_account_ignores_balance_date`) |
| **U13** | update | **date ignored when the payload has `balance: 0` plus a date** | **Iteration 2: SURVIVED. Iteration 3 re-run at 82c7afd: KILLED** (`test_update_to_zero_balance_with_date_stores_date_and_deletes_opening`) |
| F1 | `_query_filters.py` | `>=` -> `>` | Killed (`test_create_account_with_negative_balance`) |
| F2 | floor | `cutoff < bd` -> `<=` | Killed (`test_balance_at_or_after_opening_date_excludes_earlier_transactions`) |
| F3 | floor | NULL branch dropped | Killed (`test_get_accounts_previous_balance_uses_each_account_currency`) |
| F4 | floor | subquery correlation removed | Killed (`test_floor_is_evaluated_per_account`) |
| RS1-RS7 | `dashboard_service.py:1333,1397`, `account_service.py:77,101,728,994,1041` | each `within_opening_floor(...)` call replaced by `true()` | All 7 Killed (`test_dashboard_service.py:1253`, `:1307`; `test_account_service.py:1830`, `:1941`, `:2006`; `test_accounts_api.py:807`, `:876`) |
| S1 | serializer | `balance_date: None` | Killed (`test_account_responses_return_the_stored_balance_date`) |
| S2 | `schemas/account.py` | read schema drops `balance_date` | Killed (`test_account_responses_return_balance_date_null_when_unset`) |
| R1 | `report_service.py` | `connection_id` guard dropped | Killed (`test_net_worth_report_connected_account_with_a_saved_date_is_not_a_reset`) |
| R2 | resets | window start inclusive | Killed |
| R3 | resets | history `<` -> `<=` | Killed |
| R4 | resets | `is_ignored` filter dropped | Killed |
| R5 | resets | opening rows count as history | Killed |
| R6 | resets | window end exclusive | Killed |
| B1 | migration 098 | `max` -> `min` | Killed (`test_upgrade_backfills_...`) |
| B2 | migration | `connection_id IS NULL` dropped | Killed |
| B3 | migration | `source = 'opening_balance'` dropped | Killed |
| B4 | migration | backfill UPDATE made a no-op | Killed |
| D1 | `accounts.tsx` | create always sends the date | Killed (`sends no balance_date for balance 0 with an untouched date`) |
| D2 | dialog | create sends only a changed date | Killed (`sends the date shown (today) for a non-zero balance...`) |
| D3 | dialog | create sends only for non-zero | Killed (`sends the chosen date for balance 0 when the date was changed`) |
| D4 | dialog | edit always sends the date | Killed (`omits balance and balance_date on a name-only edit of a dated account`) |
| D5 | dialog | create omits `balance` when 0 | Killed |
| D6 | dialog | edit initial date ignores the saved date | Killed (`keeps the saved date in the payload when only the balance changes`) |
| D7 | dialog | edit: a date change no longer counts as touched | Killed (`sends balance and balance_date when the date changes`) |

Not injected as equivalent: replacing `data.balance_date if "balance_date" in data.model_fields_set else None` by `data.balance_date` (`account_service.py:272`) cannot change behavior because an unset field defaults to `None` (explicit null and unset are identical). The `model_fields_set` expression is dead complexity (SUGGESTION).

### Iteration 3 mutations

Scratch worktree at 82c7afd (`/Volumes/MacOnlySSD/tmp-verifier7`, removed afterwards, `git worktree prune` run), `PYTHONPATH` pointed at the worktree backend (confirmed `app.__file__`), each pattern required to match exactly once, original restored after each run. Baseline: 405 passed on the 7 backend test files. Frontend mutants ran `vitest run accounts-dialog`.

| # | File | Mutation | Result |
| - | ---- | -------- | ------ |
| U13 (re-run) | `account_service.py` update | date ignored when payload has `balance: 0` | KILLED (`test_update_to_zero_balance_with_date_stores_date_and_deletes_opening`) |
| M1 | update | zero test `!= 0` -> `> 0` (negative balance deletes opening) | KILLED (`test_update_account_balance_creates_negative_opening`) |
| M2 | update | zero branch no longer deletes the opening tx | KILLED (`test_update_to_zero_balance_with_date_stores_date_and_deletes_opening`) |
| M3 | update | existing opening amount not updated | KILLED (`test_update_account_balance_updates_existing_opening`) |
| M4 | create | default date only when balance `> 0` (negative gets NULL) | KILLED (`test_create_account_with_negative_balance`) |
| M6 | `_query_filters.py` | `cutoff < bd` -> `cutoff > bd` | KILLED (`test_list_balance_ignores_expense_dated_before_opening`) |
| M7 | floor | `bd.is_(None)` -> `is_not(None)` | KILLED (`test_get_accounts_previous_balance_uses_each_account_currency`) |
| M9 | `_find_balance_resets` | account filter widened (`or account_id != None`) | KILLED (`test_net_worth_report_skips_accounts_without_a_reset`) |
| F2 | `accounts.tsx` | edit sends the date only when `dateChanged` (a balance-only edit loses it) | KILLED (`keeps the saved date in the payload when only the balance changes`) |
| M8 | `_find_balance_resets` | window end `<= window_end + 1 day` | SURVIVED. Non-equivalent, boundary of the P1 notice (day after window end not tested); SUGGESTION N8 |
| M10 | update | date-only move of the opening tx skipped for `credit_card` | SURVIVED. Type-gated, contrived: no test updates the date of a credit-card account. SUGGESTION N9 |
| M12 | create | zero balance without date stores today for `credit_card` | SURVIVED. Same cause: ABD-01 AC10 create tests use `checking` only. SUGGESTION N9 (code has no type branch; spec makes no type distinction) |
| M11 | update | `balance_date` in the future clamped to today | SURVIVED. Non-equivalent: contradicts spec.md:36 (future date accepted). **Blocker N7** |
| M13 | create | explicit future `balance_date` clamped to today | SURVIVED. Non-equivalent, same edge case. **Blocker N7** |
| F1 | `accounts.tsx` | create sends date when `balanceValue > 0` instead of `!== 0` | SURVIVED. Equivalent in effect for the saved row: with a negative balance and an untouched date, the server defaults to `app_today()`, which is what the dialog would have sent (tiny timezone edge only) |

**Totals (iteration 3)**: 14 new mutants injected plus the U13 re-run (15 runs): 9 killed (8 new plus U13), 6 survived (M8, M10, M11, M12, M13 non-equivalent; F1 equivalent in effect). **Cumulative**: 59 distinct mutants injected, 53 killed, 6 survived (5 non-equivalent). Of those, only M11 and M13 map to a spec-stated outcome on the P0 write paths.

**Totals (iteration 2)**: 46 mutations injected (45 distinct code mutants plus the targeted re-run of C2 against the regression test and the import probe), 45 killed, 1 survived (U13, non-equivalent, P0 update rule). Isolation: worktree and scratch removed, real-tree `git status --porcelain` identical to baseline.


### Iteration 4 mutations

Scratch git worktree at 8e97364 (`/Volumes/MacOnlySSD/tmp-verifier8`, removed afterwards, `git worktree prune` run), `PYTHONPATH` pointed at the worktree backend (confirmed `app.__file__`), each pattern required to match exactly once, original restored after each run. Baseline: 415 passed on the 7 backend files.

| # | File | Mutation | Result |
| - | ---- | -------- | ------ |
| M11 (re-run) | `account_service.py` update | future `balance_date` clamped to today | KILLED (`test_update_account_accepts_a_future_balance_date`) |
| M13 (re-run) | create | explicit future date clamped to today | KILLED (`test_create_account_accepts_a_future_balance_date`) |
| M8 (re-run) | `report_service.py` | window end `<= window_end + 1 day` | KILLED (`test_net_worth_report_ignores_opening_the_day_after_window_end`) |
| M10 (re-run) | update | date-only opening move skipped for `credit_card` | KILLED (`test_update_credit_card_date_only_moves_the_opening_date`) |
| M12 (re-run) | create | zero balance without date stores today for `credit_card` | KILLED (`test_create_credit_card_zero_balance_has_no_opening_and_no_date`) |
| N-c | create | opening tx dated today instead of `account.balance_date` | KILLED (`test_create_account_with_balance_date`) |
| N-e | update | non-zero update ignores stored date, uses today | KILLED (`test_sequential_writes_...`) |
| N-f | update | balance update does not realign the existing opening `date` | KILLED (`test_sequential_writes_...`) |
| N-g | create | default date for balance `> 0` or credit card only (negative gets NULL) | KILLED (`test_create_account_with_negative_balance`) |
| N-h | migration 098 | `max` -> `min` | KILLED (`test_upgrade_backfills_manual_accounts_...`) |
| N-i | `_find_balance_resets` | earlier-history `<` -> `<=` | KILLED (`..._transaction_on_opening_day_is_not_earlier_history`) |
| N-j | update | non-credit-card update clears `balance_date` | KILLED (`test_update_with_null_balance_date_leaves_the_stored_date`) |
| N-k | update | zero-balance branch keeps the opening tx when a date is sent | KILLED (`test_update_to_zero_balance_with_date_stores_date_and_deletes_opening`) |
| N-m | update | date written only if the account has none | KILLED (`test_update_account_accepts_a_future_balance_date`) |
| N-a | update | date-only move skips `apply_effective_date` on the opening tx | SURVIVED. Non-equivalent but secondary: `effective_date` of the opening tx (only differs from `date` for credit cards under bill bucketing); pre-existing call (present at f56667f), asserted by no test; the floor reads `Transaction.date`. SUGGESTION N10 |
| N-b | create | `apply_effective_date` dropped for the opening tx | SURVIVED. Same cause, pre-existing behavior, same SUGGESTION N10 |
| N-d | serializer | `balance_date` returned as None for `credit_card` only | SURVIVED. Type-gated contrived mutant (the unconditional form S1 is killed); no credit-card list/detail read test. SUGGESTION N11 |
| N-l | `import_service.py` | import stamps `balance_date = today` on accounts with NULL | SURVIVED. Mutation lives in code the feature does not touch; no committed end-to-end import test (the iteration-2/3 import probe was scratch). Create-side regression is pinned by `test_accounts_api.py:1110`. SUGGESTION N12 |

**Totals (iteration 4)**: 18 runs: 5 re-runs of earlier survivors (5 killed) plus 13 new distinct mutants (9 killed, 4 survived, none on a P0 path). **Cumulative**: 72 distinct mutants injected, 67 killed, 5 survived (F1 equivalent in effect; N-a, N-b, N-d, N-l non-equivalent but outside P0 write rules, floor, backfill and the create regression: credit-card-only gating, the pre-existing opening-tx `effective_date` and an untouched import path).

---

## Gate Check (item 5, real tree, read-only)

- **Backend** (iteration 4, HEAD 8e97364): `cd backend && .venv/bin/python -m pytest -q` -> 4449 passed, 8 skipped, 0 failed (iteration 3: 4439; iteration 2: 4433; iteration 1: 4426; previous release: 4394). `ruff check .` -> All checks passed. `ty check` -> All checks passed.
- **Frontend**: `npm run typecheck` clean, `npm run lint` clean, `npx vitest run` -> 112 files, 967 passed, 0 failed (unchanged by F5 and F6).
- **Skipped**: 8 backend skips pre-existing, unchanged.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / surgical changes | OK. Fix commits touch only create, the dialog payload, and tests. `model_fields_set` check is redundant (SUGGESTION) |
| Tests map to ACs | OK; each new test cites its AC |
| Test integrity | OK (see review table): fixture mirroring only, two dialog assertions changed as AC7 requires |
| Documented guidelines | `CONTRIBUTING.md`, `backend/pyproject.toml`, `frontend/package.json` followed |

---

## Ranked Gaps

| # | Severity | Gap | Location |
| - | -------- | --- | -------- |
| N7 | CLOSED in iteration 4 | AC13 tests at service and HTTP level; M11/M13 killed | `test_account_service.py:252,266,285`; `test_accounts_api.py:1082,1098,1127` |
| N8 | CLOSED | day-after-window-end case, M8 killed | `test_report_service.py:2889` |
| N9 | CLOSED | credit-card create, zero-balance and date-only update tests, M10/M12 killed | `test_account_service.py:302-345` |
| N10 | SUGGESTION | The opening tx `effective_date` is asserted by no test (N-a, N-b survive); only matters for credit cards under bill bucketing; behavior pre-dates the feature | `account_service.py:310,424,435,448` |
| N11 | SUGGESTION | No credit-card account read (list/detail) asserts `balance_date` (N-d, type-gated mutant) | `test_accounts_api.py:1030,1046` |
| N12 | SUGGESTION | No committed end-to-end test that a CSV import leaves a NULL `balance_date` untouched and counts the imported history (N-l); the create side is pinned by `test_accounts_api.py:1110` | `backend/app/services/import_service.py:1068` |
| N2 | SUGGESTION | Redundant `model_fields_set` expression (equivalent to `data.balance_date`) | `account_service.py:272` |
| N3 | SUGGESTION | `test_dashboard_api.py::test_balance_date_parameter_overrides_default_cutoff` fixture date is vestigial after the owner decision | `test_dashboard_api.py:553-557` |
| N5 | SUGGESTION | ABD-04 AC2/AC3 display tests assert the year only; the create payload date is exact elsewhere | `accounts-dialog.test.tsx:325-334` |
| N6 | SUGGESTION | No UI hint at import time that rows before an account's balance date do not move the balance (iteration-1 G6, out of scope) | `frontend/src/pages/import.tsx` |

(N1 and N4 were closed in iteration 3.) No fix plan: no blocking gap remains.

---

## Requirement Traceability Update

| Requirement | Previous Status | New Status |
| ----------- | --------------- | ---------- |
| ABD-01 | Verified (AC11/AC12 covered); future-date test gap N7 | Verified (AC13 covered) |
| ABD-02 | Needs Fix | Verified |
| ABD-03 | Verified with gap G2 | Verified (automated) |
| ABD-04 | Verified | Verified (AC7 added and covered) |

---

## Summary

**Overall**: Ready. The only blocker (N7) is closed with discriminating tests; remaining items are SUGGESTIONs.

**Spec-anchored check**: all 34 ACs/edge cases covered (AC13 added), 0 uncovered; AC13 evidence independently re-derived at service and HTTP level
**Sensor**: 18 runs this iteration (5 re-runs killed, 13 new: 9 killed, 4 survived outside P0); cumulative 72 distinct, 67 killed, 5 survived (1 equivalent, 4 non-P0 suggestions)
**Gate**: backend 4449 passed / 8 skipped, ruff and ty clean; frontend 967 passed, typecheck and lint clean

**What works**: M11, M13, M8, M10, M12 now die; write rules (create, update, zero-balance, future date), floor, backfill and the zero-balance create regression have no surviving non-equivalent mutant.
