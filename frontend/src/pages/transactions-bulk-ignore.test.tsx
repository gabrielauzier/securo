import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import TransactionsPage from '@/pages/transactions'
import { renderWithProviders, t } from '@/test/utils'

const api = vi.hoisted(() => ({
  list: vi.fn(),
  bulkIgnore: vi.fn(),
  toastSuccess: vi.fn(),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    transactions: { ...actual.transactions, list: api.list, bulkIgnore: api.bulkIgnore },
    accounts: { ...actual.accounts, list: vi.fn().mockResolvedValue([{ id: 'acc-1', name: 'Conta', type: 'checking' }]) },
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

function tx(n: number) {
  return {
    id: `tx-${n}`,
    user_id: 'u-1',
    account_id: 'acc-1',
    category_id: null,
    category: null,
    external_id: null,
    description: `Purchase ${n}`,
    original_description: null,
    amount: 10,
    currency: 'BRL',
    date: '2026-04-01',
    type: 'debit',
    source: 'manual',
    status: 'posted',
    payee: null,
    payee_id: null,
    payee_name: null,
    notes: null,
    transfer_pair_id: null,
    amount_primary: 10,
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
  }
}

function listOf(count: number) {
  const items = Array.from({ length: count }, (_, i) => tx(i + 1))
  return { items, total: count, page: 1, limit: count }
}

async function selectFirstRows(
  user: ReturnType<typeof renderWithProviders>['user'],
  rows: number,
) {
  await screen.findByText('Purchase 1')
  const boxes = screen.getAllByRole('checkbox')
  // boxes[0] is the select-all header; the rest are rows in order.
  for (let i = 1; i <= rows; i++) await user.click(boxes[i])
}

describe('transactions page bulk ignore (IGN-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.bulkIgnore.mockResolvedValue({ updated: 2 })
  })

  it('Ignore sends the selected ids with ignored=true and reports the count', async () => {
    api.list.mockResolvedValue(listOf(3))
    const { user } = renderWithProviders(<TransactionsPage />)

    await selectFirstRows(user, 2)
    await user.click(screen.getByRole('button', { name: t('transactions.bulkIgnore') }))

    await waitFor(() => expect(api.bulkIgnore).toHaveBeenCalledWith(['tx-1', 'tx-2'], true))
    await waitFor(() =>
      expect(api.toastSuccess).toHaveBeenCalledWith(
        t('transactions.bulkIgnoreSuccess', { count: 2 }),
      ),
    )
    // Success clears the selection, like the sibling bulk actions.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: t('transactions.bulkIgnore') })).toBeNull(),
    )
  })

  it('keeps the bar offset by the scrollbar width while a dialog locks page scroll', async () => {
    api.list.mockResolvedValue(listOf(3))
    const { user } = renderWithProviders(<TransactionsPage />)

    await selectFirstRows(user, 1)

    // react-remove-scroll shifts only elements carrying this class, so without it the
    // full-width bar widens when the scrollbar disappears and slides to the right.
    const bar = screen.getByRole('button', { name: t('transactions.bulkIgnore') }).closest('.fixed')
    expect(bar).toHaveClass('right-scroll-bar-position')
  })

  it('Stop ignoring sends the selected ids with ignored=false', async () => {
    api.list.mockResolvedValue(listOf(3))
    const { user } = renderWithProviders(<TransactionsPage />)

    await selectFirstRows(user, 2)
    await user.click(screen.getByRole('button', { name: t('transactions.bulkUnignore') }))

    await waitFor(() => expect(api.bulkIgnore).toHaveBeenCalledWith(['tx-1', 'tx-2'], false))
  })

  it('refreshes the transactions list after a successful bulk ignore', async () => {
    api.list.mockResolvedValue(listOf(3))
    const { user } = renderWithProviders(<TransactionsPage />)

    await selectFirstRows(user, 1)
    const callsBefore = api.list.mock.calls.length
    await user.click(screen.getByRole('button', { name: t('transactions.bulkIgnore') }))

    await waitFor(() => expect(api.list.mock.calls.length).toBeGreaterThan(callsBefore))
  })

  it('disables both actions and shows the hint above 100 selected', async () => {
    api.list.mockResolvedValue(listOf(101))
    const { user } = renderWithProviders(<TransactionsPage />)

    await screen.findByText('Purchase 1')
    await user.click(screen.getAllByRole('checkbox')[0]) // select all 101

    const ignore = screen.getByRole('button', { name: t('transactions.bulkIgnore') })
    const unignore = screen.getByRole('button', { name: t('transactions.bulkUnignore') })
    expect(ignore).toBeDisabled()
    expect(unignore).toBeDisabled()
    expect(screen.getByText(t('transactions.bulkLimitHint'))).toBeInTheDocument()
    expect(api.bulkIgnore).not.toHaveBeenCalled()
  })
})
