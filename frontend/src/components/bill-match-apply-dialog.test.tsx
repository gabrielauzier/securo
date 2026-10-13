import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'

import { BillMatchApplyDialog } from '@/components/bill-match-apply-dialog'
import { TransactionsPageActions } from '@/components/transactions-page-actions'
import { creditCardBills } from '@/lib/api'
import { renderWithProviders } from '@/test/utils'
import type { BillMatchProposal } from '@/types'

const toastSuccess = vi.hoisted(() => vi.fn())

vi.mock('sonner', () => ({ toast: { success: toastSuccess, error: vi.fn() } }))

vi.mock('@/hooks/use-display-locale', () => ({
  useDisplayLocale: () => 'pt-BR',
  useDateLocale: () => 'pt-BR',
}))

vi.mock('@/lib/api', () => ({
  creditCardBills: {
    previewMatches: vi.fn(),
    applyMatches: vi.fn(),
  },
}))

function proposal(overrides: Partial<BillMatchProposal>): BillMatchProposal {
  return {
    transaction_id: 'tx-1',
    bill_id: 'bill-sep',
    kind: 'exact',
    reason: 'exact_amount',
    payment_account_id: 'acc-checking',
    payment_account_name: 'Nubank',
    payment_date: '2026-09-14',
    payment_description: 'Pagamento fatura Nubank',
    payment_amount: 1283.2,
    bill_account_id: 'acc-card',
    bill_account_name: 'Cartão de Crédito Nubank',
    reference_month: '2026-09-01',
    effective_due_date: '2026-09-14',
    remaining_amount: 1283.2,
    currency: 'BRL',
    ...overrides,
  }
}

const reference = proposal({})
const partial = proposal({
  transaction_id: 'tx-2',
  bill_id: 'bill-inter',
  kind: 'partial',
  reason: 'partial_amount',
  payment_description: 'Pagamento Inter',
  payment_amount: 500,
  bill_account_name: 'Cartão Inter',
  remaining_amount: 1283.2,
})

function renderDialog() {
  const onClose = vi.fn()
  const result = renderWithProviders(<BillMatchApplyDialog open onClose={onClose} />)
  return { ...result, onClose }
}

describe('BillMatchApplyDialog', () => {
  beforeEach(() => {
    vi.mocked(creditCardBills.previewMatches).mockResolvedValue([reference, partial])
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lists each proposed link with a checked checkbox and writes nothing on open (BMATCH AC 10)', async () => {
    renderDialog()

    const boxes = await screen.findAllByRole('checkbox')
    expect(boxes).toHaveLength(2)
    boxes.forEach((box) => expect(box).toBeChecked())
    expect(
      screen.getByRole('checkbox', { name: 'Link Pagamento fatura Nubank to Cartão de Crédito Nubank setembro de 2026' }),
    ).toBeInTheDocument()

    const row = boxes[0].closest('li')!
    expect(row).toHaveTextContent('Pagamento fatura Nubank')
    expect(row).toHaveTextContent('Nubank · 14/09/2026')
    expect(row).toHaveTextContent(/R\$\s1\.283,20/)
    expect(row).toHaveTextContent('Cartão de Crédito Nubank')
    expect(row).toHaveTextContent('Exact')

    expect(vi.mocked(creditCardBills.applyMatches)).not.toHaveBeenCalled()
  })

  it('applies only the checked pairs and reports the linked count (BMATCH AC 11)', async () => {
    vi.mocked(creditCardBills.applyMatches).mockResolvedValue({ linked: 1, failed: [] })
    const { user, onClose } = renderDialog()

    await user.click(await screen.findByRole('checkbox', { name: /Pagamento Inter/ }))
    await user.click(screen.getByRole('button', { name: 'Apply selected' }))

    await waitFor(() =>
      expect(vi.mocked(creditCardBills.applyMatches)).toHaveBeenCalledWith([
        { transaction_id: 'tx-1', bill_id: 'bill-sep' },
      ]),
    )
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Payments linked: 1'))
    expect(onClose).toHaveBeenCalled()
  })

  it('lists the pairs that failed with their reason', async () => {
    vi.mocked(creditCardBills.applyMatches).mockResolvedValue({
      linked: 1,
      failed: [{ transaction_id: 'tx-2', bill_id: 'bill-inter', reason: 'The transaction already pays another bill' }],
    })
    const { user, onClose } = renderDialog()

    await screen.findAllByRole('checkbox')
    await user.click(screen.getByRole('button', { name: 'Apply selected' }))

    await waitFor(() =>
      expect(vi.mocked(creditCardBills.applyMatches)).toHaveBeenCalledWith([
        { transaction_id: 'tx-1', bill_id: 'bill-sep' },
        { transaction_id: 'tx-2', bill_id: 'bill-inter' },
      ]),
    )
    const failures = await screen.findByRole('list', { name: 'Not linked' })
    expect(within(failures).getByText('Pagamento Inter')).toBeInTheDocument()
    expect(within(failures).getByText('The transaction already pays another bill')).toBeInTheDocument()
    expect(toastSuccess).toHaveBeenCalledWith('Payments linked: 1')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('disables apply when every pair is unchecked', async () => {
    const { user } = renderDialog()

    for (const box of await screen.findAllByRole('checkbox')) await user.click(box)

    expect(screen.getByRole('button', { name: 'Apply selected' })).toBeDisabled()
  })

  it('shows an empty state when nothing is proposed', async () => {
    vi.mocked(creditCardBills.previewMatches).mockResolvedValue([])
    renderDialog()

    expect(await screen.findByText('No payment matches to apply.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Apply selected' })).toBeDisabled()
  })
})

describe('TransactionsPageActions bill match entry', () => {
  it('offers "Apply payment matches" when the page passes the handler', async () => {
    const onApplyBillMatches = vi.fn()
    const { user } = renderWithProviders(
      <TransactionsPageActions
        month={{ value: '2026-09', onChange: vi.fn(), locale: 'en', prevLabel: 'Prev', nextLabel: 'Next' }}
        view={{ value: 'list', onChange: vi.fn(), listLabel: 'List', calendarLabel: 'Calendar' }}
        columnPicker={null}
        exportLabel="Export"
        exporting={false}
        onExport={vi.fn()}
        onApplyBillMatches={onApplyBillMatches}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Apply payment matches' }))

    expect(onApplyBillMatches).toHaveBeenCalledTimes(1)
  })
})
