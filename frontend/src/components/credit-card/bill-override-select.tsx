import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useDateLocale } from '@/hooks/use-display-locale'
import { creditCardBills } from '@/lib/api'
import { monthLabel } from '@/lib/month-utils'

// Radix Select items cannot carry an empty value; this one stands for "no override".
const AUTO = '__auto__'

type Props = {
  accountId: string
  /** The override as stored: a bill's due date (YYYY-MM-DD), or '' for automatic. */
  value: string
  onChange: (value: string) => void
}

function formatDate(iso: string, dateLocale: string) {
  return new Date(iso + 'T00:00:00').toLocaleDateString(dateLocale)
}

/** Pick the bill a card transaction belongs to. Saves the bill's nominal due date
 * as `effective_bill_date`, which the backend matches to that bill (BIMP AC 4). */
export function BillOverrideSelect({ accountId, value, onChange }: Props) {
  const { t } = useTranslation()
  const dateLocale = useDateLocale()
  const { data: bills = [] } = useQuery({
    queryKey: ['credit-card-bills', 'list', { accountId }],
    queryFn: () => creditCardBills.list({ accountId }),
    enabled: !!accountId,
  })

  // An override written as the effective due date still names its bill.
  const matched = value
    ? bills.find((b) => b.due_date === value || b.effective_due_date === value)
    : undefined
  const selected = !value ? AUTO : (matched?.due_date ?? value)

  return (
    <Select value={selected} onValueChange={(next) => onChange(next === AUTO ? '' : next)}>
      <SelectTrigger className="w-full sm:w-auto sm:min-w-[260px]" aria-label={t('bills.override.label')}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={AUTO}>{t('bills.override.auto')}</SelectItem>
        {bills.map((b) => {
          const month = (b.reference_month ?? b.due_date).slice(0, 7)
          return (
            <SelectItem key={b.id} value={b.due_date}>
              <span className="capitalize">{monthLabel(month, dateLocale)}</span>
              {' · '}
              {t('bills.link.dueOn', { date: formatDate(b.effective_due_date ?? b.due_date, dateLocale) })}
            </SelectItem>
          )
        })}
        {value && !matched && (
          <SelectItem value={value}>{t('bills.override.unknown', { date: formatDate(value, dateLocale) })}</SelectItem>
        )}
      </SelectContent>
    </Select>
  )
}
