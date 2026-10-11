import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'

import TransactionsPage from '@/pages/transactions'
import { renderWithProviders, t } from '@/test/utils'

const api = vi.hoisted(() => ({
  list: vi.fn(),
  bulkTransferPreview: vi.fn(),
  bulkTransfer: vi.fn(),
  toastSuccess: vi.fn(),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    transactions: {
      ...actual.transactions,
      list: api.list,
      bulkTransferPreview: api.bulkTransferPreview,
      bulkTransfer: api.bulkTransfer,
    },
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

const emptyPreview = { pairs: [], ambiguous: [], unmatched: [], already_linked: [] }

function proposed(a: string, b: string) {
  return {
    a: {
      id: a, date: '2026-04-01', account_id: 'acc-1', account_name: 'Conta',
      description: `Purchase ${a.slice(3)}`, amount: 10, currency: 'BRL', type: 'debit',
    },
    b: {
      id: b, date: '2026-04-01', account_id: 'acc-2', account_name: 'Poupança',
      description: `Purchase ${b.slice(3)}`, amount: 10, currency: 'BRL', type: 'credit',
    },
    strategy: 'exact_amount_nearby',
  }
}

describe('transactions page bulk mark as transfer (BTR-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.bulkTransferPreview.mockResolvedValue({
      ...emptyPreview,
      pairs: [proposed('tx-1', 'tx-2')],
      unmatched: ['tx-3'],
    })
    api.bulkTransfer.mockResolvedValue({ linked: 1, skipped: [] })
  })

  it('previews the selection: pairs plus the unmatched, ambiguous and already linked groups', async () => {
    api.list.mockResolvedValue(listOf(5))
    api.bulkTransferPreview.mockResolvedValue({
      pairs: [proposed('tx-1', 'tx-2')],
      unmatched: ['tx-3'],
      ambiguous: ['tx-4'],
      already_linked: ['tx-5'],
    })
    const { user } = renderWithProviders(<TransactionsPage />)

    await selectFirstRows(user, 5)
    await user.click(screen.getByRole('button', { name: t('transactions.bulkTransfer') }))

    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByText(t('transactions.bulkTransferUnmatched'), { exact: false })
    expect(api.bulkTransferPreview).toHaveBeenCalledWith(['tx-1', 'tx-2', 'tx-3', 'tx-4', 'tx-5'])
    // The base dialog caps width at sm:max-w-lg; the pair table and id lists need the wider cap to fit.
    expect(dialog.className).toContain('sm:max-w-3xl')
    expect(within(dialog).getByText(t('transactions.bulkTransferAmbiguous'), { exact: false })).toBeInTheDocument()
    expect(within(dialog).getByText(t('transactions.bulkTransferAlreadyLinked'), { exact: false })).toBeInTheDocument()
    expect(within(dialog).getByText('Purchase 3')).toBeInTheDocument()
    expect(within(dialog).getByText('Purchase 4')).toBeInTheDocument()
    expect(within(dialog).getByText('Purchase 5')).toBeInTheDocument()
    expect(within(dialog).getAllByRole('checkbox')).toHaveLength(1)
    // Opening the preview links nothing.
    expect(api.bulkTransfer).not.toHaveBeenCalled()
  })

  it('confirm links only the checked pairs, refreshes the list and toasts the counts', async () => {
    api.list.mockResolvedValue(listOf(4))
    api.bulkTransferPreview.mockResolvedValue({
      ...emptyPreview,
      pairs: [proposed('tx-1', 'tx-2'), proposed('tx-3', 'tx-4')],
    })
    const { user } = renderWithProviders(<TransactionsPage />)
    await selectFirstRows(user, 4)
    await user.click(screen.getByRole('button', { name: t('transactions.bulkTransfer') }))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findAllByRole('checkbox')
    const callsBefore = api.list.mock.calls.length

    await user.click(within(dialog).getAllByRole('checkbox')[1]) // uncheck the second pair
    await user.click(within(dialog).getByRole('button', { name: t('transactions.bulkTransferConfirm') }))

    await waitFor(() =>
      expect(api.bulkTransfer).toHaveBeenCalledWith([{ a: 'tx-1', b: 'tx-2' }]),
    )
    await waitFor(() =>
      expect(api.toastSuccess).toHaveBeenCalledWith(
        t('transactions.bulkTransferSuccess', { linked: 1, skipped: 0 }),
      ),
    )
    await waitFor(() => expect(api.list.mock.calls.length).toBeGreaterThan(callsBefore))
  })

  it('cannot confirm when the selection produced no pair', async () => {
    api.list.mockResolvedValue(listOf(2))
    api.bulkTransferPreview.mockResolvedValue({ ...emptyPreview, unmatched: ['tx-1', 'tx-2'] })
    const { user } = renderWithProviders(<TransactionsPage />)
    await selectFirstRows(user, 2)
    await user.click(screen.getByRole('button', { name: t('transactions.bulkTransfer') }))

    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByText(t('transferPreview.empty'))

    expect(
      within(dialog).getByRole('button', { name: t('transactions.bulkTransferConfirm') }),
    ).toBeDisabled()
    expect(api.bulkTransfer).not.toHaveBeenCalled()
  })

  it('cancelling the preview links nothing and keeps the selection', async () => {
    api.list.mockResolvedValue(listOf(3))
    const { user } = renderWithProviders(<TransactionsPage />)
    await selectFirstRows(user, 2)
    await user.click(screen.getByRole('button', { name: t('transactions.bulkTransfer') }))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findAllByRole('checkbox')

    await user.click(within(dialog).getByRole('button', { name: t('common.cancel') }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(api.bulkTransfer).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: t('transactions.bulkTransfer') })).toBeInTheDocument()
  })

  it('disables the action and shows the hint above 100 selected', async () => {
    api.list.mockResolvedValue(listOf(101))
    const { user } = renderWithProviders(<TransactionsPage />)

    await screen.findByText('Purchase 1')
    await user.click(screen.getAllByRole('checkbox')[0]) // select all 101

    expect(screen.getByRole('button', { name: t('transactions.bulkTransfer') })).toBeDisabled()
    expect(screen.getByText(t('transactions.bulkLimitHint'))).toBeInTheDocument()
    expect(api.bulkTransferPreview).not.toHaveBeenCalled()
  })
})
