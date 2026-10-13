/**
 * BREP AC 16: the admin settings describe the three credit card accounting
 * modes and let the admin pick one.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'

import AdminSettingsPage from '@/pages/admin/settings'
import { renderWithProviders } from '@/test/utils'

const api = vi.hoisted(() => ({
  admin: {
    listUsers: vi.fn(),
    createUser: vi.fn(),
    updateUser: vi.fn(),
    deleteUser: vi.fn(),
    getSetting: vi.fn(),
    updateSetting: vi.fn(),
  },
  currencies: { list: vi.fn() },
}))

vi.mock('@/lib/api', () => ({
  admin: api.admin,
  currencies: api.currencies,
}))

vi.mock('@/contexts/auth-context', () => ({
  useAuth: () => ({ user: { id: 'admin-1', email: 'admin@example.com' } }),
}))

vi.mock('@/hooks/use-local-auth', () => ({
  useLocalAuthEnabled: () => true,
}))

vi.mock('@/components/timezone-settings', () => ({
  TimezoneSettings: () => null,
}))

function mockMode(mode: string | null) {
  api.admin.getSetting.mockImplementation(async (key: string) => {
    if (key === 'credit_card_accounting_mode') {
      if (mode === null) throw new Error('404')
      return { key, value: mode }
    }
    throw new Error('404')
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  api.admin.listUsers.mockResolvedValue({ items: [], total: 0 })
  api.currencies.list.mockResolvedValue([])
  api.admin.updateSetting.mockImplementation(async (key: string, value: string) => {
    mockMode(value)
    return { key, value }
  })
})

async function modeGroup() {
  return within(await screen.findByRole('radiogroup', { name: 'Accounting' }))
}

describe('credit card accounting mode', () => {
  it('describes the three modes', async () => {
    mockMode(null)
    renderWithProviders(<AdminSettingsPage />)
    const group = await modeGroup()

    expect(group.getAllByRole('radio').map((radio) => radio.textContent)).toEqual([
      'Cash basisCredit card purchases count on the day they happen (default).',
      "Accrual basisCredit card purchases count on the bill's due date — reflects actual cash flow.",
      'On bill settlementCredit card purchases count on the date their bill is fully paid; until then they show as projected expenses.',
    ])
  })

  it('shows cash as the current mode when the setting is unset', async () => {
    mockMode(null)
    renderWithProviders(<AdminSettingsPage />)
    const group = await modeGroup()

    await waitFor(() =>
      expect(group.getByRole('radio', { name: /Cash basis/ })).toHaveAttribute('aria-checked', 'true'),
    )
    expect(group.getByRole('radio', { name: /On bill settlement/ })).toHaveAttribute('aria-checked', 'false')
  })

  it.each([
    ['accrual', /Accrual basis/],
    ['settlement', /On bill settlement/],
  ])('shows %s as the current mode when it is saved', async (mode, name) => {
    mockMode(mode)
    renderWithProviders(<AdminSettingsPage />)
    const group = await modeGroup()

    await waitFor(() => expect(group.getByRole('radio', { name })).toHaveAttribute('aria-checked', 'true'))
    expect(group.getByRole('radio', { name: /Cash basis/ })).toHaveAttribute('aria-checked', 'false')
  })

  it('saves settlement when the admin picks it', async () => {
    mockMode('cash')
    const { user } = renderWithProviders(<AdminSettingsPage />)
    const group = await modeGroup()

    await user.click(group.getByRole('radio', { name: /On bill settlement/ }))

    await waitFor(() =>
      expect(api.admin.updateSetting).toHaveBeenCalledWith('credit_card_accounting_mode', 'settlement'),
    )
    await waitFor(() =>
      expect(group.getByRole('radio', { name: /On bill settlement/ })).toHaveAttribute('aria-checked', 'true'),
    )
    expect(group.getByRole('radio', { name: /Cash basis/ })).toHaveAttribute('aria-checked', 'false')
  })
})
