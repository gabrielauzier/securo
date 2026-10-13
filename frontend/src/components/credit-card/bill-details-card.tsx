import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { BillFormDialog } from '@/components/credit-card/bill-form-dialog'
import { BillStatusBadge } from '@/components/credit-card/bill-status-badge'
import { DeleteConfirmationDialog } from '@/components/delete-confirmation-dialog'
import { Button } from '@/components/ui/button'
import { useDateLocale, useDisplayLocale } from '@/hooks/use-display-locale'
import { usePrivacyMode } from '@/hooks/use-privacy-mode'
import { creditCardBills } from '@/lib/api'
import { extractApiError } from '@/lib/api-errors'
import { formatCurrency } from '@/lib/format'
import { invalidateBillQueries } from '@/lib/invalidate-queries'
import type { Account, CreditCardBill } from '@/types'

type Props = {
  account: Account
  /** The bill of the cycle on screen, or null when the cycle has none. */
  bill: CreditCardBill | null
  canWrite: boolean
  /** Reference month (`YYYY-MM`) offered when creating a bill. */
  defaultMonth: string
}

function formatDate(iso: string, dateLocale: string) {
  return new Date(iso + 'T00:00:00').toLocaleDateString(dateLocale)
}

function Figure({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="min-w-0">
      <p className="truncate text-[10px] font-medium text-muted-foreground sm:text-xs">{label}</p>
      <p className={`truncate text-sm font-semibold tabular-nums sm:text-base ${className ?? 'text-foreground'}`}>
        {value}
      </p>
    </div>
  )
}

/** The stored bill of a card cycle: status, due dates, totals, payments and the
 * actions to edit, delete or create one. Provider bills keep their dates and stay. */
export function BillDetailsCard({ account, bill, canWrite, defaultMonth }: Props) {
  const { t } = useTranslation()
  const locale = useDisplayLocale()
  const dateLocale = useDateLocale()
  const { mask } = usePrivacyMode()
  const queryClient = useQueryClient()
  const [formOpen, setFormOpen] = useState<'create' | 'edit' | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)

  const deleteMutation = useMutation({
    mutationFn: (id: string) => creditCardBills.delete(id),
    onSuccess: () => {
      invalidateBillQueries(queryClient)
      toast.success(t('bills.manage.deleted'))
      setDeleteOpen(false)
    },
    onError: (err) => toast.error(extractApiError(err, t('common.error'))),
  })

  const money = (value: number) => mask(formatCurrency(value, bill?.currency ?? account.currency, locale))
  const isProvider = bill?.source === 'provider'
  const payments = bill?.payments ?? []
  const rolled = !!bill?.effective_due_date && bill.effective_due_date !== bill.due_date
  const difference = bill?.declared_total != null ? bill.declared_total - bill.computed_total : null

  return (
    <section
      aria-label={t('bills.manage.title')}
      className="mb-6 rounded-xl border border-border bg-card p-4 shadow-sm sm:p-5"
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="text-sm font-semibold text-foreground">{t('bills.manage.title')}</h2>
          {bill && (
            <BillStatusBadge
              status={bill.status}
              dueDate={bill.due_date}
              effectiveDueDate={bill.effective_due_date}
            />
          )}
          {bill?.source && (
            <span className="text-[10px] font-medium text-muted-foreground sm:text-xs">
              {t(`bills.manage.source.${bill.source}`)}
            </span>
          )}
        </div>
        {canWrite && (
          <div className="flex flex-wrap items-center gap-1">
            {bill && (
              <Button variant="ghost" size="sm" onClick={() => setFormOpen('edit')}>
                <Pencil className="mr-1 h-3.5 w-3.5" />
                {t('bills.manage.edit')}
              </Button>
            )}
            {bill && !isProvider && (
              <Button variant="ghost" size="sm" onClick={() => setDeleteOpen(true)}>
                <Trash2 className="mr-1 h-3.5 w-3.5" />
                {t('bills.manage.delete')}
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={() => setFormOpen('create')}>
              <Plus className="mr-1 h-3.5 w-3.5" />
              {t('bills.manage.create')}
            </Button>
          </div>
        )}
      </div>

      {bill ? (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="min-w-0">
              <Figure
                label={t('bills.manage.effectiveDueDate')}
                value={formatDate(bill.effective_due_date ?? bill.due_date, dateLocale)}
              />
              {rolled && (
                <p className="truncate text-[10px] text-muted-foreground sm:text-xs">
                  {t('bills.manage.nominalDueDate', { date: formatDate(bill.due_date, dateLocale) })}
                </p>
              )}
            </div>
            <Figure label={t('bills.manage.computedTotal')} value={money(bill.computed_total ?? 0)} />
            <Figure
              label={t('bills.manage.declaredTotal')}
              value={bill.declared_total != null ? money(bill.declared_total) : '—'}
            />
            <Figure
              label={t('bills.manage.difference')}
              value={difference != null ? money(difference) : '—'}
              className={difference != null && Math.abs(difference) >= 0.005 ? 'text-amber-600' : undefined}
            />
            <Figure label={t('bills.manage.paid')} value={money(bill.paid_amount ?? 0)} className="text-emerald-600" />
            <Figure label={t('bills.manage.remaining')} value={money(bill.remaining_amount ?? 0)} />
            {(bill.overpaid_amount ?? 0) > 0 && (
              <Figure label={t('bills.manage.overpaid')} value={money(bill.overpaid_amount)} />
            )}
          </div>

          <div className="mt-4 border-t border-border pt-3">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              {t('bills.manage.payments')}
            </p>
            {payments.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('bills.manage.noPayments')}</p>
            ) : (
              <ul className="space-y-1">
                {payments.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 text-sm">
                    <Link
                      to={`/accounts/${p.account_id}`}
                      className="min-w-0 truncate text-foreground hover:underline"
                    >
                      {formatDate(p.date, dateLocale)} · {p.description}
                    </Link>
                    <span className="shrink-0 tabular-nums text-foreground">
                      {mask(formatCurrency(p.amount, p.currency, locale))}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      ) : (
        <p className="text-xs text-muted-foreground">{t('bills.manage.noBill')}</p>
      )}

      {formOpen && (
        <BillFormDialog
          open
          onClose={() => setFormOpen(null)}
          account={account}
          bill={formOpen === 'edit' ? bill : null}
          defaultMonth={defaultMonth}
        />
      )}
      {bill && !isProvider && (
        <DeleteConfirmationDialog
          open={deleteOpen}
          title={t('bills.manage.deleteTitle')}
          description={t('bills.manage.deleteDescription')}
          isPending={deleteMutation.isPending}
          onClose={() => setDeleteOpen(false)}
          onConfirm={() => deleteMutation.mutate(bill.id)}
        />
      )}
    </section>
  )
}
