import type { Account, Transaction } from '@/types'

/** "Vincular a fatura" applies to a debit outside a card account that pays no
 *  bill yet; the API checks the rest (BPAY AC 10). */
export function canLinkBill(tx: Transaction | undefined, account: Account | undefined): boolean {
  return !!tx && !!account && !tx.is_shared && tx.type === 'debit'
    && account.type !== 'credit_card' && !tx.paid_bill_id
}
