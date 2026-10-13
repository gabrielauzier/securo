import type { Account, CreditCardBill } from '@/types'

export type BillSummary = {
  target: number
  paid: number
  remaining: number
  /** Earliest effective due date among bills that are not paid, YYYY-MM-DD. */
  nextDue: string | null
  /** Null when no card has a limit. */
  limit: number | null
  available: number | null
}

/**
 * Month figures of the consolidated card page (BVIEW AC 5).
 *
 * Cards that share a `shared_balance_group` share one limit, so each group
 * counts once, with the highest limit in the group. The group's available
 * credit is read from that same card.
 */
export function summarizeBills(bills: CreditCardBill[], cards: Account[]): BillSummary {
  let target = 0
  let paid = 0
  let remaining = 0
  let nextDue: string | null = null
  for (const b of bills) {
    target += b.target_amount ?? 0
    paid += b.paid_amount ?? 0
    remaining += b.remaining_amount ?? 0
    const due = b.effective_due_date ?? b.due_date
    if (b.status !== 'paid' && (nextDue == null || due < nextDue)) nextDue = due
  }

  // One entry per limit pool: the shared group, or the card on its own.
  const pools = new Map<string, Account>()
  for (const card of cards) {
    if (card.credit_limit == null) continue
    const key = card.shared_balance_group ? `group:${card.shared_balance_group}` : `card:${card.id}`
    const current = pools.get(key)
    if (!current || Number(card.credit_limit) > Number(current.credit_limit)) pools.set(key, card)
  }
  let limit: number | null = null
  let available: number | null = null
  for (const card of pools.values()) {
    limit = (limit ?? 0) + Number(card.credit_limit)
    if (card.available_credit != null) available = (available ?? 0) + Number(card.available_credit)
  }

  const round = (n: number) => Math.round(n * 100) / 100
  return {
    target: round(target),
    paid: round(paid),
    remaining: round(remaining),
    nextDue,
    limit: limit == null ? null : round(limit),
    available: available == null ? null : round(available),
  }
}
