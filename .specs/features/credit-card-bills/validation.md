# Credit Card Bills Validation (round 2)

**Date**: 2026-10-13
**Spec**: `.specs/features/credit-card-bills/spec.md`
**Diff range**: `7da4813..HEAD` (HEAD `74ffcff`, 67 commits). Round 1 fixes: `7568df7..HEAD` (T55-T60 and `74ffcff`).
**Verifier**: independent sub-agent, round 2 (author ≠ verifier)

## Validation: credit-card-bills - FAIL ❌

All six round 1 gaps are closed. Each fix has a test, and a mutation that removes the fix is killed. All gates are green: backend 4765 passed, frontend 1055 passed, ruff and ty clean. The sensor killed 14 of 14 mutations.

The verdict is still FAIL because the AD-004 re-audit found two write paths outside `transaction_service` that change card transactions without refreshing their bills. Both were reproduced in a scratch worktree:

1. **Deleting a category and moving its rows to another category** (`category_service.delete_category` with `transfer_to_id`, `backend/app/services/category_service.py:448` → `_transfer_category_references`, bulk `UPDATE transactions SET category_id` at `:411-419`) does not refresh any bill. In the probe, a 100.00 card purchase sat in an `is_ignored` category, so the bill's `computed_total` was 0.00. The category was then deleted and its rows moved to "Mercado". `computed_total` stayed at 0.00 when it should have been 100.00. The reverse case, moving rows into a flagged category, leaves the total too high.
2. **Applying rules to existing transactions** (`rule_service.apply_single_rule`, `backend/app/services/rule_service.py:1382-1455`, called on rule create and update at `backend/app/api/rules.py:99,202`, and `apply_all_rules`, `:1458-1523`, at `backend/app/api/rules.py:284`) sets `category_id` and `is_ignored` on card rows and commits without `bill_service.touch`. In the probe, an `ignore` rule matched a 100.00 card purchase (1 row changed). `computed_total` stayed at 100.00 when it should have been 0.00.

Both break the stored aggregate contract (AD-003, AD-004). They also break the spec's computed-total rule (Assumptions: ignored rows and rows in `is_bill_payment`/`is_ignored` categories do not count) as it feeds P1 AC 5/6 and, through `settled_on`, the `settlement` recognition date. `rebuild-bills` repairs the data, but no write path triggers it.

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1-T54 | ✅ Done | All checkboxes `[x]`. T50's browser check was recorded by the orchestrator on 2026-10-13 (`tasks.md`, T50 Done-when). |
| T55 import undo refresh | ✅ Done | `backend/app/api/import_logs.py:94-114` |
| T56 account delete refresh | ✅ Done | `backend/app/services/account_service.py:642-681,712` |
| T57 sync phantom cleanup refresh | ✅ Done | `backend/app/services/connection_service.py:1625-1652` |
| T58 concurrent batches test | ✅ Done | `backend/tests/test_bill_service.py:323-348` |
| T59 cross-page figures test | ✅ Done | `frontend/src/pages/credit-cards-consistency.test.tsx` |
| T60 badge truncation | ✅ Done | `frontend/src/components/bill-payment-row-badge.test.tsx:48-73`. The orchestrator does the browser re-check (open item). |

---

## Spec-Anchored Acceptance Criteria

I re-derived this coverage from the spec and the current test files. Backend paths are relative to `backend/tests/`, frontend paths to `frontend/src/`.

### P1: Bills exist (BILL-01..04)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | at most one bill per card/month | `test_bill_service.py:167-178` `created_again is False`, `count == 1`; `:190` `pytest.raises(IntegrityError)` | ✅ |
| 2 | 08-05..09-04, close 09-05, due 09-12, eff 09-14 | `test_bill_period.py:18-25` `== BillPeriod(...)`; API `test_credit_card_bills_api.py:136-140` | ✅ |
| 3 | close 31 clamps | `test_bill_period.py:31` `close_date == date(2026, 9, 30)` | ✅ |
| 4 | 2026-12-05..2027-01-04 | `test_bill_period.py:40-41` | ✅ |
| 5 | computed, declared (nullable), paid, remaining ≥ 0, overpaid, status, source | `test_credit_card_bills_api.py:142-149` (`source == "auto"`, `declared_total is None`, `remaining_amount == 783.20`, `overpaid_amount == 0.0`, `status == "partially_paid"`); `test_bill_service.py:73-74` overpaid `16.80`, remaining `0.00` | ✅ |
| 6 | status derived by precedence, not stored | `test_bill_service.py:51-100` (one test per precedence branch), `:110-115` (`not hasattr(bill, "status")`) | ✅ |
| 7 | manual bill, links period rows without override | `test_bill_manual.py:87-99` | ✅ |
| 8 | 409, nothing stored | `test_bill_manual.py:139-141`; API `test_credit_card_bills_api.py:258-262` | ✅ |
| 9 | declared total edit recomputes target/remaining/status | `test_bill_manual.py:169-174` (`500.00`, `0.00`, `"paid"`); API `test_credit_card_bills_api.py:301-304` | ✅ |
| 10 | provider dates → 422 | `test_bill_manual.py:196`; API `test_credit_card_bills_api.py:334` | ✅ |
| 11 | delete unlinks rows and payments, keeps transactions | `test_bill_manual.py:250-254`; pair undone `test_bill_payment_pairing.py:218-220` | ✅ |
| 12 | cycle change re-dates unpaid bills, paid unchanged | `test_bill_linking.py:212-231`; `test_account_cycle_relink.py:86-99` | ✅ |
| 13 | no cycle, no auto bills | `test_bill_linking.py:156-158` `LinkSummary(0, 0)`, `{}` | ✅ |
| 14 | backfill creates, links, idempotent | `test_credit_card_bills_backfill_migration.py:201-221`, `:238-239` | ✅ |
| 15 | provider bills untouched | `test_credit_card_bills_backfill_migration.py:252-260` | ✅ |

### P1: Imported transactions join their bill (BIMP-01)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | import, sync, manual entry link the period bill | `test_import_bills.py:74-77`; `test_sync_bills.py:114-116`; `test_transaction_bill_hooks.py:105-108` | ✅ |
| 2 | missing bill created `auto` | `test_bill_linking.py:79,85` | ✅ |
| 3 | close-day row goes to the next bill | `test_bill_linking.py:83`; `test_bill_period.py:64` | ✅ |
| 4 | override links by effective/nominal due, creates none | `test_bill_linking.py:129-133` | ✅ |
| 5 | date or account change relinks | `test_transaction_bill_hooks.py:141-143`, `:155-157` | ✅ |
| 6 | import reports linked + created | `test_import_bills.py:69` `(3, 3)`; route `:101-103` | ✅ |
| 7 | same file twice, no duplicate bill | `test_import_bills.py:85-86` | ✅ |
| 8 | installment links the bill of its own date | `test_bill_linking.py:149`; `test_transaction_bill_hooks.py:128` | ✅ |

### P1: Bill payments (BPAY-01..03)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | link recorded, paid + status recomputed | `test_bill_payment_service.py:79-82` | ✅ |
| 2 | payment out of income/expense in every mode | cash/accrual `test_bill_payment_pnl.py:88-89,101-103,113-114,140-141`; settlement `test_dashboard_settlement.py:54` (1,000.00 linked payment, Sept expenses `== 1000.0`) | ✅ |
| 3 | paired with the card credit | `test_bill_payment_pairing.py:102-106` | ✅ |
| 4 | no credit: link kept, `needs_counterpart` | `test_bill_payment_pairing.py:120-123` | ✅ |
| 5 | reference payment: `paid`, remaining 0 | `test_bill_payment_service.py:81-83`; API `test_credit_card_bills_api.py:433-435` | ✅ |
| 6 | 500.00 of 1,283.20: `partially_paid`, 783.20 | `test_bill_payment_service.py:92-93` | ✅ |
| 7 | two partials: `paid` | `test_bill_payment_service.py:103` | ✅ |
| 8 | overpayment: `paid` + overpaid | `test_bill_payment_service.py:113-114` (`16.80`) | ✅ |
| 9 | unlink removes link, undoes pair, recomputes | `test_bill_payment_pairing.py:160-166` | ✅ |
| 10 | credit/card/ignored/currency → 422 | `test_bill_payment_service.py:152` (parametrized) | ✅ |
| 11 | already pays another → 409 | `test_bill_payment_service.py:167` | ✅ |
| 12 | other workspace → 404 | `test_bill_payment_service.py:197`; API `test_credit_card_bills_api.py:514` | ✅ |
| 13 | `is_bill_payment` category excluded before linking | `test_bill_payment_pnl.py:102,114` (200.00 in the flagged category gives 0.0) | ✅ |

### P2: Matching (BDAY-01, BMATCH-01..03)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | weekend/holiday → next business day | `test_business_days.py:97,101,111` | ✅ |
| 2 | Easter-derived holidays 2026-28 | `test_business_days.py:24` (Easter dates), `:81` (exact holiday sets) | ✅ |
| 3 | window `[close, eff due + 5]`, remaining > 0 | `test_bill_match_candidates.py:90`, `:121` | ✅ |
| 4 | unique exact pair auto-links | `test_bill_match_apply.py:79-81` | ✅ |
| 5 | below remaining → `partial`, no link | `test_bill_match_apply.py:128-130`; `test_bill_match_candidates.py:111` | ✅ |
| 6 | several bills or payments → suggestions only | `test_bill_match_apply.py:94-96`, `:112-115` | ✅ |
| 7 | matcher runs on import, sync, entry, new bill | `test_import_bill_match.py:87,106`; `test_sync_bills.py:209`; `test_transaction_bill_hooks.py:320,340,354` | ✅ |
| 8 | dialog: candidates first with card/month/due/target/remaining/reason, then others | `test_credit_card_bills_api.py:572-583`; `components/link-bill-dialog.test.tsx:113-128` | ✅ |
| 9 | dismissed pair never suggested again | `test_bill_match_dismiss.py:84-86`; API `test_credit_card_bills_api.py:677` | ✅ |
| 10 | preview lists checkboxes and writes nothing | `test_credit_card_bills_api.py:611-619`; `components/bill-match-apply-dialog.test.tsx:74-78` | ✅ |
| 11 | apply links checked pairs, reports failures | `test_bill_match_apply.py:171-178`; `test_credit_card_bills_api.py:638` | ✅ |
| 12 | 09-14 payment inside the window of nominal due 09-12 | `test_bill_match_candidates.py:74` | ✅ |
| 13 | 09-20 vs eff due 09-14: no auto link, listed as other | `test_bill_match_candidates.py:100`; `test_bill_match_apply.py:141-143` | ✅ |
| 14 | indicator "Possível pagamento de fatura" with confirm/dismiss | `pages/transactions-bill-payment.test.tsx:202,209,230,243` | ✅ |
| 15 | hint ranking | `test_bill_match_candidates.py:167-169` | ✅ |

### P2: Settlement mode (BREP-01..02)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | `cash`/`accrual`/`settlement`, default `cash` | `test_credit_card_accounting_mode.py:347`, `:2025` | ✅ |
| 2 | paid bill realized on the completing payment date | `test_dashboard_settlement.py:167-171`; `test_settlement_filters.py:48` | ✅ |
| 3 | unpaid: projected in the eff due month, not realized | `test_dashboard_settlement.py:116-121` | ✅ |
| 4 | overdue past month: projected in the current month | `test_dashboard_settlement.py:130-135`; `test_settlement_filters.py:67` | ✅ |
| 5 | paid 09-14: Sept 600/400, Aug none | `test_dashboard_settlement.py:54-60` | ✅ |
| 6 | 500.00: 0 realized, 1,000 projected | `test_dashboard_settlement.py:142-146` | ✅ |
| 7 | + 500.00 on 09-20: realized, recognition 09-20 | `test_dashboard_settlement.py:72-78` | ✅ |
| 8 | unlink the completing payment: back to projected | `test_dashboard_settlement.py:158-160` | ✅ |
| 9 | card rows without a bill: purchase date | `test_settlement_filters.py:88` | ✅ |
| 10 | dashboard, categories, budgets, reports, splits | `test_budget_settlement.py:42-46`; `test_report_settlement.py:55-59`; `test_split_offsets_mode.py:98-111` | ✅ |
| 11 | open bills = sum of remaining of unpaid bills | `test_dashboard_settlement.py:203` (`700.0`); `pages/dashboard.test.tsx:158-159` | ✅ |
| 12 | main date + "Lançada em" line | `components/transaction-drill-down.test.tsx:159-160`, `:167-168` | ✅ |
| 13 | unpaid: projected badge + eff due date | `components/transaction-drill-down.test.tsx:176-177` | ✅ |
| 14 | cash unchanged, no extra line | `components/transaction-drill-down.test.tsx:185-187` | ✅ |
| 15 | sorted by main date | `components/transaction-drill-down.test.tsx:208` | ✅ |
| 16 | admin describes and picks the three modes | `pages/admin/settings-accounting-mode.test.tsx:70`, `:108-111` | ✅ |

### P3: Consolidated page (BVIEW-01)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | sub-item + palette at `/accounts/credit-cards` | `lib/nav-items.test.ts:119-121`; `components/command-palette-credit-cards.test.tsx:40`; `App.routes.test.tsx:32` | ✅ |
| 2 | opens on the month of the next eff due | `pages/credit-cards.test.tsx:164` | ✅ |
| 3 | `?account=<id>` scopes every figure | `pages/credit-cards.test.tsx:205-212` | ✅ |
| 4 | previous/next month | `pages/credit-cards.test.tsx:230-236` | ✅ |
| 5 | sums, earliest due, limit, available | `pages/credit-cards.test.tsx:165-170` | ✅ |
| 6 | bill rows with figures + payment links | `pages/credit-cards.test.tsx:177-181` | ✅ |
| 7 | transactions + card column | `pages/credit-cards.test.tsx:190-192`, `:211` | ✅ |
| 8 | same figures as the account detail page | `pages/credit-cards-consistency.test.tsx:168-169`: both renders `toEqual({ target: 'R$1,283.20', paid: 'R$500.00', remaining: 'R$783.20', status: 'Partially paid', due: '9/14/2026' })` | ✅ (round 1 gap closed) |
| 9 | empty state with create call | `pages/credit-cards.test.tsx:251-252` | ✅ |
| 10 | configure call for an unconfigured card | `pages/credit-cards.test.tsx:261-262` | ✅ |
| 11 | no horizontal scroll at 375 px | browser check by the orchestrator, recorded in `tasks.md` T50 | ✅ (manual evidence) |

**Status**: all 78 ACs trace to an assertion of the spec outcome. No spec-precision gap remains. The failures are on write paths (see the AD-004 audit), not on missing AC tests.

---

## Edge Cases

| Edge case | Evidence | Result |
| --------- | -------- | ------ |
| close = due = 10 | `test_bill_period.py:49-51` | ✅ |
| nominal due 2026-09-07 → 09-08 | `test_bill_period.py:57-58` | ✅ |
| payment amount 0 or negative → 422 | `test_bill_payment_service.py:152` (`zero`, `negative` cases) | ✅ |
| negative declared total → 422 | `test_bill_manual.py:148`; API `test_credit_card_bills_api.py:273,315` | ✅ |
| closed card still accepts payments | `test_bill_payment_service.py:208` | ✅ |
| linked payment deleted: link dropped, status recomputed | single `test_transaction_bill_hooks.py:280-281`; bulk `:297-298`; import undo `test_import_undo_bills.py:106-108`; account delete `test_account_delete_bills.py:54-56`; sync cleanup `test_sync_bills.py:269-272` | ✅ |
| card account deleted: bills deleted, payments unlinked | `test_account_delete_bills.py:88-93` (PostgreSQL: `bills == []`, `paid_bill_id is None`, `bill_payment_pair is False`, `transfer_pair_id is None`) | ✅ |
| concurrent imports: one bill, both batches linked | `test_bill_service.py:336` (`len(set(ids)) == 1`), `:347-348` (`count == 1`, `linked == [ids[0]] * 3`), PostgreSQL | ✅ |
| empty bill: total 0, `paid` once closed | `test_bill_service.py:98-100`, `:290` | ✅ |
| incompatible cycle days → 422 `incompatible_cycle_days` | `test_account_cycle_relink.py:153-156`, `:176-179` | ✅ |

---

## Round 1 Gap Closure

| Round 1 gap | Fix (`file:line`) | Test (`file:line`) | Mutation | Closed? |
| ----------- | ----------------- | ------------------ | -------- | ------- |
| Import undo refresh | `backend/app/api/import_logs.py:94-114` (`collect_bill_ids` before, `refresh_bills` after, pair unlinked) | `backend/tests/test_import_undo_bills.py:70` (`computed_total == 50.00`), `:106-108` (`paid_amount == 0.00`, `settled_on is None`, `"closed"`), `:114` (pair undone) | M1, M2 killed | ✅ |
| Non-card account deletion refresh | `backend/app/services/account_service.py:651,712` | `backend/tests/test_account_delete_bills.py:54-58` | M3 killed | ✅ |
| Card account deletion test on PostgreSQL | `backend/app/services/account_service.py:644-681` | `backend/tests/test_account_delete_bills.py:61-93` (`postgres_sessions`) | M4 killed | ✅ |
| Concurrent batches both linked | n/a (test gap) | `backend/tests/test_bill_service.py:323-348` | M6 killed | ✅ |
| BVIEW AC 8 cross-page comparison | n/a (test gap) | `frontend/src/pages/credit-cards-consistency.test.tsx:156-170` | M13, M14 killed | ✅ |
| Sync phantom cleanup refresh | `backend/app/services/connection_service.py:1647,1652` | `backend/tests/test_sync_bills.py:269-272` | M5 killed | ✅ |

---

## AD-004 Write-Path Audit (re-run)

I enumerated every `delete(Transaction)`, `update(Transaction)`, `session.delete(...)` of a transaction, and direct write of `bill_id`, `paid_bill_id`, `category_id`, `is_ignored`, `amount` and `date` in `backend/app`.

| Write path | Bill refresh | Test | Result |
| ---------- | ------------ | ---- | ------ |
| `transaction_service` create, installments, transfer, counterpart, link-as-transfer, update (with paired legs, `:1749`/`:1781`), bulk category, bulk ignore, toggle ignore, delete, bulk delete | `_sync_card_bills` / `touch` / `collect_bill_ids` → `refresh_bills` | `test_transaction_bill_hooks.py:99-298`; `test_bill_payment_pairing.py:194` | ✅ |
| `import_service.import_transactions` | `link_account_transactions` + `run_auto_match` (`:1101,1111`) | `test_import_bills.py:65`; `test_import_bill_match.py:78` | ✅ |
| `api/import_logs.delete_import_log` | `:94-114` | `test_import_undo_bills.py` | ✅ (fixed) |
| `account_service.delete_account` (non-card and card) | `:642-681,712` | `test_account_delete_bills.py` | ✅ (fixed) |
| `account_service.update_account` cycle change | `relink_account` | `test_account_cycle_relink.py:60,191` | ✅ |
| `account_service` opening-balance writes (`:452-480,573-602`) | none needed: opening rows are never linked or counted | `test_bill_linking.py:161-164` | ✅ |
| `connection_service` sync, provider bills, finance-charge orphans (`:1808`) | `_sync_account_bills` refreshes every bill of the card (`:1836-1842`, after cleanup at `:2468`) | `test_sync_bills.py:106-148` | ✅ |
| `connection_service._cleanup_phantom_duplicates` | `:1647,1652` | `test_sync_bills.py:232-272` | ✅ (fixed) |
| `connection_service` workspace move `update(Transaction)` (`:2049`) | not needed: changes only `user_id`/`workspace_id` | n/a | ✅ |
| `recurring_transaction_service.generate_pending` | `link_account_transactions` | `test_recurring_bills.py:47-51` | ✅ |
| `category_service.update_category` flag change | `refresh_workspace_bills` (`:247-256`) | `test_category_bill_payment.py:69,97` | ✅ |
| `transfer_detection_service` pair/unpair | `touch` (`:622`) | `test_transfer_pairing_bills.py:82,92` | ✅ |
| `bill_payment_service` link/unlink, `bill_service` CRUD | `refresh_bills` | BPAY and BILL-02 rows above | ✅ |
| `payee_service` `update(Transaction)` (`:315,346,387`) | not needed: changes only payee fields | n/a | ✅ |
| **`category_service.delete_category` with `transfer_to_id`** (`:448` → `:411-419`) | **none** | **none**. Probe: `computed_total` stays `0.00` (expected `100.00`) | ❌ |
| **`rule_service.apply_single_rule`** (`:1382-1455`; `api/rules.py:99,202`) and **`apply_all_rules`** (`:1458-1523`; `api/rules.py:284`) | **none** | **none**. Probe: `ignore` rule → `computed_total` stays `100.00` (expected `0.00`) | ❌ |
| `import_service` recurring placeholder upgrade (`:1016-1047`) setting `is_ignored`/category on a placeholder already on its bill | `link_account_transactions` refreshes only bills whose rows move | none | ⚠️ Low likelihood, not reproduced |

Observation, not a failure: undoing a card import whose credit was paired with a checking payment deletes the credit and leaves the payment's `transfer_pair_id` dangling (`import_logs.py:96-108` unlinks only pairs whose payment is in the import). The payment stays linked to its bill and `paid_amount` is correct, but `needs_counterpart` reads `false`. Import undo already left transfer pairs dangling before this feature.

---

## Discrimination Sensor

**Scratch**: `git worktree add --detach <scratchpad>/mut HEAD`. Each mutation rewrote one line, ran the feature tests (backend with `POSTGRES_TEST_URL` set, frontend with vitest), then restored the file with `git checkout`. The scratch worktree was removed with `git worktree remove --force`. Real-tree `git status --porcelain` before the run: empty. After cleanup: only `?? .specs/features/credit-card-bills/ajustes.md`, a file the owner added during the run (not created by the verifier, left untouched).

| # | File:line | Mutation | Killed? | Killing test(s) |
| - | --------- | -------- | ------- | --------------- |
| M1 | `backend/app/api/import_logs.py:114` | import undo skips `refresh_bills` | ✅ | `test_import_undo_bills.py` (both tests) |
| M2 | `backend/app/api/import_logs.py:108` | import undo keeps the payment's transfer pair | ✅ | `test_import_undo_bills.py::test_undoing_a_checking_import_unlinks_its_payment_from_the_bill` |
| M3 | `backend/app/services/account_service.py:712` | account delete skips `refresh_bills` | ✅ | `test_account_delete_bills.py::test_deleting_the_paying_account_unpays_the_bill` |
| M4 | `backend/app/services/account_service.py:662` | card delete ignores payments of its own bills (no pair undo) | ✅ | `test_account_delete_bills.py::TestCardDeletionOnPostgres::test_deleting_a_card_deletes_its_bills_and_unlinks_their_payments` |
| M5 | `backend/app/services/connection_service.py:1652` | phantom cleanup skips `refresh_bills` | ✅ | `test_sync_bills.py::test_phantom_cleanup_drops_the_deleted_payment_from_its_bill` |
| M6 | `backend/app/services/bill_service.py:128` | race loser returns its own bill, not the winner | ✅ | `test_bill_service.py::test_concurrent_get_or_create_keeps_one_bill` (PostgreSQL) |
| M7 | `backend/app/services/bill_service.py:73` | overdue `>` → `>=` | ✅ | 6 tests, e.g. `test_bill_service.py::TestBillStatus::test_on_effective_due_unpaid_is_closed` |
| M8 | `backend/app/services/bill_service.py:210` | `settled_on` crossing `>=` → `>` | ✅ | 6 tests, e.g. `test_dashboard_settlement.py::test_paid_bill_counts_in_the_month_it_was_paid` |
| M9 | `backend/app/services/bill_service.py:154` | computed total counts ignored rows | ✅ | `test_bill_service.py::test_computed_total_excludes_non_purchase_rows`, 2 hook tests |
| M10 | `backend/app/services/_query_filters.py:288` | P&L stops excluding linked payments | ✅ | 6 `test_dashboard_settlement.py` tests |
| M11 | `backend/app/services/bill_match_service.py:23` | match window +5 → +6 days | ✅ | `test_bill_match_candidates.py::test_window_bounds_are_close_date_and_effective_due_plus_five` and 2 more |
| M12 | `backend/app/core/business_days.py:64` | business day ignores holidays | ✅ | `test_business_days.py::test_every_holiday_is_not_a_business_day[*]` |
| M13 | `frontend/src/components/credit-card/bill-details-card.tsx:139` | account detail shows target as remaining | ✅ | `credit-cards-consistency.test.tsx` |
| M14 | `frontend/src/lib/bill-summary.ts:29` | consolidated summary sums targets as remaining | ✅ | `credit-cards-consistency.test.tsx` |

**Sensor depth**: expanded (14 manual behavior-level mutations: one or two per round 1 gap, plus core money paths)
**Result**: 14/14 killed. The sensor passes.

The two AD-004 gaps above are not mutants: the code has no refresh call there and no test, so the scratch probes stand in for the sensor on those paths.

---

## Gate Check

- **Backend**: `TZ=UTC python -m pytest -q -rs` with `POSTGRES_TEST_URL` pointing at a throwaway `public.ecr.aws/supabase/postgres:17.11.0.002` container (`ccr2-pg`, since removed). **4765 passed, 0 failed, 0 skipped.** PostgreSQL-only tests ran.
- **Backend lint/types**: `ruff check .`: all checks passed. `ty check`: all checks passed.
- **Frontend**: `npm run typecheck && npm run lint && npm test`: exit 0. **125 files, 1055 tests passed.**
- **Test count before the feature** (`7da4813`, round 1 figure): backend 4457, frontend 968. **Now**: 4765 / 1055. **Delta**: +308 / +87. No decrease; round 1 had 4760 / 1051.
- **Skipped tests**: none.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / surgical changes / no scope creep (fix commits) | ✅ |
| Matches patterns (`collect_bill_ids` → delete → `refresh_bills`, the same as `delete_transaction`) | ✅ |
| Spec-anchored outcome check | ✅ (0 spec-precision gaps) |
| Per-layer coverage (domain 1:1, routes happy + edge + error) | ✅ |
| Every test maps to an AC, edge case or Done-when | ✅ |
| AD-004: every card/payment write path refreshes bills | ❌ (category transfer delete, rule re-application) |

---

## Fix Plans

### Fix 1: Refresh bills when a deleted category's rows move (Major)
- **Root cause**: `_transfer_category_references` bulk-updates `Transaction.category_id` and does not refresh any bill. A row that crosses into or out of an `is_bill_payment`/`is_ignored` category changes its bill's computed total.
- **Fix task**: In `delete_category`, when `transfer_to_id` is given and either category carries `is_bill_payment` or `is_ignored`, call `refresh_workspace_bills(session, workspace_id)` (or `touch` the moved rows) before the commit. Test: card purchase in an `is_ignored` category, delete it with a transfer to a plain category, assert `computed_total == 100.00`. Add the reverse case.
- **Where**: `backend/app/services/category_service.py:404-455`, test in `backend/tests/test_category_bill_payment.py`.

### Fix 2: Refresh bills after rules are applied to existing transactions (Major)
- **Root cause**: `apply_single_rule` and `apply_all_rules` change `category_id`/`is_ignored` on card rows and commit without `bill_service.touch`.
- **Fix task**: Collect the ids of changed rows (`before != after`) and call `bill_service.touch(session, changed_ids)` before each commit. Test: an `ignore` rule applied to a card purchase makes `computed_total == 0.00`. A rule moving a row into an `is_bill_payment` category does the same. `apply_all_rules` resetting a rule-set `is_ignored` brings it back.
- **Where**: `backend/app/services/rule_service.py:1382-1523`, new test `backend/tests/test_rule_bill_refresh.py`.

### Fix 3 (Minor, optional): Import placeholder upgrade
- `touch` the `upgraded_placeholders` ids after `link_account_transactions` in `import_service.import_transactions` (`:1099-1103`).

---

## Known Open Items (not counted as failures)

- The `settlement` transactions-page summary counts projected purchases. This is outside the spec.
- The import screen does not show `bills_linked`/`bills_created`. The API returns them (`test_import_bills.py:101-103`).
- The orchestrator does the browser layout re-check for T60 (badge truncation at desktop and 375 px).

---

## Requirement Traceability Update

| Requirement | New status |
| ----------- | ---------- |
| BILL-02, BILL-03, BILL-04, BIMP-01, BPAY-02, BPAY-03, BDAY-01, BMATCH-01, BMATCH-02, BMATCH-03, BREP-01, BREP-02, BVIEW-01 | ✅ Verified |
| BILL-01 | ❌ Needs fix: stored computed total goes stale on category-transfer delete and rule re-application |
| BPAY-01 | ✅ Verified (every deleted-payment path now refreshes) |

---

## Summary

**Overall**: ❌ Not ready

**Spec-anchored check**: 78/78 ACs match the spec outcome. 0 spec-precision gaps. 10/10 edge cases covered.
**Round 1 gaps**: 6/6 closed, each with a killed mutation.
**Sensor**: 14/14 mutations killed.
**Gate**: backend 4765 passed (PostgreSQL included); frontend 1055 passed; ruff and ty clean.
**New gaps**: 2 AD-004 write paths, both reproduced: category delete with transfer, and rule re-application.

**Next steps**: Fixes 1 and 2, then round 3 re-verification. This is the last round before the bound of 3 is reached.
