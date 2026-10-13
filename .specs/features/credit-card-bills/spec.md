# Credit Card Bills Specification

PRD: `.specs/prd/v0.16.3-selfhost.4-cartao-de-credito.md` (approved 2026-10-12) · Target release: `0.16.3-selfhost.4`

## Problem Statement

A credit-card bill (`CreditCardBill`) exists only when a provider (Pluggy `/bills`) delivers one. Cards fed by manual entry or CSV/OFX import, the real case of this self-hosted fork, have no stored bill: the account detail page derives cycles on the fly, nothing records whether a bill was paid, and the payment made from the checking account counts as an ordinary expense. The dashboard therefore counts the bill twice (the card purchases plus the payment), payments made on the next business day after a weekend due date never match their bill, and a user with several cards must open each account to see their bills.

## Goals

- [ ] Every credit card with close and due days configured has one stored bill per reference month, and 100% of its non-opening transactions are linked to a bill after import, manual entry or the upgrade backfill.
- [ ] A bill payment linked to a bill never counts as income or expense in the dashboard, reports or budgets (0 occurrences).
- [ ] The effective due date equals the next Brazilian business day on or after the nominal due date in 100% of automated test cases.
- [ ] A payment with a single candidate bill at the exact remaining amount links with zero user interaction; any other candidate resolves in at most 2 clicks.
- [ ] In the new `settlement` accounting mode, card purchases count as expenses only on the date their bill is fully paid, and as projected expenses until then.

## Out of Scope

| Feature | Reason |
| ------- | ------ |
| State and municipal holidays; calendars of other countries | PRD: Brazil national calendar only in this release |
| Interest, fines, IOF, revolving credit and computed minimum payment | PRD out of scope |
| Importing bill PDFs | PRD out of scope |
| Bills for accounts whose type is not `credit_card` | PRD out of scope |
| Changing `cash` and `accrual` totals | Decision Q1: both modes keep their calculations; only the `accrual` drill-down display changes (Q11) |
| Partial recognition of expenses per partial payment | Decision Q9: nothing is recognized until the bill is fully paid |
| Matching historical payments during the upgrade backfill | Decision Q7: the user applies them through the bulk match preview |
| Auto-creating or auto-flagging a "bill payment" category during upgrade | Decision Q8: the user flags the category |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| Accounting mode for the new rule | New third mode `settlement`; `cash` stays the default | PRD Q1 | y |
| CC credit matching a payment | Payment is linked to the bill AND paired as a transfer with the card credit | PRD Q2 | y |
| Bill total | Computed from linked transactions plus an optional declared total; difference shown | PRD Q3 | y |
| Consolidated view location | Sub-item of Accounts at `/accounts/credit-cards` | PRD Q4 | y |
| Match tolerance after due date | 5 calendar days after the effective due date | PRD Q5 | y |
| Recognition date in `settlement` | Date of the payment that fully paid the bill | PRD Q6 | y |
| Backfill and historical payments | Backfill creates bills and links purchases only; no payment matching | PRD Q7 | y |
| Bill-payment category flag | Included as `is_bill_payment` on categories | PRD Q8 | y |
| Partially paid bill in `settlement` | Recognizes nothing; all purchases stay projected | PRD Q9 | y |
| Drill-down layout | Main date = recognition date (`settlement`) or reporting date (`accrual`); extra line "Lançada em <purchase date> · <card>" | PRD Q10, Q11 | y |
| Reference month | Month of the nominal due date (Brazilian convention already used by `creditCardCycleLabel`) | Matches the existing UI label | y |
| Bill period | `[previous close date, close date − 1]`; a purchase on the close day belongs to the next bill; close and due days clamp to the month's last day | Existing rule in `compute_effective_date` | y |
| Nominal due date | First occurrence of `payment_due_day` strictly after the close date | Existing rule in `compute_effective_date` | y |
| Business-day calendar | Weekends plus Brazilian national holidays: 01/01, Carnival Monday and Tuesday, Good Friday, 21/04, 01/05, Corpus Christi, 07/09, 12/10, 02/11, 15/11, 20/11, 25/12 | Days Brazilian banks do not process payments (FEBRABAN); 20/11 is national since Law 14.759/2023 | y |
| Effective due date | Nominal due date rolled forward to the next business day; equals nominal when it is a business day | PRD C4 | y |
| Target amount | Declared total when set, else computed total | Matches what the bank charges when the user typed it | y |
| Computed total | Sum of linked debits minus linked credits, excluding opening-balance rows, ignored rows, rows in a category flagged `is_bill_payment` or `is_ignored`, and credits that are the card leg of a bill payment | Payments reduce what is owed, not what was spent | y |
| Bill status (derived, evaluated in order) | 1 `paid`: today ≥ close date and paid ≥ target · 2 `open`: today < close date · 3 `overdue`: today > effective due date · 4 `partially_paid`: paid > 0 · 5 `closed` | Single deterministic precedence; a zero-target closed bill is `paid` | y |
| Provider bills | Keep provider `due_date` as nominal due date; period from cycle math; no automatic bill is created in a reference month already covered by a provider bill | Provider is bank truth; avoids duplicates | y |
| Ignored card transactions | Stay linked to their bill (so un-ignoring needs no relink) but do not count in the computed total | Simplest reversible behavior | y |
| Payment eligibility | A posted debit in a non-`credit_card` account of the same workspace, same currency as the bill, not ignored, not already paying a bill | One payment pays one bill | y |
| Payment pairing window | The card credit must have the same amount and fall inside the transfer rule's date window around the payment date | PRD F2/F4 reuse; one definition of a valid pair | y |
| Overdue unpaid bill in `settlement` projections | Its purchases are projected in the current month, not in the past month of the due date | A past-month projection is never seen; the debt is still due | y |
| CC transactions without a bill (no cycle configured) in `settlement` | Bucketed by purchase date, as in `cash` | PRD C5 | y |
| Transactions list period filter in `settlement` | Buckets card rows by recognition date when paid, else by the bill's effective due date | Same month everywhere the user looks (existing `reporting_date_col` contract) | y |
| Shared credit limit on the consolidated page | Accounts sharing a `shared_balance_group` add their limit once (the highest limit in the group) | Avoids double-counting a shared limit | y |
| Amount equality for matching | Equal to the cent (`Decimal` quantized to 0.01) | PRD "centavos" tolerance, kept exact | y |
| Close/due days near month end | Combinations that map two cycles to one reference month are rejected at account create/update (HTTP 422 `incompatible_cycle_days`) | Owner decision 2026-10-12; keeps one bill per reference month | y |
| Permissions | Mutating endpoints require `current_writable_workspace`; reads require `current_workspace` | Existing convention | y |

**Open questions:** none. All assumptions confirmed by the owner on 2026-10-12.

---

## User Stories

### P1: Bills exist for every configured card ⭐ MVP

**User Story**: As a user whose card is fed by imports, I want each bill stored with its period, dates, totals and status, so that I know what I owe and what I already paid.

**Why P1**: Every other story reads or writes a stored bill.

**Acceptance Criteria**:

1. The system SHALL store at most one bill per card per reference month.
2. WHEN a bill is computed for close day 5 and due day 12 with reference month 2026-09 THEN the system SHALL set period `2026-08-05..2026-09-04`, close date `2026-09-05`, nominal due date `2026-09-12` and effective due date `2026-09-14`.
3. WHEN close day is 31 and the month has 30 days THEN the system SHALL clamp the close date to the month's last day.
4. WHEN a bill spans a year boundary (reference month 2027-01, close day 5, due day 12) THEN the system SHALL set period `2026-12-05..2027-01-04`.
5. The system SHALL return for each bill: computed total, declared total (nullable), paid amount, remaining amount (target − paid, never below 0), overpaid amount (paid − target when positive), status and source (`provider`, `auto`, `manual`).
6. WHEN a bill's derived inputs change (linked rows, payments, today) THEN the system SHALL return the status defined by the precedence in Assumptions without storing it.
7. WHEN the user creates a manual bill with reference month, close date and nominal due date THEN the system SHALL store it with source `manual` and link the card's transactions whose date falls in its period and that have no manual override.
8. IF the user creates a bill for a reference month the card already has THEN the system SHALL respond HTTP 409 and store nothing.
9. WHEN the user edits the declared total of any bill THEN the system SHALL store it and recompute target, remaining and status.
10. IF the user edits the dates of a `provider` bill THEN the system SHALL respond HTTP 422.
11. WHEN the user deletes an `auto` or `manual` bill THEN the system SHALL unlink its transactions and payments and SHALL NOT delete any transaction.
12. WHEN the card's close or due day changes THEN the system SHALL recompute dates of its `auto` and `manual` bills that have no linked payment and relink their transactions, and SHALL leave bills with payments unchanged.
13. WHILE a card lacks `statement_close_day` or `payment_due_day` the system SHALL NOT create automatic bills for it.
14. WHEN the upgrade runs THEN the system SHALL create `auto` bills covering every existing transaction of each configured card, link those transactions, and produce the same result when run twice.
15. The system SHALL keep provider-synced bills and their transaction links unchanged by the backfill.

**Independent Test**: Configure a card (close 5, due 12), insert transactions on 2026-08-04, 2026-08-05 and 2026-09-04, run the backfill, then list bills: 2026-08 holds the first, 2026-09 holds the other two, with the dates of AC 2.

---

### P1: Imported card transactions join their bill ⭐ MVP

**User Story**: As a user, I want transactions I import into a card to land on the right bill automatically, creating the bill when missing.

**Why P1**: Without it, new data falls outside bills after the backfill.

**Acceptance Criteria**:

1. WHEN a transaction is created on a configured card by import, sync or manual entry THEN the system SHALL link it to the bill whose period contains its date.
2. WHEN no bill exists for that period THEN the system SHALL create an `auto` bill and link the transaction.
3. WHEN a transaction dated on the close day is created THEN the system SHALL link it to the next bill.
4. WHILE a transaction has a manual override (`effective_bill_date`) the system SHALL link it to the bill whose effective or nominal due date equals the override, creating none.
5. WHEN a card transaction's date or account changes THEN the system SHALL relink it to the bill of its new period.
6. WHEN an import finishes THEN the system SHALL report the number of transactions linked to bills and the number of bills created.
7. IF the same file is imported twice THEN the system SHALL create no duplicate bill.
8. WHEN an installment row is created THEN the system SHALL link it to the bill of the installment's own date.

**Independent Test**: Import a CSV with rows on 2026-09-04, 2026-09-05 and 2026-10-06 into a card with close 5; the import summary reports 3 linked and the bills 2026-09, 2026-10 and 2026-11 hold one row each.

---

### P1: Bill payments are linked and leave the totals ⭐ MVP

**User Story**: As a user, I want to mark that a checking-account debit paid a bill, fully or partly, so that it stops counting as an expense and the bill shows as paid.

**Why P1**: Removes the double-counted expense, the core problem.

**Acceptance Criteria**:

1. WHEN the user links an eligible payment to a bill THEN the system SHALL record the link and recompute the bill's paid amount and status.
2. The system SHALL exclude a linked payment from income and expense totals in dashboard, reports and budgets, in every accounting mode.
3. WHEN a payment is linked and the bill's card has an unpaired credit with the same amount inside the transfer rule's window THEN the system SHALL pair the payment and that credit as a transfer.
4. WHEN a payment is linked and no such card credit exists THEN the system SHALL keep the link and the API SHALL flag the payment as `needs_counterpart`.
5. WHEN the reference payment (1,283.20 on 2026-09-14 from "Nubank") is linked to the 2026-09 bill of "Cartão de Crédito Nubank" whose target is 1,283.20 THEN the system SHALL report status `paid` and remaining 0.
6. WHEN a 500.00 payment is linked to a bill whose target is 1,283.20 and today is on or before its effective due date THEN the system SHALL report status `partially_paid` and remaining 783.20.
7. WHEN two partial payments summing the target are linked THEN the system SHALL report status `paid`.
8. WHEN linked payments exceed the target THEN the system SHALL report status `paid` and the overpaid amount.
9. WHEN the user unlinks a payment THEN the system SHALL remove the link, unpair the transfer created by AC 3, and recompute the bill status.
10. IF the transaction is a credit, belongs to a `credit_card` account, is ignored, or has a different currency than the bill THEN the system SHALL respond HTTP 422.
11. IF the payment already pays another bill THEN the system SHALL respond HTTP 409.
12. IF the bill or the transaction belongs to another workspace THEN the system SHALL respond HTTP 404.
13. WHEN a category is flagged `is_bill_payment` THEN the system SHALL exclude its transactions from income and expense totals even before they are linked.

**Independent Test**: Link the reference payment, then read the September dashboard: expenses exclude 1,283.20 and the bill reports `paid`.

---

### P2: Payments match their bill automatically or by suggestion

**User Story**: As a user, I want the system to recognize bill payments on its own and suggest the bill when it is not sure.

**Why P2**: Removes manual linking work; P1 already allows linking by hand.

**Acceptance Criteria**:

1. WHEN the nominal due date is a Saturday, Sunday or national holiday THEN the system SHALL set the effective due date to the next business day.
2. WHEN computing holidays for 2026, 2027 and 2028 THEN the system SHALL place Carnival, Good Friday and Corpus Christi on the dates derived from Easter (2026-04-05, 2027-03-28, 2028-04-16).
3. The system SHALL consider a bill a candidate for a payment when the payment date is within `[close date, effective due date + 5 days]` and the bill's remaining amount is greater than 0.
4. WHEN exactly one candidate bill has a remaining amount equal to the payment amount and that bill has exactly one such candidate payment THEN the system SHALL link them automatically.
5. WHEN a payment is below the remaining amount of its only candidate bill THEN the system SHALL offer a `partial` suggestion and SHALL NOT link automatically.
6. WHEN more than one bill or more than one payment qualifies THEN the system SHALL offer suggestions and SHALL NOT link automatically.
7. WHEN an import, sync or manual entry adds debits to a non-card account, or adds a new bill to a card, THEN the system SHALL run the matcher over unlinked eligible payments of the workspace.
8. WHEN the user opens "Vincular a fatura" on an eligible transaction THEN the system SHALL list candidate bills first, each with card, reference month, effective due date, target, remaining and match reason, followed by the other unpaid bills of all cards.
9. WHEN the user dismisses a suggestion THEN the system SHALL NOT suggest that payment-bill pair again.
10. WHEN the user opens the bulk match preview THEN the system SHALL list proposed payment-bill links with a checkbox each and SHALL write nothing until the user applies.
11. WHEN the user applies the preview THEN the system SHALL link only the checked pairs and report how many were linked and which failed with a reason.
12. WHEN the reference payment (2026-09-14) is matched against the bill with nominal due 2026-09-12 THEN the system SHALL treat it as inside the window.
13. WHEN a payment is dated 2026-09-20 for a bill whose effective due date is 2026-09-14 THEN the system SHALL NOT link it automatically and SHALL list that bill in the dialog's other unpaid bills.
14. WHEN a transaction has a pending suggestion THEN the transactions list SHALL show the indicator "Possível pagamento de fatura" with actions to confirm or dismiss.
15. The system SHALL rank candidates with a matching `is_bill_payment` category or a description containing "fatura" or "cartão" above others at equal amount and date distance.

**Independent Test**: Import a checking CSV containing the reference payment after the card bill exists; the payment links automatically and the bill reads `paid`.

---

### P2: Dashboard counts card purchases when the bill is paid

**User Story**: As a user, I want card purchases counted as expenses when I pay the bill, and the unpaid bill shown as a projected expense.

**Why P2**: Opt-in mode; P1 already removes the double count.

**Acceptance Criteria**:

1. The system SHALL accept `credit_card_accounting_mode` values `cash`, `accrual` and `settlement`, defaulting to `cash`.
2. WHILE the mode is `settlement`, WHEN a bill is `paid` THEN the system SHALL count each of its purchases as an expense in its category on the date of the payment that made paid reach the target.
3. WHILE the mode is `settlement`, WHEN a bill is not `paid` THEN the system SHALL count its purchases as projected expenses in their categories in the month of the effective due date and SHALL NOT count them as realized expenses.
4. WHILE the mode is `settlement`, WHEN an unpaid bill's effective due date is in a past month THEN the system SHALL project its purchases in the current month.
5. WHEN a 1,000.00 bill (600.00 Mercado, 400.00 Restaurantes) is paid on 2026-09-14 THEN September SHALL show 600.00 and 400.00 in those categories and August SHALL show neither.
6. WHEN that bill receives 500.00 on 2026-09-14 THEN September SHALL show 0 realized and 1,000.00 projected in those categories.
7. WHEN that bill then receives 500.00 on 2026-09-20 THEN September SHALL show 600.00 and 400.00 realized with recognition date 2026-09-20.
8. WHEN a payment that completed a bill is unlinked THEN the system SHALL move the bill's purchases back to projected.
9. WHILE the mode is `settlement`, the system SHALL bucket card transactions without a bill by purchase date.
10. The system SHALL apply the active mode to dashboard totals, category spending, budgets, reports and the split adjustments (`owner_split_offset_pnl`, `viewer_shared_pnl`).
11. WHILE the mode is `settlement`, the dashboard "Faturas de cartão em aberto" value SHALL equal the sum of remaining amounts of bills that are not `paid`.
12. WHILE the mode is `settlement` or `accrual`, the drill-down SHALL show card purchases with the bucketing date as the main date and an extra line "Lançada em <purchase date> · <card name>".
13. WHILE the mode is `settlement`, the drill-down SHALL show purchases of unpaid bills with the projected badge and the bill's effective due date as main date.
14. WHILE the mode is `cash`, the drill-down SHALL show card purchases exactly as today, without the extra line.
15. The drill-down SHALL sort rows by the date shown as main date.
16. The admin settings SHALL describe the three modes and let the admin pick one.

**Independent Test**: Set `settlement`, create the AC 5 bill unpaid, read September projections, link the payment, read September realized spending.

---

### P3: Consolidated credit card page

**User Story**: As a user with several cards, I want all bills and card transactions in one page, with a filter for one card.

**Why P3**: Read-only convenience over data the other stories create.

**Acceptance Criteria**:

1. The system SHALL add the sub-item "Cartão de Crédito" under Accounts in the navigation and the command palette, opening `/accounts/credit-cards`.
2. WHEN the page opens without a filter THEN the system SHALL show all cards for the current reference month (the month of the next effective due date).
3. WHEN the user picks a card THEN the system SHALL store it in the URL as `?account=<id>` and scope every figure to that card.
4. WHEN the user moves to the previous or next reference month THEN the system SHALL show the bills whose reference month matches.
5. The page SHALL show for the month: sum of targets, sum paid, sum remaining, the earliest effective due date among unpaid bills, total limit and total available.
6. The page SHALL list one row per bill with card, status, effective due date, computed total, declared total, difference, and links to each linked payment.
7. The page SHALL list the month's card transactions with date, description, category, amount, and a card column when showing all cards.
8. WHEN one card is selected THEN the bill figures SHALL equal those the account detail page shows for the same bill.
9. WHILE no credit card exists the page SHALL show an empty state with a call to create one.
10. WHILE a card lacks close or due day the page SHALL show a call to configure it.
11. The page SHALL render without horizontal page scroll at 375 px width.

**Independent Test**: With two cards and bills in 2026-09, open the page, check totals equal the sum of both bills, pick one card, check the URL and totals.

---

### P2: Post-delivery adjustments (owner review, 2026-10-13)

Source: `.specs/features/credit-card-bills/ajustes.md`, approved by the owner for this release.

**User Story**: As the owner using `settlement`, I want card rows, bills and categories to show bill dates and states consistently everywhere, so that a month filter never looks like it shows another month's spending.

**Why P2**: Usability and correctness fixes found while using the delivered feature.

**Acceptance Criteria**:

1. WHEN a category has `is_bill_payment` THEN the categories list SHALL show a "Pagamento de fatura" badge next to it, styled like the existing "Transferências" and "Ignorado" badges.
2. WHILE the mode is `settlement`, the transactions list SHALL show, for each card row with a bill, the reporting date as the row date with the label "Paga em" when the bill is `paid` or "Pagar até" otherwise, and below it the line "Lançada em <purchase date>".
3. WHILE the mode is `cash` or `accrual`, the transactions list SHALL show card rows exactly as before.
4. WHILE the mode is `settlement`, the transactions list SHALL show the existing "Prevista" badge on rows with `is_bill_projected = true`.
5. WHEN the user opens a card transaction that has a bill THEN the transaction dialog SHALL show, read-only, the bill (card and reference month) and either "Quitada em <settled_on>" or "Não quitada · vence em <effective due date>".
6. WHILE the mode is `settlement`, the dashboard "Gastos por Categoria" card SHALL show next to each category with projected purchases a badge with their count (e.g. "Compras (2 previstas)"); categories with none show no badge.
7. The credit card account detail page SHALL show available credit equal to `credit_limit − amount owed`, where amount owed is the card's current balance computed with the balance-date floor (AD-001/AD-002), the same balance the accounts list shows.
8. WHEN the user clicks a payment in a bill's payment list THEN the system SHALL open the transactions list highlighting that payment transaction (`/transactions?highlight=<id>` with the payment's month), not the paying account.
9. The release notes SHALL explain that card CSVs with inverted signs are handled by the existing "inverter sinal" import option saved with the mapping (owner decision: no code change).

**Independent Test**: With `settlement` on and the reference data, open October transactions: the 05/09 "Petz Digital" card purchase on the 13/10 bill shows "Pagar até 13/10/2026", "Lançada em 05/09/2026" and the "Prevista" badge.

---

## Edge Cases

- WHEN close day equals due day (both 10) THEN the system SHALL set the nominal due date to the 10th of the month after the close.
- WHEN the nominal due date falls on 2026-09-07 (holiday, Monday) THEN the system SHALL set the effective due date to 2026-09-08.
- IF a payment's amount is 0 or negative THEN the system SHALL respond HTTP 422 when linking it.
- IF the declared total is negative THEN the system SHALL respond HTTP 422.
- IF the bill's card is closed (`is_closed`) THEN the system SHALL still allow linking payments to its existing bills.
- WHEN a linked payment transaction is deleted THEN the system SHALL drop the link and recompute the bill status.
- WHEN a card account is deleted THEN the system SHALL delete its bills and unlink their payments.
- WHEN rules are applied to existing transactions, or a category is deleted and its rows move to another category, or an import upgrades a recurring placeholder, THEN the system SHALL refresh every bill whose card rows or payments changed (AD-004).
- WHEN two imports create the same bill concurrently THEN the system SHALL keep one bill and link both batches to it.
- WHEN a bill has no linked rows and no declared total THEN the system SHALL report computed total 0 and, once closed, status `paid`.
- IF a card's `statement_close_day` and `payment_due_day` would map two consecutive close dates to the same reference month (e.g. close 30, due 31) THEN creating or updating the account SHALL respond HTTP 422 with detail `incompatible_cycle_days` and store nothing.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| BILL-01 | P1: Bills exist (AC 1-6, period and status math) | Tasks | In Tasks |
| BILL-02 | P1: Bills exist (AC 7-11, manual create/edit/delete) | Tasks | In Tasks |
| BILL-03 | P1: Bills exist (AC 12-13, card cycle change) | Tasks | In Tasks |
| BILL-04 | P1: Bills exist (AC 14-15, backfill) | Tasks | In Tasks |
| BIMP-01 | P1: Imported transactions join their bill (AC 1-8) | Tasks | In Tasks |
| BPAY-01 | P1: Bill payments (AC 1-2, 5-12, link/unlink and totals) | Tasks | In Tasks |
| BPAY-02 | P1: Bill payments (AC 3-4, transfer pairing) | Tasks | In Tasks |
| BPAY-03 | P1: Bill payments (AC 13, `is_bill_payment` category) | Tasks | In Tasks |
| BDAY-01 | P2: Matching (AC 1-2, business-day calendar) | Tasks | In Tasks |
| BMATCH-01 | P2: Matching (AC 3-7, 12-13, 15, engine) | Tasks | In Tasks |
| BMATCH-02 | P2: Matching (AC 8-9, 14, dialog and suggestions) | Tasks | In Tasks |
| BMATCH-03 | P2: Matching (AC 10-11, bulk preview) | Tasks | In Tasks |
| BREP-01 | P2: Settlement mode (AC 1-11, 16) | Tasks | In Tasks |
| BREP-02 | P2: Settlement mode (AC 12-15, drill-down) | Tasks | In Tasks |
| ADJ-01 | P2: Adjustments (AC 1, category badge) | Tasks | In Tasks |
| ADJ-02 | P2: Adjustments (AC 2-4, transactions list in settlement) | Tasks | In Tasks |
| ADJ-03 | P2: Adjustments (AC 5, transaction dialog bill info) | Tasks | In Tasks |
| ADJ-04 | P2: Adjustments (AC 6, projected count badge) | Tasks | In Tasks |
| ADJ-05 | P2: Adjustments (AC 7, available credit) | Tasks | In Tasks |
| ADJ-06 | P2: Adjustments (AC 8, payment link) | Tasks | In Tasks |
| ADJ-07 | P2: Adjustments (AC 9, release notes on inverted signs) | Tasks | In Tasks |
| BVIEW-01 | P3: Consolidated page (AC 1-11) | Tasks | In Tasks |

**Coverage:** 22 total, 22 mapped to tasks (see `tasks.md` Requirement Coverage), 0 unmapped.

---

## Success Criteria

- [ ] Backfill on the production data links every card transaction of configured cards (0 unlinked rows reported).
- [ ] After matching, September 2026 dashboard expenses exclude every linked bill payment.
- [ ] At least 80% of the user's real bill payments link automatically; the rest resolve in at most 2 clicks.
- [ ] Business-day tests cover every 2026-2028 holiday listed in Assumptions.
