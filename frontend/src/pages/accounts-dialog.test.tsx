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
})
