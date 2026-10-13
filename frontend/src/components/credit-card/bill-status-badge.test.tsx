import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'

import { BillStatusBadge } from '@/components/credit-card/bill-status-badge'
import { i18n, renderWithProviders, t } from '@/test/utils'
import type { CreditCardBillStatus } from '@/types'

vi.mock('@/contexts/auth-context', () => ({
  useAuth: () => ({ user: { preferences: { currency_display: 'BRL' } } }),
}))

vi.mock('@/lib/api', () => ({
  admin: {
    numberFormat: vi.fn().mockResolvedValue({ format: 'auto' }),
    dateFormat: vi.fn().mockResolvedValue({ format: 'auto' }),
  },
}))

const STATUSES: CreditCardBillStatus[] = ['paid', 'open', 'overdue', 'partially_paid', 'closed']

describe('BillStatusBadge', () => {
  it('renders a distinct label for each of the five statuses', () => {
    const labels = STATUSES.map((status) => {
      const { unmount } = renderWithProviders(
        <BillStatusBadge status={status} dueDate="2026-09-14" effectiveDueDate="2026-09-14" />,
      )
      const label = t(`bills.status.${status}`)
      expect(screen.getByText(label)).toBeInTheDocument()
      unmount()
      return label
    })

    expect(labels).toEqual(['Paid', 'Open', 'Overdue', 'Partially paid', 'Closed'])
    expect(new Set(labels).size).toBe(5)
  })

  it('uses the Portuguese status names in pt-BR', async () => {
    await i18n.changeLanguage('pt-BR')
    try {
      const labels = STATUSES.map((status) => i18n.t(`bills.status.${status}`))
      expect(labels).toEqual(['Paga', 'Aberta', 'Vencida', 'Parcialmente paga', 'Fechada'])
    } finally {
      await i18n.changeLanguage('en')
    }
  })

  it('shows the original due date with its weekday when the effective date differs', async () => {
    // BILL-01 AC 2: nominal 2026-09-12 (Saturday) rolls to 2026-09-14.
    const { user } = renderWithProviders(
      <BillStatusBadge status="open" dueDate="2026-09-12" effectiveDueDate="2026-09-14" />,
    )

    await user.hover(screen.getByText('Open'))

    const tooltip = await screen.findByRole('tooltip')
    expect(tooltip).toHaveTextContent('Original due date 12/09/2026 (Saturday)')
  })

  it('reads "Vencimento original" in pt-BR', async () => {
    await i18n.changeLanguage('pt-BR')
    try {
      const { user } = renderWithProviders(
        <BillStatusBadge status="open" dueDate="2026-09-12" effectiveDueDate="2026-09-14" />,
      )

      await user.hover(screen.getByText('Aberta'))

      const tooltip = await screen.findByRole('tooltip')
      expect(tooltip).toHaveTextContent('Vencimento original 12/09/2026 (sábado)')
    } finally {
      await i18n.changeLanguage('en')
    }
  })

  it('has no tooltip when the effective due date equals the nominal one', async () => {
    const { user } = renderWithProviders(
      <BillStatusBadge status="paid" dueDate="2026-09-14" effectiveDueDate="2026-09-14" />,
    )

    await user.hover(screen.getByText('Paid'))

    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })
})
