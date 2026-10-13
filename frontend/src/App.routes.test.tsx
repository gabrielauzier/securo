/**
 * `/accounts/credit-cards` must open the credit card page, not the account
 * detail page with "credit-cards" read as an account id (BVIEW AC 1).
 */
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Outlet } from 'react-router-dom'

import App from '@/App'

const { passthrough } = vi.hoisted(() => ({
  passthrough: ({ children }: { children: ReactNode }) => children,
}))

vi.mock('@/contexts/auth-provider', () => ({ AuthProvider: passthrough }))
vi.mock('@/contexts/workspace-provider', () => ({ WorkspaceProvider: passthrough }))
vi.mock('@/contexts/collection-filter-provider', () => ({ CollectionFilterProvider: passthrough }))
vi.mock('@/components/protected-route', () => ({ ProtectedRoute: passthrough }))
vi.mock('@/components/module-route', () => ({ ModuleRoute: passthrough }))
vi.mock('@/components/app-layout', () => ({ AppLayout: () => <Outlet /> }))
vi.mock('@/pages/credit-cards', () => ({ default: () => <p>credit card page</p> }))
vi.mock('@/pages/account-detail', () => ({ default: () => <p>account detail page</p> }))

afterEach(() => window.history.pushState({}, '', '/'))

describe('account routes', () => {
  it('opens the credit card page at /accounts/credit-cards', async () => {
    window.history.pushState({}, '', '/accounts/credit-cards?account=acc-1')
    render(<App />)

    expect(await screen.findByText('credit card page')).toBeInTheDocument()
    expect(screen.queryByText('account detail page')).not.toBeInTheDocument()
  })

  it('still opens an account at /accounts/:id', async () => {
    window.history.pushState({}, '', '/accounts/acc-1')
    render(<App />)

    expect(await screen.findByText('account detail page')).toBeInTheDocument()
  })
})
