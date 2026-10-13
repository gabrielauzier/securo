import type { MouseEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Check, CreditCard, HelpCircle, Unlink, X } from 'lucide-react'

import { useDateLocale } from '@/hooks/use-display-locale'
import { creditCardBills } from '@/lib/api'
import { extractApiError } from '@/lib/api-errors'
import { invalidateBillQueries } from '@/lib/invalidate-queries'
import { monthLabel } from '@/lib/month-utils'
import type { Transaction } from '@/types'

const PILL = 'inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded-full border shrink-0'
const ICON_BUTTON = 'inline-flex items-center justify-center rounded-full p-0.5 hover:bg-black/5 dark:hover:bg-white/10 disabled:opacity-50'

type Props = {
  tx: Transaction
  canWrite: boolean
  /** Opens "Vincular a fatura" for the suggested payment. */
  onConfirmSuggestion: (tx: Transaction) => void
}

/** Row marker for bill payments: the paid bill with an unlink action, or the
 *  "Possível pagamento de fatura" suggestion with confirm and dismiss. */
export function BillPaymentRowBadge({ tx, canWrite, onConfirmSuggestion }: Props) {
  const { t } = useTranslation()
  const dateLocale = useDateLocale()
  const queryClient = useQueryClient()

  const unlinkMutation = useMutation({
    mutationFn: () => creditCardBills.unlinkPayment(tx.id),
    onSuccess: () => {
      invalidateBillQueries(queryClient)
      toast.success(t('bills.row.unlinkSuccess'))
    },
    onError: (error) => toast.error(extractApiError(error)),
  })

  // A suggestion is any undismissed in-window candidate; dismissing the row
  // dismisses each of them so the indicator goes away (BMATCH AC 9).
  const dismissMutation = useMutation({
    mutationFn: async () => {
      const candidates = await creditCardBills.paymentCandidates(tx.id)
      for (const c of candidates.filter((c) => c.kind !== 'other')) {
        await creditCardBills.dismissSuggestion({ transaction_id: tx.id, bill_id: c.bill_id })
      }
    },
    onSuccess: () => {
      invalidateBillQueries(queryClient)
      toast.success(t('bills.row.dismissSuccess'))
    },
    onError: (error) => toast.error(extractApiError(error)),
  })

  const stop = (e: MouseEvent) => e.stopPropagation()

  if (tx.paid_bill) {
    return (
      <span
        onClick={stop}
        className={`${PILL} normal-case text-sky-700 bg-sky-50 border-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:border-sky-900`}
      >
        <CreditCard className="h-3 w-3" />
        {t('bills.row.paidBill', {
          card: tx.paid_bill.account_name,
          month: monthLabel(tx.paid_bill.reference_month.slice(0, 7), dateLocale),
        })}
        {canWrite && (
          <button
            type="button"
            aria-label={t('bills.row.unlink')}
            title={t('bills.row.unlink')}
            disabled={unlinkMutation.isPending}
            onClick={() => unlinkMutation.mutate()}
            className={ICON_BUTTON}
          >
            <Unlink className="h-3 w-3" />
          </button>
        )}
      </span>
    )
  }

  if (!tx.bill_payment_suggestion) return null

  return (
    <span
      onClick={stop}
      className={`${PILL} text-amber-700 bg-amber-50 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900`}
    >
      <HelpCircle className="h-3 w-3" />
      {t('bills.row.suggestion')}
      {canWrite && (
        <>
          <button
            type="button"
            aria-label={t('bills.row.confirm')}
            title={t('bills.row.confirm')}
            onClick={() => onConfirmSuggestion(tx)}
            className={ICON_BUTTON}
          >
            <Check className="h-3 w-3" />
          </button>
          <button
            type="button"
            aria-label={t('bills.row.dismiss')}
            title={t('bills.row.dismiss')}
            disabled={dismissMutation.isPending}
            onClick={() => dismissMutation.mutate()}
            className={ICON_BUTTON}
          >
            <X className="h-3 w-3" />
          </button>
        </>
      )}
    </span>
  )
}
