/**
 * ADJ-02 (ADJ AC 2-4): in `settlement`, a card row with a bill shows its bill
 * date ("Paga em" / "Pagar até"), then "Lançada em <purchase date>", and the
 * "Prevista" badge while the bill is unpaid. `cash` and `accrual` keep the row
 * as before.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, screen, waitFor, within } from '@testing-library/react'

import TransactionsPage from '@/pages/transactions'
import { i18n, renderWithProviders } from '@/test/utils'

const api = vi.hoisted(() => ({
  list: vi.fn(),
  accountingMode: vi.fn(),
  mobile: { value: false },
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
    admin: { ...actual.admin, accountingMode: api.accountingMode },
  }
})

vi.mock('@/hooks/use-mobile', () => ({ useIsMobile: () => api.mobile.value }))

vi.mock('@/hooks/use-display-locale', () => ({
  useDisplayLocale: () => 'pt-BR',
  useDateLocale: () => 'pt-BR',
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
    id: 'tx-petz',
    user_id: 'u-1',
    account_id: 'acc-card',
    category_id: null,
    category: null,
    external_id: null,
    description: 'Petz Digital',
    original_description: null,
    amount: 120,
    currency: 'BRL',
    date: '2026-09-05',
    type: 'debit',
    source: 'manual',
    status: 'posted',
    payee: null,
    payee_id: null,
    payee_name: null,
    notes: null,
    transfer_pair_id: null,
    amount_primary: 120,
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

// The spec's Independent Test row: bought 05/09/2026 on the 10/2026 bill, due 13/10/2026, unpaid.
const petzUnpaid = tx({ bill_id: 'bill-oct', reporting_date: '2026-10-13', is_bill_projected: true })
const petzPaid = tx({ bill_id: 'bill-oct', reporting_date: '2026-10-10', is_bill_projected: false })

function listOf(...items: ReturnType<typeof tx>[]) {
  return { items, total: items.length, page: 1, limit: 50 }
}

async function desktopRow(description: string) {
  return (await screen.findByText(description)).closest('tr')! as HTMLElement
}

beforeEach(async () => {
  vi.clearAllMocks()
  api.mobile.value = false
  await i18n.changeLanguage('pt-BR')
})

afterEach(async () => {
  await i18n.changeLanguage('en')
})

describe('settlement mode, desktop table (ADJ AC 2, 4)', () => {
  beforeEach(() => api.accountingMode.mockResolvedValue({ mode: 'settlement' }))

  it('shows "Pagar até 13/10/2026", "Lançada em 05/09/2026" and Prevista for the unpaid Petz Digital purchase', async () => {
    api.list.mockResolvedValue(listOf(petzUnpaid))
    renderWithProviders(<TransactionsPage />)

    await screen.findByText('Petz Digital')
    const row = within(await desktopRow('Petz Digital'))
    expect(await row.findByText('Pagar até')).toBeInTheDocument()
    expect(row.getByText('13/10/2026')).toBeInTheDocument()
    expect(row.getByText('Lançada em 05/09/2026')).toBeInTheDocument()
    expect(row.getByText('Prevista')).toBeInTheDocument()
    expect(row.queryByText('Paga em')).not.toBeInTheDocument()
  })

  it('shows "Paga em <payment date>" and no Prevista once the bill is paid', async () => {
    api.list.mockResolvedValue(listOf(petzPaid))
    renderWithProviders(<TransactionsPage />)

    const row = within(await desktopRow('Petz Digital'))
    expect(await row.findByText('Paga em')).toBeInTheDocument()
    expect(row.getByText('10/10/2026')).toBeInTheDocument()
    expect(row.getByText('Lançada em 05/09/2026')).toBeInTheDocument()
    expect(row.queryByText('Pagar até')).not.toBeInTheDocument()
    expect(row.queryByText('Prevista')).not.toBeInTheDocument()
  })

  it('keeps the purchase date on a row without a bill', async () => {
    api.list.mockResolvedValue(listOf(tx({
      id: 'tx-pix', account_id: 'acc-checking', description: 'Pix padaria',
      reporting_date: '2026-09-05', is_bill_projected: false,
    })))
    renderWithProviders(<TransactionsPage />)

    const row = within(await desktopRow('Pix padaria'))
    expect(row.getByText('05/09/2026')).toBeInTheDocument()
    expect(row.queryByText(/Lançada em/)).not.toBeInTheDocument()
    expect(row.queryByText('Pagar até')).not.toBeInTheDocument()
  })
})

describe.each(['cash', 'accrual'])('%s mode keeps card rows as before (ADJ AC 3)', (mode) => {
  it('shows the purchase date with no bill labels and no Prevista', async () => {
    api.accountingMode.mockResolvedValue({ mode })
    // The server never projects outside settlement; reporting_date is the purchase date.
    api.list.mockResolvedValue(listOf(tx({ bill_id: 'bill-oct', reporting_date: '2026-09-05', is_bill_projected: false })))
    renderWithProviders(<TransactionsPage />)

    const row = within(await desktopRow('Petz Digital'))
    // Let the mode query settle so the row has rendered with it.
    await waitFor(() => expect(api.accountingMode).toHaveBeenCalled())
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
    expect(row.getByText('05/09/2026')).toBeInTheDocument()
    expect(row.queryByText(/Lançada em/)).not.toBeInTheDocument()
    expect(row.queryByText('Pagar até')).not.toBeInTheDocument()
    expect(row.queryByText('Paga em')).not.toBeInTheDocument()
    expect(row.queryByText('Prevista')).not.toBeInTheDocument()
  })
})

describe('settlement mode, mobile rows (ADJ AC 2, 4)', () => {
  beforeEach(() => {
    api.mobile.value = true
    api.accountingMode.mockResolvedValue({ mode: 'settlement' })
  })

  it('shows the bill dates and Prevista, grouped under the bill date', async () => {
    api.list.mockResolvedValue(listOf(petzUnpaid))
    renderWithProviders(<TransactionsPage />)

    expect(await screen.findByText('Pagar até')).toBeInTheDocument()
    expect(screen.getByText('13/10/2026')).toBeInTheDocument()
    expect(screen.getByText('Lançada em 05/09/2026')).toBeInTheDocument()
    expect(screen.getByText('Prevista')).toBeInTheDocument()
    const header = new Date('2026-10-13T00:00:00').toLocaleDateString('pt-BR', {
      weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
    })
    expect(screen.getByText(header)).toBeInTheDocument()
  })

  it('shows "Paga em" once the bill is paid', async () => {
    api.list.mockResolvedValue(listOf(petzPaid))
    renderWithProviders(<TransactionsPage />)

    expect(await screen.findByText('Paga em')).toBeInTheDocument()
    expect(screen.getByText('10/10/2026')).toBeInTheDocument()
    expect(screen.queryByText('Prevista')).not.toBeInTheDocument()
  })
})
