import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useDateLocale } from '@/hooks/use-display-locale'
import { cn } from '@/lib/utils'
import type { CreditCardBillStatus } from '@/types'

const STATUS_CLASSES: Record<CreditCardBillStatus, string> = {
  paid: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300',
  open: 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-300',
  overdue: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300',
  partially_paid: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300',
  closed: 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-300',
}

type Props = {
  status: CreditCardBillStatus | null
  /** Nominal due date, YYYY-MM-DD. */
  dueDate: string
  /** Effective due date (next business day), YYYY-MM-DD. */
  effectiveDueDate: string | null
  className?: string
}

/** Bill status pill; explains a rolled due date with the original date and weekday. */
export function BillStatusBadge({ status, dueDate, effectiveDueDate, className }: Props) {
  const { t } = useTranslation()
  const dateLocale = useDateLocale()

  if (!status) return null

  const rolled = !!effectiveDueDate && effectiveDueDate !== dueDate
  const badge = (
    <Badge
      variant="outline"
      tabIndex={rolled ? 0 : undefined}
      className={cn(STATUS_CLASSES[status], className)}
    >
      {t(`bills.status.${status}`)}
    </Badge>
  )

  if (!rolled) return badge

  const nominal = new Date(dueDate + 'T00:00:00')
  return (
    <Tooltip>
      <TooltipTrigger asChild>{badge}</TooltipTrigger>
      <TooltipContent>
        {t('bills.originalDueDate', {
          date: nominal.toLocaleDateString(dateLocale),
          weekday: nominal.toLocaleDateString(dateLocale, { weekday: 'long' }),
        })}
      </TooltipContent>
    </Tooltip>
  )
}
