/**
 * BVIEW AC 8: for the same bill, the consolidated page shows the same figures
 * as the card's account detail page (target, paid, remaining, status and
 * effective due date).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'

import AccountDetailPage from '@/pages/account-detail'
import CreditCardsPage from '@/pages/credit-cards'
import { renderWithProviders } from '@/test/utils'
import type { CreditCardBill } from '@/types'

const api = vi.hoisted(() => ({
  accounts: {
    get: vi.fn(),
    bills: vi.fn(),
    summary: vi.fn(),
    list: vi.fn(),
    update: vi.fn(),
  },
  transactions: { list: vi.fn(), update: vi.fn(), delete: vi.fn(), create: vi.fn() },
  dashboard: { projectedTransactions: vi.fn() },
  categories: { list: vi.fn() },
  categoryGroups: { list: vi.fn() },
  creditCardBills: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
}))

vi.mock('@/lib/api', () => api)

vi.mock('@/hooks/use-display-locale', () => ({
  useDisplayLocale: () => 'en-US',
  useDateLocale: () => 'en-US',
}))

vi.mock('@/hooks/use-privacy-mode', () => ({
  usePrivacyMode: () => ({ mask: (value: string) => value, privacyMode: false, MASK: '***' }),
}))

vi.mock('@/contexts/auth-context', () => ({
  useAuth: () => ({ user: { preferences: { currency_display: 'BRL' } } }),
}))

vi.mock('@/contexts/workspace-context', () => ({
  useWorkspace: () => ({ canWrite: true }),
}))

const card = {
  id: 'acc-1',
  name: 'Cartão de Crédito Nubank',
  display_name: null,
  type: 'credit_card',
  currency: 'BRL',
  balance: -1283.2,
  is_active: true,
  is_closed: false,
  shared_balance_group: null,
  credit_limit: 5000,
  available_credit: 3716.8,
  statement_close_day: 5,
  payment_due_day: 12,
}

// The reference bill with one 500.00 partial payment (BPAY AC 6).
const bill: CreditCardBill = {
  id: 'bill-sep',
  account_id: 'acc-1',
  external_id: null,
  due_date: '2026-09-12',
  total_amount: 0,
  currency: 'BRL',
  minimum_payment: null,
  source: 'auto',
  reference_month: '2026-09-01',
  period_start: '2026-08-05',
  period_end: '2026-09-04',
  close_date: '2026-09-05',
  effective_due_date: '2026-09-14',
  declared_total: null,
  computed_total: 1283.2,
  target_amount: 1283.2,
  paid_amount: 500,
  remaining_amount: 783.2,
  overpaid_amount: 0,
  settled_on: null,
  status: 'partially_paid',
  payments: [
    { id: 'pay-1', account_id: 'acc-checking', date: '2026-09-08', description: 'Pagamento parcial', amount: 500, currency: 'BRL' },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.setSystemTime(new Date('2026-09-08T12:00:00'))
  api.accounts.get.mockResolvedValue(card)
  api.accounts.list.mockResolvedValue([card])
  api.accounts.bills.mockResolvedValue([bill])
  api.creditCardBills.list.mockResolvedValue([bill])
  api.accounts.summary.mockResolvedValue({
    monthly_income: 0, monthly_expenses: 0, projected_income: 0, projected_expenses: 0,
  })
  api.transactions.list.mockResolvedValue({ items: [], total: 0 })
  api.dashboard.projectedTransactions.mockResolvedValue([])
  api.categories.list.mockResolvedValue([])
  api.categoryGroups.list.mockResolvedValue([])
})

type Figures = { target: string; paid: string; remaining: string; status: string; due: string }

/** The value shown under a label inside a container. */
function valueOf(container: HTMLElement, label: string) {
  return within(container).getByText(label).nextElementSibling?.textContent ?? ''
}

async function detailFigures(): Promise<Figures> {
  const { unmount } = renderWithProviders(<AccountDetailPage />, {
    route: '/accounts/acc-1',
    path: '/accounts/:id',
  })
  const panel = await screen.findByRole('region', { name: 'Bill' })
  await within(panel).findByText('Partially paid')
  const figures = {
    // No declared total: the computed total is the bill's target.
    target: valueOf(panel, 'Computed total'),
    paid: valueOf(panel, 'Paid'),
    remaining: valueOf(panel, 'Remaining'),
    status: within(panel).getByText('Partially paid').textContent ?? '',
    due: valueOf(panel, 'Effective due date'),
  }
  unmount()
  return figures
}

async function consolidatedFigures(): Promise<Figures> {
  const { unmount } = renderWithProviders(<CreditCardsPage />, {
    route: '/accounts/credit-cards?account=acc-1',
  })
  const region = await screen.findByRole('region', { name: 'Bills' })
  const table = await within(region).findByRole('table')
  await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(2))
  const cells = within(within(table).getAllByRole('row')[1])
    .getAllByRole('cell')
    .map((cell) => cell.textContent ?? '')
  const summary = screen.getByRole('group', { name: 'Bills of the month' })
  const figures = {
    target: valueOf(summary, 'Bills total'),
    paid: valueOf(summary, 'Paid'),
    remaining: valueOf(summary, 'Remaining'),
    status: cells[1],
    due: cells[2],
  }
  unmount()
  return figures
}

describe('bill figures on both pages (BVIEW AC 8)', () => {
  it('shows the same target, paid, remaining, status and effective due date', async () => {
    const detail = await detailFigures()
    const consolidated = await consolidatedFigures()

    const expected = {
      target: 'R$1,283.20',
      paid: 'R$500.00',
      remaining: 'R$783.20',
      status: 'Partially paid',
      due: '9/14/2026',
    }
    expect(detail).toEqual(expected)
    expect(consolidated).toEqual(expected)
  })
})
