import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'

import { LinkBillDialog } from '@/components/link-bill-dialog'
import { creditCardBills, transactions } from '@/lib/api'
import { renderWithProviders, t } from '@/test/utils'
import type { Account, BillCandidate, BillPaymentLinkResult, CreditCardBill, Transaction } from '@/types'

vi.mock('@/contexts/auth-context', () => ({
  useAuth: () => ({ user: { preferences: { currency_display: 'BRL' } } }),
}))

vi.mock('@/lib/api', () => ({
  admin: {
    numberFormat: vi.fn().mockResolvedValue({ format: 'auto' }),
    dateFormat: vi.fn().mockResolvedValue({ format: 'auto' }),
  },
  creditCardBills: {
    paymentCandidates: vi.fn(),
    linkPayment: vi.fn(),
  },
  transactions: {
    createTransferCounterpart: vi.fn(),
  },
}))

// The reference payment: 1,283.20 on 2026-09-14 from "Nubank" (BPAY AC 5).
const payment = {
  id: 'tx-1',
  account_id: 'acc-checking',
  description: 'Pagamento fatura Nubank',
  amount: 1283.2,
  currency: 'BRL',
  date: '2026-09-14',
  type: 'debit',
} as Transaction

const accounts = [
  { id: 'acc-checking', name: 'Nubank', type: 'checking' },
  { id: 'acc-card', name: 'Cartão de Crédito Nubank', type: 'credit_card' },
] as Account[]

const exactCandidate: BillCandidate = {
  bill_id: 'bill-sep',
  account_id: 'acc-card',
  account_name: 'Cartão de Crédito Nubank',
  reference_month: '2026-09-01',
  effective_due_date: '2026-09-14',
  target_amount: 1283.2,
  remaining_amount: 1283.2,
  currency: 'BRL',
  kind: 'exact',
  reason: 'exact_amount',
  rank: 1,
}

// BMATCH AC 13: a bill whose window the payment misses is listed as "other".
const otherCandidate: BillCandidate = {
  bill_id: 'bill-aug',
  account_id: 'acc-inter',
  account_name: 'Cartão Inter',
  reference_month: '2026-08-01',
  effective_due_date: '2026-08-10',
  target_amount: 450,
  remaining_amount: 450,
  currency: 'BRL',
  kind: 'other',
  reason: 'outside_window',
  rank: 2,
}

function linkResult(needsCounterpart: boolean): BillPaymentLinkResult {
  return {
    transaction_id: 'tx-1',
    bill: { id: 'bill-sep', account_id: 'acc-card' } as CreditCardBill,
    paired_credit_id: needsCounterpart ? null : 'tx-credit',
    needs_counterpart: needsCounterpart,
  }
}

function apiError(status: number, detail: string) {
  return Object.assign(new Error(detail), { response: { status, data: { detail } } })
}

function renderDialog() {
  const onClose = vi.fn()
  const result = renderWithProviders(
    <LinkBillDialog open onClose={onClose} transaction={payment} accounts={accounts} />,
  )
  return { ...result, onClose }
}

async function pickAndConfirm(user: ReturnType<typeof renderDialog>['user'], cardName: string) {
  await user.click(await screen.findByRole('button', { name: new RegExp(cardName) }))
  await user.click(screen.getByRole('button', { name: t('bills.link.confirm') }))
}

describe('LinkBillDialog', () => {
  beforeEach(() => {
    vi.mocked(creditCardBills.paymentCandidates).mockResolvedValue([exactCandidate, otherCandidate])
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('lists candidate bills first, with card, month, due date, target, remaining and reason', async () => {
    renderDialog()

    const candidates = await screen.findByRole('list', { name: 'Suggested bills' })
    const others = screen.getByRole('list', { name: 'Other unpaid bills' })
    // Candidates come before the other unpaid bills.
    expect(candidates.compareDocumentPosition(others) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(vi.mocked(creditCardBills.paymentCandidates)).toHaveBeenCalledWith('tx-1')

    const row = within(candidates).getByRole('button')
    expect(row).toHaveTextContent('Cartão de Crédito Nubank')
    expect(row).toHaveTextContent(/september 2026/i)
    expect(row).toHaveTextContent('Due 14/09/2026')
    expect(row).toHaveTextContent(/Total R\$\s1\.283,20/)
    expect(row).toHaveTextContent(/Remaining R\$\s1\.283,20/)
    expect(row).toHaveTextContent('Exact amount')

    const otherRow = within(others).getByRole('button')
    expect(otherRow).toHaveTextContent('Cartão Inter')
    expect(otherRow).toHaveTextContent(/august 2026/i)
    expect(otherRow).toHaveTextContent('Due 10/08/2026')
    expect(otherRow).toHaveTextContent('Outside the payment window')
  })

  it('shows an empty state when there is no unpaid bill', async () => {
    vi.mocked(creditCardBills.paymentCandidates).mockResolvedValue([])
    renderDialog()

    expect(await screen.findByText('No unpaid bills found.')).toBeInTheDocument()
  })

  it('confirms the picked bill through the link endpoint and closes', async () => {
    vi.mocked(creditCardBills.linkPayment).mockResolvedValue(linkResult(false))
    const { user, onClose } = renderDialog()

    await pickAndConfirm(user, 'Cartão de Crédito Nubank')

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(vi.mocked(creditCardBills.linkPayment)).toHaveBeenCalledWith('bill-sep', 'tx-1')
    expect(screen.queryByText(t('bills.link.counterpartCreate'))).not.toBeInTheDocument()
  })

  it('links one of the other unpaid bills too', async () => {
    vi.mocked(creditCardBills.linkPayment).mockResolvedValue(linkResult(false))
    const { user, onClose } = renderDialog()

    await pickAndConfirm(user, 'Cartão Inter')

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(vi.mocked(creditCardBills.linkPayment)).toHaveBeenCalledWith('bill-aug', 'tx-1')
  })

  it('shows the 409 message when the payment already pays another bill', async () => {
    vi.mocked(creditCardBills.linkPayment).mockRejectedValue(
      apiError(409, 'The transaction already pays another bill'),
    )
    const { user, onClose } = renderDialog()

    await pickAndConfirm(user, 'Cartão de Crédito Nubank')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This transaction already pays another bill.',
    )
    expect(onClose).not.toHaveBeenCalled()
  })

  it('shows the 422 reason when the payment is not eligible', async () => {
    vi.mocked(creditCardBills.linkPayment).mockRejectedValue(
      apiError(422, 'The payment and the bill have different currencies'),
    )
    const { user, onClose } = renderDialog()

    await pickAndConfirm(user, 'Cartão de Crédito Nubank')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This transaction cannot pay this bill: The payment and the bill have different currencies',
    )
    expect(onClose).not.toHaveBeenCalled()
  })

  it('offers to create the counterpart on the card when the link needs one', async () => {
    vi.mocked(creditCardBills.linkPayment).mockResolvedValue(linkResult(true))
    vi.mocked(transactions.createTransferCounterpart).mockResolvedValue({} as never)
    const { user, onClose } = renderDialog()

    await pickAndConfirm(user, 'Cartão de Crédito Nubank')

    expect(
      await screen.findByText(
        'No matching credit was found on Cartão de Crédito Nubank. Create it so the card balance reflects the payment.',
      ),
    ).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Create counterpart' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(vi.mocked(transactions.createTransferCounterpart)).toHaveBeenCalledWith('tx-1', 'acc-card')
  })

  it('lets the user skip the counterpart and keep the link', async () => {
    vi.mocked(creditCardBills.linkPayment).mockResolvedValue(linkResult(true))
    const { user, onClose } = renderDialog()

    await pickAndConfirm(user, 'Cartão de Crédito Nubank')
    await user.click(await screen.findByRole('button', { name: 'Not now' }))

    expect(onClose).toHaveBeenCalled()
    expect(vi.mocked(transactions.createTransferCounterpart)).not.toHaveBeenCalled()
  })
})
