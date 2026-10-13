/**
 * The stored bill of the cycle on screen (P1 AC 5, 7, 9-11): status, due dates,
 * computed vs declared total and payments, plus creating, editing and deleting.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'

import AccountDetailPage from '@/pages/account-detail'
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
  creditCardBills: { create: vi.fn(), update: vi.fn(), delete: vi.fn() },
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

// Close day 5, due day 12: the 2026-09 bill closes 2026-09-05, is due
// 2026-09-12 (a Saturday) and effectively due 2026-09-14 (P1 AC 2).
const account = {
  id: 'acc-1',
  name: 'Cartão de Crédito Nubank',
  type: 'credit_card',
  currency: 'BRL',
  balance: -1283.2,
  is_active: true,
  credit_limit: 5000,
  statement_close_day: 5,
  payment_due_day: 12,
}

function bill(overrides: Partial<CreditCardBill> = {}): CreditCardBill {
  return {
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
    ...overrides,
  }
}

function apiError(status: number, detail: string) {
  return Object.assign(new Error(detail), { response: { status, data: { detail } } })
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.setSystemTime(new Date('2026-09-08T12:00:00'))
  api.accounts.get.mockResolvedValue(account)
  api.accounts.bills.mockResolvedValue([bill()])
  api.accounts.list.mockResolvedValue([account])
  api.accounts.summary.mockResolvedValue({
    monthly_income: 0, monthly_expenses: 0, projected_income: 0, projected_expenses: 0,
  })
  api.transactions.list.mockResolvedValue({ items: [], total: 0 })
  api.dashboard.projectedTransactions.mockResolvedValue([])
  api.categories.list.mockResolvedValue([])
  api.categoryGroups.list.mockResolvedValue([])
})

async function renderPage() {
  const rendered = renderWithProviders(<AccountDetailPage />, {
    route: '/accounts/acc-1',
    path: '/accounts/:id',
  })
  const panel = await screen.findByRole('region', { name: 'Bill' })
  await within(panel).findByText('Partially paid')
  return { ...rendered, panel }
}

/** The value shown under a figure label inside the bill panel. */
function figure(panel: HTMLElement, label: string) {
  return within(panel).getByText(label).nextElementSibling?.textContent
}

describe('bill details on the card account page', () => {
  it('shows the status, due dates, totals and payments of the cycle bill', async () => {
    const { panel } = await renderPage()

    expect(within(panel).getByText('Partially paid')).toBeInTheDocument()
    expect(figure(panel, 'Effective due date')).toBe('9/14/2026')
    expect(within(panel).getByText('Original due date 9/12/2026')).toBeInTheDocument()
    expect(figure(panel, 'Computed total')).toBe('R$1,283.20')
    expect(figure(panel, 'Declared total')).toBe('—')
    expect(figure(panel, 'Difference')).toBe('—')
    expect(figure(panel, 'Paid')).toBe('R$500.00')
    expect(figure(panel, 'Remaining')).toBe('R$783.20')
    const payment = within(panel).getByRole('link', { name: '9/8/2026 · Pagamento parcial' })
    expect(payment).toHaveAttribute('href', '/accounts/acc-checking')
  })

  it('stores an edited declared total and shows the recomputed figures (AC 9)', async () => {
    const { panel, user } = await renderPage()
    api.creditCardBills.update.mockResolvedValue(bill({ declared_total: 1300 }))
    api.accounts.bills.mockResolvedValue([
      bill({ declared_total: 1300, target_amount: 1300, remaining_amount: 800 }),
    ])

    await user.click(within(panel).getByRole('button', { name: 'Edit bill' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Declared total'), '1300')
    await user.click(within(dialog).getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(api.creditCardBills.update).toHaveBeenCalledWith('bill-sep', {
        declared_total: 1300,
        reference_month: '2026-09-01',
        close_date: '2026-09-05',
        due_date: '2026-09-12',
      }),
    )
    await waitFor(() => expect(figure(panel, 'Declared total')).toBe('R$1,300.00'))
    expect(figure(panel, 'Difference')).toBe('R$16.80')
    expect(figure(panel, 'Remaining')).toBe('R$800.00')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('rejects a negative declared total without calling the API', async () => {
    const { panel, user } = await renderPage()

    await user.click(within(panel).getByRole('button', { name: 'Edit bill' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Declared total'), '-10')
    await user.click(within(dialog).getByRole('button', { name: 'Save' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'The declared total must be zero or more.',
    )
    expect(api.creditCardBills.update).not.toHaveBeenCalled()
  })

  it('hides date editing and delete on a provider bill (AC 10)', async () => {
    api.accounts.bills.mockResolvedValue([bill({ source: 'provider', external_id: 'pluggy-1' })])
    const { panel, user } = await renderPage()
    api.creditCardBills.update.mockResolvedValue(bill({ source: 'provider', declared_total: 1283.2 }))

    expect(within(panel).queryByRole('button', { name: 'Delete bill' })).not.toBeInTheDocument()

    await user.click(within(panel).getByRole('button', { name: 'Edit bill' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByText('Close date')).not.toBeInTheDocument()
    expect(within(dialog).queryByText('Due date')).not.toBeInTheDocument()
    expect(within(dialog).queryByText('Reference month')).not.toBeInTheDocument()

    await user.type(within(dialog).getByLabelText('Declared total'), '1283.20')
    await user.click(within(dialog).getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(api.creditCardBills.update).toHaveBeenCalledWith('bill-sep', { declared_total: 1283.2 }),
    )
  })

  it('creates a manual bill from the card cycle days (AC 7)', async () => {
    const { panel, user } = await renderPage()
    api.creditCardBills.create.mockResolvedValue(bill({ id: 'bill-oct', source: 'manual' }))
    const billCalls = api.accounts.bills.mock.calls.length

    await user.click(within(panel).getByRole('button', { name: 'New bill' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'New manual bill' })).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Next month' }))
    await user.click(within(dialog).getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(api.creditCardBills.create).toHaveBeenCalledWith({
        account_id: 'acc-1',
        reference_month: '2026-10-01',
        close_date: '2026-10-05',
        due_date: '2026-10-12',
        declared_total: null,
      }),
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(api.accounts.bills.mock.calls.length).toBeGreaterThan(billCalls))
  })

  it('shows the duplicate message when the reference month already has a bill (AC 8)', async () => {
    const { panel, user } = await renderPage()
    api.creditCardBills.create.mockRejectedValue(
      apiError(409, 'The card already has a bill for this reference month'),
    )

    await user.click(within(panel).getByRole('button', { name: 'New bill' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Save' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'The card already has a bill for this reference month.',
    )
    expect(api.creditCardBills.create).toHaveBeenCalledWith(
      expect.objectContaining({ reference_month: '2026-09-01', close_date: '2026-09-05', due_date: '2026-09-12' }),
    )
  })

  it('deletes an automatic bill after confirmation (AC 11)', async () => {
    const { panel, user } = await renderPage()
    api.creditCardBills.delete.mockResolvedValue(undefined)

    await user.click(within(panel).getByRole('button', { name: 'Delete bill' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Its transactions and payments stay, unlinked from the bill.')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(api.creditCardBills.delete).toHaveBeenCalledWith('bill-sep'))
  })
})
