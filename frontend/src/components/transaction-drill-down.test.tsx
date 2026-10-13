import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { within } from '@testing-library/react'

import { TransactionDrillDown } from '@/components/transaction-drill-down'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { admin, dashboard, transactions } from '@/lib/api'
import { renderWithProviders } from '@/test/utils'
import { createTestQueryClient } from '@/test/utils'
import i18n from '@/lib/i18n'

vi.mock('@/contexts/auth-context', () => ({
  useAuth: () => ({ user: { preferences: { currency_display: 'USD' } } }),
}))

vi.mock('@/lib/api', () => ({
  transactions: { list: vi.fn() },
  dashboard: { projectedTransactions: vi.fn() },
  admin: { accountingMode: vi.fn() },
}))

const filter = { title: 'Uncategorized', uncategorized: true }

function renderPanel({ dialogOpen }: { dialogOpen: boolean }) {
  const onClose = vi.fn()
  const result = renderWithProviders(
    <>
      <TransactionDrillDown filter={filter} onClose={onClose} />
      <Dialog open={dialogOpen}>
        <DialogContent>
          <DialogTitle>Edit transaction</DialogTitle>
          <button type="button">Category</button>
        </DialogContent>
      </Dialog>
    </>,
  )
  return { ...result, onClose }
}

// The outside-click listener is attached after a short delay so the click
// that opened the panel does not close it.
async function waitForOutsideClickListener() {
  await new Promise(resolve => setTimeout(resolve, 150))
}

describe('TransactionDrillDown', () => {
  beforeEach(() => {
    vi.mocked(transactions.list).mockResolvedValue({ items: [], total: 0 } as never)
    vi.mocked(dashboard.projectedTransactions).mockResolvedValue([])
    vi.mocked(admin.accountingMode).mockResolvedValue({ mode: 'cash' } as never)
  })

  afterEach(() => {
    vi.resetAllMocks()
  })

  it('closes on a click outside the panel', async () => {
    const { onClose } = renderPanel({ dialogOpen: false })
    await waitForOutsideClickListener()

    fireEvent.mouseDown(document.body)

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('stays open while the user clicks inside a dialog opened from it', async () => {
    const { onClose } = renderPanel({ dialogOpen: true })
    await waitForOutsideClickListener()

    fireEvent.mouseDown(await screen.findByRole('button', { name: 'Category' }))

    expect(onClose).not.toHaveBeenCalled()
  })

  it('leaves Escape to the open dialog', async () => {
    const { onClose } = renderPanel({ dialogOpen: true })
    await screen.findByRole('dialog')

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(onClose).not.toHaveBeenCalled()
  })

  it('closes on Escape when no dialog is open', async () => {
    const { onClose } = renderPanel({ dialogOpen: false })

    fireEvent.keyDown(document, { key: 'Escape' })

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })
})

// --- BREP-02: the date a card purchase is reported on ------------------------

const CARD = { id: 'card-1', name: 'Cartão de Crédito Nubank', display_name: null, type: 'credit_card' }
const CHECKING = { id: 'checking-1', name: 'Nubank', display_name: null, type: 'checking' }

function row(overrides: Record<string, unknown>) {
  return {
    id: 'tx-1',
    account_id: CARD.id,
    description: 'Google',
    amount: 50,
    amount_primary: 50,
    currency: 'USD',
    date: '2026-10-11',
    reporting_date: '2026-10-11',
    is_bill_projected: false,
    type: 'debit',
    status: 'posted',
    category: null,
    attachment_count: 0,
    fx_fallback: false,
    ...overrides,
  }
}

function renderReporting(
  mode: 'cash' | 'accrual' | 'settlement',
  items: unknown[],
  { dateFormat }: { dateFormat?: 'dmy' } = {},
) {
  vi.mocked(admin.accountingMode).mockResolvedValue({ mode } as never)
  vi.mocked(transactions.list).mockResolvedValue({ items, total: items.length } as never)
  // The accounts the app has already loaded, so the panel can name the card.
  const queryClient = createTestQueryClient()
  queryClient.setQueryDefaults(['accounts', 'closed'], { staleTime: Infinity })
  queryClient.setQueryData(['accounts', 'closed'], [CARD, CHECKING])
  if (dateFormat) queryClient.setQueryData(['admin', 'date-format'], { format: dateFormat })
  return renderWithProviders(
    <TransactionDrillDown
      filter={{ title: 'Expenses', type: 'debit', from: '2026-11-01', to: '2026-11-30' }}
      onClose={vi.fn()}
    />,
    { queryClient },
  )
}

async function rowOf(description: string) {
  return within((await screen.findByText(description)).closest('[role="listitem"]') as HTMLElement)
}

function rowDescriptions() {
  return screen.getAllByRole('listitem').map((item) => item.querySelector('p')?.textContent)
}

describe('TransactionDrillDown reporting date', () => {
  afterEach(async () => {
    vi.resetAllMocks()
    await i18n.changeLanguage('en')
  })

  it('shows the PRD Google purchase on its bill date with the purchase line (accrual)', async () => {
    // A Brazilian install: Portuguese UI, day-first dates.
    await i18n.changeLanguage('pt-BR')
    renderReporting('accrual', [row({ reporting_date: '2026-11-12' })], { dateFormat: 'dmy' })

    const google = await rowOf('Google')
    expect(google.getByText('12/11/2026')).toBeInTheDocument()
    expect(await google.findByText('Lançada em 11/10/2026 · Cartão de Crédito Nubank')).toBeInTheDocument()
  })

  it('shows a paid purchase on its recognition date with the purchase line (settlement)', async () => {
    renderReporting('settlement', [row({ reporting_date: '2026-11-14' })])

    const google = await rowOf('Google')
    expect(google.getByText('11/14/2026')).toBeInTheDocument()
    expect(await google.findByText('Posted on 10/11/2026 · Cartão de Crédito Nubank')).toBeInTheDocument()
    expect(google.queryByText('Projected')).not.toBeInTheDocument()
  })

  it('shows a purchase of an unpaid bill as projected on the effective due date (settlement)', async () => {
    renderReporting('settlement', [row({ reporting_date: '2026-11-16', is_bill_projected: true })])

    const google = await rowOf('Google')
    expect(google.getByText('Projected')).toBeInTheDocument()
    expect(google.getByText('11/16/2026')).toBeInTheDocument()
    expect(await google.findByText('Posted on 10/11/2026 · Cartão de Crédito Nubank')).toBeInTheDocument()
  })

  it('shows card purchases exactly as before in cash mode', async () => {
    renderReporting('cash', [row({ date: '2026-11-03', reporting_date: '2026-11-03' })])

    const google = await rowOf('Google')
    expect(google.getByText('11/3/2026')).toBeInTheDocument()
    expect(screen.queryByText(/Posted on/)).not.toBeInTheDocument()
    expect(google.queryByText('Projected')).not.toBeInTheDocument()
  })

  it('adds no purchase line to rows that are not card purchases', async () => {
    renderReporting('accrual', [
      row({ id: 'tx-2', account_id: CHECKING.id, description: 'Padaria', date: '2026-11-05', reporting_date: '2026-11-05' }),
      row({ reporting_date: '2026-11-12' }),
    ])

    await screen.findByText('Posted on 10/11/2026 · Cartão de Crédito Nubank')
    const bakery = await rowOf('Padaria')
    expect(bakery.queryByText(/Posted on/)).not.toBeInTheDocument()
  })

  it('sorts rows by the date shown as main date', async () => {
    renderReporting('accrual', [
      row({ id: 'tx-1', description: 'Google', date: '2026-10-11', reporting_date: '2026-11-12' }),
      row({ id: 'tx-2', account_id: CHECKING.id, description: 'Padaria', date: '2026-11-05', reporting_date: '2026-11-05' }),
    ])

    await screen.findByText('Google')
    expect(rowDescriptions()).toEqual(['Padaria', 'Google'])
  })
})
