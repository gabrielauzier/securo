# Credit Card Bills Validation

**Date**: 2026-10-13
**Spec**: `.specs/features/credit-card-bills/spec.md`
**Diff range**: `7da4813..HEAD` (HEAD `3db59bc`, 58 commits, 131 files)
**Verifier**: independent sub-agent (author ≠ verifier)

## Validation: Credit Card Bills - FAIL ❌

The tests that exist are strong: every gate is green and all 15 mutations were killed. The verdict is FAIL because two write paths break AD-004 and the spec edge case for a deleted payment. Reproductions in a scratch worktree confirmed both:

1. **Undoing an import does not refresh bills.** `DELETE /api/import-logs/{id}` (`backend/app/api/import_logs.py:93-97`) bulk-deletes the import's transactions with no `collect_bill_ids` / `refresh_bills`. In the probe, a card import linked a 100.00 row to the 2026-09 bill. After the undo the row was gone, but `computed_total` stayed at `100.00`. On a checking import, deleting a linked payment the same way leaves `paid_amount` and `settled_on` stale. The bill then reads `paid`, and `settlement` keeps the purchases recognized.
2. **Deleting a non-card account that holds a linked payment does not refresh the bill.** `account_service.delete_account` (`backend/app/services/account_service.py:622`) removes the payments through the ORM cascade. In the probe, `paid_amount` stayed at `100.00` after the account was deleted. This breaks the edge case "WHEN a linked payment transaction is deleted THEN the system SHALL drop the link and recompute the bill status" on this path.
3. **The edge case "WHEN a card account is deleted THEN the system SHALL delete its bills and unlink their payments" has no test.** On PostgreSQL the behavior is correct: the probe showed the bills removed through `credit_card_bills.account_id ON DELETE CASCADE` (migration `040`) and `paid_bill_id ON DELETE SET NULL` (migration `099`). No feature test asserts it, and the SQLite test schema does not enforce foreign keys. Under evidence-or-zero this counts as NOT covered.

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1-T54 | ✅ Done | All task checkboxes are `[x]` in `tasks.md`. |
| T50 browser check | ⏳ Pending | `tasks.md:1442`: the 375 px check of BVIEW AC 1 and AC 11 is pending with the orchestrator (known open item). |

---

## Spec-Anchored Acceptance Criteria

Paths are relative to `backend/tests/` (backend) or `frontend/src/` (frontend).

### BILL-01 / BILL-02 / BILL-03 / BILL-04: P1 bills exist

| Criterion | Spec-defined outcome | `file:line`: assertion | Result |
| --------- | -------------------- | ---------------------- | ------ |
| AC1 at most one bill per card per month | one bill | `test_bill_service.py:166-177`: `created_again is False`, `count == 1`; `:189` `pytest.raises(IntegrityError)` | ✅ |
| AC2 close 5 / due 12 / ref 2026-09 | period 08-05..09-04, close 09-05, due 09-12, effective 09-14 | `test_bill_period.py:18-25`: `== BillPeriod(... date(2026,9,14))`; API `test_credit_card_bills_api.py:136-140` | ✅ |
| AC3 close 31 in a 30-day month | clamped to the 30th | `test_bill_period.py:31`: `period.close_date == date(2026, 9, 30)` | ✅ |
| AC4 year boundary | 2026-12-05..2027-01-04 | `test_bill_period.py:40-41` | ✅ |
| AC5 returned fields | computed, declared (nullable), paid, remaining ≥ 0, overpaid, status, source | `test_credit_card_bills_api.py:142-150`: `remaining_amount == 783.20`, `overpaid_amount == 0.0`, `source == "auto"`, `declared_total is None`; `test_bill_service.py:72` overpaid `16.80` | ✅ |
| AC6 status derived, not stored | precedence order | `test_bill_service.py:109-114`: `[open, partially_paid, overdue]`, `not hasattr(bill, "status")`; precedence `:75-99` | ✅ |
| AC7 manual bill | source `manual`, links period rows without override | `test_bill_manual.py:87-99`: `source == "manual"`, `overridden.bill_id is None`, `close_day.bill_id is None` | ✅ |
| AC8 duplicate month | 409, nothing stored | `test_bill_manual.py:139-141`: `status_code == 409`, count `== 1`; API `test_credit_card_bills_api.py:249` | ✅ |
| AC9 edit declared total | target, remaining and status recomputed | `test_bill_manual.py:169-174`: target `500.00`, remaining `0.00`, `"paid"` | ✅ |
| AC10 provider dates | 422 | `test_bill_manual.py:196`: `status_code == 422`; API `test_credit_card_bills_api.py:318` | ✅ |
| AC11 delete auto/manual | unlink rows and payments, keep transactions | `test_bill_manual.py:250-254`: `purchase.bill_id is None`, `payment.paid_bill_id is None`; pair undone `test_bill_payment_pairing.py:218-220` | ✅ |
| AC12 cycle change | unpaid bills re-dated and relinked; paid bills unchanged | `test_bill_linking.py:214-228`; `test_account_cycle_relink.py:86-99` | ✅ |
| AC13 no cycle | no automatic bills | `test_bill_linking.py:156-158`: `LinkSummary(0, 0)`, `{}`; migration `test_credit_card_bills_backfill_migration.py:223` | ✅ |
| AC14 backfill | auto bills cover rows, links them, idempotent | `test_credit_card_bills_backfill_migration.py:201-205`, `:238-239` (`second == first`) | ✅ |
| AC15 provider bills untouched | dates, totals and links kept | `test_credit_card_bills_backfill_migration.py:252-260` | ✅ |

### BIMP-01: P1 imported transactions join their bill

| Criterion | Spec-defined outcome | `file:line`: assertion | Result |
| --------- | -------------------- | ---------------------- | ------ |
| AC1 link on import, sync and manual entry | bill of the period | `test_import_bills.py:74-77`; sync `test_sync_bills.py:114-116`; manual `test_transaction_bill_hooks.py:107` | ✅ |
| AC2 create a missing bill | `auto` bill | `test_bill_linking.py:79,85`: `bills_created=3`, `{"auto"}` | ✅ |
| AC3 close-day row | next bill | `test_bill_linking.py:83`; `test_bill_period.py:64` | ✅ |
| AC4 override | bill whose effective or nominal due equals the override; none created | `test_bill_linking.py:129-133`: `bills_created=0`, `orphan.bill_id is None` | ✅ |
| AC5 date or account change | relinked | `test_transaction_bill_hooks.py:141-143` (date), `:155-157` (account) | ✅ |
| AC6 import reports counts | linked + created | `test_import_bills.py:69`: `(3, 3)`; route `:102-103` | ✅ |
| AC7 same file twice | no duplicate bill | `test_import_bills.py:85-86`: `(0, 0)`, `len == 3` | ✅ |
| AC8 installment | bill of its own date | `test_bill_linking.py:149`; `test_transaction_bill_hooks.py:128` | ✅ |

### BPAY-01 / BPAY-02 / BPAY-03: P1 bill payments

| Criterion | Spec-defined outcome | `file:line`: assertion | Result |
| --------- | -------------------- | ---------------------- | ------ |
| AC1 link records and recomputes | link + paid + status | `test_bill_payment_service.py:79-82` | ✅ |
| AC2 payment out of totals in every mode | excluded from dashboard, reports, budgets | cash/accrual: `test_bill_payment_pnl.py:88,101-103,113-114,140`; settlement: `test_dashboard_settlement.py:54` (Sept expenses `== 1000.0` with a 1,000.00 payment linked) | ✅ |
| AC3 pair with the card credit | transfer pair | `test_bill_payment_pairing.py:102-106` | ✅ |
| AC4 no credit | link kept, `needs_counterpart` | `test_bill_payment_pairing.py:120-123`; API `test_transactions_bill_fields_api.py:78` | ✅ |
| AC5 reference payment | `paid`, remaining 0 | `test_bill_payment_service.py:82-83` | ✅ |
| AC6 500.00 of 1,283.20 | `partially_paid`, 783.20 | `test_bill_payment_service.py:92-93` | ✅ |
| AC7 two partials | `paid` | `test_bill_payment_service.py:103` | ✅ |
| AC8 overpayment | `paid` + overpaid | `test_bill_payment_service.py:113-114`: `overpaid == 16.80` | ✅ |
| AC9 unlink | link removed, pair undone, status recomputed | `test_bill_payment_pairing.py:160-166` | ✅ |
| AC10 ineligible | 422 | `test_bill_payment_service.py:152` (credit, card, ignored, currency) | ✅ |
| AC11 already pays another | 409 | `test_bill_payment_service.py:167` | ✅ |
| AC12 cross-workspace | 404 | `test_bill_payment_service.py:197`: `(404, 404)`; API `test_credit_card_bills_api.py:500` | ✅ |
| AC13 `is_bill_payment` category | excluded before linking | `test_bill_payment_pnl.py:102,114` (200.00 unlinked in the flagged category gives 0.0) | ✅ |

### BDAY-01 / BMATCH-01 / BMATCH-02 / BMATCH-03: P2 matching

| Criterion | Spec-defined outcome | `file:line`: assertion | Result |
| --------- | -------------------- | ---------------------- | ------ |
| AC1 weekend or holiday | next business day | `test_business_days.py:97,101,111` | ✅ |
| AC2 Easter-derived holidays 2026-28 | Easter 04-05, 03-28, 04-16 | `test_business_days.py:24,81`: exact holiday sets | ✅ |
| AC3 window `[close, eff due + 5]`, remaining > 0 | candidate | `test_bill_match_candidates.py:90,121` | ✅ |
| AC4 unique exact pair | auto-link | `test_bill_match_apply.py:79-81` | ✅ |
| AC5 below remaining | `partial`, not linked | `test_bill_match_apply.py:128-130`; `test_bill_match_candidates.py:111` | ✅ |
| AC6 several bills or payments | suggestions only | `test_bill_match_apply.py:94-96,112-115` | ✅ |
| AC7 matcher on import, sync, entry, new bill | runs | `test_import_bill_match.py:87,106`; `test_sync_bills.py:209`; `test_transaction_bill_hooks.py:320,340,354` | ✅ |
| AC8 dialog fields and order | candidates first, then other unpaid bills | `test_credit_card_bills_api.py:572-583`; `components/link-bill-dialog.test.tsx` (row text + `DOCUMENT_POSITION_FOLLOWING`) | ✅ |
| AC9 dismiss | never suggested again | `test_bill_match_dismiss.py:84-86`; API `test_credit_card_bills_api.py:677` | ✅ |
| AC10 preview writes nothing | checkbox list, no write | `test_credit_card_bills_api.py:611-619`; `components/bill-match-apply-dialog.test.tsx:74` | ✅ |
| AC11 apply checked | linked count + failures with reason | `test_bill_match_apply.py:171-178`; `test_credit_card_bills_api.py:638` | ✅ |
| AC12 reference payment 09-14 | inside the window | `test_bill_match_candidates.py:74` | ✅ |
| AC13 09-20 vs eff due 09-14 | not auto-linked, listed as other | `test_bill_match_candidates.py:100`; `test_bill_match_apply.py:141-143` | ✅ |
| AC14 indicator "Possível pagamento de fatura" | shown with confirm and dismiss | `pages/transactions-bill-payment.test.tsx:198-234`; API `test_credit_card_bills_api.py:665` | ✅ |
| AC15 hint ranking | hinted ranks higher at equal amount and distance | `test_bill_match_candidates.py:167-169` | ✅ |

### BREP-01 / BREP-02: P2 settlement mode

| Criterion | Spec-defined outcome | `file:line`: assertion | Result |
| --------- | -------------------- | ---------------------- | ------ |
| AC1 three modes, default cash | accepted | `test_credit_card_accounting_mode.py:345` (`"cash"`), `:2023-2042` | ✅ |
| AC2 paid bill on the completing payment date | realized | `test_dashboard_settlement.py:167-171`; `test_settlement_filters.py:48` | ✅ |
| AC3 unpaid bill projected in the effective due month | projected, not realized | `test_dashboard_settlement.py:116-121` | ✅ |
| AC4 overdue in a past month | projected in the current month | `test_dashboard_settlement.py:130-135`; `test_settlement_filters.py:67` | ✅ |
| AC5 1,000.00 paid 09-14 | Sept 600/400, Aug none | `test_dashboard_settlement.py:54-60` | ✅ |
| AC6 500.00 on 09-14 | 0 realized, 1,000 projected | `test_dashboard_settlement.py:142-146` | ✅ |
| AC7 + 500.00 on 09-20 | realized, recognition 09-20 | `test_dashboard_settlement.py:72-78` | ✅ |
| AC8 unlink the completing payment | back to projected | `test_dashboard_settlement.py:157-160` | ✅ |
| AC9 card rows without a bill | purchase date | `test_settlement_filters.py:88` | ✅ |
| AC10 dashboard, categories, budgets, reports, splits | mode applied | `test_budget_settlement.py:42-46`; `test_report_settlement.py:55-59`; `test_split_offsets_mode.py:98-111` | ✅ |
| AC11 open bills value | sum of remaining of unpaid bills | `test_dashboard_settlement.py:203`: `== 700.0`; `pages/dashboard.test.tsx:158` | ✅ |
| AC12 drill-down main date + "Lançada em" line | bucketing date + purchase line | `components/transaction-drill-down.test.tsx:159-160` (accrual), `:167-168` (settlement) | ✅ |
| AC13 unpaid purchase | projected badge, effective due date | `components/transaction-drill-down.test.tsx:176-177` | ✅ |
| AC14 cash unchanged | no extra line | `components/transaction-drill-down.test.tsx:185-187` | ✅ |
| AC15 sorted by main date | order | `components/transaction-drill-down.test.tsx:208` | ✅ |
| AC16 admin describes three modes | pick one | `pages/admin/settings-accounting-mode.test.tsx:70,108` | ✅ |

### BVIEW-01: P3 consolidated page

| Criterion | Spec-defined outcome | `file:line`: assertion | Result |
| --------- | -------------------- | ---------------------- | ------ |
| AC1 nav + palette at `/accounts/credit-cards` | sub-item | `lib/nav-items.test.ts:119`; `components/command-palette-credit-cards.test.tsx:40`; `App.routes.test.tsx:32` | ✅ (browser check pending, T50) |
| AC2 month of the next effective due date | all cards | `pages/credit-cards.test.tsx:164` (`September 2026`) | ✅ |
| AC3 `?account=<id>` scopes figures | URL + figures | `pages/credit-cards.test.tsx:205-212` | ✅ |
| AC4 previous and next month | matching bills | `pages/credit-cards.test.tsx:230-236` | ✅ |
| AC5 month figures | sums, earliest due, limits | `pages/credit-cards.test.tsx:165-170`; shared limit `components/credit-card/bill-summary-card.test.tsx:64-70` | ✅ |
| AC6 bill rows | card, status, due, totals, difference, payment links | `pages/credit-cards.test.tsx:177-181` | ✅ |
| AC7 transactions + card column | columns | `pages/credit-cards.test.tsx:190-192` | ✅ |
| AC8 equals the account detail page | same figures | `pages/credit-cards.test.tsx:177` asserts the API values; no side-by-side comparison with the account detail page | ⚠️ Spec-precision gap (both pages read the same API, so equality is structural) |
| AC9 empty state | create call | `pages/credit-cards.test.tsx:251-252` | ✅ |
| AC10 unconfigured card | configure call | `pages/credit-cards.test.tsx:261-262` | ✅ |
| AC11 375 px no horizontal scroll | browser | none | ⏳ Pending, T50 (known open item) |

**Status**: ❌ Gaps present. All ACs are covered except BVIEW AC 11 (pending, known). Three edge-case or AD-004 defects are listed below.

---

## Edge Cases

| Edge case | Evidence | Result |
| --------- | -------- | ------ |
| close = due = 10 | `test_bill_period.py:49-51` | ✅ |
| nominal due 2026-09-07 gives 09-08 | `test_bill_period.py:57-58` | ✅ |
| payment amount 0 or negative gives 422 | `test_bill_payment_service.py:133-152` (`zero`, `negative`) | ✅ |
| negative declared total gives 422 | `test_bill_manual.py:148`; API `test_credit_card_bills_api.py:265,307` | ✅ |
| closed card still accepts payments | `test_bill_payment_service.py:208` | ✅ |
| linked payment deleted: link dropped, status recomputed | `test_transaction_bill_hooks.py:280-281` (single delete), `:297-298` (bulk) | ❌ **Fails on two other delete paths**: import undo and non-card account delete (reproduced, see Verdict 1-2) |
| card account deleted: bills deleted, payments unlinked | no test; behavior holds on PostgreSQL through FK cascades (probe) | ❌ **No evidence** (Verdict 3) |
| concurrent imports create the same bill | `test_bill_service.py:330-335`: one bill id, `count == 1` (PostgreSQL) | ⚠️ Spec-precision gap: "link both batches to it" is not asserted |
| empty bill: total 0, `paid` once closed | `test_bill_service.py:97-99`, `:289` | ✅ |
| incompatible cycle days give 422 `incompatible_cycle_days` | `test_account_cycle_relink.py:153-156,176-179` | ✅ |

---

## AD-004 Write-Path Audit

| Write path | Bill hook | Test | Result |
| ---------- | --------- | ---- | ------ |
| `transaction_service.create_transaction` | `_sync_card_bills` + auto-match (`:777-780`) | `test_transaction_bill_hooks.py:99,309` | ✅ |
| `create_installment_series` | `_sync_card_bills` (`:880`) | `test_transaction_bill_hooks.py:111` | ✅ |
| `create_transfer` | `_sync_card_bills` (`:1008`) | `test_transaction_bill_hooks.py:195` | ✅ |
| `create_transfer_counterpart` | `_sync_card_bills` (`:1272`) | `test_transaction_bill_hooks.py:212` | ✅ |
| `link_existing_as_transfer` | `touch` (`:1180`) | `test_bill_payment_pairing.py:194` | ✅ |
| `update_transaction` | `collect_bill_ids` + `_sync_card_bills` + auto-match (`:1749-1784`) | `test_transaction_bill_hooks.py:132,146,166,325` | ✅ |
| `bulk_update_category` | `touch` (`:1804`) | `test_transaction_bill_hooks.py:244` | ✅ |
| `bulk_set_ignored` | `touch` (`:1830`) | `test_transaction_bill_hooks.py:237` | ✅ |
| `toggle_ignore_transaction` | `touch` (`:2034`) | `test_transaction_bill_hooks.py:225` (mutant M12 killed) | ✅ |
| `delete_transaction` | `collect_bill_ids` → `refresh_bills` (`:2100-2106`) | `test_transaction_bill_hooks.py:259,266` | ✅ |
| `bulk_delete_transactions` | `collect_bill_ids` → `refresh_bills` (`:2147-2152`) | `test_transaction_bill_hooks.py:284` | ✅ |
| `import_service.import_transactions` | `link_account_transactions` + `run_auto_match` | `test_import_bills.py:65`; `test_import_bill_match.py:78` | ✅ |
| `connection_service` sync | `_sync_account_bills` + `_match_bill_payments` | `test_sync_bills.py:106,201`; `test_account_cycle_relink.py:191` | ✅ |
| `recurring_transaction_service.generate_pending` | `link_account_transactions` | `test_recurring_bills.py:47-51` | ✅ |
| `account_service.update_account` (cycle) | `relink_account` | `test_account_cycle_relink.py:60,191` | ✅ |
| `category_service` flag change | `refresh_workspace_bills` | `test_category_bill_payment.py:69,97` | ✅ |
| `transfer_detection_service` apply, detect and unlink pairs | `touch` | `test_transfer_pairing_bills.py:82,92`; `test_bill_payment_pairing.py:149` | ✅ |
| `bill_payment_service.link_payment` / `unlink_payment`, `bill_service` CRUD | `refresh_bills` | see BPAY / BILL-02 rows | ✅ |
| **`api/import_logs.delete_import_log`** (`backend/app/api/import_logs.py:93-97`) | **none** | **none**; probe: `computed_total` stays `100.00` after undo | ❌ |
| **`account_service.delete_account`** (`backend/app/services/account_service.py:622`) for an account holding linked payments | **none** | **none**; probe: `paid_amount` stays `100.00` after delete | ❌ |
| `connection_service` phantom/twin cleanup `session.delete(tx)` (`:1645`) on a non-card linked payment | only card bills of synced cards refreshed | none | ⚠️ Low-likelihood; not reproduced |
| `account_service.delete_account` for a card | DB cascade (`040` CASCADE, `099` SET NULL) | none (see Edge Cases) | ⚠️ Correct on PostgreSQL, untested |

---

## Discrimination Sensor

Scratch: temporary `git worktree add --detach <scratchpad>/mut HEAD`. For each mutant, one file was rewritten, the 46 feature test files (backend, PostgreSQL included) or the drill-down vitest file were run, and the file was restored. The scratch worktree was then removed with `git worktree remove --force`. The real-tree `git status --porcelain` matched the pre-sensor baseline (empty).

| # | File:line | Mutation | Killed? | Killing test |
| - | --------- | -------- | ------- | ------------ |
| M1 | `backend/app/core/business_days.py:64` | business day ignores national holidays | ✅ | `test_bill_period.py::test_effective_due_date_on_holiday_rolls_to_next_business_day` |
| M2 | `backend/app/services/credit_card_service.py:195` | close-day boundary `<=` → `<` | ✅ | `test_bill_linking.py::test_rows_join_the_bill_of_their_period_creating_missing_bills` |
| M3 | `backend/app/services/bill_service.py:73` | status precedence: `partially_paid` before `overdue` | ✅ | `test_bill_service.py::test_after_effective_due_partially_paid_is_overdue` |
| M4 | `backend/app/services/bill_service.py:154` | computed total counts ignored rows | ✅ | `test_bill_service.py::test_computed_total_excludes_non_purchase_rows` |
| M5 | `backend/app/services/bill_service.py:162` | computed total keeps the payment's card leg | ✅ | `test_bill_payment_pairing.py::test_payment_is_paired_with_the_card_credit_inside_the_window` |
| M6 | `backend/app/services/bill_service.py:210` | `settled_on` crossing `>=` → `>` | ✅ | `test_bill_manual.py::test_editing_the_declared_total_recomputes_target_remaining_and_status` |
| M7 | `backend/app/services/_query_filters.py:288` | `counts_as_pnl` drops the `paid_bill_id IS NULL` exclusion | ✅ | `test_bill_payment_pnl.py::test_dashboard_expenses_exclude_bill_payments[cash]` |
| M8 | `backend/app/services/bill_match_service.py:246` | auto-match ignores the one-payment-per-bill rule | ✅ | `test_bill_match_apply.py::test_two_payments_at_the_bill_amount_are_only_suggested` |
| M9 | `backend/app/services/_query_filters.py:177` | `is_recognized` → `true()` in settlement | ✅ | `test_budget_settlement.py::test_mercado_actual_counts_only_after_the_bill_is_paid` |
| M10 | `backend/app/services/_query_filters.py:162` | `reporting_date_col`: overdue branch removed | ✅ | `test_dashboard_settlement.py::test_overdue_bill_is_projected_in_the_current_month` |
| M11 | `backend/app/services/bill_match_service.py:23` | match window +5 → +4 days | ✅ | `test_bill_match_candidates.py::test_window_bounds_are_close_date_and_effective_due_plus_five` |
| M12 | `backend/app/services/transaction_service.py:2034` | AD-004: `toggle_ignore` skips `touch` | ✅ | `test_transaction_bill_hooks.py::test_toggle_ignore_transaction_refreshes_the_bill` |
| M13 | `backend/app/services/bill_payment_service.py:116` | `link_payment` never pairs the card credit | ✅ | `test_bill_match_apply.py::test_auto_match_pairs_the_payment_with_the_card_credit` |
| M14 | `frontend/src/components/transaction-drill-down.tsx:123` | main date = purchase date | ✅ | `transaction-drill-down.test.tsx` (4 failed) |
| M15 | `frontend/src/components/transaction-drill-down.tsx:133` | projected badge dropped | ✅ | `transaction-drill-down.test.tsx` (1 failed) |

**Sensor depth**: P0 expanded (15 manual behavior-level mutations; no mutation tool configured)
**Sensor outcome**: 15/15 killed (sensor passes)

---

## Gate Check

- **Backend**: `TZ=UTC python -m pytest -q` with `POSTGRES_TEST_URL` set to a throwaway `public.ecr.aws/supabase/postgres:17.11.0.002` container, since removed. Result: **4760 passed, 0 failed, 0 skipped** (PostgreSQL-only tests ran).
- **Backend lint/types**: `ruff check .`: all checks passed; `ty check`: all checks passed.
- **Frontend**: `npm run typecheck && npm run lint && npm test`: exit 0; **123 files, 1051 tests passed**.
- **Test count before feature** (`7da4813`): backend 4457 collected, frontend 968 listed. **After**: 4760 / 1051. **Delta**: +303 / +83. No decrease.
- **Skipped tests**: none.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / surgical changes / no scope creep | ✅ |
| Matches patterns | ✅ |
| Spec-anchored outcome check | ✅ (2 spec-precision gaps flagged) |
| Per-layer coverage (domain 1:1, routes happy + edge + error, viewer 403) | ✅ |
| AD-004: every card/payment write path refreshes bills | ❌ (2 paths) |
| Documented SPEC_DEVIATIONs | `bill_match_service.py:104` (above-remaining payment listed as `partial`, never auto-linked) and `:316` (no savepoint per pair; validation precedes writes). Both reviewed; neither violates an AC. |

---

## Fix Plans

### Fix 1: Undoing an import refreshes the bills it touched (Major)
- **Root cause**: `delete_import_log` bulk-deletes with `delete(Transaction)` and never refreshes bills.
- **Fix task**: Before the delete, `bill_ids = await bill_service.collect_bill_ids(session, tx_ids)`. After the delete, `await bill_service.refresh_bills(session, bill_ids)`, and undo any `bill_payment_pair` transfer as `delete_transaction` does. Test: import card rows, link a checking payment from a second import, undo each import, then assert `computed_total == 0.00`, `paid_amount == 0.00` and `settled_on is None`.
- **Where**: `backend/app/api/import_logs.py`, new test in `backend/tests/test_transaction_bill_hooks.py` or `test_import_bills.py`.

### Fix 2: Deleting an account refreshes the bills its payments paid (Major)
- **Root cause**: `delete_account` cascades the account's transactions without touching `paid_bill_id` bills.
- **Fix task**: Before `session.delete(account)`, collect `paid_bill_id`s of the account's rows that sit on other accounts' bills. Unlink any transfer pairs created by the link, then `refresh_bills` after the flush. Test: link a checking payment, delete the checking account, then assert the bill is `paid_amount == 0.00`, `settled_on is None` and its status is no longer `paid`.
- **Where**: `backend/app/services/account_service.py:622`, a test in `backend/tests/test_transaction_bill_hooks.py`.

### Fix 3: Test the card-account deletion edge case (Minor)
- **Fix task**: A PostgreSQL test (`postgres_sessions`): delete a card with a bill and a linked checking payment, then assert no bill remains for the card and `payment.paid_bill_id is None`. Optionally delete the bills explicitly in `delete_account` so SQLite matches.

### Fix 4: Spec-precision gaps (Minor)
- Concurrent creation: extend `test_bill_service.py::test_concurrent_get_or_create_keeps_one_bill` to link one row per session and assert both rows carry the single bill id.
- BVIEW AC 8: optionally assert in one test that the account detail page and `/accounts/credit-cards?account=<id>` render the same target, paid and remaining for the same bill payload.

---

## Known Open Items (tracked by the orchestrator; not counted as failures)

- T50: the 375 px browser check (BVIEW AC 1 and AC 11) is pending.
- The settlement transactions-page summary counts projected purchases. This is outside the spec.
- The import screen does not show `bills_linked` / `bills_created`. The API returns them (BIMP AC 6 is met at the API, `test_import_bills.py:102-103`).

---

## Requirement Traceability Update

| Requirement | New status |
| ----------- | ---------- |
| BILL-01, BILL-02, BILL-03, BILL-04, BIMP-01, BPAY-02, BPAY-03, BDAY-01, BMATCH-01, BMATCH-02, BMATCH-03, BREP-01, BREP-02 | ✅ Verified |
| BPAY-01 | ❌ Needs fix (deleted-payment edge case on the import-undo and account-delete paths) |
| BVIEW-01 | ⏳ Verified except AC 11 (T50 pending) |

---

## Summary

**Overall**: ❌ Not ready

**Spec-anchored check**: 77/78 ACs match the spec outcome (BVIEW AC 11 pending). 2 spec-precision gaps are flagged (BVIEW AC 8, concurrent-import edge case). 2 edge cases fail (deleted payment on two paths; card-account deletion untested).
**Sensor**: 15/15 mutations killed
**Gate**: backend 4760 passed; frontend 1051 passed; ruff and ty clean

**What works**: period math, the business-day calendar, status precedence, stored aggregates, payment link and pairing, the matcher, settlement bucketing and recognition, the drill-down, the consolidated page, and every `transaction_service` / import / sync / recurring / category / cycle write path.

**Next steps**: Fixes 1-2 (Major), then Fix 3, then re-verify.
