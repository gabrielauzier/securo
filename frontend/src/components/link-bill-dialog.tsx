import { useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { AlertTriangle, ArrowLeft } from 'lucide-react'

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
import { getAccountName } from '@/lib/account-utils'
import { creditCardBills, transactions as transactionsApi } from '@/lib/api'
import { extractApiError } from '@/lib/api-errors'
import { formatCurrency } from '@/lib/format'
import { invalidateBillQueries } from '@/lib/invalidate-queries'
import { monthLabel } from '@/lib/month-utils'
import type { Account, BillCandidate, Transaction } from '@/types'

type Props = {
  open: boolean
  onClose: () => void
  /** The debit to link as a bill payment. */
  transaction: Transaction | null
  accounts: Account[]
}

type Formatters = { t: ReturnType<typeof useTranslation>['t']; locale: string; dateLocale: string }

function formatDate(iso: string, dateLocale: string) {
  return new Date(iso + 'T00:00:00').toLocaleDateString(dateLocale)
}

function CandidateDetails({ candidate, t, locale, dateLocale }: { candidate: BillCandidate } & Formatters) {
  return (
    <>
      <div className="flex min-w-0 items-center gap-2">
        <p className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">{candidate.account_name}</p>
        <span className="shrink-0 rounded-full border border-border bg-muted/50 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
          {t(`bills.reason.${candidate.reason}`, candidate.reason)}
        </span>
      </div>
      <p className="text-xs capitalize text-muted-foreground">
        {monthLabel(candidate.reference_month.slice(0, 7), dateLocale)}
      </p>
      <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted-foreground tabular-nums">
        <span>{t('bills.link.dueOn', { date: formatDate(candidate.effective_due_date, dateLocale) })}</span>
        <span>{t('bills.link.target', { amount: formatCurrency(candidate.target_amount, candidate.currency, locale) })}</span>
        <span className="font-medium text-foreground">
          {t('bills.link.remaining', { amount: formatCurrency(candidate.remaining_amount, candidate.currency, locale) })}
        </span>
      </p>
    </>
  )
}

function CandidateList({
  label,
  items,
  onPick,
  ...formatters
}: { label: string; items: BillCandidate[]; onPick: (c: BillCandidate) => void } & Formatters) {
  if (items.length === 0) return null
  const id = `bill-list-${label.replace(/\s+/g, '-').toLowerCase()}`
  return (
    <div>
      <p id={id} className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <ul aria-labelledby={id} className="space-y-1.5">
        {items.map((c) => (
          <li key={c.bill_id}>
            <button
              type="button"
              onClick={() => onPick(c)}
              className="w-full min-w-0 rounded-lg border border-border bg-card p-3 text-left transition-colors hover:border-primary/40 hover:bg-muted/50"
            >
              <CandidateDetails candidate={c} {...formatters} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** "Vincular a fatura": pick the bill a debit pays (BMATCH AC 8), confirm, then
 *  offer the card counterpart when the API reports `needs_counterpart`. */
export function LinkBillDialog({ open, onClose, transaction, accounts }: Props) {
  const { t } = useTranslation()
  const locale = useDisplayLocale()
  const dateLocale = useDateLocale()
  const queryClient = useQueryClient()

  const [picked, setPicked] = useState<BillCandidate | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [counterpartFor, setCounterpartFor] = useState<BillCandidate | null>(null)

  // Reset the steps when the dialog reopens or targets another transaction.
  const sessionKey = `${open ? '1' : '0'}-${transaction?.id ?? ''}`
  const [prevSessionKey, setPrevSessionKey] = useState(sessionKey)
  if (sessionKey !== prevSessionKey) {
    setPrevSessionKey(sessionKey)
    setPicked(null)
    setError(null)
    setCounterpartFor(null)
  }

  const { data: candidates, isLoading } = useQuery({
    queryKey: ['bill-payment-candidates', transaction?.id],
    queryFn: () => creditCardBills.paymentCandidates(transaction!.id),
    enabled: open && !!transaction,
  })

  const [inWindow, others] = useMemo(() => {
    const sorted = [...(candidates ?? [])].sort((a, b) => a.rank - b.rank)
    return [sorted.filter((c) => c.kind !== 'other'), sorted.filter((c) => c.kind === 'other')]
  }, [candidates])

  const linkMutation = useMutation({
    mutationFn: (candidate: BillCandidate) => creditCardBills.linkPayment(candidate.bill_id, transaction!.id),
    onSuccess: (result, candidate) => {
      invalidateBillQueries(queryClient)
      toast.success(t('bills.link.success'))
      if (result.needs_counterpart) {
        setCounterpartFor(candidate)
      } else {
        onClose()
      }
    },
    onError: (err) => {
      const status = (err as { response?: { status?: number } }).response?.status
      setError(
        status === 409
          ? t('bills.link.alreadyLinked')
          : t('bills.link.notEligible', { detail: extractApiError(err, t('common.error')) }),
      )
    },
  })

  const counterpartMutation = useMutation({
    mutationFn: (candidate: BillCandidate) =>
      transactionsApi.createTransferCounterpart(transaction!.id, candidate.account_id),
    onSuccess: () => {
      invalidateBillQueries(queryClient)
      queryClient.invalidateQueries({ queryKey: ['transfer-candidates'] })
      toast.success(t('bills.link.counterpartSuccess'))
      onClose()
    },
    onError: (err) => setError(extractApiError(err, t('common.error'))),
  })

  if (!open || !transaction) return null

  const formatters = { t, locale, dateLocale }
  const account = accounts.find((a) => a.id === transaction.account_id)
  const busy = linkMutation.isPending || counterpartMutation.isPending

  const errorAlert = error && (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300"
    >
      <AlertTriangle size={14} className="mt-0.5 shrink-0" />
      <span>{error}</span>
    </div>
  )

  let title = t('bills.link.title')
  let body: ReactNode
  let footer: ReactNode

  if (counterpartFor) {
    title = t('bills.link.counterpartTitle')
    body = (
      <>
        <DialogDescription>
          {t('bills.link.counterpartDescription', { card: counterpartFor.account_name })}
        </DialogDescription>
        {errorAlert}
      </>
    )
    footer = (
      <>
        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
          {t('bills.link.counterpartSkip')}
        </Button>
        <Button type="button" onClick={() => counterpartMutation.mutate(counterpartFor)} disabled={busy}>
          {busy ? t('common.loading') : t('bills.link.counterpartCreate')}
        </Button>
      </>
    )
  } else if (picked) {
    title = t('bills.link.confirmTitle')
    body = (
      <>
        <DialogDescription>{t('bills.link.description')}</DialogDescription>
        <div className="rounded-lg border border-border bg-muted/30 p-3">
          <CandidateDetails candidate={picked} {...formatters} />
        </div>
        {errorAlert}
      </>
    )
    footer = (
      <>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setPicked(null)
            setError(null)
          }}
          disabled={busy}
          className="mr-auto"
        >
          <ArrowLeft size={14} className="mr-1" />
          {t('bills.link.back')}
        </Button>
        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
          {t('common.cancel')}
        </Button>
        <Button type="button" onClick={() => linkMutation.mutate(picked)} disabled={busy}>
          {busy ? t('common.loading') : t('bills.link.confirm')}
        </Button>
      </>
    )
  } else {
    body = (
      <>
        <DialogDescription>{t('bills.link.description')}</DialogDescription>
        <div className="min-w-0 rounded-lg border border-border bg-muted/30 p-3">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            {t('bills.link.payment')}
          </p>
          <p className="truncate text-sm font-semibold text-foreground" title={transaction.description}>
            {transaction.description}
          </p>
          <p className="truncate text-xs text-muted-foreground">
            {account ? getAccountName(account) : '—'} · {formatDate(transaction.date, dateLocale)}
          </p>
          <p className="mt-1 text-sm font-bold tabular-nums text-rose-500">
            −{formatCurrency(Math.abs(Number(transaction.amount)), transaction.currency, locale)}
          </p>
        </div>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : inWindow.length + others.length === 0 ? (
          <p className="py-4 text-center text-xs italic text-muted-foreground">{t('bills.link.empty')}</p>
        ) : (
          <>
            <CandidateList label={t('bills.link.candidatesHeader')} items={inWindow} onPick={setPicked} {...formatters} />
            <CandidateList label={t('bills.link.otherHeader')} items={others} onPick={setPicked} {...formatters} />
          </>
        )}
      </>
    )
    footer = (
      <Button type="button" variant="outline" onClick={onClose}>
        {t('common.cancel')}
      </Button>
    )
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden p-4 sm:max-w-xl sm:p-6">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="min-h-0 min-w-0 space-y-4 overflow-y-auto overscroll-contain pr-1">{body}</div>
        <DialogFooter className="shrink-0 gap-2 sm:gap-2">{footer}</DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
