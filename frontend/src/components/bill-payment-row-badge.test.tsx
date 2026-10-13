/**
 * The bill markers in a transaction row shrink and truncate instead of hiding
 * the description (BPAY-01, BMATCH-02; browser check finding on desktop and 375 px).
 */
import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'

import { BillPaymentRowBadge } from '@/components/bill-payment-row-badge'
import { renderWithProviders } from '@/test/utils'
import type { Transaction } from '@/types'

vi.mock('@/hooks/use-display-locale', () => ({
  useDisplayLocale: () => 'en-US',
  useDateLocale: () => 'en-US',
}))

const FULL_LABEL = 'Bill payment Cartão de Crédito Nubank October 2026'
const DESCRIPTION = 'Pagamento fatura cartão de crédito Nubank outubro'

function tx(overrides: Partial<Transaction>): Transaction {
  return {
    id: 'tx-1',
    description: DESCRIPTION,
    paid_bill: null,
    bill_payment_suggestion: false,
    ...overrides,
  } as Transaction
}

const paid = tx({
  paid_bill_id: 'bill-oct',
  paid_bill: {
    id: 'bill-oct', account_id: 'acc-card', account_name: 'Cartão de Crédito Nubank', reference_month: '2026-10-01',
  },
})

/** The description cell as the transactions page lays it out. */
function renderRow(row: Transaction) {
  return renderWithProviders(
    <div className="flex items-center gap-2">
      <p className="min-w-0 truncate">{row.description}</p>
      <BillPaymentRowBadge tx={row} canWrite onConfirmSuggestion={() => {}} />
    </div>,
  )
}

describe('bill markers keep the description visible', () => {
  it('shows the paid bill as card name and MMM/yy, with the full label as title and accessible text', () => {
    renderRow(paid)

    const short = screen.getByText('Cartão de Crédito Nubank · Oct/26')
    expect(short).toHaveClass('truncate')
    const pill = short.parentElement!
    expect(pill).toHaveAttribute('title', FULL_LABEL)
    expect(screen.getByText(FULL_LABEL)).toHaveClass('sr-only')
    expect(pill).toHaveClass('min-w-0', 'max-w-48')
    expect(pill).not.toHaveClass('shrink-0')
    expect(screen.getByText(DESCRIPTION)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Unlink from bill' })).toBeInTheDocument()
  })

  it('truncates the "possible bill payment" badge and keeps its full text as title', () => {
    renderRow(tx({ bill_payment_suggestion: true }))

    const label = screen.getByText('Possible bill payment')
    expect(label).toHaveClass('truncate')
    const pill = label.parentElement!
    expect(pill).toHaveAttribute('title', 'Possible bill payment')
    expect(pill).toHaveClass('min-w-0', 'max-w-48')
    expect(pill).not.toHaveClass('shrink-0')
    expect(screen.getByText(DESCRIPTION)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm bill payment' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dismiss suggestion' })).toBeInTheDocument()
  })
})
