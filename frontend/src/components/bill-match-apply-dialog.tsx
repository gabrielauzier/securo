import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { AlertTriangle, ArrowRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useDateLocale, useDisplayLocale } from '@/hooks/use-display-locale'
import { creditCardBills } from '@/lib/api'
import { extractApiError } from '@/lib/api-errors'
import { formatCurrency } from '@/lib/format'
import { invalidateBillQueries } from '@/lib/invalidate-queries'
import { monthLabel } from '@/lib/month-utils'
import type { BillMatchFailure, BillMatchPair, BillMatchProposal } from '@/types'

const pairKey = (p: BillMatchPair) => `${p.transaction_id}:${p.bill_id}`

function formatDate(iso: string, dateLocale: string) {
  return new Date(iso + 'T00:00:00').toLocaleDateString(dateLocale)
}

/**
 * "Aplicar match de pagamentos": the proposed payment-bill links, one checkbox
 * each. Opening only reads; only the checked pairs are linked on apply
 * (BMATCH AC 10, 11).
 */
export function BillMatchApplyDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const locale = useDisplayLocale()
  const dateLocale = useDateLocale()
  const queryClient = useQueryClient()
  // Held as the unchecked keys so a freshly loaded preview is all checked.
  const [deselected, setDeselected] = useState<Set<string>>(new Set())
  const [failed, setFailed] = useState<BillMatchFailure[] | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['bill-match-preview'],
    queryFn: creditCardBills.previewMatches,
    enabled: open,
    gcTime: 0,
    staleTime: 0,
  })

  const close = () => {
    setDeselected(new Set())
    setFailed(null)
    onClose()
  }

  const proposals = data ?? []
  const chosen: BillMatchPair[] = proposals
    .filter((p) => !deselected.has(pairKey(p)))
    .map((p) => ({ transaction_id: p.transaction_id, bill_id: p.bill_id }))

  const apply = useMutation({
    mutationFn: (pairs: BillMatchPair[]) => creditCardBills.applyMatches(pairs),
    onSuccess: (result) => {
      invalidateBillQueries(queryClient)
      toast.success(t('bills.apply.success', { count: result.linked }))
      if (result.failed.length > 0) setFailed(result.failed)
      else close()
    },
    onError: (error) => toast.error(extractApiError(error, t('common.error'))),
  })

  const toggle = (p: BillMatchProposal) => {
    const next = new Set(deselected)
    const key = pairKey(p)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setDeselected(next)
  }

  const describe = (pair: BillMatchPair) => proposals.find((p) => pairKey(p) === pairKey(pair))

  let body
  if (isLoading) {
    body = <Skeleton className="h-32 w-full" />
  } else if (failed) {
    body = (
      <div className="space-y-2">
        <p id="bill-match-failed" className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('bills.apply.failedTitle')}
        </p>
        <ul aria-labelledby="bill-match-failed" className="space-y-1.5">
          {failed.map((f) => {
            const p = describe(f)
            return (
              <li
                key={pairKey(f)}
                className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300"
              >
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <div className="min-w-0">
                  {p && <p className="truncate font-semibold">{p.payment_description}</p>}
                  <p>{f.reason}</p>
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    )
  } else if (proposals.length === 0) {
    body = <p className="py-6 text-center text-sm text-muted-foreground">{t('bills.apply.empty')}</p>
  } else {
    body = (
      <ul className="max-h-[60vh] space-y-1.5 overflow-y-auto pr-1">
        {proposals.map((p) => {
          const month = monthLabel(p.reference_month.slice(0, 7), dateLocale)
          return (
            <li key={pairKey(p)}>
              <label className="flex min-w-0 cursor-pointer items-start gap-3 rounded-lg border border-border bg-card p-3 hover:bg-muted/50">
                <input
                  type="checkbox"
                  checked={!deselected.has(pairKey(p))}
                  onChange={() => toggle(p)}
                  aria-label={t('bills.apply.selectPair', {
                    payment: p.payment_description,
                    card: p.bill_account_name,
                    month,
                  })}
                  className="mt-1 h-4 w-4 shrink-0 rounded border-border accent-primary"
                />
                <div className="grid min-w-0 flex-1 grid-cols-1 gap-2 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground" title={p.payment_description}>
                      {p.payment_description}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {p.payment_account_name} · {formatDate(p.payment_date, dateLocale)}
                    </p>
                    <p className="text-sm font-semibold tabular-nums text-rose-500">
                      −{formatCurrency(Math.abs(Number(p.payment_amount)), p.currency, locale)}
                    </p>
                  </div>
                  <ArrowRight size={16} className="hidden text-muted-foreground sm:block" />
                  <div className="min-w-0">
                    <div className="flex min-w-0 items-center gap-2">
                      <p className="min-w-0 truncate text-sm font-medium text-foreground">{p.bill_account_name}</p>
                      <span className="shrink-0 rounded-full border border-border bg-muted/50 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                        {t(`bills.apply.kind.${p.kind}`, p.kind)}
                      </span>
                    </div>
                    <p className="truncate text-xs capitalize text-muted-foreground">{month}</p>
                    <p className="text-xs text-muted-foreground tabular-nums">
                      {t('bills.link.dueOn', { date: formatDate(p.effective_due_date, dateLocale) })} ·{' '}
                      {t('bills.link.remaining', { amount: formatCurrency(p.remaining_amount, p.currency, locale) })}
                    </p>
                  </div>
                </div>
              </label>
            </li>
          )
        })}
      </ul>
    )
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) close() }}>
      <DialogContent className="sm:max-w-3xl [&>*]:min-w-0">
        <DialogHeader>
          <DialogTitle>{t('bills.apply.action')}</DialogTitle>
          <DialogDescription>{t('bills.apply.description')}</DialogDescription>
        </DialogHeader>
        {body}
        <DialogFooter>
          {failed ? (
            <Button type="button" onClick={close}>{t('common.close')}</Button>
          ) : (
            <>
              <Button type="button" variant="outline" onClick={close} disabled={apply.isPending}>
                {t('common.cancel')}
              </Button>
              <Button
                type="button"
                onClick={() => apply.mutate(chosen)}
                disabled={chosen.length === 0 || apply.isPending}
              >
                {t('bills.apply.confirm')}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
