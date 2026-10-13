import { monthRange } from '@/lib/month-utils'
import type { Account, BillPayment, Transaction } from '@/types'

/** The transactions list highlighting a bill payment, scoped to the payment's
 *  month so the row is on screen (ADJ AC 8). */
export function billPaymentHref(payment: Pick<BillPayment, 'id' | 'date'>): string {
  const { from, to } = monthRange(payment.date.slice(0, 7))
  return `/transactions?highlight=${payment.id}&from=${from}&to=${to}`
}

/** "Vincular a fatura" applies to a debit outside a card account that pays no
 *  bill yet; the API checks the rest (BPAY AC 10). */
export function canLinkBill(tx: Transaction | undefined, account: Account | undefined): boolean {
  return !!tx && !!account && !tx.is_shared && tx.type === 'debit'
    && account.type !== 'credit_card' && !tx.paid_bill_id
}
