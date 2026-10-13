# Credit Card Bills Validation (round 4)

**Date**: 2026-10-13
**Spec**: `.specs/features/credit-card-bills/spec.md`
**Diff range**: `7da4813..HEAD` (HEAD `aea94ae`, 90 commits). Since round 3 (`9fd6f85`): `91d0d1d..aea94ae`, which covers AD-005, the design addendum and Phase 13 (T75-T78).
**Verifier**: independent sub-agent, round 4 (author ≠ verifier). The owner approved this extra round after the round 3 FAIL.

## Validation: credit-card-bills - PASS ✅

Round 3 gap 1 is closed. Accepting a reconciliation transfer suggestion now leaves the bill at the recomputed total. The API test `backend/tests/test_reconciliation_bills.py:98` asserts `computed_total == 1000.00`, and it fails when the listener is unregistered (mutant L1r). The fix is the AD-005 session listener (`backend/app/services/bill_service.py:201-277`). I audited it adversarially in a scratch worktree with 13 probes. It refreshes the right bills on every ORM path the app uses, defers correctly through savepoints, does not recurse, and adds no queries to commits that leave the watched attributes alone. Core bulk statements still need an explicit refresh, and the T64 guard still enforces that.

All gates are green. Backend: 4792 passed, 0 skipped, PostgreSQL included. Frontend: 1072 passed. ruff and ty are clean. The sensor made 24 runs over 21 distinct mutants. All 20 non-equivalent mutants were killed. One equivalent mutant survived: L7, the re-entrancy flag, which no code path can reach (see the sensor section). All 87 ACs and 11 edge cases trace to assertions that match the spec outcome.

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1-T74 | ✅ Done | Verified in rounds 1-3; checkboxes `[x]` |
| T75 single sync refresh core | ✅ Done | `backend/app/services/bill_service.py:170-198`. `refresh_bills` is `await session.run_sync(refresh_bills_sync, ids)` (`:198`); the full suite passes unchanged |
| T76 session listener | ✅ Done | `backend/app/services/bill_service.py:201-277`; test `backend/tests/test_bill_refresh_listener.py` (10 cases) |
| T77 reconciliation accept | ✅ Done | `backend/tests/test_reconciliation_bills.py`. No explicit `touch` was needed. The guard is not extended, and the reason is documented at `:3-9` |
| T78 payment link highlight | ✅ Done | `frontend/src/pages/transactions.tsx:347-349` (URL sync keeps `highlight`), `:447-466` (flash effect moved below the query and re-run on `data`); test `frontend/src/pages/transactions-highlight.test.tsx:115-123` |

---

## Spec-Anchored Acceptance Criteria

I re-derived coverage from spec.md. No test file cited in the round 3 tables changed between `9fd6f85` and HEAD. The changed and new test files are `test_bill_refresh_listener.py`, `test_reconciliation_bills.py`, `test_cli_rebuild_bills.py` and `transactions-highlight.test.tsx`. So the round 3 line citations still point at the same assertions. I re-read a sample against the spec outcome: P1 AC 1, 2 and 6, BPAY AC 3, 5 and 6, BMATCH AC 12 and BREP AC 5. The rows below add the round 4 evidence where it applies (BILL AC 5, BPAY AC 3, ADJ AC 8). Backend paths are relative to `backend/tests/`, frontend paths to `frontend/src/`.

### P1: Bills exist (BILL-01..04)

| AC | Spec outcome | `file:line`: assertion | Result |
| -- | ------------ | ---------------------- | ------ |
| 1 | at most one bill per card/month | `test_bill_service.py:167-178` `created_again is False`, `count == 1`; `:190` `pytest.raises(IntegrityError)` | ✅ |
| 2 | 08-05..09-04, close 09-05, due 09-12, eff 09-14 | `test_bill_period.py:18-25` `== BillPeriod(period_start=date(2026, 8, 5), ..., effective_due_date=date(2026, 9, 14))`; API `test_credit_card_bills_api.py:136-140` | ✅ |
| 3 | close 31 clamps | `test_bill_period.py:31` `close_date == date(2026, 9, 30)` | ✅ |
| 4 | 2026-12-05..2027-01-04 | `test_bill_period.py:40-41` | ✅ |
| 5 | computed, declared (nullable), paid, remaining ≥ 0, overpaid, status, source | `test_credit_card_bills_api.py:142-149`; `test_bill_service.py:73-74` (overpaid `16.80`, remaining `0.00`) | ✅ The stored value now stays current on every ORM commit: `test_bill_refresh_listener.py:87` `== (Decimal("600.00"), Decimal("0.00"), None)`, `:139` `== (Decimal("1000.00"), Decimal("1000.00"), date(2026, 9, 14))` |
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
| 3 | paired with the card credit | `test_bill_payment_pairing.py:102-106`. Pairing through the reconciliation queue: `test_reconciliation_bills.py:92` (one shared `transfer_pair_id`), `:98` `computed_total == Decimal("1000.00")`, `:101` `status == "partially_paid"` | ✅ |
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
| 8 | payment link → `/transactions?highlight=<id>` in the payment's month | `pages/account-detail-bills.test.tsx:138` `href '/transactions?highlight=pay-1&from=2026-09-01&to=2026-09-30'`; `pages/credit-cards.test.tsx:184`. Target page (T78): `pages/transactions-highlight.test.tsx:119` row `toHaveClass('securo-highlight-flash')`, `:120` `highlight` still `'pay-1'` in the URL, `:121` list called with `from: '2026-09-01', to: '2026-09-30'`, `:122` other row not flashed | ✅ |
| 9 | release notes explain the inverted-sign option | `deploy/public/RELEASE-NOTES.md:106-109`. It names the real UI label "Inverter valores (trocar entrada/saída)" (`frontend/src/locales/pt-BR.json:1669`), and the option is saved with the mapping (`backend/app/schemas/import_mapping.py:14` `flip_amount`). Docs only, no test by design | ✅ (document evidence) |

**Status**: 87/87 ACs trace to an assertion, or to document or manual evidence, that matches the spec outcome. There are no spec-precision gaps.

### SPEC_DEVIATION 1 assessment (`frontend/src/lib/settlement-dates.ts:19-26`)

ADJ AC 2 says the label is "Paga em" when the bill is `paid`. The code reads `!tx.is_bill_projected` instead, which is true when the bill has `settled_on` (`backend/app/services/_query_filters.py:209-213`). Under the status precedence, `paid` means `today ≥ close date and paid ≥ target`, and `settled_on` is set exactly when `paid ≥ target` (`bill_service.py:203-213`). The two disagree only for a bill paid in full before its close date. For that bill the status is `open`, but the reporting date is already the payment date (`reporting_date_of`, `_query_filters.py:198-200`). A literal implementation would show "Pagar até <payment date>", a deadline that is really a past payment. The owner's text (`ajustes.md`: "Pagar até" or "Paga em" depending on whether the bill is paid; the date of the due date or of the payment) means the label should describe the date shown. "Paga em <payment date>" does that. **Verdict: it does not violate the intent, and no user-visible outcome contradicts the spec's purpose. It is not counted as a failure.** Recommendation: change the AC 2 wording to "when the bill is settled (`settled_on` set)".

### SPEC_DEVIATION 2 assessment (`backend/app/services/bill_service.py:258-268`, accepted by the orchestrator)

The design addendum adds the pair leg's bills only when `transfer_pair_id` changes. The code adds them whenever a collected row has a `transfer_pair_id`, whether it changed or not. The spec's computed-total rule excludes "credits that are the card leg of a bill payment" (`_computed_total`, `:159-163`). That status depends on the *other* leg's `paid_bill_id`. So linking, unlinking or deleting an already paired payment changes the card bill's total while that leg's own row stays the same. Under the addendum's literal rule that bill would go stale. Two tests prove it. `test_bill_refresh_listener.py:189` checks that linking a pre-paired payment moves the October bill from `-700.00` to `300.00`. `:216` checks that deleting the payment returns it to `-700.00`. Mutant L8, which removes the pair-leg lookup, is killed by `:189`. The cost is one indexed `SELECT` on `transactions` per commit that touches a paired row. **Verdict: the deviation is required for the spec outcome (BILL AC 5, BPAY AC 9) and is not a failure.** The addendum's wording should follow the code.

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
| rules applied / category deleted with reassignment / placeholder upgrade refresh bills (AD-004) | rules `test_rule_apply_bills.py:70,82,122` (`0.00`, `0.00`, `1000.00`); category `test_category_delete_bills.py:62,78` (`100.00`, `0.00`); placeholder `test_import_bills.py:178-181` (`is_ignored is True`, `computed_total == 0.00`) | ✅ for the three named paths; every other ORM path is covered by AD-005 (see the audit) |
| concurrent imports: one bill | `test_bill_service.py:336`, `:347-348` (PostgreSQL) | ✅ |
| empty bill: 0, `paid` once closed | `test_bill_service.py:98-100`, `:290` | ✅ |
| incompatible cycle days → 422 | `test_account_cycle_relink.py:153-156`, `:176-179` | ✅ |

---

## AD-005 Audit (adversarial)

The listener lives at `backend/app/services/bill_service.py`. `_WATCHED` is at `:204-218`. `before_flush` `_collect_touched_bills` (`:224-245`) records the old, unchanged and new `bill_id`/`paid_bill_id` of new, dirty-with-a-watched-change and deleted `Transaction` rows, plus their `transfer_pair_id` values. `before_commit` `_refresh_touched_bills` (`:248-273`) returns early inside a savepoint or while a refresh runs (`:250`), flushes (`:253`), pops the ids, adds the pair legs' bills (`:258-268`) and runs `refresh_bills_sync` under the re-entrancy flag (`:269-273`). Registration is at `:276-277`. I checked each question below with a probe in a scratch worktree (`tests/test_probe_ad005.py`, 13 cases, never committed) or with a mutant.

| Question | Evidence | Result |
| -------- | -------- | ------ |
| Every ORM path that changes a watched attribute | The 13 watched columns cover every input of `_computed_total` (`:146-167`: `type`, `amount`, `bill_id`, `source`, `is_ignored`, `category_id`, `transfer_pair_id`) and of the paid/settled pass (`:182-188`: `paid_bill_id`, `date`, `amount`). Inserts, deletes and dirty rows are all handled. Probes: an `amount` change, a move between bills (`bill_id` old and new, P11), unpairing one leg only (P12) and the `expire_on_commit=True` change and delete path (P7) all store the recomputed value. Mutants L2, L3, L4, L5 and L9 (drop a watched column, drop old values, drop deletes) are each killed | ✅ |
| Relationship assignment instead of the FK column | Probes P5 (`Transaction(bill=bill)`) and P6 (`tx.category = ignored`) leave the bill stale. The FK column is synced after `before_flush`, so attribute history does not show it. **No app code assigns these relationships.** `grep` of `backend/app` finds only `bill=` in dataclass constructors (`bill_payment_service.py:130`, `bill_match_service.py:120`) | ⚠️ Residual, no current path (open item) |
| Savepoints (`begin_nested`) | A savepoint commit defers (`:250`). The test `test_bill_refresh_listener.py:272-279` asserts no refresh at the savepoint and exactly one at the commit (mutant L6 killed). Probes: change in a released savepoint, then commit (P2) → `900.00`; change in a rolled-back savepoint, then commit (P1) → original `600.00`; nested-in-nested rollback keeps the outer ids (P3) → `800.00` | ✅ |
| Rollbacks | Ids survive a full rollback (`session.info` is not cleared). Probe P4: the next empty commit runs one extra bill refresh, which recomputes from the database and so stays correct. Cost only | ✅ (minor cost) |
| `expire_on_commit=False` | The refresh writes the bill objects in the identity map before the commit. `test_bill_refresh_listener.py:89`, `:99` assert the in-session `bill.computed_total`. With `expire_on_commit=True`, probe P7 passes | ✅ |
| Multiple flushes per commit | Ids accumulate across flushes (`:242-245`). `test_bill_refresh_listener.py:268-278` runs two flushes and a savepoint, then gets one refresh with the summed total `700.00`. The pre-commit flush (`:253`) catches rows that are still pending. Mutant L10, which removes that flush, is killed | ✅ |
| Celery worker | `app.worker` `conf.include` loads `app.tasks.sync_tasks`, which imports `bill_service` (import check: `sync_tasks`, `recurring_tasks`, `invoice_schedule_tasks` and `app.main` all register the listener). `fx_*` and `asset_tasks` do not load it, and they write only `amount_primary`/`fx_rate_used` (`tasks/fx_backfill_tasks.py:89-90`), which are not watched. `app.cli rebuild-bills` imports `bill_service` itself (`app/cli.py:35`) | ✅ |
| `connection_service`, `import_service`, reconciliation sessions | Every session is a stock `AsyncSession` (`core/database.py:11`, `tasks/*`), so its sync `Session` carries the class listener. Reconciliation: `accept_suggestion` pairs inside `begin_nested` (`api/reconciliation.py:451`) and commits at `:464`. The deferred refresh runs at that commit (`test_reconciliation_bills.py:98`, mutant L1r killed). With the listener removed (L1all), the import and sync tests still pass, because those paths keep their explicit AD-004 refreshes, so the listener only adds redundancy there. With it on, the full suite passes | ✅ |
| Recursion | The refresh writes only `credit_card_bills`. Its flush calls `before_flush`, which skips non-`Transaction` objects, and it never calls `commit`. `test_bill_refresh_listener.py:278` `calls == [{bill.id}]` | ✅ (the flag itself is unreachable; L7 below) |
| Bills from another workspace | Ids come only from the touched rows' own FKs and from legs that share their `transfer_pair_id`. Nothing is returned to the caller; at worst it recomputes from rows. Probe P10: an unrelated session's commit runs 0 bill statements | ✅ |
| Queries on commits with no watched change | `test_bill_refresh_listener.py:251-252` (0 bill statements for a description change and for an empty commit). Probe P8: a `notes` change issues exactly 1 statement, the `UPDATE`, and inserting a non-card row with no bill issues only the `INSERT` | ✅ |
| Core bulk statements | They bypass ORM events. Probe P9: an ORM-enabled `update(Transaction)` leaves the bill stale, as expected. The T64 guard (`test_ad004_guard.py:121-127`, unchanged) still flags them: mutant G1 (remove `touch` after the bulk `sa_update` at `category_service.py:430`) is killed by the guard, and G1b by the behavior tests with the listener on, so the listener does not hide the gap. No bulk transaction statement exists outside `services`/`api` (grep of `tasks`, `agents`, `cli`, `fiscal`, `providers`) | ✅ |

**AD-005 verdict**: sound for every write path in the code today. One residual is noted: future code that assigns the `bill`/`category` relationships instead of the FK columns.

### `test_cli_rebuild_bills.py` change (approved by the orchestrator)

The old test corrupted the aggregates in the same commit that added rows. The listener now recomputes at that commit, which would erase the corruption before the rebuild ran. The new test commits the rows first, corrupts only bill columns in a commit of their own, and asserts from a fresh session that the corruption is stored. The first test checks `(5.00, 1.00, None)` at `:80-85`; the second checks `5.00` at `:110`. Only then does it run the rebuild and assert the repair (`:91-95`: `1000.00`, `1000.00`, `2026-09-14`, "1 transactions linked"; `:118`: `100.00`). It still proves that real stored corruption is repaired. Mutant R1, which removes the rebuild's `refresh_bills`, is killed by `:118`. A bill-only commit touches no watched `Transaction` attribute, so the listener cannot repair it.

---

## Round 1 Gap Closure (re-confirmed)

| Round 1 gap | Fix | Test (`file:line`) | Closed? |
| ----------- | --- | ------------------ | ------- |
| Import undo refresh | `backend/app/api/import_logs.py:94-114` | `backend/tests/test_import_undo_bills.py:70,106-108,114` | ✅ |
| Non-card account deletion refresh | `backend/app/services/account_service.py` (`collect_bill_ids` → delete → `refresh_bills`) | `backend/tests/test_account_delete_bills.py:54-58` (mutant C3 is killed here too) | ✅ |
| Card account deletion on PostgreSQL | `backend/app/services/account_service.py` (card branch) | `backend/tests/test_account_delete_bills.py:61-93` (ran against PostgreSQL) | ✅ |
| Concurrent batches both linked | n/a | `backend/tests/test_bill_service.py:323-348` | ✅ |
| BVIEW AC 8 cross-page | n/a | `frontend/src/pages/credit-cards-consistency.test.tsx:156-170` | ✅ |
| Sync phantom cleanup refresh | `backend/app/services/connection_service.py:1647,1652` | `backend/tests/test_sync_bills.py:269-272` | ✅ |

## Round 2 Gap Closure (re-confirmed)

| Round 2 gap | Fix | Test (`file:line`) | Closed? |
| ----------- | --- | ------------------ | ------- |
| Category delete with reassignment | `backend/app/services/category_service.py:430` | `backend/tests/test_category_delete_bills.py:62,78`; this round's mutants G1 and G1b are killed | ✅ |
| Rules applied to existing rows | `backend/app/services/rule_service.py:1458,1531` | `backend/tests/test_rule_apply_bills.py:70,82,122,126` | ✅ |
| Recurring placeholder upgrade | `backend/app/services/import_service.py:1106` | `backend/tests/test_import_bills.py:178-181` | ✅ |

## Round 3 Gap Closure

| Round 3 gap | Fix | Test (`file:line`): assertion | Mutation | Closed? |
| ----------- | --- | ----------------------------- | -------- | ------- |
| Reconciliation transfer accept left the bill stale (`computed_total` 0.00 vs 1000.00) | AD-005 listener `backend/app/services/bill_service.py:248-277`; the route needs no explicit call (`backend/app/api/reconciliation.py:451,464`) | `backend/tests/test_reconciliation_bills.py:98` `Decimal(str(body["computed_total"])) == Decimal("1000.00")`, `:99` `paid_amount == 600.00`, `:101` `status == "partially_paid"`; unit form `test_bill_refresh_listener.py:139` | L1r killed (listener unregistered → the API test fails) | ✅ |
| Recommendation: change ADJ AC 2 wording | not done; spec text unchanged | n/a | n/a | open (documentation only) |

---

## Discrimination Sensor

**Scratch**: `git worktree add --detach <scratchpad>/mut HEAD`, with `frontend/node_modules` symlinked in. A script applied each mutation as one exact replacement and asserted that the replacement matched exactly once. It ran the backend with `POSTGRES_TEST_URL` on a throwaway `public.ecr.aws/supabase/postgres:17.11.0.002` container (`ccr4-pg`, database owner and `public` schema owner set to `postgres` as `supabase_admin`). Unless a row says otherwise, the run was the full suite with `-x`; the frontend ran with vitest. After each mutation the file was restored with `git checkout`. Afterwards I removed the worktree with `git worktree remove --force` and `git worktree prune`, and the container with `docker rm -f ccr4-pg`. The real tree's `git status --porcelain` was empty before and empty after, so the two match.

| # | File:line | Mutation | Killed? | Killing test |
| - | --------- | -------- | ------- | ------------ |
| L1 | `backend/app/services/bill_service.py:276-277` | listener registration removed | ✅ | `test_bill_refresh_listener.py::test_inserting_a_card_row_with_a_bill_refreshes_the_total` |
| L1r | same | same, reconciliation test only | ✅ | `test_reconciliation_bills.py::test_accepting_the_transfer_of_a_linked_payment_keeps_the_bill_total` |
| L1all | same | same, full suite without `-x` | ✅ | 11 failed (10 listener cases + reconciliation), 4781 passed |
| L2 | `bill_service.py:209` | `category_id` dropped from `_WATCHED` | ✅ | `test_moving_a_row_into_an_ignored_category_drops_it_from_the_total` |
| L3 | `bill_service.py:214` | `transfer_pair_id` dropped from `_WATCHED` | ✅ | `test_pairing_a_payment_with_the_card_credit_takes_the_credit_out_of_the_total` |
| L4 | `bill_service.py:210` | `is_ignored` dropped from `_WATCHED` | ✅ | `test_ignoring_a_row_drops_it_from_the_total` |
| L5 | `bill_service.py:241` | old values (`history.deleted`) skipped for `paid_bill_id` | ✅ | `test_linking_and_unlinking_a_payment_refreshes_the_paid_amount` |
| L6 | `bill_service.py:250` | nested-transaction guard removed | ✅ | `test_refresh_runs_once_per_commit_and_does_not_recurse` |
| L7 | `bill_service.py:250` | re-entrancy flag check removed | ➖ Survived, equivalent | none can exist: `refresh_bills_sync` never calls `commit`, so `before_commit` cannot fire again while it runs. The flag is defensive code with no reachable effect. Full suite 4792 passed |
| L8 | `bill_service.py:259` | pair-leg lookup (SPEC_DEVIATION 2) disabled | ✅ | `test_linking_a_paired_payment_refreshes_the_card_leg_bill` |
| L9 | `bill_service.py:231` | deleted rows not collected | ✅ | `test_deleting_a_payment_refreshes_the_paid_amount_and_the_card_leg` |
| L10 | `bill_service.py:253` | no flush before popping the ids | ✅ | `test_inserting_a_card_row_with_a_bill_refreshes_the_total` |
| L11 | `bill_service.py:198` | async `refresh_bills` becomes a no-op (T75 single implementation) | ✅ | `test_bill_linking.py::test_rows_join_the_bill_of_their_period_creating_missing_bills` |
| G1 | `backend/app/services/category_service.py:430` | refresh after a Core bulk `sa_update` removed | ✅ | `test_ad004_guard.py::test_every_bulk_transaction_write_refreshes_bills` |
| G1b | same | same, behavior tests with the listener on | ✅ | `test_category_delete_bills.py` (2 fail) |
| R1 | `backend/app/cli.py:56` | rebuild skips `refresh_bills` | ✅ | `test_cli_rebuild_bills.py::test_rebuild_limited_to_a_workspace_leaves_other_workspaces_alone` |
| C1 | `bill_service.py:163` | card leg of a bill payment counted as a refund | ✅ | `test_bill_payment_pairing.py::test_payment_is_paired_with_the_card_credit_inside_the_window` |
| C2 | `bill_service.py:297` | `settled_on` needs `running > target` | ✅ | `test_bill_manual.py::test_editing_the_declared_total_recomputes_target_remaining_and_status` |
| C3 | `bill_service.py:70` | status `paid` needs `paid > target` | ✅ | `test_account_delete_bills.py::test_deleting_the_paying_account_unpays_the_bill` |
| C4 | `bill_service.py:62` | remaining may go below 0 | ✅ | `test_bill_service.py::TestBillStatus::test_overpayment_is_paid_and_reports_overpaid` |
| C5 | `backend/app/services/bill_match_service.py:23` | match window `+5` → `+4` days | ✅ | `test_bill_match_candidates.py::test_window_bounds_are_close_date_and_effective_due_plus_five` |
| C6 | `backend/app/core/business_days.py:64` | national holidays ignored | ✅ | `test_bill_period.py::test_effective_due_date_on_holiday_rolls_to_next_business_day` |
| F1 | `frontend/src/pages/transactions.tsx:349` | URL sync drops `highlight` (T78) | ✅ | `transactions-highlight.test.tsx` |
| F2 | `frontend/src/pages/transactions.tsx:466` | flash effect not re-run when `data` loads (T78) | ✅ | `transactions-highlight.test.tsx` |

**Sensor depth**: expanded (P0 money paths). There were 24 runs over 21 distinct behavior-level mutants; one of them (L7) is equivalent. They cover the listener (registration, watched columns, history, nested guard, re-entrancy, pair legs, deletes, pre-commit flush), the T75 single implementation, the T64 guard on a bulk statement, the CLI rebuild, core money rules (pair exclusion, settled date, paid status, remaining, match window, holidays) and T78.
**Result**: 20/20 non-equivalent mutants killed (23/23 runs). L7 is equivalent and is not counted. The sensor passes.

---

## Gate Check

- **Backend**: `TZ=UTC python -m pytest -q -rs` with `POSTGRES_TEST_URL` on the throwaway container: **4792 passed, 0 failed, 0 skipped**. PostgreSQL-only tests ran.
- **Backend lint/types**: `ruff check .`: all checks passed. `ty check`: all checks passed.
- **Frontend**: `npm run typecheck && npm run lint && npm test`: exit 0. **127 files, 1072 tests passed.**
- **Test count before the feature** (`7da4813`): backend 4457, frontend 968. **Now**: 4792 / 1072. **Delta**: +335 / +104. Round 3 had 4781 / 1071; round 4 adds 11 backend tests (10 listener + 1 reconciliation) and 1 frontend test. No count went down.
- **Skipped tests**: none.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / surgical changes (Phase 13) | ✅ |
| Single refresh implementation (T75); explicit AD-004 calls kept and idempotent | ✅ |
| Spec-anchored outcome check | ✅ (0 spec-precision gaps) |
| Every new test maps to an AC, edge case or Done-when (T76 Done-when list, T77, T78) | ✅ |
| AD-004/AD-005: every card/payment write path refreshes bills | ✅ |
| Dead code | ⚠️ the `_REFRESHING` flag (`bill_service.py:250,269-273`) cannot be reached (L7). Keeping it is harmless |

---

## Known Open Items (not counted as failures)

- The `settlement` transactions-page summary counts projected purchases. This is outside the spec.
- The import screen does not show `bills_linked`/`bills_created`. The API returns them (`backend/tests/test_import_bills.py:101-103`).
- The orchestrator does the browser checks: T50 layout at 375 px, T60 badge truncation, the ADJ rows and dialog, and the T78 highlight flash in the real app.
- SPEC_DEVIATION 1 (`frontend/src/lib/settlement-dates.ts`) is accepted on intent. Changing the ADJ AC 2 wording is still recommended.
- SPEC_DEVIATION 2 (pair legs refreshed whenever a row has `transfer_pair_id`) is accepted because the spec outcome needs it. The design addendum's wording should follow the code.
- AD-005 residual: assigning the `Transaction.bill` or `Transaction.category` relationship (instead of `bill_id`/`category_id`) on a dirty row, or `bill=` on a new row, goes past the listener. No current code does this (probes P5/P6). Before relying on it, a later change could read the FK through `inspect(obj).attrs` after `flush_context` sync, or watch the relationships.
- Bill ids collected before a rollback cause one extra recompute at the next commit (probe P4). This is a cost only.

---

## Requirement Traceability Update

| Requirement | Previous status | New status |
| ----------- | --------------- | ---------- |
| BILL-01, BPAY-02 | ❌ Needs fix (round 3) | ✅ Verified |
| BILL-02, BILL-03, BILL-04, BIMP-01, BPAY-01, BPAY-03, BDAY-01, BMATCH-01, BMATCH-02, BMATCH-03, BREP-01, BREP-02, BVIEW-01, ADJ-01, ADJ-02, ADJ-03, ADJ-04, ADJ-05, ADJ-06, ADJ-07 | ✅ Verified | ✅ Verified (re-confirmed) |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 87/87 ACs match the spec outcome, with 0 spec-precision gaps. 11/11 edge cases are covered. Both SPEC_DEVIATIONs are accepted.
**Round 1 gaps**: 6/6 closed. **Round 2 gaps**: 3/3 closed. **Round 3 gap**: 1/1 closed, with killed mutant L1r.
**AD-005**: sound on every current ORM path, savepoints, rollbacks, sessions and the worker. Bulk statements stay under the T64 guard. One residual (relationship assignment) has no current path.
**Sensor**: 20/20 non-equivalent mutants killed (23/23 runs); 1 equivalent mutant (L7) survived.
**Gate**: backend 4792 passed (PostgreSQL included, 0 skipped); frontend 1072 passed; ruff and ty clean.

**Next steps**: the orchestrator's browser re-check (T78 highlight in the real app), then the PR.
