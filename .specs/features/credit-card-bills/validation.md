# Credit Card Bills Validation (round 3)

**Date**: 2026-10-13
**Spec**: `.specs/features/credit-card-bills/spec.md`
**Diff range**: `7da4813..HEAD` (HEAD `300f423`, 84 commits). Since round 2 (`b8d1c2e`): `df9cd0f..300f423`, which covers Phase 11 (T61-T66) and Phase 12 (T73, T74, T67-T72).
**Verifier**: independent sub-agent, round 3 (author ≠ verifier)

## Validation: credit-card-bills - FAIL ❌

All three round 2 gaps are closed. Each one has a test that asserts the spec outcome, and a mutation that removes the fix is killed. The follow-ups T73 and T74 and the T64 guard work. All 9 ADJ ACs trace to assertions of the spec outcome. All gates are green: backend 4781 passed with 0 skipped (PostgreSQL included), frontend 1071 passed, ruff and ty clean. The sensor killed 19 of 19 mutation runs.

The verdict is FAIL because the last AD-004 hand audit found one more write path that changes card rows and leaves the stored bill aggregate stale. A scratch probe reproduced it:

- **Accepting a transfer suggestion from the reconciliation queue** (`backend/app/api/reconciliation.py:559-562`, `_settle` → `leg.transfer_pair_id = pair_id`, reached from `accept_suggestion` at `:421-464`) pairs the two legs and commits. It never calls `bill_service`. When the debit is a payment already linked to a bill (`needs_counterpart`), the card credit becomes "the card leg of a bill payment". The spec's computed-total rule (Assumptions) then excludes that credit, so the bill's `computed_total` must change. In the probe, a 1,000.00 purchase and a 1,000.00 card credit sat on the 2026-09 bill. Two checking debits of 1,000.00 on the same day made the pair ambiguous, so `detect_transfer_pairs` queued a question rather than pairing. The suggestion for the linked payment and the credit was accepted (HTTP 200). The stored `computed_total` stayed at **0.00**. Recomputing from the rows gives **1000.00**. The bill then reports target 0, overpaid 1,000.00 and, once closed, status `paid`, which contradicts P1 AC 5 and AC 6. `settled_on` and the `settlement` recognition date go wrong with it. The T64 guard cannot see this path, because it is an ORM attribute write in a loop and not a bulk statement.

The other pairing paths refresh: `transfer_detection_service` (`:507`, `:601`, `:622`), `transaction_service.link_existing_as_transfer` and `create_transfer_counterpart`, and `bill_payment_service`. The gap is limited to the reconciliation accept route.

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1-T60 | ✅ Done | Verified in rounds 1 and 2; checkboxes `[x]` |
| T61 category delete refresh | ✅ Done | `backend/app/services/category_service.py:411-430` |
| T62 rules apply refresh | ✅ Done | `backend/app/services/rule_service.py:1415,1455-1458,1482,1527-1531` |
| T63 placeholder upgrade refresh | ✅ Done | `backend/app/services/import_service.py:1104-1106` |
| T64 AD-004 guard | ✅ Done | `backend/tests/test_ad004_guard.py:121-134`; allow-list reasons at `:34-49` |
| T65 projected count | ✅ Done | `backend/app/services/dashboard_service.py:1016-1018,1033`; schema `backend/app/schemas/dashboard.py:49` |
| T66 available credit | ✅ Done | `backend/app/services/account_service.py:60-81`; `backend/app/api/accounts.py:139-142` |
| T73 user delete refresh | ✅ Done | `backend/app/services/admin_service.py:193-198,221-222`; no longer allow-listed |
| T74 create returns floored balance | ✅ Done | `backend/app/api/accounts.py:155-156` (update at `:175-180` as well) |
| T67 category badge | ✅ Done | `frontend/src/pages/categories.tsx:280-287` |
| T68 projected count badge | ✅ Done | `frontend/src/pages/dashboard.tsx:483,959-966` |
| T69 settlement dates in the list | ✅ Done | `frontend/src/lib/settlement-dates.ts`, `frontend/src/components/settlement-date.tsx`, `frontend/src/pages/transactions.tsx:834-852,1193,1266-1275,1306-1315,1627` |
| T70 bill info in the dialog | ✅ Done | `frontend/src/components/credit-card/bill-info.tsx`, `frontend/src/components/transaction-dialog.tsx:1224-1229` |
| T71 payment links | ✅ Done | `frontend/src/lib/bill-payment.ts:5-9`; used at `bill-details-card.tsx:157` and `credit-cards.tsx:229` |
| T72 release notes | ✅ Done | `deploy/public/RELEASE-NOTES.md:106-109` |

---

## Spec-Anchored Acceptance Criteria

I re-derived this coverage from spec.md and the current test files. For the 78 pre-ADJ ACs, I re-read the cited assertions against the spec outcome, starting from the round 2 table. Only `credit-cards.test.tsx` moved since round 2: T71 added one line at `:183`, so the citations below it shift by +1. Backend paths are relative to `backend/tests/`, frontend paths to `frontend/src/`.

### P1: Bills exist (BILL-01..04)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | at most one bill per card/month | `test_bill_service.py:167-178` `created_again is False`, `count == 1`; `:190` `pytest.raises(IntegrityError)` | ✅ |
| 2 | 08-05..09-04, close 09-05, due 09-12, eff 09-14 | `test_bill_period.py:18-25` `== BillPeriod(period_start=date(2026, 8, 5), ..., effective_due_date=date(2026, 9, 14))`; API `test_credit_card_bills_api.py:136-140` | ✅ |
| 3 | close 31 clamps | `test_bill_period.py:31` `close_date == date(2026, 9, 30)` | ✅ |
| 4 | 2026-12-05..2027-01-04 | `test_bill_period.py:40-41` | ✅ |
| 5 | computed, declared (nullable), paid, remaining ≥ 0, overpaid, status, source | `test_credit_card_bills_api.py:142-149`; `test_bill_service.py:73-74` (overpaid `16.80`, remaining `0.00`) | ✅ (test level; see the AD-004 gap for the stored value) |
| 6 | status derived by precedence, not stored | `test_bill_service.py:51-100`, `:110-115` `not hasattr(bill, "status")` | ✅ |
| 7 | manual bill, links period rows without override | `test_bill_manual.py:87-99` | ✅ |
| 8 | 409, nothing stored | `test_bill_manual.py:139-141`; API `test_credit_card_bills_api.py:258-262` | ✅ |
| 9 | declared total edit recomputes | `test_bill_manual.py:169-174` (`500.00`, `0.00`, `"paid"`) | ✅ |
| 10 | provider dates → 422 | `test_bill_manual.py:196`; API `test_credit_card_bills_api.py:334` | ✅ |
| 11 | delete unlinks, keeps transactions | `test_bill_manual.py:250-254`; `test_bill_payment_pairing.py:218-220` | ✅ |
| 12 | cycle change re-dates unpaid bills only | `test_bill_linking.py:212-231`; `test_account_cycle_relink.py:86-99` | ✅ |
| 13 | no cycle, no auto bills | `test_bill_linking.py:156-158` `LinkSummary(0, 0)` | ✅ |
| 14 | backfill creates, links, idempotent | `test_credit_card_bills_backfill_migration.py:201-221`, `:238-239` | ✅ |
| 15 | provider bills untouched | `test_credit_card_bills_backfill_migration.py:252-260` | ✅ |

### P1: Imported transactions join their bill (BIMP-01)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | import, sync, entry link the period bill | `test_import_bills.py:74-77`; `test_sync_bills.py:114-116`; `test_transaction_bill_hooks.py:105-108` | ✅ |
| 2 | missing bill created `auto` | `test_bill_linking.py:79,85` | ✅ |
| 3 | close-day row → next bill | `test_bill_linking.py:83`; `test_bill_period.py:64` | ✅ |
| 4 | override links by due date, creates none | `test_bill_linking.py:129-133` | ✅ |
| 5 | date/account change relinks | `test_transaction_bill_hooks.py:141-143`, `:155-157` | ✅ |
| 6 | import reports linked + created | `test_import_bills.py:69` `(3, 3)`; route `:101-103` | ✅ |
| 7 | same file twice, no duplicate | `test_import_bills.py:85-86` | ✅ |
| 8 | installment → bill of its own date | `test_bill_linking.py:149`; `test_transaction_bill_hooks.py:128` | ✅ |

### P1: Bill payments (BPAY-01..03)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | link recorded, paid + status recomputed | `test_bill_payment_service.py:79-82` | ✅ |
| 2 | payment out of P&L in every mode | `test_bill_payment_pnl.py:88-89,101-103,113-114,140-141`; `test_dashboard_settlement.py:54` (`== 1000.0`) | ✅ |
| 3 | paired with the card credit | `test_bill_payment_pairing.py:102-106` | ✅ |
| 4 | no credit: link kept, `needs_counterpart` | `test_bill_payment_pairing.py:120-123` | ✅ |
| 5 | reference payment: `paid`, remaining 0 | `test_bill_payment_service.py:81-83`; API `test_credit_card_bills_api.py:433-435` | ✅ |
| 6 | 500 of 1,283.20: `partially_paid`, 783.20 | `test_bill_payment_service.py:92-93` `== "partially_paid"`, `remaining == Decimal("783.20")` | ✅ |
| 7 | two partials: `paid` | `test_bill_payment_service.py:103` | ✅ |
| 8 | overpayment: `paid` + overpaid | `test_bill_payment_service.py:113-114` (`16.80`) | ✅ |
| 9 | unlink removes link, undoes pair | `test_bill_payment_pairing.py:160-166` | ✅ |
| 10 | credit/card/ignored/currency → 422 | `test_bill_payment_service.py:152` (parametrized) | ✅ |
| 11 | already paying → 409 | `test_bill_payment_service.py:167` | ✅ |
| 12 | other workspace → 404 | `test_bill_payment_service.py:197`; API `test_credit_card_bills_api.py:514` | ✅ |
| 13 | flagged category excluded before linking | `test_bill_payment_pnl.py:102,114`; rule path `test_rule_apply_bills.py:116,126` (`200.0` → `0.0`) | ✅ |

### P2: Matching (BDAY-01, BMATCH-01..03)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | weekend/holiday → next business day | `test_business_days.py:97,101,111` | ✅ |
| 2 | Easter-derived holidays 2026-28 | `test_business_days.py:24`, `:81` | ✅ |
| 3 | window `[close, eff + 5]`, remaining > 0 | `test_bill_match_candidates.py:90`, `:121` | ✅ |
| 4 | unique exact pair auto-links | `test_bill_match_apply.py:79-81` | ✅ |
| 5 | below remaining → `partial`, no link | `test_bill_match_apply.py:128-130`; `test_bill_match_candidates.py:111` | ✅ |
| 6 | several → suggestions only | `test_bill_match_apply.py:94-96`, `:112-115` | ✅ |
| 7 | matcher on import, sync, entry, new bill | `test_import_bill_match.py:87,106`; `test_sync_bills.py:209`; `test_transaction_bill_hooks.py:320,340,354` | ✅ |
| 8 | dialog lists candidates then others | `test_credit_card_bills_api.py:572-583`; `components/link-bill-dialog.test.tsx:113-128` | ✅ |
| 9 | dismissed pair never again | `test_bill_match_dismiss.py:84-86`; API `test_credit_card_bills_api.py:677` | ✅ |
| 10 | preview writes nothing | `test_credit_card_bills_api.py:611-619`; `components/bill-match-apply-dialog.test.tsx:74-78` | ✅ |
| 11 | apply links checked, reports failures | `test_bill_match_apply.py:171-178`; `test_credit_card_bills_api.py:638` | ✅ |
| 12 | 09-14 inside window of nominal 09-12 | `test_bill_match_candidates.py:74` `== [(bill.id, "exact", "exact_amount", 1)]` | ✅ |
| 13 | 09-20 vs eff 09-14: no auto link, listed as other | `test_bill_match_candidates.py:100`; `test_bill_match_apply.py:141-143` | ✅ |
| 14 | "Possível pagamento de fatura" indicator | `pages/transactions-bill-payment.test.tsx:202,209,230,243` | ✅ |
| 15 | hint ranking | `test_bill_match_candidates.py:167-169` | ✅ |

### P2: Settlement mode (BREP-01..02)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | three modes, default `cash` | `test_credit_card_accounting_mode.py:347`, `:2025` | ✅ |
| 2 | paid bill realized on the completing payment date | `test_dashboard_settlement.py:167-171`; `test_settlement_filters.py:48` | ✅ |
| 3 | unpaid: projected in eff due month | `test_dashboard_settlement.py:116-121` | ✅ |
| 4 | overdue past month → current month | `test_dashboard_settlement.py:130-135`; `test_settlement_filters.py:67` | ✅ |
| 5 | paid 09-14: Sept 600/400, Aug none | `test_dashboard_settlement.py:54-60` `{"Mercado": 600.0, "Restaurantes": 400.0}`, Aug `{}` | ✅ |
| 6 | 500.00: 0 realized, 1,000 projected | `test_dashboard_settlement.py:142-146` `(0.0, 1000.0, {...})` | ✅ |
| 7 | + 500 on 09-20: recognition 09-20 | `test_dashboard_settlement.py:72-78` | ✅ |
| 8 | unlink → back to projected | `test_dashboard_settlement.py:158-160` | ✅ |
| 9 | no bill: purchase date | `test_settlement_filters.py:88` | ✅ |
| 10 | mode in dashboard, categories, budgets, reports, splits | `test_budget_settlement.py:42-46`; `test_report_settlement.py:55-59`; `test_split_offsets_mode.py:98-111` | ✅ |
| 11 | open bills = sum of remaining | `test_dashboard_settlement.py:203` `== 700.0`; `pages/dashboard.test.tsx:158-159` | ✅ |
| 12 | drill-down main date + "Lançada em" | `components/transaction-drill-down.test.tsx:159-160`, `:167-168` | ✅ |
| 13 | unpaid: projected badge + eff due | `components/transaction-drill-down.test.tsx:176-177` | ✅ |
| 14 | cash unchanged | `components/transaction-drill-down.test.tsx:185-187` | ✅ |
| 15 | sorted by main date | `components/transaction-drill-down.test.tsx:208` | ✅ |
| 16 | admin describes/picks modes | `pages/admin/settings-accounting-mode.test.tsx:70`, `:108-111` | ✅ |

### P3: Consolidated page (BVIEW-01)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | sub-item + palette | `lib/nav-items.test.ts:119-121`; `components/command-palette-credit-cards.test.tsx:40`; `App.routes.test.tsx:32` | ✅ |
| 2 | opens on next eff due month | `pages/credit-cards.test.tsx:164` | ✅ |
| 3 | `?account=<id>` scopes figures | `pages/credit-cards.test.tsx:206-213` | ✅ |
| 4 | previous/next month | `pages/credit-cards.test.tsx:231-237` | ✅ |
| 5 | sums, earliest due, limit, available | `pages/credit-cards.test.tsx:165-170` | ✅ |
| 6 | bill rows + payment links | `pages/credit-cards.test.tsx:177-185` | ✅ |
| 7 | transactions + card column | `pages/credit-cards.test.tsx:191-193`, `:212` | ✅ |
| 8 | same figures as account detail | `pages/credit-cards-consistency.test.tsx:168-169` | ✅ |
| 9 | empty state | `pages/credit-cards.test.tsx:252-253` | ✅ |
| 10 | configure call | `pages/credit-cards.test.tsx:262-263` | ✅ |
| 11 | no horizontal scroll at 375 px | browser check by the orchestrator (`tasks.md` T50) | ✅ (manual evidence) |

### P2: Post-delivery adjustments (ADJ-01..07)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | "Pagamento de fatura" badge only on `is_bill_payment` | `pages/categories-bill-payment.test.tsx:133,135-136` (badge on the flagged row, absent on the plain one, exactly 1); `:143` `billPaymentBadge` `toBe('Pagamento de fatura')`. It uses the same badge classes as the transfer/ignored badges (`categories.tsx:280-287`) | ✅ |
| 2 | settlement: reporting date, "Paga em"/"Pagar até", "Lançada em <purchase>" | `pages/transactions-settlement-dates.test.tsx:136-140` (Petz: `'Pagar até'`, `'13/10/2026'`, `'Lançada em 05/09/2026'`); `:148-151` (`'Paga em'`, `'10/10/2026'`); mobile `:198-205` (grouped under 13/10), `:212-213`. The backend contract for `reporting_date`/`is_bill_projected` is `test_transactions_reporting_fields_api.py:45-48,61-64,75-78` | ✅ (see SPEC_DEVIATION) |
| 3 | cash/accrual unchanged | `pages/transactions-settlement-dates.test.tsx:169-185` (`describe.each(['cash','accrual'])`: `'05/09/2026'`, no "Lançada em", no labels, no Prevista); non-card row `:163-165` | ✅ |
| 4 | "Prevista" on `is_bill_projected` rows in settlement | `pages/transactions-settlement-dates.test.tsx:139` (present), `:152`, `:214` (absent once paid), `:201` (mobile) | ✅ |
| 5 | dialog: bill (card + month) and "Quitada em <settled_on>" / "Não quitada · vence em <eff due>" | `components/transaction-dialog.test.tsx:217-219` (`'Cartão de Crédito Nubank · October 2026'`, `'Quitada em 10/10/2026'`); `:227-229` (`'Não quitada · vence em 10/13/2026'`); non-card `:237` | ✅ |
| 6 | settlement: projected count badge, none for 0 | backend `test_dashboard_projected_count.py:48-52` (`{"Compras": 2, "Mercado": 1, "Restaurantes": 1}`), `:62-66` (paid → 0), `:77-78` (cash/accrual → 0); frontend `pages/dashboard.test.tsx:189` (`'Compras(2 projected)'`), `:191` (`/^Mercado$/`), `:200-201` (`'(1 prevista)'`, `'(2 previstas)'`) | ✅ |
| 7 | detail available credit = limit − floored owed, same as list | `test_card_available_credit.py:53-56` (list and detail `current_balance == -1200.0`, `available_credit == 3800.0`); create `:76-77` (`-300.0`, `700.0`) | ✅ |
| 8 | payment link → `/transactions?highlight=<id>` in the payment's month | `pages/account-detail-bills.test.tsx:138` `href '/transactions?highlight=pay-1&from=2026-09-01&to=2026-09-30'`; `pages/credit-cards.test.tsx:184` | ✅ |
| 9 | release notes explain the inverted-sign option | `deploy/public/RELEASE-NOTES.md:106-109`. It names the real UI label "Inverter valores (trocar entrada/saída)" (`frontend/src/locales/pt-BR.json:1669`), and the option is saved with the mapping (`backend/app/schemas/import_mapping.py:14` `flip_amount`). Docs only, no test by design | ✅ (document evidence) |

**Status**: 87/87 ACs trace to an assertion, or to document or manual evidence, that matches the spec outcome. There are no spec-precision gaps. The FAIL comes from a write path (AD-004), not from a missing AC test.

### SPEC_DEVIATION assessment (`frontend/src/lib/settlement-dates.ts:19-26`)

ADJ AC 2 says the label is "Paga em" when the bill is `paid`. The code reads `!tx.is_bill_projected` instead, which is true when the bill has `settled_on` (`backend/app/services/_query_filters.py:209-213`). Under the status precedence, `paid` means `today ≥ close date and paid ≥ target`, and `settled_on` is set exactly when `paid ≥ target` (`bill_service.py:203-213`). The two disagree only for a bill paid in full before its close date. For that bill the status is `open`, but the reporting date is already the payment date (`reporting_date_of`, `_query_filters.py:198-200`). A literal implementation would show "Pagar até <payment date>", a deadline that is really a past payment. The owner's text (`ajustes.md`: "Pagar até" or "Paga em" depending on whether the bill is paid; the date of the due date or of the payment) means the label should describe the date shown. "Paga em <payment date>" does that. **Verdict: it does not violate the intent, and no user-visible outcome contradicts the spec's purpose. It is not counted as a failure.** Recommendation: change the AC 2 wording to "when the bill is settled (`settled_on` set)".

---

## Edge Cases

| Edge case | Evidence | Result |
| --------- | -------- | ------ |
| close = due = 10 | `test_bill_period.py:49-51` | ✅ |
| nominal due 2026-09-07 → 09-08 | `test_bill_period.py:57-58` | ✅ |
| payment 0 or negative → 422 | `test_bill_payment_service.py:152` | ✅ |
| negative declared total → 422 | `test_bill_manual.py:148`; API `test_credit_card_bills_api.py:273,315` | ✅ |
| closed card accepts payments | `test_bill_payment_service.py:208` | ✅ |
| linked payment deleted | `test_transaction_bill_hooks.py:280-281,297-298`; `test_import_undo_bills.py:106-108`; `test_account_delete_bills.py:54-56`; `test_sync_bills.py:269-272`; user delete `test_delete_user_bills.py:54-56` (`paid_amount == 0.00`, `settled_on is None`, `"closed"`) | ✅ |
| card account deleted | `test_account_delete_bills.py:88-93` (PostgreSQL) | ✅ |
| rules applied / category deleted with reassignment / placeholder upgrade refresh bills (AD-004) | rules `test_rule_apply_bills.py:70,82,122` (`0.00`, `0.00`, `1000.00`); category `test_category_delete_bills.py:62,78` (`100.00`, `0.00`); placeholder `test_import_bills.py:178-181` (`is_ignored is True`, `computed_total == 0.00`) | ✅ for the three named paths |
| concurrent imports: one bill | `test_bill_service.py:336`, `:347-348` (PostgreSQL) | ✅ |
| empty bill: 0, `paid` once closed | `test_bill_service.py:98-100`, `:290` | ✅ |
| incompatible cycle days → 422 | `test_account_cycle_relink.py:153-156`, `:176-179` | ✅ |

---

## Round 1 Gap Closure (re-confirmed)

| Round 1 gap | Fix (`file:line`) | Test (`file:line`) | Closed? |
| ----------- | ----------------- | ------------------ | ------- |
| Import undo refresh | `backend/app/api/import_logs.py:94-114` | `backend/tests/test_import_undo_bills.py:70,106-108,114` | ✅ |
| Non-card account deletion refresh | `backend/app/services/account_service.py` (`collect_bill_ids` → delete → `refresh_bills`) | `backend/tests/test_account_delete_bills.py:54-58` | ✅ |
| Card account deletion on PostgreSQL | `backend/app/services/account_service.py` (card branch) | `backend/tests/test_account_delete_bills.py:61-93` | ✅ |
| Concurrent batches both linked | n/a | `backend/tests/test_bill_service.py:323-348` | ✅ |
| BVIEW AC 8 cross-page | n/a | `frontend/src/pages/credit-cards-consistency.test.tsx:156-170` | ✅ |
| Sync phantom cleanup refresh | `backend/app/services/connection_service.py:1647,1652` | `backend/tests/test_sync_bills.py:269-272` | ✅ |

These tests pass in the round 3 gate. Round 2's sensor already killed their mutants (M1-M6, M13, M14 there).

## Round 2 Gap Closure

| Round 2 gap | Fix (`file:line`) | Test (`file:line`): assertion | Mutation | Closed? |
| ----------- | ----------------- | ----------------------------- | -------- | ------- |
| Category delete with reassignment | `backend/app/services/category_service.py:413-420` (collect moved ids), `:430` (`touch`) | `backend/tests/test_category_delete_bills.py:62` `computed_total == Decimal("100.00")` (out of an ignored category); `:78` `== Decimal("0.00")` (into one) | M1 killed (behavior test and guard) | ✅ |
| Rules applied to existing rows | `backend/app/services/rule_service.py:1455,1458` (`apply_single_rule`), `:1527-1531` (`apply_all_rules`) | `backend/tests/test_rule_apply_bills.py:70` (single, `0.00`), `:82` (all, `0.00`), `:122,126` (flagged category: `1000.00`, expenses `0.0`) | M2, M2b, M3 killed | ✅ |
| Recurring placeholder upgrade | `backend/app/services/import_service.py:1106` | `backend/tests/test_import_bills.py:178-181` `computed_total == Decimal("0.00")` | M4 killed | ✅ |

## Follow-ups

| Item | Fix | Test | Mutation | Result |
| ---- | --- | ---- | -------- | ------ |
| T73 user deletion in a shared workspace | `backend/app/services/admin_service.py:197-198` (collect before), `:222` (refresh after the accounts are gone) | `backend/tests/test_delete_user_bills.py:54-56` | M5 killed by the test; M5g killed by the guard | ✅ |
| T74 account create balance | `backend/app/api/accounts.py:156` | `backend/tests/test_card_available_credit.py:76-77` | M7 killed | ✅ |
| T66 detail balance | `backend/app/api/accounts.py:139-142`, `backend/app/services/account_service.py:64-71,159-160` | `backend/tests/test_card_available_credit.py:53-56` | M6 killed | ✅ |
| T64 AD-004 guard | `backend/tests/test_ad004_guard.py` | passes on HEAD (2 passed). It fails when the refresh is removed from T61's path (M1), T62's path (M2) and T73's path (M5g) | 3/3 killed | ✅ |

---

## AD-004 Write-Path Audit (final)

I ran the guard: `tests/test_ad004_guard.py` gives 2 passed. Then I searched `backend/app` (services, api, agents, tasks, cli, fiscal, providers) by hand for ORM attribute writes and `setattr` on `category_id`, `is_ignored`, `amount`, `date`, `account_id`, `bill_id`, `paid_bill_id`, `effective_bill_date`, `type` and `transfer_pair_id`. The guard's AST patterns cannot see these writes.

| Write path | Bill refresh | Result |
| ---------- | ------------ | ------ |
| Round 2 table rows (transaction CRUD, import, import undo, account delete/update, sync, phantom cleanup, recurring, category flag, transfer detection, bill CRUD/payments, payee, workspace move) | unchanged since round 2 | ✅ |
| `category_service._transfer_category_references` | `touch` `:430` | ✅ (fixed) |
| `rule_service.apply_single_rule` / `apply_all_rules` (ORM writes via `apply_rule_actions`, `tx.category_id = None` `:1505`) | `touch` `:1458`, `:1531` | ✅ (fixed) |
| `import_service` placeholder upgrade (`placeholder.is_ignored = True` `:1046`) | `touch` `:1106` | ✅ (fixed) |
| `admin_service.delete_user` | `refresh_bills` `:222` | ✅ (fixed) |
| `transaction_service.link_existing_as_transfer` (`:1178`), `create_transfer_counterpart` (`:1260`), update with paired legs (`:1611-1637`), toggle ignore (`:2033`) | `touch` / `_sync_card_bills` in the same function | ✅ |
| `transfer_detection_service` pair/apply/unlink (`:502-507`, `:594-601`, `:620-622`) | `touch` | ✅ |
| `connection_service` sync ORM writes (`:1189`, `:1255`, `:1427`, `:1771-1775`, `:2218-2260`, `:2375`, `:2403`) | `_sync_account_bills` refreshes every bill of the synced card | ✅ |
| `account_service` opening-balance ORM writes (`:474-485`, `:622-624`) | not needed: opening rows are never counted | ✅ |
| `tasks/fx_*` (`amount_primary` only) | not needed: the bill total reads `amount` | ✅ |
| **`api/reconciliation._settle` transfer accept (`:559-562`, `leg.transfer_pair_id = pair_id`, from `accept_suggestion` `:421-464`)** | **none** | ❌ Probe: stored `computed_total` `0.00`, recomputed `1000.00` |

---

## Discrimination Sensor

**Scratch**: `git worktree add --detach <scratchpad>/mut HEAD`, with `frontend/node_modules` symlinked in. A script applied each mutation as one exact replacement and ran the covering tests: backend with `POSTGRES_TEST_URL` on a throwaway `public.ecr.aws/supabase/postgres:17.11.0.002` container (`ccr3-pg`), frontend with vitest. It then restored the file with `git checkout`. The scratch was removed with `git worktree remove --force`, and the container with `docker rm -f`. Real-tree `git status --porcelain`: empty before and empty after (they match).

| # | File:line | Mutation | Killed? | Killing test |
| - | --------- | -------- | ------- | ------------ |
| M1 | `backend/app/services/category_service.py:430` | category delete drops `touch(moved_ids)` (round 2 gap 1) | ✅ | `test_category_delete_bills.py::test_moving_rows_out_of_an_ignored_category_raises_the_bill_total`; also `test_ad004_guard.py` |
| M2 | `backend/app/services/rule_service.py:1458` | `apply_single_rule` drops its refresh call (round 2 gap 2; refresh removal) | ✅ | `test_ad004_guard.py::test_every_bulk_transaction_write_refreshes_bills` |
| M2b | same as M2 | same mutant, behavior tests only | ✅ | `test_rule_apply_bills.py::test_apply_single_rule_ignoring_a_card_purchase_drops_the_bill_total` |
| M3 | `backend/app/services/rule_service.py:1527` | `apply_all_rules` collects no changed rows | ✅ | `test_rule_apply_bills.py::test_apply_all_rules_ignoring_a_card_purchase_drops_the_bill_total` |
| M4 | `backend/app/services/import_service.py:1106` | import drops `touch(upgraded_placeholders)` (round 2 gap 3) | ✅ | `test_import_bills.py::test_upgraded_placeholder_ignored_by_a_rule_leaves_its_bill_updated` |
| M5 | `backend/app/services/admin_service.py:222` | user delete drops `refresh_bills` (T73) | ✅ | `test_delete_user_bills.py::test_deleting_the_paying_user_unpays_the_other_users_bill` |
| M5g | same as M5 | same mutant, guard only | ✅ | `test_ad004_guard.py::test_every_bulk_transaction_write_refreshes_bills` |
| M6 | `backend/app/api/accounts.py:139-142` | GET account back to the unfloored `serialize_account` (T66) | ✅ | `test_card_available_credit.py::test_detail_and_list_show_the_same_owed_amount_and_available_credit` |
| M7 | `backend/app/api/accounts.py:156` | POST account returns the unfloored serializer (T74) | ✅ | `test_card_available_credit.py::test_create_returns_the_floored_balance_and_available_credit` |
| M8 | `backend/app/services/dashboard_service.py:1016` | `projected_count` counts realized rows (`not bill_projected_row`) | ✅ | `test_dashboard_projected_count.py::test_unpaid_purchases_are_counted_per_category` |
| M9 | `frontend/src/lib/settlement-dates.ts:26` | settlement date label flipped (`paid: !!is_bill_projected`) | ✅ | `transactions-settlement-dates.test.tsx` (4 of 7 fail) |
| M10 | `frontend/src/lib/settlement-dates.ts:26` | "Lançada em" shows the bill date | ✅ | `transactions-settlement-dates.test.tsx` (3 fail) |
| M11 | `frontend/src/lib/settlement-dates.ts:19` | `accrual` gets settlement labels (`mode === 'cash'` guard) | ✅ | `transactions-settlement-dates.test.tsx` (accrual case) |
| M12 | `frontend/src/pages/transactions.tsx:1193` | desktop row drops the Prevista badge | ✅ | `transactions-settlement-dates.test.tsx` (1 fail) |
| M13 | `frontend/src/pages/dashboard.tsx:961` | projected count badge shown for 0 (`>= 0`) | ✅ | `dashboard.test.tsx` (Mercado `/^Mercado$/`) |
| M14 | `frontend/src/pages/dashboard.tsx:483` | projected count never reaches the badge (`0`) | ✅ | `dashboard.test.tsx` (Compras `(2 projected)`) |
| M15 | `frontend/src/pages/categories.tsx:280` | bill payment badge keyed on `is_ignored` | ✅ | `categories-bill-payment.test.tsx` |
| M16 | `frontend/src/components/credit-card/bill-info.tsx:41` | dialog swaps Quitada / Não quitada | ✅ | `transaction-dialog.test.tsx` (2 fail) |
| M17 | `frontend/src/lib/bill-payment.ts:8` | payment link loses its month scope | ✅ | `account-detail-bills.test.tsx`, `credit-cards.test.tsx` |

**Sensor depth**: expanded. 19 runs over 17 distinct behavior-level mutants: one or more per round 2 gap, T73, T66/T74, a refresh removal caught by the T64 guard (M2; also M1 and M5g), and 9 in ADJ frontend code (including the settlement date label M9-M11 and the projected count badge M13-M14).
**Result**: 19/19 killed. The sensor passes.

The reconciliation gap is not a mutant: the code has no refresh call there and no test. The scratch probe `tests/test_probe_recon.py` (scratch only, never committed) stands in for the sensor on that path. I also confirmed that the guard does not list `api/reconciliation.py` with M1 removed, so the path is invisible to it.

---

## Gate Check

- **Backend**: `TZ=UTC python -m pytest -q -rs` with `POSTGRES_TEST_URL` pointing at the throwaway container: **4781 passed, 0 failed, 0 skipped**. PostgreSQL-only tests ran.
- **Backend lint/types**: `ruff check .`: all checks passed. `ty check`: all checks passed.
- **Frontend**: `npm run typecheck && npm run lint && npm test`: exit 0. **126 files, 1071 tests passed.**
- **Test count before the feature** (`7da4813`): backend 4457, frontend 968. **Now**: 4781 / 1071. **Delta**: +324 / +103. Round 2 had 4765 / 1055, so there is no decrease.
- **Skipped tests**: none.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / surgical changes (Phase 11-12) | ✅ |
| Matches patterns (`collect_bill_ids` → write → `refresh_bills`/`touch`; `get_serialized_account` reuses the list query) | ✅ |
| Spec-anchored outcome check | ✅ (0 spec-precision gaps) |
| Per-layer coverage (domain 1:1; routes happy + edge + error) | ✅ |
| Every new test maps to an AC, edge case, or Done-when | ✅ |
| AD-004: every card/payment write path refreshes bills | ❌ (reconciliation transfer accept) |

---

## Fix Plans

### Fix 1: Refresh bills when a reconciliation transfer suggestion is accepted (Major)
- **Root cause**: `_settle` in `backend/app/api/reconciliation.py:559-562` writes `transfer_pair_id` on both legs and `accept_suggestion` commits (`:464`) without `bill_service.touch`. Pairing a linked bill payment with its card credit takes the credit out of the bill's computed total.
- **Fix task**: After the nested block in `accept_suggestion`, `touch` the legs of every accepted transfer member (or call `touch(session, [moved.id, counterpart.id])` at the end of the transfer branch of `_settle`). Extend the T64 guard to flag `transfer_pair_id` ORM assignments, or allow-list them with a reason. Test (new `backend/tests/test_reconciliation_bills.py`): link a payment with no counterpart, add the card credit and a second equal debit so the pair is queued, accept the suggestion through the API, then assert `computed_total == Decimal("1000.00")` and `needs_counterpart` false.
- **Where**: `backend/app/api/reconciliation.py:421-562`, `backend/tests/test_ad004_guard.py`.

---

## Known Open Items (not counted as failures)

- The `settlement` transactions-page summary counts projected purchases. This is outside the spec.
- The import screen does not show `bills_linked`/`bills_created`. The API returns them (`backend/tests/test_import_bills.py:101-103`).
- The orchestrator does the browser checks: T50 layout at 375 px, T60 badge truncation, and the ADJ rows and dialog in the real app.
- The SPEC_DEVIATION in `frontend/src/lib/settlement-dates.ts` is accepted on intent (see the assessment above). Changing the AC 2 wording is recommended.

---

## Requirement Traceability Update

| Requirement | New status |
| ----------- | ---------- |
| BILL-02, BILL-03, BILL-04, BIMP-01, BPAY-01, BPAY-03, BDAY-01, BMATCH-01, BMATCH-02, BMATCH-03, BREP-01, BREP-02, BVIEW-01, ADJ-01, ADJ-02, ADJ-03, ADJ-04, ADJ-05, ADJ-06, ADJ-07 | ✅ Verified |
| BILL-01 | ❌ Needs fix: the stored computed total goes stale when a reconciliation transfer suggestion pairs a linked payment with its card credit |
| BPAY-02 | ❌ Needs fix (same path: a pair made outside `bill_payment_service`/transfer detection does not refresh the bill) |

---

## Summary

**Overall**: ❌ Not ready

**Spec-anchored check**: 87/87 ACs match the spec outcome. 0 spec-precision gaps. 11/11 edge cases covered. 1 SPEC_DEVIATION, accepted on intent.
**Round 1 gaps**: 6/6 closed. **Round 2 gaps**: 3/3 closed, each with a killed mutation. **Follow-ups**: T73, T74 and T64 verified.
**Sensor**: 19/19 mutation runs killed.
**Gate**: backend 4781 passed (PostgreSQL included, 0 skipped); frontend 1071 passed; ruff and ty clean.
**New gap**: 1 AD-004 write path, reproduced: reconciliation transfer accept.

**Next steps**: this was round 3, so the fix→re-verify bound is reached. Escalate to the owner with Fix 1. It is a one-call fix plus one test.
