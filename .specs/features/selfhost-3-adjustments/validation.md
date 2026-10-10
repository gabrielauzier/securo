# Selfhost.3 Adjustments Validation

**Date**: 2026-10-10
**Spec**: `.specs/features/selfhost-3-adjustments/spec.md`
**Diff range**: `2cf3480..HEAD` (HEAD = 143d756, branch `feat/selfhost-3-adjustments`, 44 commits; includes iteration-1 fixes fbf444f, 4e52998, 6abdd63, 8bd14e2, 3be2e1c and iteration-2 fixes bfce5bf, 90d2e59, 6bac023, 22a547b, 143d756)
**Verifier**: fresh independent sub-agent; iteration 4 scoped closing check (author != verifier)

**Result**: PASS

**Iteration 4 (scoped closing check, fresh Verifier)**: fix commits c624dad (F12) and b8eafaf (F11) re-verified. No uncovered AC, no CRITICAL gap, no surviving non-equivalent mutant on a P0 path. The 8 iteration-3 blockers/warnings (FE5-FE8, X19, X20) are all killed, plus 6 new mutations. Gates: backend 4394 passed / 8 skipped, ruff and ty clean; frontend typecheck and lint clean, 957 passed. The iteration-3 text below is kept as history.

Scoped findings:
- ACC-01 AC4 (edit mode shows the selected account's values): `accounts-dialog.test.tsx:185-190` asserts currency combobox `toHaveValue('USD')` for a USD account (user currency BRL) and credit limit 5000, close day 8, due day 15 (spinbuttons); name, type and balance remain pinned by `:136-149`. Now PASS.
- Name-only submit (`accounts-dialog.test.tsx:192-205`): asserts `currency: 'USD'`, the three card fields, and `not.toHaveProperty('balance'|'balance_date')`. Not a CRITICAL issue: the handler (`accounts.tsx:~751-753`) always sends `currency` for a manual account, and the backend `AccountUpdate` schema (`schemas/account.py:20-30`) has no `currency` field, so `update_account` (`account_service.py:312`, `model_dump(exclude_unset=True)`) never applies it; the currency of an existing account cannot change through this path. The assertion pins the loaded value (N6 and FE5 die on it) and no stricter expectation is warranted; the payload's `balance` omission is the edit-rule that matters and is asserted.
- TRF-01 AC4 (stale or foreign pairs skipped with a reason): `test_transfer_detection.py:668` `reason == ["already_linked"]`, `:676-692` new test `test_apply_reports_a_pair_in_another_workspace_as_not_found` asserts `(a, b, "not_found")`, linked 0 and neither leg linked, `:712` `reason == ["not_found"]` for the deleted leg. Now PASS with reason pinned.

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1-T33 | Done | tasks.md: all checked. |
| F1-F10 (Verification Fixes) | Done | F6 bfce5bf, F7 90d2e59, F8 6bac023, F9 22a547b, F10 143d756 (spec Assumptions row, `Confirmed? n`). |

F10 design residual (accepted, owner-pending assumption, not a failure): the account-detail running-balance walk (`frontend/src/pages/account-detail.tsx`) adds every in-window row, so when the chart window spans the opening date its last running balance can differ from `current_balance`; the summary seed and `current_balance` follow the floor. Recorded at `spec.md` Assumptions ("Account detail running-balance walk", Confirmed? n).

---

## Spec-Anchored Acceptance Criteria (evidence-or-zero)

Key: PASS = an assertion targets the spec outcome; PARTIAL = assertion exists but a spec'd field/value is unpinned; GAP = no evidence.

### ACC-01: New-account dialog (frontend)

| Criterion | `file:line` + assertion | Status |
| --------- | ----------------------- | ------ |
| AC1 create-mode defaults | `accounts-dialog.test.tsx:44` + `expectCreateDefaults`; payload `:151-182` currency `'BRL'`, display_name null, balance 0, balance_date == today | PASS |
| AC2 reopen after save | `accounts-dialog.test.tsx:49` and full-field reset `:68-112` (name, type, currency combobox `'BRL'`, date, balance, credit limit, close day, due day null after switching to credit card, payload) | PASS |
| AC3 reopen after close | `accounts-dialog.test.tsx:59`, `:68-112`; display name `:114-134` | PASS |
| AC4 edit mode shows selected values | `accounts-dialog.test.tsx:136-149` name `'Savings'`, type `'savings'`, balance `250.5`; `:185-190` currency `'USD'`, credit limit 5000, close day 8, due day 15 | PASS (FE5-FE8 killed in iteration 4) |
| Name-only edit keeps opening date | `accounts-dialog.test.tsx:184-192` `not.toHaveProperty('balance')`; `:194-212` both sent | PASS |

### BAL-01: Opening balance is a floor (ACs 1-5, 8, 9)

| Criterion | `file:line` + assertion | Status |
| --------- | ----------------------- | ------ |
| AC1 opening + rows >= D | `test_account_service.py:1519` `approx(1000.0)`, `:1535` `approx(800.0)`, `:1551` `approx(1200.0)` | PASS |
| AC2 pre-D excluded / stays visible | `test_opening_floor.py:52`; `test_accounts_api.py:981` (listed, balance `approx(1000.0)`) | PASS |
| AC3 dated exactly D | `test_account_service.py:1567` `approx(800.0)`; `test_opening_floor.py:67` | PASS |
| AC4 edit recompute | `test_accounts_api.py:928` (date), `:959` (amount) | PASS |
| AC5 no opening row | `test_opening_floor.py:92` | PASS |
| AC8 connected unchanged | `test_account_service.py:1603`; `test_accounts_api.py:834`; `test_dashboard_service.py:1289`; branch guard `dashboard._account_balance_at` pinned by `test_dashboard_service.py:165` (mutant X5 killed) | PASS |
| AC9 credit card | `test_account_service.py:1583`; `test_accounts_api.py:818` | PASS |
| Edge two opening rows | `test_opening_floor.py:102` | PASS |
| Edge opening deleted | `test_opening_floor.py:92` (state-equivalent) | PASS |

### BAL-02: all balance read sites (AC6) and BAL-03 (AC7)

| Site | `file:line` + assertion | Status |
| ---- | ----------------------- | ------ |
| Accounts list | `test_account_service.py:1519` | PASS |
| `previous_balance` opening before month end | `test_account_service.py:1628` `approx(950.0)` | PASS |
| `previous_balance` opening in current month (AC7) | `test_account_service.py:1646` (S4 killed) | PASS |
| Summary `current_balance` | `test_accounts_api.py:795` equals list balance | PASS |
| Summary `opening_balance`: window after / before / starting on D | `test_accounts_api.py:855`, `:880`, `:904` (S1-S3 killed) | PASS |
| Balance history | `test_account_service.py:1725`, `:1745` last point == list balance | PASS |
| Dashboard `_account_balance_at`, goals, reports | `test_dashboard_service.py:1241`, `:1263`; future clamp `:1250` and `test_account_service.py:1697` (S5 killed) | PASS |
| Dashboard `_total_balance_by_currency` | `test_dashboard_service.py:1274` (X7 killed) | PASS |
| AC7 cutoff < D includes all rows; cutoff == D floors | `test_opening_floor.py:78`; `test_account_service.py:1683`, `:1711`; `test_dashboard_service.py:1263` | PASS |

### NWN-01: Net-worth notice

| Criterion | `file:line` + assertion | Status |
| --------- | ----------------------- | ------ |
| AC1 listed with name and date | `test_report_service.py:2768` | PASS |
| AC1 negatives; window start exclusive, end inclusive | `:2787`, `:2861`, `:2885` | PASS |
| Opening-day tx / two openings / older opening row | `:2907`, `:2924`, `:2952` | PASS |
| Connected account not listed | `:2974` | PASS |
| AC2 note rendered | `reports.test.tsx` note test (per-account text) | PASS |
| AC3 empty -> no note | `test_report_service.py:2787`; `reports.test.tsx` empty case | PASS |
| AC4 collection filter | `test_report_service.py:2816` | PASS |

### IMP-01: Saved CSV import mappings

| Criterion | `file:line` + assertion | Status |
| --------- | ----------------------- | ------ |
| AC1 name non-empty <= 100 | `test_import_mapping_service.py:110`; `test_import_mappings_api.py:87` 422 | PASS (FE blank-name guard `import.tsx:609` is redundant with the disabled Save button, equivalent mutant FM6) |
| AC2 stores all fields | `test_import_mapping_service.py:59`; `test_import_mappings_api.py:60` | PASS |
| AC3 duplicate -> 409 | `test_import_mappings_api.py:77`; `test_import_mapping_service.py:90` | PASS |
| AC4 exact match applies + preselect + badge | `import-mapping.test.tsx:116`; `test_import_mapping_service.py:149` (order-insensitive, trimmed, exact set) | PASS |
| AC5 several matches | `test_import_mapping_service.py:178` | PASS |
| AC6 no match | `import-mapping.test.tsx:186`; `test_import_mapping_service.py:169` | PASS |
| AC7 adjust / switch / remove | `import-mapping.test.tsx:168`, `:203`; inflow/outflow apply `:149` | PASS |
| AC8 per user | `test_import_mapping_service.py:218`; `test_import_mappings_api.py:161` (X21-X23 killed) | PASS |
| AC9 account gone | `test_import_mapping_service.py:246`; FE `import-mapping.test.tsx:134` (FM1 killed) | PASS |
| AC10 Nubank layout | `test_import_mapping_service.py:59` | PASS |
| Edge blank/over 100; no header row | `test_import_mappings_api.py:87`; `test_import_mapping_service.py:169` | PASS |
| Destination account validation (spec Assumptions) | `test_import_mappings_api.py:195,203,212` incl. detail text; `test_import_mapping_service.py:270,290` managed workspace | PASS |

### IGN-01: Bulk ignore

| Criterion | `file:line` + assertion | Status |
| --------- | ----------------------- | ------ |
| AC1/AC2 explicit state | `test_transactions_bulk_ignore.py:81`, `:94`, `:107`; FE `transactions-bulk-ignore.test.tsx` | PASS |
| AC3 >100 -> 422, nothing changed; exactly 100 real rows | `:166`, `:180`, `:191` (B7 killed) | PASS |
| AC4 other workspace | `:117`, `:220` (X13 killed) | PASS |
| AC5 changed-row count | `:81`, `:153` (X14, X15 killed) | PASS |
| AC6 write access | `:232` | PASS |
| Edge empty list / no cascade | `:130`, `:134` | PASS |

### TRF-01: Manual pairing with preview

| Criterion | `file:line` + assertion | Status |
| --------- | ----------------------- | ------ |
| AC1 preview writes nothing | `test_transfer_detection.py:390`; `test_transfer_api.py` preview test | PASS |
| AC2 pair fields + strategy | `test_transfer_detection.py:411` | PASS |
| AC3 link chosen, atomic, count | `test_transfer_detection.py:609`; `test_transfer_api.py` apply test | PASS |
| AC4 stale (linked/deleted/foreign) skipped with reason | `test_transfer_detection.py:655,668`, `:675`, `:712` (X16-X20 killed); foreign pair `not_found` | PASS |
| AC5 all strategies disabled | `test_transfer_detection.py:455` | PASS |
| AC6 write/read gates | `test_transfer_api.py` 403/200 test | PASS |
| AC7 no suggestions | `test_transfer_detection.py:715` | PASS |
| Forged pair; rule-wide revalidation (spec Assumptions) | `:695`; `:631` (P4 killed) | PASS |
| FE only checked pairs | `components/reconciliation-rules-apply.test.tsx` | PASS |

### BTR-01: Bulk "mark as transfer"

| Criterion | `file:line` + assertion | Status |
| --------- | ----------------------- | ------ |
| AC1 selection only, rule window/tolerance | `test_transfer_detection.py:479`, `:501`, `:518`, `:535` | PASS |
| AC2 valid pair | `test_transactions_bulk_transfer.py:66` | PASS |
| AC3 ambiguous | `test_transactions_bulk_transfer.py:87`; `test_transfer_detection.py:551` | PASS |
| AC4 unmatched | `test_transactions_bulk_transfer.py:66` | PASS |
| AC5 already linked | `test_transactions_bulk_transfer.py:104`; `test_transfer_detection.py:572` | PASS |
| AC6 confirm links, count | `test_transactions_bulk_transfer.py:179` | PASS |
| AC7 >100 / >50 pairs -> 422; exactly 100 / exactly 50 accepted | `:152`, `:162`, `:170`, `:196` (B9 killed) | PASS |
| AC8 confirm needs write | `test_transactions_bulk_transfer.py:251` | PASS |
| FE grouped, only checked, cancel, >100 hint | `transactions-bulk-transfer.test.tsx` | PASS |

**Status**: 9/9 requirement IDs covered, 0 uncovered ACs, 0 CRITICAL, 0 PARTIAL (ACC-01 AC4 closed in iteration 4).

---

## Discrimination Sensor

Depth: P0-full. Scratch copy of `git archive HEAD` under `/Volumes/MacOnlySSD/tmp-verifier3` (node_modules symlinked, `PYTHONPATH` set and `app.__file__` verified to resolve to the scratch backend). Each mutation replaced a single occurrence on a named line; KILLED means a named test failed (proving the mutation took effect). A first harness run printed no failing names and was discarded and redone with `-rf` output. File restored from `git show HEAD:` after each run. Scratch deleted; `git status --porcelain` identical before and after (only `.gitignore`, `frontend/package-lock.json`, `validation.md`).

### Iteration-2 survivors re-run (23)

| # | Mutation | Result |
| - | -------- | ------ |
| S2 | `account_service.py:981` seed cutoff `date_from - 1` -> `date_from` | KILLED `test_summary_opening_balance_window_starting_on_opening_date_keeps_earlier_rows` |
| S4 | `account_service.py:101` `prev_month_end` -> `today` | KILLED `test_list_previous_balance_with_opening_in_current_month_keeps_history` |
| S5a | `account_service.py:1021` drop `min(cutoff, app_today())` | KILLED `test_balance_at_future_cutoff_stops_at_today` |
| S5b | `dashboard_service.py:1272` drop `min(cutoff, today)` | KILLED `test_account_balance_at_future_cutoff_stops_at_today` |
| B7 | `transaction_service.py:1665` `in_(transaction_ids[:99])` | KILLED `test_route_ignores_exactly_100_real_rows` |
| B9 | `schemas/transaction.py:231` pairs cap 50 -> 49 | KILLED `test_confirm_links_exactly_50_pairs` |
| A2 | `import_mapping_service.py:33` drop managed workspaces | KILLED `test_account_of_a_managed_workspace_is_accepted` |
| A5 | `api/import_mappings.py:23` 404 text changed | KILLED `test_create_with_unknown_account_is_404` |
| P4 | `transfer_detection_service.py:568` `restrict_ids=None` | KILLED `test_apply_links_a_rule_wide_pair_even_if_an_unselected_row_now_contests_a_leg` |
| FA4 | `accounts.tsx:715` no display-name reset | KILLED |
| FA5a/FA5b | `accounts.tsx:721/722` no close-day / due-day reset | KILLED / KILLED |
| FA7 | `accounts.tsx:718` no currency reset | KILLED |
| FA8 | `accounts.tsx:719` no balance-date reset | KILLED |
| FA9 | `accounts.tsx:720` no credit-limit reset | KILLED |
| FA10 | `accounts.tsx:721` no close-day reset | KILLED |
| FM1 | `import.tsx:291` account guard -> `true` | KILLED |
| FM7 | `import.tsx:298` ignore `inflow_column` on apply | KILLED |
| FA2 | `accounts.tsx:713` reset when `!open` | SURVIVED, equivalent: state is reset on close instead of on open, the next open shows the same defaults |
| FM5 | `import.tsx:306` do not store matched list | SURVIVED, equivalent: the picker already lists every saved mapping |
| FM6 | `import.tsx:609` drop `if (!name) return` | SURVIVED, equivalent: Save is disabled for a blank name |
| W1 | `transfer_detection_service.py:271` prefilter window +30 | SURVIVED, equivalent: prefilter only widens candidates; the engine's `evaluate` still enforces the real window |
| W2 | `transfer_detection_service.py:280` prefilter ratio x100 | SURVIVED, equivalent (same reason) |

### New mutations (34)

| # | File:line | Description | Result |
| - | --------- | ----------- | ------ |
| X1 | `_query_filters.py:79` | `date >= opening` -> `>` | KILLED `test_rows_before_opening_date_are_excluded_when_cutoff_is_after_it` |
| X2 | `_query_filters.py:78` | `cutoff < opening` -> `<=` | KILLED `test_balance_at_or_after_opening_date_excludes_earlier_transactions` |
| X3 | `_query_filters.py:77` | no-opening accounts excluded | KILLED `test_account_without_opening_row_is_unaffected` |
| X4 | `_query_filters.py:69` | latest -> earliest opening date | KILLED `test_latest_opening_date_wins_when_there_are_two_opening_rows` |
| X5 | `dashboard_service.py:1273` | connected-account guard `if False` | KILLED `test_account_balance_at_bank_connected` |
| X6 | `dashboard_service.py:1333` | drop floor in `_account_balance_at` | KILLED `test_account_balance_at_today_excludes_transactions_before_opening` |
| X7 | `dashboard_service.py:1397` | drop floor in `_total_balance_by_currency` | KILLED `test_total_balance_snapshots_apply_the_floor_by_cutoff` |
| X8 | `account_service.py:715` | summary `current_balance` floor removed | KILLED `test_summary_balance_applies_opening_floor_and_matches_list` |
| X9 | `account_service.py:77` | list `current_balance` floor removed | KILLED `test_list_balance_ignores_expense_dated_before_opening` |
| X10 | `report_service.py:329` | `_find_balance_resets` drop non-ignored filter | KILLED `test_net_worth_report_skips_accounts_without_a_reset` |
| X11 | `report_service.py:337` | window start `>` -> `>=` | KILLED `test_net_worth_report_ignores_opening_on_window_start_and_after_end` |
| X12 | `report_service.py:328` | drop `source != opening_balance` | KILLED `test_net_worth_report_older_opening_row_is_not_earlier_history` |
| X13 | `transaction_service.py:1666` | `bulk_set_ignored` drop workspace scoping | KILLED `test_other_workspace_rows_are_untouched_and_uncounted` |
| X14 | `transaction_service.py:1667` | drop changed-row filter (count) | KILLED `test_ignore_sets_the_flag_and_counts_only_changed_rows` |
| X15 | `transaction_service.py:1669` | invert requested state | KILLED (same test) |
| X16 | `transfer_detection_service.py:587` | `not in proposed` -> `in proposed` | KILLED `test_apply_links_the_requested_pairs_and_returns_the_count` |
| X17 | `transfer_detection_service.py:587` | forged-pair check disabled | KILLED `test_apply_rejects_a_forged_pair_the_rule_would_not_propose` |
| X18 | `transfer_detection_service.py:583` | missing-leg `or` -> `and` | KILLED `test_apply_skips_a_pair_whose_leg_was_deleted_since_the_preview` |
| X19 | `transfer_detection_service.py:585` | already-linked `or` -> `and` | **SURVIVED** (93 passed): skipped either way, only `reason` changes to `not_proposed`; spec-equivalent, WARNING |
| X20 | `transfer_detection_service.py:574` | row lookup loses workspace filter | **SURVIVED** (93 passed): probe confirmed a cross-workspace pair is still skipped, 0 linked, `reason` becomes `not_proposed` instead of `not_found`; spec-equivalent, WARNING |
| X21 | `import_mapping_service.py:83` | list drops user scoping | KILLED `test_another_users_mappings_are_invisible_and_untouchable` |
| X22 | `import_mapping_service.py:151` | match drops user scoping | KILLED (same test) |
| X23 | `import_mapping_service.py:60` | update/delete/touch drop owner check | KILLED (same test) |
| X24 | `import_mapping_service.py:43` | header set not sorted | KILLED `test_patching_headers_changes_which_uploads_match` |
| X25 | `import_mapping_service.py:43` | headers lower-cased (case-insensitive) | KILLED `test_nubank_mapping_round_trips_with_all_saved_fields` |
| X26 | `import_mapping_service.py:43` | headers not trimmed | KILLED `test_patching_headers_changes_which_uploads_match` |
| FE1 | `accounts.tsx:714` | edit load: name -> '' | KILLED |
| FE2 | `accounts.tsx:715` | edit load: display name -> '' | KILLED |
| FE3 | `accounts.tsx:716` | edit load: type -> checking | KILLED |
| FE4 | `accounts.tsx:717` | edit load: balance -> '0' | KILLED (3 tests) |
| FE5 | `accounts.tsx:718` | edit load: currency -> user currency | **SURVIVED** (10 passed) |
| FE6 | `accounts.tsx:720` | edit load: credit limit -> '' | **SURVIVED** (10 passed) |
| FE7 | `accounts.tsx:721` | edit load: close day -> '' | **SURVIVED** (10 passed) |
| FE8 | `accounts.tsx:722` | edit load: due day -> '' | **SURVIVED** (10 passed) |

**Totals**: 57 mutations (23 re-runs + 34 new): 46 killed, 11 survived. Of the 11: 5 equivalent (FA2, FM5, FM6, W1, W2), 2 spec-equivalent reason-label survivors (X19, X20), 4 real test gaps (FE5-FE8). Sensor result this iteration: 34 new injected, 28 killed, 6 survived.

---

## Gate

| Gate | Command (real tree, read-only) | Counts |
| ---- | ------------------------------ | ------ |
| Backend tests | `.venv/bin/python -m pytest -q -p no:cacheprovider` | 4393 passed, 8 skipped, 0 failed |
| Ruff | `.venv/bin/ruff check .` | All checks passed |
| Ty | `.venv/bin/ty check` | All checks passed |
| Frontend typecheck | `npm run typecheck` | clean |
| Frontend lint | `npm run lint` | clean |
| Frontend tests | `npx vitest run` | 112 files, 955 passed, 0 failed |

Test integrity: no test removed in the range; iteration-2 fix commits only add tests (+410/-1 lines in 12 files, one line of context in `test_import_mappings_api.py` edited). Skips are the 8 pre-existing ones. Real-tree `git status --porcelain` unchanged by this run.

---

## Ranked gaps (fix tasks)

Iteration 4. Former gaps 1 and 2 (FE5-FE8, X19, X20) are closed by F11/F12.

| # | Severity | Location | Gap | Fix |
| - | -------- | -------- | --- | --- |
| 1 | SUGGESTION (owner decision) | `frontend/src/pages/account-detail.tsx` | F10 residual: running-balance walk vs `current_balance` when the window spans the opening date; accepted default, `Confirmed? n` in spec.md | Owner to confirm or request a floored walk |
| 2 | SUGGESTION | `accounts.tsx:~753` | The edit payload sends `currency` for manual accounts though the backend ignores it (`AccountUpdate` has no `currency`); harmless, only noise | Optional: omit `currency` when editing |

No CRITICAL gaps. No wholly uncovered AC. Equivalent survivors (FA2, FM5, FM6, W1, W2) need no action.

---

## Code Quality Check

| Check | Pass? |
| ----- | ----- |
| No features beyond what was asked | Yes |
| No single-use abstractions | Yes |
| Only files required touched (iteration-2 fixes touch tests and spec/tasks only) | Yes |
| Matches existing patterns | Yes |
| Tests map to ACs; spec-anchored values | Yes, one PARTIAL (ACC-01 AC4) |
| Project quality guidelines | None beyond lint/typecheck gates, applied |

---

## Iteration history

| Iteration | Verdict | Summary |
| --------- | ------- | ------- |
| 1 | FAIL | CRITICAL: summary `opening_balance` unfloored (F1); BAL-01 AC4 uncovered; mutants N2, N4 (P0), N6, N7, I10, P4 survived; account_id validation missing. |
| 2 | FAIL | Iteration-1 gaps closed. Survivors S2, S4 (floor), B7, B9 (bulk cap) and unpinned dialog reset fields. |
| 3 | FAIL | Iteration-2 survivors all killed; gates green (4393 backend, 955 frontend). New pass: 34 injected, 28 killed. Blocking survivors FE5-FE8 on the `AccountDialog` edit-mode load (currency, credit limit, close day, due day); WARNING survivors X19, X20 on the skipped-pair reason label. Owner decision requested: apply fix 1 (about 6 assertions) or accept the edit-mode gap. |
| 4 (this report, scoped) | PASS | F12 c624dad and F11 b8eafaf verified. FE5-FE8, X19, X20 killed; 6 new mutations (N1-N6) all killed; 0 survivors in this pass. Gates green: backend 4394 passed / 8 skipped, frontend 957 passed, ruff, ty, typecheck, lint clean. |

### Iteration 4 sensor (scoped; scratch `git archive HEAD` copy, deleted afterwards)

| # | Mutation | Result |
| - | -------- | ------ |
| FE5 | `accounts.tsx` edit load currency -> user currency | KILLED (2 tests: shows currency and card fields; name-only submit) |
| FE6 | edit load credit limit -> '' | KILLED (same 2 tests) |
| FE7 | edit load close day -> '' | KILLED (same 2 tests) |
| FE8 | edit load due day -> '' | KILLED (same 2 tests) |
| X19 | `transfer_detection_service.py:585` already-linked `or` -> `and` | KILLED `test_apply_skips_a_pair_whose_leg_was_linked_since_the_preview` |
| X20 | `:574` drop workspace filter on row lookup | KILLED `test_apply_reports_a_pair_in_another_workspace_as_not_found` |
| N1 | edit load name -> '' | KILLED `loads the selected account in edit mode` |
| N2 | edit load type -> checking | KILLED (3 tests) |
| N3 | edit load balance -> '0' | KILLED (4 tests) |
| N4 | `apply_pairs` `linked += 1` -> `+= 0` | KILLED (3 tests incl. `test_apply_links_the_requested_pairs_and_returns_the_count`) |
| N5 | `apply_pairs` missing-leg `or` -> `and` | KILLED `test_apply_skips_a_pair_whose_leg_was_deleted_since_the_preview` |
| N6 | submit sends `userCurrency` instead of `currency` | KILLED name-only submit test |

Totals iteration 4: 12 injected, 12 killed, 0 survived (4 of them re-runs FE5-FE8, 2 re-runs X19/X20, 6 new). Cumulative: 63 mutations, 58 killed, 5 survived, all 5 equivalent (FA2, FM5, FM6, W1, W2). Gate (real tree, read-only): backend 4394 passed, 8 skipped; ruff and ty clean; frontend typecheck and lint clean, 112 files / 957 passed. `git status --porcelain` unchanged (only `.gitignore`, `frontend/package-lock.json`, `validation.md`).
