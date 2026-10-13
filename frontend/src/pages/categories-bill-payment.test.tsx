/**
 * BPAY-03: the category form flags a category as "bill payment", so its
 * transactions leave income and expense totals (BPAY AC 13).
 */
import { createContext } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'

import CategoriesPage from '@/pages/categories'
import { renderWithProviders } from '@/test/utils'

const api = vi.hoisted(() => ({
  categories: {
    listIncludingHidden: vi.fn(),
    usage: vi.fn(),
    delete: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    ruleUsage: vi.fn(),
  },
  categoryGroups: {
    listIncludingHidden: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/lib/api', () => ({
  categories: api.categories,
  categoryGroups: api.categoryGroups,
}))

vi.mock('@/contexts/workspace-context', () => ({
  useWorkspace: () => ({ canWrite: true }),
  WorkspaceContext: createContext<{ canWrite: boolean } | undefined>({ canWrite: true }),
}))

function category(id: string, name: string, overrides = {}) {
  return {
    id,
    user_id: 'user-1',
    name,
    icon: 'circle-help',
    color: '#6366f1',
    group_id: null,
    is_system: false,
    is_hidden: false,
    treat_as_transfer: false,
    is_ignored: false,
    is_bill_payment: false,
    ...overrides,
  }
}

const TOGGLE = /Credit card bill payment/

beforeEach(() => {
  vi.clearAllMocks()
  api.categoryGroups.listIncludingHidden.mockResolvedValue([])
  api.categories.update.mockImplementation(async (id: string, data: object) => ({ id, ...data }))
  api.categories.create.mockImplementation(async (data: object) => ({ id: 'new', ...data }))
})

async function openEdit(user: ReturnType<typeof renderWithProviders>['user'], name: string) {
  const row = (await screen.findByText(name)).closest('div')!.parentElement!
  await user.click(within(row).getByTitle('Edit'))
  return within(await screen.findByRole('dialog'))
}

describe('bill payment toggle', () => {
  it('saves is_bill_payment when the user turns it on', async () => {
    api.categories.listIncludingHidden.mockResolvedValue([category('cat-1', 'Pagamento de fatura')])
    const { user } = renderWithProviders(<CategoriesPage />)

    const dialog = await openEdit(user, 'Pagamento de fatura')
    const toggle = dialog.getByRole('checkbox', { name: TOGGLE })
    expect(toggle).not.toBeChecked()

    await user.click(toggle)
    await user.click(dialog.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(api.categories.update).toHaveBeenCalledTimes(1))
    expect(api.categories.update.mock.calls[0][0]).toBe('cat-1')
    expect(api.categories.update.mock.calls[0][1]).toMatchObject({ is_bill_payment: true })
  })

  it('shows the saved flag and saves it off when the user turns it off', async () => {
    api.categories.listIncludingHidden.mockResolvedValue([
      category('cat-1', 'Pagamento de fatura', { is_bill_payment: true }),
    ])
    const { user } = renderWithProviders(<CategoriesPage />)

    const dialog = await openEdit(user, 'Pagamento de fatura')
    const toggle = dialog.getByRole('checkbox', { name: TOGGLE })
    expect(toggle).toBeChecked()

    await user.click(toggle)
    await user.click(dialog.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(api.categories.update).toHaveBeenCalledTimes(1))
    expect(api.categories.update.mock.calls[0][1]).toMatchObject({ is_bill_payment: false })
  })

  it('creates a category with the flag on', async () => {
    api.categories.listIncludingHidden.mockResolvedValue([])
    const { user } = renderWithProviders(<CategoriesPage />)

    await user.click(await screen.findByRole('button', { name: 'Add Category' }))
    const dialogElement = await screen.findByRole('dialog')
    const dialog = within(dialogElement)
    await user.type(dialogElement.querySelector<HTMLInputElement>('input[name="name"]')!, 'Pagamento de fatura')
    await user.click(dialog.getByRole('checkbox', { name: TOGGLE }))
    await user.click(dialog.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(api.categories.create).toHaveBeenCalledTimes(1))
    expect(api.categories.create.mock.calls[0][0]).toMatchObject({
      name: 'Pagamento de fatura',
      is_bill_payment: true,
    })
  })
})

describe('bill payment badge in the list (ADJ AC 1)', () => {
  it('shows the badge only next to categories flagged as bill payment', async () => {
    api.categories.listIncludingHidden.mockResolvedValue([
      category('cat-1', 'Fatura do cartão', { is_bill_payment: true }),
      category('cat-2', 'Mercado'),
    ])
    renderWithProviders(<CategoriesPage />)

    const flagged = (await screen.findByText('Fatura do cartão')).parentElement!
    expect(within(flagged).getByText('Bill payment')).toBeInTheDocument()
    const plain = screen.getByText('Mercado').parentElement!
    expect(within(plain).queryByText('Bill payment')).not.toBeInTheDocument()
    expect(screen.getAllByText('Bill payment')).toHaveLength(1)
  })
})

describe('bill payment badge label in pt-BR (ADJ AC 1)', () => {
  it('reads "Pagamento de fatura"', async () => {
    const ptBR = (await import('@/locales/pt-BR.json')).default
    expect(ptBR.categories.billPaymentBadge).toBe('Pagamento de fatura')
  })
})
