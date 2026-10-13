import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQueries, useQuery } from '@tanstack/react-query'
import { AlertTriangle, CreditCard } from 'lucide-react'

import { BillStatusBadge } from '@/components/credit-card/bill-status-badge'
import { BillSummaryCard } from '@/components/credit-card/bill-summary-card'
import { MonthStepper } from '@/components/month-stepper'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/contexts/auth-context'
import { useDateLocale, useDisplayLocale } from '@/hooks/use-display-locale'
import { usePrivacyMode } from '@/hooks/use-privacy-mode'
import { getAccountName, sortAccountsByDisplayName } from '@/lib/account-utils'
import { accounts as accountsApi, creditCardBills, transactions as transactionsApi } from '@/lib/api'
import { localDateString } from '@/lib/date-utils'
import { formatCurrency } from '@/lib/format'
import { currentMonth } from '@/lib/month-utils'
import type { CreditCardBill } from '@/types'

const ALL = '__all__'

function billMonth(bill: CreditCardBill): string {
  return (bill.reference_month ?? bill.due_date).slice(0, 7)
}

function dueOf(bill: CreditCardBill): string {
  return bill.effective_due_date ?? bill.due_date
}

/** The reference month of the next effective due date among unpaid bills,
 * or the current month when nothing is left to pay (BVIEW AC 2). */
function defaultMonth(bills: CreditCardBill[], today: string): string {
  const next = bills
    .filter((b) => b.status !== 'paid' && dueOf(b) >= today)
    .sort((a, b) => dueOf(a).localeCompare(dueOf(b)))[0]
  return next ? billMonth(next) : currentMonth()
}

export default function CreditCardsPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const locale = useDisplayLocale()
  const dateLocale = useDateLocale()
  const { mask } = usePrivacyMode()
  const [searchParams, setSearchParams] = useSearchParams()
  const [pickedMonth, setPickedMonth] = useState<string | null>(null)

  const { data: accountList, isLoading: accountsLoading } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })
  const cards = useMemo(
    () => sortAccountsByDisplayName((accountList ?? []).filter((a) => a.type === 'credit_card')),
    [accountList],
  )
  const requested = searchParams.get('account')
  const selected = cards.find((c) => c.id === requested) ?? null
  const scopeCards = selected ? [selected] : cards
  const names = useMemo(() => new Map(cards.map((c) => [c.id, getAccountName(c)])), [cards])
  const cardName = (id: string) => names.get(id) ?? ''

  const { data: bills = [], isLoading: billsLoading } = useQuery({
    queryKey: ['credit-card-bills', 'list', { accountId: selected?.id ?? null }],
    queryFn: () => creditCardBills.list({ accountId: selected?.id }),
    enabled: cards.length > 0,
  })
  const month = pickedMonth ?? defaultMonth(bills, localDateString())
  const monthBills = useMemo(
    () =>
      bills
        .filter((b) => billMonth(b) === month)
        .sort(
          (a, b) =>
            dueOf(a).localeCompare(dueOf(b)) ||
            (names.get(a.account_id) ?? '').localeCompare(names.get(b.account_id) ?? ''),
        ),
    [bills, month, names],
  )

  const txQueries = useQueries({
    queries: monthBills.map((b) => ({
      queryKey: ['transactions', { account_id: b.account_id, bill_id: b.id, limit: 500 }],
      queryFn: () => transactionsApi.list({ account_id: b.account_id, bill_id: b.id, limit: 500 }),
    })),
  })
  const monthTransactions = txQueries
    .flatMap((q) => q.data?.items ?? [])
    .sort((a, b) => b.date.localeCompare(a.date))
  const txLoading = txQueries.some((q) => q.isLoading)

  const currency = scopeCards[0]?.currency ?? user?.preferences?.currency_display ?? 'BRL'
  const money = (n: number, cur = currency) => mask(formatCurrency(n, cur, locale))
  const formatDate = (iso: string) => new Date(iso + 'T00:00:00').toLocaleDateString(dateLocale)
  const showCardColumn = !selected

  const pickCard = (value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value === ALL) next.delete('account')
    else next.set('account', value)
    setSearchParams(next)
  }

  const header = <PageHeader section={t('nav.accounts')} title={t('bills.page.title')} />

  if (accountsLoading) {
    return (
      <div>
        {header}
        <Skeleton className="h-32" />
      </div>
    )
  }

  if (cards.length === 0) {
    return (
      <div>
        {header}
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border bg-card px-4 py-10 text-center">
          <CreditCard className="h-8 w-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">{t('bills.page.empty')}</p>
          <Button asChild size="sm">
            <Link to="/accounts">{t('bills.page.createCard')}</Link>
          </Button>
        </div>
      </div>
    )
  }

  const unconfigured = scopeCards.filter((c) => !c.statement_close_day || !c.payment_due_day)

  return (
    <div className="min-w-0 space-y-6">
      {header}

      <div className="flex flex-wrap items-center gap-2">
        <Select value={selected?.id ?? ALL} onValueChange={pickCard}>
          <SelectTrigger className="w-full sm:w-64" aria-label={t('bills.page.card')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('bills.page.allCards')}</SelectItem>
            {cards.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {getAccountName(c)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <MonthStepper
          value={month}
          onChange={setPickedMonth}
          locale={dateLocale}
          prevLabel={t('bills.page.previousMonth')}
          nextLabel={t('bills.page.nextMonth')}
        />
      </div>

      {unconfigured.map((c) => (
        <div
          key={c.id}
          role="status"
          className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300"
        >
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span className="min-w-0 flex-1">{t('bills.page.configure', { card: getAccountName(c) })}</span>
          <Link to={`/accounts/${c.id}`} className="font-medium underline">
            {t('bills.page.configureAction')}
          </Link>
        </div>
      ))}

      <BillSummaryCard bills={monthBills} cards={scopeCards} currency={currency} />

      <section aria-labelledby="credit-cards-bills" className="rounded-xl border border-border bg-card p-3 shadow-sm sm:p-4">
        <h2 id="credit-cards-bills" className="mb-2 text-sm font-semibold text-foreground">
          {t('bills.page.billsTitle')}
        </h2>
        {billsLoading ? (
          <Skeleton className="h-16" />
        ) : monthBills.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('bills.page.noBills')}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('bills.page.card')}</TableHead>
                <TableHead>{t('bills.page.status')}</TableHead>
                <TableHead>{t('bills.manage.effectiveDueDate')}</TableHead>
                <TableHead className="text-right">{t('bills.manage.computedTotal')}</TableHead>
                <TableHead className="text-right">{t('bills.manage.declaredTotal')}</TableHead>
                <TableHead className="text-right">{t('bills.manage.difference')}</TableHead>
                <TableHead>{t('bills.manage.payments')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {monthBills.map((b) => {
                const difference = b.declared_total != null ? b.declared_total - b.computed_total : null
                return (
                  <TableRow key={b.id}>
                    <TableCell>
                      <Link to={`/accounts/${b.account_id}`} className="font-medium hover:underline">
                        {cardName(b.account_id)}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <BillStatusBadge status={b.status} dueDate={b.due_date} effectiveDueDate={b.effective_due_date} />
                    </TableCell>
                    <TableCell className="tabular-nums">{formatDate(dueOf(b))}</TableCell>
                    <TableCell className="text-right tabular-nums">{money(b.computed_total, b.currency)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {b.declared_total != null ? money(b.declared_total, b.currency) : '—'}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {difference != null ? money(difference, b.currency) : '—'}
                    </TableCell>
                    <TableCell>
                      {b.payments.length === 0 ? (
                        <span className="text-muted-foreground">—</span>
                      ) : (
                        <ul className="space-y-0.5">
                          {b.payments.map((p) => (
                            <li key={p.id}>
                              <Link to={`/accounts/${p.account_id}`} className="hover:underline">
                                {formatDate(p.date)} · {money(p.amount, p.currency)}
                              </Link>
                            </li>
                          ))}
                        </ul>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </section>

      <section aria-labelledby="credit-cards-transactions" className="rounded-xl border border-border bg-card p-3 shadow-sm sm:p-4">
        <h2 id="credit-cards-transactions" className="mb-2 text-sm font-semibold text-foreground">
          {t('bills.page.transactionsTitle')}
        </h2>
        {txLoading ? (
          <Skeleton className="h-16" />
        ) : monthTransactions.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('bills.page.noTransactions')}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('bills.page.date')}</TableHead>
                <TableHead>{t('bills.page.description')}</TableHead>
                <TableHead>{t('bills.page.category')}</TableHead>
                {showCardColumn && <TableHead>{t('bills.page.card')}</TableHead>}
                <TableHead className="text-right">{t('bills.page.amount')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {monthTransactions.map((tx) => (
                <TableRow key={tx.id}>
                  <TableCell className="tabular-nums">{formatDate(tx.date)}</TableCell>
                  <TableCell className="max-w-[16rem] truncate">{tx.description}</TableCell>
                  <TableCell className="text-muted-foreground">{tx.category?.name ?? '—'}</TableCell>
                  {showCardColumn && <TableCell>{tx.account_id ? cardName(tx.account_id) : ''}</TableCell>}
                  <TableCell
                    className={`text-right tabular-nums ${tx.type === 'credit' ? 'text-emerald-600' : 'text-foreground'}`}
                  >
                    {tx.type === 'credit' ? '+' : '−'}
                    {money(Math.abs(tx.amount), tx.currency)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  )
}
