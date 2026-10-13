import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'

import TransactionsPage from '@/pages/transactions'
import { renderWithProviders, t } from '@/test/utils'
import type { BillCandidate } from '@/types'

const api = vi.hoisted(() => ({
  list: vi.fn(),
  paymentCandidates: vi.fn(),
  unlinkPayment: vi.fn(),
  dismissSuggestion: vi.fn(),
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
    creditCardBills: {
      ...actual.creditCardBills,
      paymentCandidates: api.paymentCandidates,
      unlinkPayment: api.unlinkPayment,
      dismissSuggestion: api.dismissSuggestion,
    },
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

const candidate: BillCandidate = {
  bill_id: 'bill-sep',
  account_id: 'acc-card',
  account_name: 'Cartão de Crédito Nubank',
  reference_month: '2026-09-01',
  effective_due_date: '2026-09-14',
  target_amount: 1283.2,
  remaining_amount: 1283.2,
  currency: 'BRL',
  kind: 'exact',
  reason: 'exact_amount',
  rank: 1,
}

async function selectOnly(user: ReturnType<typeof renderWithProviders>['user'], description: string) {
  const row = (await screen.findByText(description)).closest('tr')!
  await user.click(within(row).getByRole('checkbox'))
}

function linkBillButton() {
  return screen.getByRole('button', { name: t('bills.link.title') })
}

describe('transactions page bill payments (BMATCH-02, BPAY-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.paymentCandidates.mockResolvedValue([candidate])
    api.unlinkPayment.mockResolvedValue({})
    api.dismissSuggestion.mockResolvedValue(undefined)
  })

  describe('"Vincular a fatura" in the selection bar', () => {
    it('opens the link-bill dialog for one eligible debit', async () => {
      api.list.mockResolvedValue(listOf(tx({})))
      const { user } = renderWithProviders(<TransactionsPage />)

      await selectOnly(user, 'Pagamento fatura')
      expect(linkBillButton()).toBeEnabled()
      await user.click(linkBillButton())

      expect(await screen.findByRole('dialog')).toHaveTextContent(t('bills.link.description'))
      await waitFor(() => expect(api.paymentCandidates).toHaveBeenCalledWith('tx-1'))
    })

    it('is disabled for a credit', async () => {
      api.list.mockResolvedValue(listOf(tx({ type: 'credit', description: 'Salary' })))
      const { user } = renderWithProviders(<TransactionsPage />)

      await selectOnly(user, 'Salary')

      expect(linkBillButton()).toBeDisabled()
    })

    it('is disabled for a credit card row', async () => {
      api.list.mockResolvedValue(listOf(tx({ account_id: 'acc-card', description: 'Mercado' })))
      const { user } = renderWithProviders(<TransactionsPage />)

      await selectOnly(user, 'Mercado')

      expect(linkBillButton()).toBeDisabled()
    })

    it('is disabled for a debit that already pays a bill', async () => {
      api.list.mockResolvedValue(listOf(tx({
        paid_bill_id: 'bill-sep',
        paid_bill: { id: 'bill-sep', account_id: 'acc-card', account_name: 'Cartão de Crédito Nubank', reference_month: '2026-09-01' },
      })))
      const { user } = renderWithProviders(<TransactionsPage />)

      await selectOnly(user, 'Pagamento fatura')

      expect(linkBillButton()).toBeDisabled()
    })

    it('is disabled when two transactions are selected', async () => {
      api.list.mockResolvedValue(listOf(tx({}), tx({ id: 'tx-2', description: 'Outro pagamento' })))
      const { user } = renderWithProviders(<TransactionsPage />)

      await selectOnly(user, 'Pagamento fatura')
      await selectOnly(user, 'Outro pagamento')

      expect(linkBillButton()).toBeDisabled()
    })
  })

  describe('pending suggestion indicator (BMATCH AC 14)', () => {
    it('shows "Possível pagamento de fatura" on a suggested row', async () => {
      api.list.mockResolvedValue(listOf(tx({ bill_payment_suggestion: true })))
      renderWithProviders(<TransactionsPage />)

      expect(await screen.findByText('Possible bill payment')).toBeInTheDocument()
    })

    it('reads "Possível pagamento de fatura" in pt-BR', async () => {
      const { i18n } = await import('@/test/utils')
      await i18n.changeLanguage('pt-BR')
      try {
        expect(i18n.t('bills.row.suggestion')).toBe('Possível pagamento de fatura')
      } finally {
        await i18n.changeLanguage('en')
      }
    })

    it('has no indicator on a row without a suggestion', async () => {
      api.list.mockResolvedValue(listOf(tx({})))
      renderWithProviders(<TransactionsPage />)

      await screen.findByText('Pagamento fatura')
      expect(screen.queryByText('Possible bill payment')).not.toBeInTheDocument()
    })

    it('confirm opens the link-bill dialog with the candidates', async () => {
      api.list.mockResolvedValue(listOf(tx({ bill_payment_suggestion: true })))
      const { user } = renderWithProviders(<TransactionsPage />)

      await user.click(await screen.findByRole('button', { name: 'Confirm bill payment' }))

      const dialog = await screen.findByRole('dialog')
      expect(await within(dialog).findByText('Cartão de Crédito Nubank')).toBeInTheDocument()
      expect(api.paymentCandidates).toHaveBeenCalledWith('tx-1')
    })

    it('dismiss dismisses the suggested pair and refreshes the list', async () => {
      api.list.mockResolvedValue(listOf(tx({ bill_payment_suggestion: true })))
      const { user } = renderWithProviders(<TransactionsPage />)

      const button = await screen.findByRole('button', { name: 'Dismiss suggestion' })
      const callsBefore = api.list.mock.calls.length
      await user.click(button)

      await waitFor(() =>
        expect(api.dismissSuggestion).toHaveBeenCalledWith({ transaction_id: 'tx-1', bill_id: 'bill-sep' }),
      )
      await waitFor(() => expect(api.list.mock.calls.length).toBeGreaterThan(callsBefore))
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  describe('paid bill label and unlink', () => {
    const paid = tx({
      paid_bill_id: 'bill-sep',
      paid_bill: { id: 'bill-sep', account_id: 'acc-card', account_name: 'Cartão de Crédito Nubank', reference_month: '2026-09-01' },
    })

    it('labels the row "Pagamento da fatura <card> <month>"', async () => {
      api.list.mockResolvedValue(listOf(paid))
      renderWithProviders(<TransactionsPage />)

      expect(await screen.findByText('Bill payment Cartão de Crédito Nubank September 2026')).toBeInTheDocument()
    })

    it('reads "Pagamento da fatura" in pt-BR', async () => {
      const { i18n } = await import('@/test/utils')
      await i18n.changeLanguage('pt-BR')
      try {
        expect(i18n.t('bills.row.paidBill', { card: 'Cartão de Crédito Nubank', month: 'setembro de 2026' }))
          .toBe('Pagamento da fatura Cartão de Crédito Nubank setembro de 2026')
      } finally {
        await i18n.changeLanguage('en')
      }
    })

    it('unlinks the payment and refreshes the list', async () => {
      api.list.mockResolvedValue(listOf(paid))
      const { user } = renderWithProviders(<TransactionsPage />)

      const button = await screen.findByRole('button', { name: 'Unlink from bill' })
      const callsBefore = api.list.mock.calls.length
      await user.click(button)

      await waitFor(() => expect(api.unlinkPayment).toHaveBeenCalledWith('tx-1'))
      await waitFor(() => expect(api.toastSuccess).toHaveBeenCalledWith('Payment unlinked from the bill'))
      await waitFor(() => expect(api.list.mock.calls.length).toBeGreaterThan(callsBefore))
      // The unlink button does not open the edit dialog behind it.
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })
})

describe('description next to the paid bill pill (T60)', () => {
  it('keeps the description in the row as a shrinkable, truncated line', async () => {
    api.list.mockResolvedValue(listOf(tx({
      paid_bill_id: 'bill-oct',
      paid_bill: { id: 'bill-oct', account_id: 'acc-card', account_name: 'Cartão de Crédito Nubank', reference_month: '2026-10-01' },
    })))
    renderWithProviders(<TransactionsPage />)

    const description = await screen.findByText('Pagamento fatura')
    expect(description).toHaveClass('min-w-0', 'truncate')
    const row = description.closest('tr')!
    expect(within(row).getByTitle('Bill payment Cartão de Crédito Nubank October 2026')).toBeInTheDocument()
  })
})
