/**
 * The command palette opens the credit card page (BVIEW AC 1).
 */
import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { useLocation } from 'react-router-dom'

import { CommandPalette } from '@/components/command-palette'
import { renderWithProviders } from '@/test/utils'

vi.mock('@/contexts/workspace-context', () => ({
  useWorkspace: () => ({ hasModule: () => true }),
}))

vi.mock('@/hooks/use-display-locale', () => ({
  useDisplayLocale: () => 'en-US',
  useDateLocale: () => 'en-US',
}))

vi.mock('@/lib/api', () => ({
  search: { query: vi.fn().mockResolvedValue([]) },
}))

function LocationProbe() {
  return <div data-testid="location">{useLocation().pathname}</div>
}

describe('command palette', () => {
  it('finds "Credit Card" and navigates to /accounts/credit-cards', async () => {
    const { user } = renderWithProviders(
      <>
        <CommandPalette open onOpenChange={vi.fn()} />
        <LocationProbe />
      </>,
    )

    await user.type(screen.getByRole('combobox'), 'fatura')
    await user.click(await screen.findByRole('option', { name: /Credit Card/ }))

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/accounts/credit-cards'))
  })
})
