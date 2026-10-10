import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import ImportPage from '@/pages/import'
import { renderWithProviders, t } from '@/test/utils'

const api = vi.hoisted(() => ({
  previewImport: vi.fn(),
  importTransactions: vi.fn(),
  accountsList: vi.fn(),
  mappings: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    match: vi.fn(),
    touch: vi.fn(),
  },
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    transactions: {
      ...actual.transactions,
      previewImport: api.previewImport,
      import: api.importTransactions,
    },
    accounts: { ...actual.accounts, list: api.accountsList },
    categories: { ...actual.categories, list: vi.fn().mockResolvedValue([]) },
    categoryGroups: { ...actual.categoryGroups, list: vi.fn().mockResolvedValue([]) },
    importLogs: { ...actual.importLogs, list: vi.fn().mockResolvedValue([]) },
    importMappings: api.mappings,
  }
})

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@/hooks/use-display-locale', () => ({
  useDisplayLocale: () => 'en-US',
  useDateLocale: () => 'en-US',
}))

vi.mock('@/contexts/auth-context', () => ({
  useAuth: () => ({ user: { preferences: { currency_display: 'BRL' } } }),
}))

vi.mock('@/contexts/workspace-context', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/contexts/workspace-context')>()),
  useWorkspace: () => ({ canWrite: true }),
}))

const NUBANK_HEADERS = ['Data', 'Valor', 'Identificador', 'Descrição']
const NUBANK_COLUMNS = {
  date: 'Data',
  amount: 'Valor',
  external_id: 'Identificador',
  description: 'Descrição',
}

const account = { id: 'acc-1', name: 'Nubank Conta', type: 'checking' }

function mapping(overrides: Record<string, unknown> = {}) {
  return {
    id: 'map-1',
    name: 'Nubank',
    account_id: 'acc-1',
    headers: [...NUBANK_HEADERS].sort(),
    column_mapping: NUBANK_COLUMNS,
    options: { date_format: 'DD/MM/YYYY', flip_amount: true, inflow_column: null, outflow_column: null },
    last_used_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

async function uploadCsv(user: ReturnType<typeof renderWithProviders>['user']) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  const file = new File(['Data,Valor,Identificador,Descrição\n'], 'nubank.csv', { type: 'text/csv' })
  await user.upload(input, file)
  await screen.findByText(t('import.csvOptions'))
}

function accountOption() {
  return screen.getByRole('option', { name: /Nubank Conta/ }) as HTMLOptionElement
}

function columnSelect(labelKey: string) {
  return screen.getByText(t(labelKey)).parentElement!.querySelector('select') as HTMLSelectElement
}

function lastPreviewOptions() {
  const calls = api.previewImport.mock.calls
  return calls[calls.length - 1][1]
}

describe('ImportPage saved mappings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.previewImport.mockResolvedValue({
      transactions: [{ description: 'Mercado', amount: 10, date: '2026-01-02', type: 'debit', external_id: 'x1' }],
      detected_format: 'csv',
      csv_columns: NUBANK_HEADERS,
      parse_error: null,
      failed_rows: [],
    })
    api.accountsList.mockResolvedValue([account])
    api.mappings.list.mockResolvedValue([])
    api.mappings.match.mockResolvedValue([])
    api.mappings.touch.mockResolvedValue(mapping())
    api.importTransactions.mockResolvedValue({ imported: 1, skipped: 0, excluded: 0, import_log_id: 'log-1' })
  })

  it('applies the matching mapping and its account on upload, with no clicks', async () => {
    api.mappings.list.mockResolvedValue([mapping()])
    api.mappings.match.mockResolvedValue([mapping()])
    const { user } = renderWithProviders(<ImportPage />)

    await uploadCsv(user)

    expect(await screen.findByText(t('import.mappingApplied', { name: 'Nubank' }))).toBeInTheDocument()
    expect(api.mappings.match).toHaveBeenCalledWith(NUBANK_HEADERS)
    await waitFor(() => expect(api.previewImport).toHaveBeenCalledTimes(2))
    expect(lastPreviewOptions()).toEqual({
      date_format: 'DD/MM/YYYY',
      flip_amount: true,
      column_mapping: NUBANK_COLUMNS,
    })
    expect(accountOption().selected).toBe(true)
  })

  it('applies the mapping without preselecting an account that is no longer valid', async () => {
    const stale = mapping({ account_id: 'deleted-account' })
    api.mappings.list.mockResolvedValue([stale])
    api.mappings.match.mockResolvedValue([stale])
    const { user } = renderWithProviders(<ImportPage />)

    await uploadCsv(user)

    expect(await screen.findByText(t('import.mappingApplied', { name: 'Nubank' }))).toBeInTheDocument()
    expect(accountOption().selected).toBe(false)
    expect(screen.getByRole('option', { name: t('import.selectAccount') }) as HTMLOptionElement).toHaveProperty('selected', true)
  })

  it('applies nothing when no mapping matches, and lets the user pick a saved one', async () => {
    api.mappings.list.mockResolvedValue([mapping({ name: 'Other layout', headers: ['A', 'B'] })])
    const { user } = renderWithProviders(<ImportPage />)

    await uploadCsv(user)

    await waitFor(() => expect(api.mappings.match).toHaveBeenCalled())
    expect(screen.queryByText(/Mapping applied/)).not.toBeInTheDocument()
    expect(api.previewImport).toHaveBeenCalledTimes(1)

    const picker = await screen.findByRole('combobox', { name: t('import.mappingPick') })
    await user.selectOptions(picker, 'map-1')

    expect(await screen.findByText(t('import.mappingApplied', { name: 'Other layout' }))).toBeInTheDocument()
    await waitFor(() => expect(lastPreviewOptions()).toMatchObject({ column_mapping: NUBANK_COLUMNS }))
  })

  it('switches to another saved mapping and removes the applied one', async () => {
    const first = mapping()
    const second = mapping({
      id: 'map-2',
      name: 'Nubank (split)',
      account_id: null,
      column_mapping: { date: 'Data', description: 'Descrição' },
      options: { date_format: null, flip_amount: false, inflow_column: null, outflow_column: null },
    })
    api.mappings.list.mockResolvedValue([first, second])
    api.mappings.match.mockResolvedValue([first, second])
    const { user } = renderWithProviders(<ImportPage />)
    await uploadCsv(user)
    await screen.findByText(t('import.mappingApplied', { name: 'Nubank' }))

    await user.selectOptions(screen.getByRole('combobox', { name: t('import.mappingSwitch') }), 'map-2')

    expect(await screen.findByText(t('import.mappingApplied', { name: 'Nubank (split)' }))).toBeInTheDocument()
    await waitFor(() => expect(lastPreviewOptions()).toEqual({ column_mapping: { date: 'Data', description: 'Descrição' } }))

    await user.click(screen.getByRole('button', { name: t('import.mappingRemove') }))

    await waitFor(() => expect(screen.queryByText(/Mapping applied/)).not.toBeInTheDocument())
    await waitFor(() => expect(lastPreviewOptions()).toEqual({}))
  })

  it('offers Save mapping only once a mapping is configured and sends the current setup', async () => {
    api.mappings.create.mockResolvedValue(mapping({ name: 'My bank' }))
    const { user } = renderWithProviders(<ImportPage />)
    await uploadCsv(user)
    expect(screen.queryByRole('button', { name: t('import.mappingSave') })).not.toBeInTheDocument()

    await user.selectOptions(screen.getByRole('option', { name: /Nubank Conta/ }).closest('select')!, 'acc-1')
    await user.selectOptions(columnSelect('import.mapDate'), 'Data')
    await user.click(await screen.findByRole('button', { name: t('import.mappingSave') }))
    await user.type(screen.getByLabelText(t('import.mappingName')), 'My bank')
    await user.click(screen.getByRole('button', { name: t('common.save') }))

    await waitFor(() => expect(api.mappings.create).toHaveBeenCalledTimes(1))
    expect(api.mappings.create).toHaveBeenCalledWith({
      name: 'My bank',
      account_id: 'acc-1',
      headers: NUBANK_HEADERS,
      column_mapping: { date: 'Data' },
      options: { date_format: null, flip_amount: false, inflow_column: null, outflow_column: null },
    })
    expect(await screen.findByText(t('import.mappingApplied', { name: 'My bank' }))).toBeInTheDocument()
  })

  it('shows the duplicate-name message inline when the save is refused with 409', async () => {
    api.mappings.create.mockRejectedValue({ response: { status: 409, data: { detail: 'exists' } } })
    const { user } = renderWithProviders(<ImportPage />)
    await uploadCsv(user)

    await user.selectOptions(columnSelect('import.mapDate'), 'Data')
    await user.click(await screen.findByRole('button', { name: t('import.mappingSave') }))
    await user.type(screen.getByLabelText(t('import.mappingName')), 'Nubank')
    await user.click(screen.getByRole('button', { name: t('common.save') }))

    expect(await screen.findByText(t('import.mappingNameDuplicate'))).toBeInTheDocument()
    expect(screen.queryByText(/Mapping applied/)).not.toBeInTheDocument()
  })

  it('marks the applied mapping as used after a successful import', async () => {
    api.mappings.list.mockResolvedValue([mapping()])
    api.mappings.match.mockResolvedValue([mapping()])
    const { user } = renderWithProviders(<ImportPage />)
    await uploadCsv(user)
    await screen.findByText(t('import.mappingApplied', { name: 'Nubank' }))
    await waitFor(() => expect(accountOption().selected).toBe(true))

    await user.click(screen.getByRole('button', { name: t('import.importButton', { count: 1 }) }))

    await waitFor(() => expect(api.importTransactions).toHaveBeenCalled())
    await waitFor(() => expect(api.mappings.touch).toHaveBeenCalledWith('map-1'))
  })
})
