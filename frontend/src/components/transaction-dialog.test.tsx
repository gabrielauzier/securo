import { screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { TransactionDialog } from '@/components/transaction-dialog'
import { currencies, groups, payees } from '@/lib/api'
import { renderWithProviders, t } from '@/test/utils'
import type { RecurringTransaction } from '@/types'

vi.mock('@/contexts/auth-context', () => ({
  useAuth: () => ({ user: { preferences: { currency_display: 'USD' } } }),
}))
vi.mock('@/hooks/use-display-locale', () => ({
  useDateLocale: () => 'en-US',
  useDisplayLocale: () => 'en-US',
}))

afterEach(() => vi.restoreAllMocks())

it.each(['America/Los_Angeles', 'Pacific/Kiritimati'])(
  'keeps a recurring calendar date unchanged in %s',
  async (timezone) => {
    const originalTimezone = process.env.TZ
    const recurringMatch: RecurringTransaction = {
      id: 'recurring-rent',
      user_id: 'synthetic-user',
      account_id: null,
      category_id: null,
      description: 'Rent',
      amount: 100,
      currency: 'USD',
      type: 'debit',
      frequency: 'monthly',
      weekend_adjustment: 'none',
      day_of_month: 8,
      start_date: '2026-01-08',
      end_date: null,
      is_active: true,
      auto_generate: false,
      next_occurrence: '2026-03-08',
      amount_primary: null,
      fx_rate_used: null,
    }
    vi.spyOn(currencies, 'list').mockResolvedValue([])
    vi.spyOn(payees, 'list').mockResolvedValue([])
    vi.spyOn(groups, 'list').mockResolvedValue([])

    try {
      process.env.TZ = timezone
      renderWithProviders(
        <TransactionDialog
          open
          onClose={vi.fn()}
          transaction={null}
          categories={[]}
          categoryGroups={[]}
          accounts={[]}
          recurringMatch={recurringMatch}
          onSave={vi.fn()}
          loading={false}
          error={null}
        />,
      )

      expect(await screen.findByText(t('transactions.recurringInfo', {
        frequency: t('recurring.monthly'),
        next: '3/8/2026',
      }))).toBeInTheDocument()
    } finally {
      if (originalTimezone === undefined) delete process.env.TZ
      else process.env.TZ = originalTimezone
    }
  },
)

// Bill override (T47). Separate imports so the lines above stay untouched.
import { waitFor } from '@testing-library/react'
import { describe } from 'vitest'
import { creditCardBills } from '@/lib/api'
import type { CreditCardBill, Transaction } from '@/types'

describe('moving a card transaction to another bill', () => {
  const card = { id: 'acc-card', name: 'Cartão de Crédito Nubank', type: 'credit_card', currency: 'BRL' }
  const cardTx = {
    id: 'tx-card',
    account_id: 'acc-card',
    description: 'Mercado',
    amount: 120,
    currency: 'BRL',
    date: '2026-09-04',
    type: 'debit',
    status: 'posted',
    source: 'manual',
    category_id: null,
    payee_id: null,
    notes: null,
    effective_bill_date: null,
  } as unknown as Transaction

  const billOf = (id: string, month: string, due: string, effective: string) =>
    ({ id, account_id: 'acc-card', reference_month: `${month}-01`, due_date: due, effective_due_date: effective }) as CreditCardBill

  function renderCardDialog(transaction: Transaction) {
    vi.spyOn(currencies, 'list').mockResolvedValue([])
    vi.spyOn(payees, 'list').mockResolvedValue([])
    vi.spyOn(groups, 'list').mockResolvedValue([])
    vi.spyOn(creditCardBills, 'list').mockResolvedValue([
      billOf('bill-oct', '2026-10', '2026-10-12', '2026-10-13'),
      billOf('bill-sep', '2026-09', '2026-09-12', '2026-09-14'),
    ])
    const onSave = vi.fn()
    const rendered = renderWithProviders(
      <TransactionDialog
        open
        onClose={vi.fn()}
        transaction={transaction}
        categories={[]}
        categoryGroups={[]}
        accounts={[card]}
        onSave={onSave}
        loading={false}
        error={null}
      />,
    )
    return { ...rendered, onSave }
  }

  it("lists the card's bills and saves the picked bill's due date as the override", async () => {
    const { user, onSave } = renderCardDialog(cardTx)

    await user.click(await screen.findByRole('combobox', { name: 'Bill' }))
    expect(creditCardBills.list).toHaveBeenCalledWith({ accountId: 'acc-card' })
    expect(await screen.findByRole('option', { name: 'September 2026 · Due 9/14/2026' })).toBeInTheDocument()
    await user.click(screen.getByRole('option', { name: 'October 2026 · Due 10/13/2026' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onSave.mock.calls[0][0]).toMatchObject({ effective_bill_date: '2026-10-12' })
  })

  it('clears the override back to automatic', async () => {
    const { user, onSave } = renderCardDialog({ ...cardTx, effective_bill_date: '2026-10-12' } as Transaction)

    const picker = await screen.findByRole('combobox', { name: 'Bill' })
    await waitFor(() => expect(picker).toHaveTextContent('October 2026 · Due 10/13/2026'))
    await user.click(picker)
    await user.click(await screen.findByRole('option', { name: 'Automatic (by date)' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onSave.mock.calls[0][0]).toMatchObject({ effective_bill_date: null })
  })
})

// Bill info (T70, ADJ AC 5). Separate imports so the lines above stay untouched.
import { within } from '@testing-library/react'
import { afterEach as afterEachBillInfo, beforeEach as beforeEachBillInfo } from 'vitest'
import { i18n } from '@/test/utils'

describe('bill info on a card transaction (ADJ AC 5)', () => {
  const card = { id: 'acc-card', name: 'Cartão de Crédito Nubank', type: 'credit_card', currency: 'BRL' }
  const checking = { id: 'acc-checking', name: 'Nubank', type: 'checking', currency: 'BRL' }
  const base = {
    id: 'tx-petz',
    description: 'Petz Digital',
    amount: 120,
    currency: 'BRL',
    date: '2026-09-05',
    type: 'debit',
    status: 'posted',
    source: 'manual',
    category_id: null,
    payee_id: null,
    notes: null,
    effective_bill_date: null,
  }
  const bill = (settledOn: string | null) => ({
    id: 'bill-oct', account_id: 'acc-card', reference_month: '2026-10-01',
    due_date: '2026-10-12', effective_due_date: '2026-10-13', close_date: '2026-10-05',
    settled_on: settledOn, status: settledOn ? 'paid' : 'closed', payments: [],
  }) as unknown as CreditCardBill

  beforeEachBillInfo(async () => {
    vi.spyOn(currencies, 'list').mockResolvedValue([])
    vi.spyOn(payees, 'list').mockResolvedValue([])
    vi.spyOn(groups, 'list').mockResolvedValue([])
    vi.spyOn(creditCardBills, 'list').mockResolvedValue([])
    await i18n.changeLanguage('pt-BR')
  })

  afterEachBillInfo(async () => {
    await i18n.changeLanguage('en')
  })

  function renderDialog(transaction: Transaction, accounts: typeof card[]) {
    return renderWithProviders(
      <TransactionDialog
        open
        onClose={vi.fn()}
        transaction={transaction}
        categories={[]}
        categoryGroups={[]}
        accounts={accounts}
        onSave={vi.fn()}
        loading={false}
        error={null}
      />,
    )
  }

  it('shows the bill and "Quitada em <settled_on>" for a paid bill', async () => {
    vi.spyOn(creditCardBills, 'get').mockResolvedValue(bill('2026-10-10'))
    renderDialog({ ...base, account_id: 'acc-card', bill_id: 'bill-oct' } as unknown as Transaction, [card])

    const info = within(await screen.findByTestId('bill-info'))
    expect(creditCardBills.get).toHaveBeenCalledWith('bill-oct')
    expect(info.getByText('Fatura')).toBeInTheDocument()
    expect(info.getByText('Cartão de Crédito Nubank · October 2026')).toBeInTheDocument()
    expect(info.getByText('Quitada em 10/10/2026')).toBeInTheDocument()
    expect(info.queryByText(/Não quitada/)).not.toBeInTheDocument()
  })

  it('shows "Não quitada · vence em <effective due date>" for an unpaid bill', async () => {
    vi.spyOn(creditCardBills, 'get').mockResolvedValue(bill(null))
    renderDialog({ ...base, account_id: 'acc-card', bill_id: 'bill-oct' } as unknown as Transaction, [card])

    const info = within(await screen.findByTestId('bill-info'))
    expect(info.getByText('Cartão de Crédito Nubank · October 2026')).toBeInTheDocument()
    expect(info.getByText('Não quitada · vence em 10/13/2026')).toBeInTheDocument()
    expect(info.queryByText(/Quitada em/)).not.toBeInTheDocument()
  })

  it('shows nothing for a non-card transaction', async () => {
    const get = vi.spyOn(creditCardBills, 'get')
    renderDialog({ ...base, account_id: 'acc-checking', bill_id: null } as unknown as Transaction, [checking])

    await screen.findByRole('button', { name: 'Salvar' })
    expect(screen.queryByTestId('bill-info')).not.toBeInTheDocument()
    expect(get).not.toHaveBeenCalled()
  })
})
