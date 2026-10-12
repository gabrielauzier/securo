import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AccountDialog } from '@/pages/accounts'
import { renderWithProviders, t } from '@/test/utils'
import type { Account } from '@/types'

vi.mock('@/contexts/auth-context', () => ({
  useAuth: () => ({ user: { preferences: { currency_display: 'BRL' } } }),
}))

vi.mock('@/lib/api', () => ({
  currencies: {
    list: vi.fn().mockResolvedValue([
      { code: 'BRL', symbol: 'R$', name: 'Real', flag: '' },
      { code: 'USD', symbol: '$', name: 'Dollar', flag: '' },
    ]),
  },
}))

const baseProps = { onClose: vi.fn(), onSave: vi.fn(), loading: false }

const nameInput = () => screen.getAllByRole('textbox')[0]
const balanceInput = () => screen.getAllByRole('spinbutton')[0]
const typeSelect = () => screen.getAllByRole('combobox')[0]

function fillCreateForm() {
  fireEvent.change(nameInput(), { target: { value: 'Previous account' } })
  fireEvent.change(typeSelect(), { target: { value: 'credit_card' } })
  fireEvent.change(balanceInput(), { target: { value: '123' } })
  fireEvent.change(screen.getAllByRole('spinbutton')[1], { target: { value: '5000' } })
}

function expectCreateDefaults() {
  expect(nameInput()).toHaveValue('')
  expect(typeSelect()).toHaveValue('checking')
  expect(balanceInput()).toHaveValue(0)
  expect(screen.queryByText(t('accounts.creditLimit'))).toBeNull()
  expect(screen.getAllByRole('spinbutton')).toHaveLength(1)
  expect(screen.getByRole('button', { name: new RegExp(String(new Date().getFullYear())) })).toBeInTheDocument()
}

describe('AccountDialog', () => {
  it('shows defaults on open in create mode', () => {
    renderWithProviders(<AccountDialog {...baseProps} open account={null} />)
    expectCreateDefaults()
  })

  it('shows defaults when reopened in create mode after a successful save', () => {
    const { rerender } = renderWithProviders(<AccountDialog {...baseProps} open account={null} />)
    fillCreateForm()
    fireEvent.submit(nameInput().closest('form')!)
    expect(baseProps.onSave).toHaveBeenCalled()
    rerender(<AccountDialog {...baseProps} open={false} account={null} />)
    rerender(<AccountDialog {...baseProps} open account={null} />)
    expectCreateDefaults()
  })

  it('shows defaults when reopened in create mode after closing without saving', () => {
    const { rerender } = renderWithProviders(<AccountDialog {...baseProps} open account={null} />)
    fillCreateForm()
    expect(nameInput()).toHaveValue('Previous account')
    rerender(<AccountDialog {...baseProps} open={false} account={null} />)
    rerender(<AccountDialog {...baseProps} open account={null} />)
    expectCreateDefaults()
  })

  it('resets every field to its default when reopened in create mode', async () => {
    vi.mocked(baseProps.onSave).mockClear()
    const { user, rerender } = renderWithProviders(<AccountDialog {...baseProps} open account={null} />)
    fireEvent.change(nameInput(), { target: { value: 'Previous account' } })
    fireEvent.change(typeSelect(), { target: { value: 'credit_card' } })
    fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: 'USD' } })
    fireEvent.change(balanceInput(), { target: { value: '123' } })
    await user.click(screen.getByRole('button', { name: new RegExp(String(new Date().getFullYear())) }))
    const todayDay = String(new Date().getDate())
    const otherDay = (await screen.findAllByRole('button', { name: /^\d{1,2}$/ })).find(
      (btn) => btn.textContent !== todayDay && !btn.hasAttribute('disabled'),
    )!
    await user.click(otherDay)
    const [, creditLimit, closeDay, dueDay] = screen.getAllByRole('spinbutton')
    fireEvent.change(creditLimit, { target: { value: '5000' } })
    fireEvent.change(closeDay, { target: { value: '10' } })
    fireEvent.change(dueDay, { target: { value: '20' } })

    rerender(<AccountDialog {...baseProps} open={false} account={null} />)
    rerender(<AccountDialog {...baseProps} open account={null} />)

    expectCreateDefaults()
    expect(screen.getAllByRole('combobox')[1]).toHaveValue('BRL')
    // The credit-card fields are hidden again; switching the type must show them empty.
    fireEvent.change(typeSelect(), { target: { value: 'credit_card' } })
    const [, limitAgain, closeAgain, dueAgain] = screen.getAllByRole('spinbutton')
    expect(limitAgain).toHaveValue(null)
    expect(closeAgain).toHaveValue(null)
    expect(dueAgain).toHaveValue(null)
    fireEvent.change(nameInput(), { target: { value: 'Fresh' } })
    fireEvent.submit(nameInput().closest('form')!)
    const payload = vi.mocked(baseProps.onSave).mock.calls.at(-1)![0]
    // Balance 0 with an untouched date sets no floor (ABD-04 AC7).
    expect(payload).not.toHaveProperty('balance_date')
    expect(payload.currency).toBe('BRL')
    expect(payload.balance).toBe(0)
    expect(payload.credit_limit).toBeNull()
    expect(payload.statement_close_day).toBeNull()
    expect(payload.payment_due_day).toBeNull()
  })

  it('clears the display name when switching from a connected account to create mode', () => {
    vi.mocked(baseProps.onSave).mockClear()
    const connected = {
      id: 'acc-9',
      name: 'Bank',
      display_name: 'Nickname',
      type: 'checking',
      balance: 10,
      currency: 'BRL',
      connection_id: 'conn-1',
    } as unknown as Account
    const { rerender } = renderWithProviders(<AccountDialog {...baseProps} open account={connected} />)
    expect(screen.getByDisplayValue('Nickname')).toBeInTheDocument()

    rerender(<AccountDialog {...baseProps} open={false} account={null} />)
    rerender(<AccountDialog {...baseProps} open account={null} />)
    fireEvent.change(nameInput(), { target: { value: 'Fresh' } })
    fireEvent.submit(nameInput().closest('form')!)

    expect(vi.mocked(baseProps.onSave).mock.calls.at(-1)![0].display_name).toBeNull()
  })

  it('loads the selected account in edit mode', () => {
    const account = {
      id: 'acc-1',
      name: 'Savings',
      type: 'savings',
      balance: 250.5,
      currency: 'USD',
      connection_id: null,
    } as unknown as Account
    renderWithProviders(<AccountDialog {...baseProps} open account={account} />)
    expect(nameInput()).toHaveValue('Savings')
    expect(typeSelect()).toHaveValue('savings')
    expect(balanceInput()).toHaveValue(250.5)
  })

  it('defaults currency to the user currency, display name to empty and the date to today', () => {
    vi.mocked(baseProps.onSave).mockClear()
    renderWithProviders(<AccountDialog {...baseProps} open account={null} />)
    fireEvent.change(nameInput(), { target: { value: 'Fresh' } })
    fireEvent.submit(nameInput().closest('form')!)
    const payload = vi.mocked(baseProps.onSave).mock.calls.at(-1)![0]
    expect(payload.currency).toBe('BRL')
    expect(payload.display_name).toBeNull()
    expect(payload.balance).toBe(0)
    // Balance 0 with an untouched date sets no floor (ABD-04 AC7).
    expect(payload).not.toHaveProperty('balance_date')
  })

  describe('create payload balance date (ABD-04 AC7)', () => {
    const todayString = () => {
      const now = new Date()
      return [
        now.getFullYear(),
        String(now.getMonth() + 1).padStart(2, '0'),
        String(now.getDate()).padStart(2, '0'),
      ].join('-')
    }

    function submitCreate() {
      fireEvent.change(nameInput(), { target: { value: 'Fresh' } })
      fireEvent.submit(nameInput().closest('form')!)
      return vi.mocked(baseProps.onSave).mock.calls.at(-1)![0]
    }

    it('sends no balance_date for balance 0 with an untouched date', () => {
      vi.mocked(baseProps.onSave).mockClear()
      renderWithProviders(<AccountDialog {...baseProps} open account={null} />)
      const payload = submitCreate()
      expect(payload.balance).toBe(0)
      expect(payload).not.toHaveProperty('balance_date')
    })

    it('sends the chosen date for balance 0 when the date was changed', async () => {
      vi.mocked(baseProps.onSave).mockClear()
      const { user } = renderWithProviders(<AccountDialog {...baseProps} open account={null} />)
      await user.click(screen.getByRole('button', { name: new RegExp(String(new Date().getFullYear())) }))
      const todayDay = String(new Date().getDate())
      const otherDay = (await screen.findAllByRole('button', { name: /^\d{1,2}$/ })).find(
        (btn) => btn.textContent !== todayDay && !btn.hasAttribute('disabled'),
      )!
      await user.click(otherDay)
      const payload = submitCreate()
      expect(payload.balance).toBe(0)
      expect(payload.balance_date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
      expect(payload.balance_date).not.toBe(todayString())
    })

    it('sends the date shown (today) for a non-zero balance with an untouched date', () => {
      vi.mocked(baseProps.onSave).mockClear()
      renderWithProviders(<AccountDialog {...baseProps} open account={null} />)
      fireEvent.change(balanceInput(), { target: { value: '250' } })
      const payload = submitCreate()
      expect(payload.balance).toBe(250)
      expect(payload.balance_date).toBe(todayString())
    })
  })

  describe('edit mode of a manual USD credit card', () => {
    const card = {
      id: 'acc-cc',
      name: 'Visa',
      type: 'credit_card',
      balance: 100,
      currency: 'USD',
      credit_limit: 5000,
      statement_close_day: 8,
      payment_due_day: 15,
      connection_id: null,
    } as unknown as Account

    it('shows the account currency and credit card fields', async () => {
      renderWithProviders(<AccountDialog {...baseProps} open account={card} />)
      expect(await screen.findByRole('option', { name: /Dollar/ })).toBeInTheDocument()
      const [, currencySelect] = screen.getAllByRole('combobox')
      expect(currencySelect).toHaveValue('USD')
      const [, limit, closeDay, dueDay] = screen.getAllByRole('spinbutton')
      expect(limit).toHaveValue(5000)
      expect(closeDay).toHaveValue(8)
      expect(dueDay).toHaveValue(15)
    })

    it('keeps currency and card fields and omits balance on a name-only change', () => {
      vi.mocked(baseProps.onSave).mockClear()
      renderWithProviders(<AccountDialog {...baseProps} open account={card} />)
      fireEvent.change(nameInput(), { target: { value: 'Visa Gold' } })
      fireEvent.submit(nameInput().closest('form')!)
      const payload = vi.mocked(baseProps.onSave).mock.calls.at(-1)![0]
      expect(payload.name).toBe('Visa Gold')
      expect(payload.currency).toBe('USD')
      expect(payload.credit_limit).toBe(5000)
      expect(payload.statement_close_day).toBe(8)
      expect(payload.payment_due_day).toBe(15)
      expect(payload).not.toHaveProperty('balance')
      expect(payload).not.toHaveProperty('balance_date')
    })
  })

  describe('edit payload', () => {
    const manualAccount = {
      id: 'acc-1',
      name: 'Savings',
      type: 'savings',
      balance: 250.5,
      currency: 'BRL',
      connection_id: null,
    } as unknown as Account

    function submit() {
      fireEvent.submit(nameInput().closest('form')!)
      return vi.mocked(baseProps.onSave).mock.calls.at(-1)![0]
    }

    it('omits balance and balance_date when only the name changes', () => {
      vi.mocked(baseProps.onSave).mockClear()
      renderWithProviders(<AccountDialog {...baseProps} open account={manualAccount} />)
      fireEvent.change(nameInput(), { target: { value: 'Renamed' } })
      const payload = submit()
      expect(payload.name).toBe('Renamed')
      expect(payload).not.toHaveProperty('balance')
      expect(payload).not.toHaveProperty('balance_date')
    })

    it('sends balance and balance_date when the balance changes', () => {
      vi.mocked(baseProps.onSave).mockClear()
      renderWithProviders(<AccountDialog {...baseProps} open account={manualAccount} />)
      fireEvent.change(balanceInput(), { target: { value: '300' } })
      const payload = submit()
      expect(payload.balance).toBe(300)
      expect(payload.balance_date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    })

    it('sends balance and balance_date when the date changes', async () => {
      vi.mocked(baseProps.onSave).mockClear()
      const { user } = renderWithProviders(<AccountDialog {...baseProps} open account={manualAccount} />)
      await user.click(screen.getByRole('button', { name: new RegExp(String(new Date().getFullYear())) }))
      const todayDay = String(new Date().getDate())
      const otherDay = (await screen.findAllByRole('button', { name: /^\d{1,2}$/ })).find(
        (btn) => btn.textContent !== todayDay && !btn.hasAttribute('disabled'),
      )!
      await user.click(otherDay)
      const payload = submit()
      expect(payload.balance).toBe(250.5)
      expect(payload.balance_date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    })
  })

  describe('saved balance date', () => {
    const savedAccount = {
      id: 'acc-dated',
      name: 'Dated',
      type: 'savings',
      balance: 250.5,
      balance_date: '2023-03-07',
      currency: 'BRL',
      connection_id: null,
    } as unknown as Account
    const undatedAccount = { ...savedAccount, id: 'acc-undated', balance_date: null } as unknown as Account

    // The trigger shows the date in the display locale, so match the parts, not the order.
    const dateTrigger = () => screen.getAllByRole('button').find((b) => /\d.*\d.*\d/.test(b.textContent ?? ''))!

    function submit() {
      fireEvent.submit(nameInput().closest('form')!)
      return vi.mocked(baseProps.onSave).mock.calls.at(-1)![0]
    }

    it('shows the saved date when editing (ABD-04 AC1)', () => {
      renderWithProviders(<AccountDialog {...baseProps} open account={savedAccount} />)
      const text = dateTrigger().textContent ?? ''
      expect(text).toMatch(/2023/)
      expect(text).toMatch(/(^|\D)0?7(\D|$)/)
      expect(text).toMatch(/(^|\D)0?3(\D|$)/)
    })

    it('shows today when the edited account has no saved date (AC2)', () => {
      renderWithProviders(<AccountDialog {...baseProps} open account={undatedAccount} />)
      expect(dateTrigger().textContent).toMatch(new RegExp(String(new Date().getFullYear())))
      expect(dateTrigger().textContent).not.toMatch(/2023/)
    })

    it('shows today in create mode (AC3)', () => {
      renderWithProviders(<AccountDialog {...baseProps} open account={null} />)
      expect(dateTrigger().textContent).toMatch(new RegExp(String(new Date().getFullYear())))
    })

    it('shows the hint under the date field (AC4)', () => {
      renderWithProviders(<AccountDialog {...baseProps} open account={savedAccount} />)
      expect(screen.getByText(t('accounts.balanceDateHint'))).toBeInTheDocument()
    })

    it('omits balance and balance_date on a name-only edit of a dated account (AC5)', () => {
      vi.mocked(baseProps.onSave).mockClear()
      renderWithProviders(<AccountDialog {...baseProps} open account={savedAccount} />)
      fireEvent.change(nameInput(), { target: { value: 'Renamed' } })
      const payload = submit()
      expect(payload.name).toBe('Renamed')
      expect(payload).not.toHaveProperty('balance')
      expect(payload).not.toHaveProperty('balance_date')
    })

    it('keeps the saved date in the payload when only the balance changes', () => {
      vi.mocked(baseProps.onSave).mockClear()
      renderWithProviders(<AccountDialog {...baseProps} open account={savedAccount} />)
      fireEvent.change(balanceInput(), { target: { value: '300' } })
      const payload = submit()
      expect(payload.balance).toBe(300)
      expect(payload.balance_date).toBe('2023-03-07')
    })

    it('shows the new account date when the dialog switches to another account', () => {
      const { rerender } = renderWithProviders(<AccountDialog {...baseProps} open account={savedAccount} />)
      rerender(<AccountDialog {...baseProps} open={false} account={savedAccount} />)
      rerender(<AccountDialog {...baseProps} open account={undatedAccount} />)
      expect(dateTrigger().textContent).not.toMatch(/2023/)
    })
  })
})
