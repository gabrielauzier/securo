import { describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'

import { BillSummaryCard } from '@/components/credit-card/bill-summary-card'
import { renderWithProviders } from '@/test/utils'
import type { Account, CreditCardBill } from '@/types'

vi.mock('@/hooks/use-display-locale', () => ({
  useDisplayLocale: () => 'en-US',
  useDateLocale: () => 'en-US',
}))

vi.mock('@/hooks/use-privacy-mode', () => ({
  usePrivacyMode: () => ({ mask: (value: string) => value, privacyMode: false, MASK: '***' }),
}))

function card(id: string, limit: number | null, available: number | null, group: string | null = null) {
  return {
    id,
    name: id,
    type: 'credit_card',
    currency: 'BRL',
    credit_limit: limit,
    available_credit: available,
    shared_balance_group: group,
  } as Account
}

function bill(id: string, fields: Partial<CreditCardBill>): CreditCardBill {
  return {
    id,
    account_id: 'nubank',
    due_date: '2026-09-12',
    effective_due_date: '2026-09-14',
    target_amount: 0,
    paid_amount: 0,
    remaining_amount: 0,
    status: 'open',
    ...fields,
  } as CreditCardBill
}

function value(label: string) {
  const group = screen.getByRole('group', { name: 'Bills of the month' })
  return within(group).getByText(label).nextElementSibling?.textContent
}

describe('BillSummaryCard', () => {
  it('sums the month bills and counts a shared limit once (BVIEW AC 5)', () => {
    const bills = [
      bill('nubank-sep', { target_amount: 1283.2, paid_amount: 500, remaining_amount: 783.2, status: 'partially_paid', effective_due_date: '2026-09-14' }),
      bill('itau-sep', { target_amount: 400, paid_amount: 400, remaining_amount: 0, status: 'paid', effective_due_date: '2026-09-10' }),
      bill('inter-sep', { target_amount: 200, paid_amount: 0, remaining_amount: 200, status: 'open', effective_due_date: '2026-09-21' }),
    ]
    // Two Nubank cards share one 5,000 limit; the 3,000 one must not add to it.
    const cards = [
      card('nubank', 5000, 3716.8, 'nubank-limit'),
      card('nubank-virtual', 3000, 3716.8, 'nubank-limit'),
      card('inter', 2000, 1500),
    ]

    renderWithProviders(<BillSummaryCard bills={bills} cards={cards} currency="BRL" />)

    expect(value('Bills total')).toBe('R$1,883.20')
    expect(value('Paid')).toBe('R$900.00')
    expect(value('Remaining')).toBe('R$983.20')
    // The paid bill due 9/10 is not the next one to pay.
    expect(value('Next due date')).toBe('9/14/2026')
    expect(value('Total limit')).toBe('R$7,000.00')
    expect(value('Total available')).toBe('R$5,216.80')
  })

  it('shows dashes when nothing is unpaid and no card has a limit', () => {
    const bills = [bill('paid', { target_amount: 100, paid_amount: 100, status: 'paid' })]

    renderWithProviders(<BillSummaryCard bills={bills} cards={[card('nubank', null, null)]} currency="BRL" />)

    expect(value('Remaining')).toBe('R$0.00')
    expect(value('Next due date')).toBe('—')
    expect(value('Total limit')).toBe('—')
    expect(value('Total available')).toBe('—')
  })
})
