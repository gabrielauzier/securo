import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { MonthStepper } from '@/components/month-stepper'
import { Button } from '@/components/ui/button'
import { DatePickerInput } from '@/components/ui/date-picker-input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useDateLocale } from '@/hooks/use-display-locale'
import { creditCardBills } from '@/lib/api'
import { extractApiError } from '@/lib/api-errors'
import { invalidateBillQueries } from '@/lib/invalidate-queries'
import type { Account, CreditCardBill, CreditCardBillUpdate } from '@/types'

type Props = {
  open: boolean
  onClose: () => void
  account: Account
  /** The bill to edit; omitted to create a manual bill. */
  bill?: CreditCardBill | null
  /** Reference month (`YYYY-MM`) a new bill starts on. */
  defaultMonth: string
}

function iso(year: number, monthIndex: number, day: number): string {
  const last = new Date(year, monthIndex + 1, 0).getDate()
  const d = new Date(year, monthIndex, Math.min(day, last))
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Close and nominal due dates of a reference month from the card's cycle days:
 * the due day clamped to the month, and the last close day strictly before it. */
function suggestedDates(month: string, closeDay: number | null, dueDay: number | null) {
  if (!closeDay || !dueDay) return { close: '', due: '' }
  const [y, m] = month.split('-').map(Number)
  const due = iso(y, m - 1, dueDay)
  const sameMonthClose = iso(y, m - 1, closeDay)
  const close = sameMonthClose < due ? sameMonthClose : iso(y, m - 2, closeDay)
  return { close, due }
}

/** Create a manual bill, or edit a bill's declared total and (except provider bills) dates. */
export function BillFormDialog({ open, onClose, account, bill, defaultMonth }: Props) {
  const { t } = useTranslation()
  const dateLocale = useDateLocale()
  const queryClient = useQueryClient()
  const isEdit = !!bill
  const canEditDates = !bill || bill.source !== 'provider'

  const initialMonth = bill?.reference_month?.slice(0, 7) ?? defaultMonth
  const initialDates = bill
    ? { close: bill.close_date ?? '', due: bill.due_date }
    : suggestedDates(initialMonth, account.statement_close_day, account.payment_due_day)

  const [month, setMonth] = useState(initialMonth)
  const [closeDate, setCloseDate] = useState(initialDates.close)
  const [dueDate, setDueDate] = useState(initialDates.due)
  const [declared, setDeclared] = useState(
    bill?.declared_total != null ? String(bill.declared_total) : '',
  )
  const [error, setError] = useState<string | null>(null)

  const changeMonth = (next: string) => {
    setMonth(next)
    const suggested = suggestedDates(next, account.statement_close_day, account.payment_due_day)
    if (suggested.due) {
      setCloseDate(suggested.close)
      setDueDate(suggested.due)
    }
  }

  const mutation = useMutation({
    mutationFn: (declaredTotal: number | null) => {
      if (bill) {
        const changes: CreditCardBillUpdate = { declared_total: declaredTotal }
        if (canEditDates) {
          changes.reference_month = `${month}-01`
          changes.close_date = closeDate
          changes.due_date = dueDate
        }
        return creditCardBills.update(bill.id, changes)
      }
      return creditCardBills.create({
        account_id: account.id,
        reference_month: `${month}-01`,
        close_date: closeDate,
        due_date: dueDate,
        declared_total: declaredTotal,
      })
    },
    onSuccess: () => {
      invalidateBillQueries(queryClient)
      toast.success(isEdit ? t('bills.manage.updated') : t('bills.manage.created'))
      onClose()
    },
    onError: (err) => {
      const status = (err as { response?: { status?: number } }).response?.status
      if (status === 409) {
        setError(t('bills.manage.duplicate'))
      } else {
        setError(extractApiError(err, t('common.error')))
      }
    },
  })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const trimmed = declared.trim().replace(',', '.')
    const declaredTotal = trimmed === '' ? null : Number(trimmed)
    if (declaredTotal != null && (Number.isNaN(declaredTotal) || declaredTotal < 0)) {
      setError(t('bills.manage.negativeTotal'))
      return
    }
    if (canEditDates && (!closeDate || !dueDate)) {
      setError(t('bills.manage.datesRequired'))
      return
    }
    mutation.mutate(declaredTotal)
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next && !mutation.isPending) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? t('bills.manage.editTitle') : t('bills.manage.createTitle')}</DialogTitle>
          <DialogDescription>
            {canEditDates ? t('bills.manage.formDescription') : t('bills.manage.providerDatesHint')}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          {canEditDates && (
            <>
              <div className="space-y-2">
                <Label>{t('bills.manage.referenceMonth')}</Label>
                <MonthStepper
                  value={month}
                  onChange={changeMonth}
                  locale={dateLocale}
                  prevLabel={t('bills.manage.previousMonth')}
                  nextLabel={t('bills.manage.nextMonth')}
                />
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>{t('bills.manage.closeDate')}</Label>
                  <DatePickerInput value={closeDate} onChange={setCloseDate} className="w-full" />
                </div>
                <div className="space-y-2">
                  <Label>{t('bills.manage.dueDate')}</Label>
                  <DatePickerInput value={dueDate} onChange={setDueDate} className="w-full" />
                </div>
              </div>
            </>
          )}
          <div className="space-y-2">
            <Label htmlFor="bill-declared-total">{t('bills.manage.declaredTotal')}</Label>
            <Input
              id="bill-declared-total"
              type="number"
              step="0.01"
              inputMode="decimal"
              value={declared}
              onChange={(e) => setDeclared(e.target.value)}
              placeholder="0.00"
            />
            <p className="text-xs text-muted-foreground">{t('bills.manage.declaredTotalHint')}</p>
          </div>
          {error && (
            <p role="alert" className="text-sm text-rose-600 dark:text-rose-400">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={mutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? t('common.loading') : t('common.save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
