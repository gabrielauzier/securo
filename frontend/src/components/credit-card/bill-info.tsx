import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { BillStatusBadge } from '@/components/credit-card/bill-status-badge'
import { useDateLocale } from '@/hooks/use-display-locale'
import { creditCardBills } from '@/lib/api'
import { monthLabel } from '@/lib/month-utils'

function formatDate(iso: string, dateLocale: string) {
  return new Date(iso + 'T00:00:00').toLocaleDateString(dateLocale)
}

type Props = {
  billId: string
  /** Display name of the bill's card. */
  cardName: string
}

/** Read-only: the bill a card transaction belongs to and whether it is settled
 *  (ADJ AC 5). Moving the row to another bill stays with BillOverrideSelect. */
export function BillInfo({ billId, cardName }: Props) {
  const { t } = useTranslation()
  const dateLocale = useDateLocale()
  const { data: bill } = useQuery({
    queryKey: ['credit-card-bills', 'detail', billId],
    queryFn: () => creditCardBills.get(billId),
  })
  if (!bill) return null

  const month = (bill.reference_month ?? bill.due_date).slice(0, 7)
  return (
    <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm" data-testid="bill-info">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">{t('bills.infoTitle')}</span>
        <BillStatusBadge status={bill.status} dueDate={bill.due_date} effectiveDueDate={bill.effective_due_date} />
      </div>
      <p className="font-medium text-foreground">
        {t('bills.infoBill', { card: cardName, month: monthLabel(month, dateLocale) })}
      </p>
      <p className="text-xs text-muted-foreground">
        {bill.settled_on
          ? t('bills.infoSettledOn', { date: formatDate(bill.settled_on, dateLocale) })
          : t('bills.infoNotSettled', {
              date: formatDate(bill.effective_due_date ?? bill.due_date, dateLocale),
            })}
      </p>
    </div>
  )
}
