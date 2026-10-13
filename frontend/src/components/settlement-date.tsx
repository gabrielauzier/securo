import { useTranslation } from 'react-i18next'

import type { SettlementRowDates } from '@/lib/settlement-dates'

function formatDay(iso: string, dateLocale: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString(dateLocale)
}

/** "Paga em" / "Pagar até", the bill date, then "Lançada em <purchase date>". */
export function SettlementDate({ dates, dateLocale }: { dates: SettlementRowDates; dateLocale: string }) {
  const { t } = useTranslation()
  return (
    <span className="flex flex-col leading-tight">
      <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {dates.paid ? t('transactions.billPaidOn') : t('transactions.billPayBy')}
      </span>
      <span>{formatDay(dates.date, dateLocale)}</span>
      <span className="text-[11px] text-muted-foreground">
        {t('transactions.billPostedOn', { date: formatDay(dates.postedOn, dateLocale) })}
      </span>
    </span>
  )
}
