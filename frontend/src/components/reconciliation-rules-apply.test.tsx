import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'

import { ReconciliationRules } from '@/components/reconciliation-rules'
import type { ProposedTransferPair } from '@/lib/api'
import { renderWithProviders, t } from '@/test/utils'

const api = vi.hoisted(() => ({
  rules: vi.fn(),
  previewTransfers: vi.fn(),
  applyTransfers: vi.fn(),
  toastSuccess: vi.fn(),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    reconciliation: { ...actual.reconciliation, rules: api.rules },
    connections: {
      ...actual.connections,
      previewTransfers: api.previewTransfers,
      applyTransfers: api.applyTransfers,
    },
    accounts: { ...actual.accounts, list: vi.fn().mockResolvedValue([]) },
    payees: { ...actual.payees, list: vi.fn().mockResolvedValue([]) },
  }
})

vi.mock('sonner', () => ({ toast: { success: api.toastSuccess, error: vi.fn() } }))

vi.mock('@/hooks/use-display-locale', () => ({
  useDisplayLocale: () => 'en-US',
  useDateLocale: () => 'en-US',
}))

const NODES = [
  { node: 'reconciliation.match_transfer', active: true, rules: [], discarded: [] },
]

function pair(n: number): ProposedTransferPair {
  return {
    a: {
      id: `d-${n}`, date: '2026-10-01', account_id: 'acc-a', account_name: 'Checking',
      description: `Sent ${n}`, amount: 100 * n, currency: 'BRL', type: 'debit',
    },
    b: {
      id: `c-${n}`, date: '2026-10-01', account_id: 'acc-b', account_name: 'Savings',
      description: `Received ${n}`, amount: 100 * n, currency: 'BRL', type: 'credit',
    },
    strategy: 'exact_amount_nearby',
  }
}

const emptyPreview = { pairs: [], ambiguous: [], unmatched: [], already_linked: [] }

describe('transfer rule apply now (TRF-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.rules.mockResolvedValue(NODES)
    api.previewTransfers.mockResolvedValue({ ...emptyPreview, pairs: [pair(1), pair(2)] })
    api.applyTransfers.mockResolvedValue({ linked: 1, skipped: [] })
  })

  it('opening the dialog loads the preview and writes nothing', async () => {
    const { user } = renderWithProviders(<ReconciliationRules canWrite />)

    await user.click(await screen.findByRole('button', { name: t('reconciliation.applyNow') }))

    expect(await screen.findByText('Sent 1')).toBeInTheDocument()
    expect(screen.getByText('Received 2')).toBeInTheDocument()
    expect(api.previewTransfers).toHaveBeenCalledTimes(1)
    expect(api.applyTransfers).not.toHaveBeenCalled()
  })

  it('confirm sends only the checked pairs and toasts linked and skipped', async () => {
    api.applyTransfers.mockResolvedValue({
      linked: 1,
      skipped: [{ a: 'x', b: 'y', reason: 'already_linked' }],
    })
    const { user } = renderWithProviders(<ReconciliationRules canWrite />)
    await user.click(await screen.findByRole('button', { name: t('reconciliation.applyNow') }))
    await screen.findByText('Sent 1')

    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getAllByRole('checkbox')[0])
    await user.click(within(dialog).getByRole('button', { name: t('reconciliation.applyNowConfirm') }))

    await waitFor(() =>
      expect(api.applyTransfers).toHaveBeenCalledWith([{ a: 'd-2', b: 'c-2' }]),
    )
    await waitFor(() =>
      expect(api.toastSuccess).toHaveBeenCalledWith(
        t('reconciliation.applyNowSuccess', { linked: 1, skipped: 1 }),
      ),
    )
  })

  it('shows the empty state and cannot confirm when nothing is proposed', async () => {
    api.previewTransfers.mockResolvedValue(emptyPreview)
    const { user } = renderWithProviders(<ReconciliationRules canWrite />)

    await user.click(await screen.findByRole('button', { name: t('reconciliation.applyNow') }))

    expect(await screen.findByText(t('transferPreview.empty'))).toBeInTheDocument()
    expect(
      within(screen.getByRole('dialog')).getByRole('button', {
        name: t('reconciliation.applyNowConfirm'),
      }),
    ).toBeDisabled()
  })

  it('offers no apply action to a read-only member', async () => {
    renderWithProviders(<ReconciliationRules canWrite={false} />)

    await screen.findByText(t('rules.export'))

    expect(screen.queryByRole('button', { name: t('reconciliation.applyNow') })).toBeNull()
  })
})
