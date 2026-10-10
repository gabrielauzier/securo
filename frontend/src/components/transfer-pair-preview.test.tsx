import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'

import {
  TransferPairPreview,
  selectedPairRefs,
} from '@/components/transfer-pair-preview'
import type { ProposedTransferPair } from '@/lib/api'
import { renderWithProviders, t } from '@/test/utils'

vi.mock('@/hooks/use-display-locale', () => ({
  useDisplayLocale: () => 'en-US',
  useDateLocale: () => 'en-US',
}))

function pair(n: number, amount: number): ProposedTransferPair {
  return {
    a: {
      id: `d-${n}`, date: '2026-10-01', account_id: 'acc-a', account_name: 'Checking',
      description: `Sent ${n}`, amount, currency: 'BRL', type: 'debit',
    },
    b: {
      id: `c-${n}`, date: '2026-10-02', account_id: 'acc-b', account_name: 'Savings',
      description: `Received ${n}`, amount, currency: 'BRL', type: 'credit',
    },
    strategy: 'exact_amount_nearby',
  }
}

const pairs = [pair(1, 100), pair(2, 250)]

function Harness({ onRefs }: { onRefs?: (refs: { a: string; b: string }[]) => void }) {
  const [deselected, setDeselected] = useState<Set<string>>(new Set())
  onRefs?.(selectedPairRefs(pairs, deselected))
  return (
    <TransferPairPreview pairs={pairs} deselected={deselected} onDeselectedChange={setDeselected} />
  )
}

describe('TransferPairPreview', () => {
  it('shows both legs and the strategy of every pair, all checked by default', () => {
    renderWithProviders(<Harness />)

    expect(screen.getByText('Sent 1')).toBeInTheDocument()
    expect(screen.getByText('Received 1')).toBeInTheDocument()
    expect(screen.getByText('Sent 2')).toBeInTheDocument()
    expect(screen.getAllByText(/Checking/)).toHaveLength(2)
    expect(screen.getAllByText(/Savings/)).toHaveLength(2)
    expect(screen.getAllByText('exact_amount_nearby')).toHaveLength(2)
    const boxes = screen.getAllByRole('checkbox')
    expect(boxes).toHaveLength(2)
    boxes.forEach((box) => expect(box).toBeChecked())
  })

  it('shows how many pairs are selected', () => {
    renderWithProviders(<Harness />)

    expect(
      screen.getByText(t('transferPreview.selectedCount', { selected: 2, total: 2 }), { exact: false }),
    ).toBeInTheDocument()
  })

  it('removes an unchecked pair from the confirm set and updates the count', async () => {
    const onRefs = vi.fn()
    const { user } = renderWithProviders(<Harness onRefs={onRefs} />)

    await user.click(screen.getAllByRole('checkbox')[0])

    expect(onRefs).toHaveBeenLastCalledWith([{ a: 'd-2', b: 'c-2' }])
    expect(screen.getAllByRole('checkbox')[0]).not.toBeChecked()
    expect(
      screen.getByText(t('transferPreview.selectedCount', { selected: 1, total: 2 }), { exact: false }),
    ).toBeInTheDocument()
  })

  it('renders the empty state when there are no pairs', () => {
    renderWithProviders(
      <TransferPairPreview pairs={[]} deselected={new Set()} onDeselectedChange={() => {}} />,
    )

    expect(screen.getByText(t('transferPreview.empty'))).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })
})
