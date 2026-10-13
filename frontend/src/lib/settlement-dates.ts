import type { Transaction } from '@/types'

/** How a card row with a bill shows its dates in `settlement` (ADJ AC 2). */
export interface SettlementRowDates {
  /** The bill is settled, so `date` is the day it was paid. */
  paid: boolean
  /** The reporting date: the bill's payment date or its due date. */
  date: string
  /** The purchase date on the card. */
  postedOn: string
}

/** Null outside `settlement` and for rows without a bill, which keep their
 *  usual date (ADJ AC 3). */
export function settlementRowDates(
  tx: Transaction,
  mode: string | undefined,
): SettlementRowDates | null {
  if (mode !== 'settlement' || !tx.bill_id || !tx.reporting_date) return null
  // SPEC_DEVIATION: ADJ AC 2 picks "Paga em" from the bill status `paid`; this
  // reads the settlement instead (`is_bill_projected` is false once the bill
  // has `settled_on`), which is the date the row shows.
  // Reason: the two only differ for a bill fully paid before its close date,
  // where the shown date is the payment date and "Pagar até" would misread it.
  // It also needs no new backend field.
  return { paid: !tx.is_bill_projected, date: tx.reporting_date, postedOn: tx.date }
}
