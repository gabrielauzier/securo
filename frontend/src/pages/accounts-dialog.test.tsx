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
    const now = new Date()
    const today = [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, '0'),
      String(now.getDate()).padStart(2, '0'),
    ].join('-')
    expect(payload.currency).toBe('BRL')
    expect(payload.display_name).toBeNull()
    expect(payload.balance).toBe(0)
    expect(payload.balance_date).toBe(today)
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
})
