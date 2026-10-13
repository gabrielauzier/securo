import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import TransactionsPage from '@/pages/transactions'
import { renderWithProviders } from '@/test/utils'

const api = vi.hoisted(() => ({
  list: vi.fn(),
  toastSuccess: vi.fn(),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    transactions: { ...actual.transactions, list: api.list },
    accounts: {
      ...actual.accounts,
      list: vi.fn().mockResolvedValue([
        { id: 'acc-checking', name: 'Nubank', type: 'checking' },
        { id: 'acc-card', name: 'Cartão de Crédito Nubank', type: 'credit_card' },
      ]),
    },
    categories: {
      ...actual.categories,
      list: vi.fn().mockResolvedValue([]),
      listIncludingHidden: vi.fn().mockResolvedValue([]),
    },
    categoryGroups: { ...actual.categoryGroups, list: vi.fn().mockResolvedValue([]) },
    payees: { ...actual.payees, list: vi.fn().mockResolvedValue([]) },
    recurring: { ...actual.recurring, list: vi.fn().mockResolvedValue([]) },
    groups: { ...actual.groups, list: vi.fn().mockResolvedValue([]) },
    admin: { ...actual.admin, accountingMode: vi.fn().mockResolvedValue({ mode: 'cash' }) },
  }
})

vi.mock('sonner', () => ({ toast: { success: api.toastSuccess, error: vi.fn() } }))

vi.mock('@/hooks/use-display-locale', () => ({
  useDisplayLocale: () => 'en-US',
  useDateLocale: () => 'en-US',
}))

vi.mock('@/contexts/auth-context', () => ({
  useAuth: () => ({ user: { preferences: { currency_display: 'BRL' } } }),
}))

vi.mock('@/contexts/workspace-context', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/contexts/workspace-context')>()),
  useWorkspace: () => ({ canWrite: true, hasModule: () => false }),
}))

vi.mock('@/contexts/collection-filter-context', () => ({
  useCollectionFilter: () => ({ activeAccountIds: null }),
}))

function tx(overrides: Record<string, unknown>) {
  return {
    id: 'tx-1',
    user_id: 'u-1',
    account_id: 'acc-checking',
    category_id: null,
    category: null,
    external_id: null,
    description: 'Pagamento fatura',
    original_description: null,
    amount: 1283.2,
    currency: 'BRL',
    date: '2026-09-14',
    type: 'debit',
    source: 'manual',
    status: 'posted',
    payee: null,
    payee_id: null,
    payee_name: null,
    notes: null,
    transfer_pair_id: null,
    amount_primary: 1283.2,
    fx_rate_used: null,
    fx_fallback: false,
    installment_number: null,
    total_installments: null,
    installment_total_amount: null,
    installment_purchase_date: null,
    installment_series_id: null,
    bill_id: null,
    effective_bill_date: null,
    splits: [],
    is_ignored: false,
    paid_bill_id: null,
    paid_bill: null,
    needs_counterpart: false,
    bill_payment_suggestion: false,
    ...overrides,
  }
}

function listOf(...items: ReturnType<typeof tx>[]) {
  return { items, total: items.length, page: 1, limit: 50 }
}

const ROUTE = '/transactions?highlight=pay-1&from=2026-09-01&to=2026-09-30'

describe('transactions page highlight from a bill payment link (ADJ-06)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // The bill page link is a real navigation: the browser URL carries the query.
    window.history.replaceState(null, '', ROUTE)
    api.list.mockResolvedValue(listOf(
      tx({ id: 'other-1', description: 'Mercado', date: '2026-09-10' }),
      tx({ id: 'pay-1', description: 'Pagamento fatura', paid_bill_id: 'bill-sep' }),
    ))
  })

  it('flashes the payment row once it renders and keeps highlight in the URL until then', async () => {
    renderWithProviders(<TransactionsPage />, { route: ROUTE })

    const row = (await screen.findByText('Pagamento fatura')).closest('tr')!
    await waitFor(() => expect(row).toHaveClass('securo-highlight-flash'))
    expect(new URLSearchParams(window.location.search).get('highlight')).toBe('pay-1')
    expect(api.list).toHaveBeenCalledWith(expect.objectContaining({ from: '2026-09-01', to: '2026-09-30' }))
    expect((await screen.findByText('Mercado')).closest('tr')).not.toHaveClass('securo-highlight-flash')
  })
})
