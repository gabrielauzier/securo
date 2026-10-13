/**
 * The consolidated credit card page (BVIEW AC 2-10).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'

import CreditCardsPage from '@/pages/credit-cards'
import { renderWithProviders } from '@/test/utils'
import type { CreditCardBill } from '@/types'

const api = vi.hoisted(() => ({
  accounts: { list: vi.fn() },
  creditCardBills: { list: vi.fn() },
  transactions: { list: vi.fn() },
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

function card(id: string, name: string, fields: Record<string, unknown> = {}) {
  return {
    id,
    name,
    display_name: null,
    type: 'credit_card',
    currency: 'BRL',
    is_closed: false,
    shared_balance_group: null,
    statement_close_day: 5,
    payment_due_day: 12,
    ...fields,
  }
}

const nubank = card('acc-nubank', 'Cartão de Crédito Nubank', { credit_limit: 5000, available_credit: 3716.8 })
const itau = card('acc-itau', 'Itaú Visa', {
  credit_limit: 2000, available_credit: 1600, statement_close_day: 1, payment_due_day: 10,
})
const checking = { ...card('acc-checking', 'Nubank'), type: 'checking' }

function bill(id: string, accountId: string, month: string, fields: Partial<CreditCardBill>): CreditCardBill {
  return {
    id,
    account_id: accountId,
    external_id: null,
    due_date: `${month}-12`,
    effective_due_date: `${month}-12`,
    reference_month: `${month}-01`,
    total_amount: 0,
    currency: 'BRL',
    minimum_payment: null,
    source: 'auto',
    period_start: null,
    period_end: null,
    close_date: null,
    declared_total: null,
    computed_total: 0,
    target_amount: 0,
    paid_amount: 0,
    remaining_amount: 0,
    overpaid_amount: 0,
    settled_on: null,
    status: 'open',
    payments: [],
    ...fields,
  }
}

const bills = [
  bill('itau-oct', 'acc-itau', '2026-10', {
    due_date: '2026-10-10', effective_due_date: '2026-10-13', computed_total: 50, target_amount: 50, remaining_amount: 50,
  }),
  bill('nubank-sep', 'acc-nubank', '2026-09', {
    effective_due_date: '2026-09-14', computed_total: 1283.2, target_amount: 1283.2, remaining_amount: 1283.2, status: 'closed',
  }),
  bill('itau-sep', 'acc-itau', '2026-09', {
    due_date: '2026-09-10', effective_due_date: '2026-09-10', computed_total: 400, declared_total: 410,
    target_amount: 410, paid_amount: 410, status: 'paid',
    payments: [{ id: 'pay-itau', account_id: 'acc-checking', date: '2026-09-09', description: 'Pagamento Itaú', amount: 410, currency: 'BRL' }],
  }),
  bill('nubank-aug', 'acc-nubank', '2026-08', {
    computed_total: 900, target_amount: 900, paid_amount: 900, status: 'paid',
  }),
]

const txByBill: Record<string, unknown[]> = {
  'nubank-sep': [
    { id: 'tx-1', account_id: 'acc-nubank', date: '2026-09-01', description: 'Mercado Extra', amount: 120, currency: 'BRL', type: 'debit', category: { id: 'c1', name: 'Mercado' } },
  ],
  'itau-sep': [
    { id: 'tx-2', account_id: 'acc-itau', date: '2026-08-20', description: 'Restaurante Fasano', amount: 280, currency: 'BRL', type: 'debit', category: { id: 'c2', name: 'Restaurantes' } },
  ],
  'itau-oct': [
    { id: 'tx-3', account_id: 'acc-itau', date: '2026-09-03', description: 'Padaria', amount: 50, currency: 'BRL', type: 'debit', category: null },
  ],
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname + location.search}</div>
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.setSystemTime(new Date('2026-09-08T12:00:00'))
  api.accounts.list.mockResolvedValue([checking, nubank, itau])
  api.creditCardBills.list.mockImplementation(async (params?: { accountId?: string }) =>
    bills.filter((b) => !params?.accountId || b.account_id === params.accountId),
  )
  api.transactions.list.mockImplementation(async (params: { bill_id?: string }) => {
    const items = txByBill[params.bill_id ?? ''] ?? []
    return { items, total: items.length }
  })
})

function renderPage(route = '/accounts/credit-cards') {
  return renderWithProviders(
    <>
      <CreditCardsPage />
      <LocationProbe />
    </>,
    { route },
  )
}

function summary(label: string) {
  const group = screen.getByRole('group', { name: 'Bills of the month' })
  return within(group).getByText(label).nextElementSibling?.textContent
}

function billsTable() {
  return within(screen.getByRole('region', { name: 'Bills' })).getByRole('table')
}

function txTable() {
  return within(screen.getByRole('region', { name: 'Card transactions' })).getByRole('table')
}

/** Cell texts of each body row of a table. */
function rows(table: HTMLElement) {
  return within(table)
    .getAllByRole('row')
    .slice(1)
    .map((row) => within(row).getAllByRole('cell').map((cell) => cell.textContent))
}

describe('consolidated credit card page', () => {
  it('opens all cards on the month of the next effective due date (AC 2, 5)', async () => {
    renderPage()

    expect(await screen.findByRole('button', { name: 'September 2026' })).toBeInTheDocument()
    await waitFor(() => expect(summary('Bills total')).toBe('R$1,693.20'))
    expect(summary('Paid')).toBe('R$410.00')
    expect(summary('Remaining')).toBe('R$1,283.20')
    expect(summary('Next due date')).toBe('9/14/2026')
    expect(summary('Total limit')).toBe('R$7,000.00')
    expect(summary('Total available')).toBe('R$5,316.80')
  })

  it('lists one row per bill with its figures and payment links (AC 6, 8)', async () => {
    renderPage()

    await waitFor(() => expect(rows(billsTable())).toHaveLength(2))
    expect(rows(billsTable())).toEqual([
      ['Itaú Visa', 'Paid', '9/10/2026', 'R$400.00', 'R$410.00', 'R$10.00', '9/9/2026 · R$410.00'],
      ['Cartão de Crédito Nubank', 'Closed', '9/14/2026', 'R$1,283.20', '—', '—', '—'],
    ])
    expect(within(billsTable()).getByRole('link', { name: '9/9/2026 · R$410.00' })).toHaveAttribute(
      'href',
      // ADJ AC 8: the payment transaction, highlighted in its month, not the paying account.
      '/transactions?highlight=pay-itau&from=2026-09-01&to=2026-09-30',
    )
  })

  it("lists the month's card transactions with a card column for all cards (AC 7)", async () => {
    renderPage()

    await waitFor(() => expect(rows(txTable())).toHaveLength(2))
    expect(within(txTable()).getByRole('columnheader', { name: 'Card' })).toBeInTheDocument()
    expect(rows(txTable())).toEqual([
      ['9/1/2026', 'Mercado Extra', 'Mercado', 'Cartão de Crédito Nubank', '−R$120.00'],
      ['8/20/2026', 'Restaurante Fasano', 'Restaurantes', 'Itaú Visa', '−R$280.00'],
    ])
  })

  it('stores the picked card in the URL and scopes every figure to it (AC 3)', async () => {
    const { user } = renderPage()
    await waitFor(() => expect(rows(billsTable())).toHaveLength(2))

    await user.click(screen.getByRole('combobox', { name: 'Card' }))
    await user.click(await screen.findByRole('option', { name: 'Cartão de Crédito Nubank' }))

    expect(screen.getByTestId('location')).toHaveTextContent('/accounts/credit-cards?account=acc-nubank')
    await waitFor(() => expect(api.creditCardBills.list).toHaveBeenCalledWith({ accountId: 'acc-nubank' }))
    await waitFor(() => expect(rows(billsTable())).toHaveLength(1))
    expect(summary('Bills total')).toBe('R$1,283.20')
    expect(summary('Total limit')).toBe('R$5,000.00')
    expect(summary('Total available')).toBe('R$3,716.80')
    expect(within(txTable()).queryByRole('columnheader', { name: 'Card' })).not.toBeInTheDocument()
    expect(rows(txTable())).toEqual([['9/1/2026', 'Mercado Extra', 'Mercado', '−R$120.00']])
  })

  it('reads the card from the URL on open', async () => {
    renderPage('/accounts/credit-cards?account=acc-itau')

    // Itaú's next unpaid bill is October's.
    expect(await screen.findByRole('button', { name: 'October 2026' })).toBeInTheDocument()
    await waitFor(() => expect(rows(billsTable())).toEqual([
      ['Itaú Visa', 'Open', '10/13/2026', 'R$50.00', '—', '—', '—'],
    ]))
  })

  it('shows the bills of the previous and next reference months (AC 4)', async () => {
    const { user } = renderPage()
    await waitFor(() => expect(rows(billsTable())).toHaveLength(2))

    await user.click(screen.getByRole('button', { name: 'Next month' }))
    await waitFor(() => expect(rows(billsTable()).map((r) => r[0])).toEqual(['Itaú Visa']))
    expect(rows(billsTable())[0][2]).toBe('10/13/2026')

    await user.click(screen.getByRole('button', { name: 'Previous month' }))
    await user.click(screen.getByRole('button', { name: 'Previous month' }))
    await waitFor(() => expect(rows(billsTable()).map((r) => r[0])).toEqual(['Cartão de Crédito Nubank']))
    expect(summary('Bills total')).toBe('R$900.00')
  })

  it('opens on the current month when no bill is left to pay', async () => {
    api.creditCardBills.list.mockResolvedValue([bills[3]])
    renderPage()

    expect(await screen.findByRole('button', { name: 'September 2026' })).toBeInTheDocument()
    expect(await screen.findByText('No bills in this month.')).toBeInTheDocument()
  })

  it('shows an empty state with a call to create a card when none exists (AC 9)', async () => {
    api.accounts.list.mockResolvedValue([checking])
    renderPage()

    expect(await screen.findByText('You have no credit card yet. Create one to track its bills here.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Create a credit card' })).toHaveAttribute('href', '/accounts')
    expect(api.creditCardBills.list).not.toHaveBeenCalled()
  })

  it('asks to configure a card that lacks close or due day (AC 10)', async () => {
    api.accounts.list.mockResolvedValue([nubank, card('acc-inter', 'Inter', { statement_close_day: null })])
    renderPage()

    const notice = await screen.findByRole('status')
    expect(notice).toHaveTextContent('Inter has no close or due day, so it has no bills.')
    expect(within(notice).getByRole('link', { name: 'Configure' })).toHaveAttribute('href', '/accounts/acc-inter')
  })
})
