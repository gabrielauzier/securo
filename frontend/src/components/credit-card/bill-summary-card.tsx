import { useTranslation } from 'react-i18next'

import { useDateLocale, useDisplayLocale } from '@/hooks/use-display-locale'
import { usePrivacyMode } from '@/hooks/use-privacy-mode'
import { summarizeBills } from '@/lib/bill-summary'
import { formatCurrency } from '@/lib/format'
import type { Account, CreditCardBill } from '@/types'

type Props = {
  /** The bills of the month on screen. */
  bills: CreditCardBill[]
  /** The cards in scope; their limits feed the limit and available figures. */
  cards: Account[]
  currency: string
}

function Tile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-xl border border-border bg-card p-3 shadow-sm sm:p-4">
      <p className="mb-1 truncate text-[10px] font-medium text-muted-foreground sm:text-xs">{label}</p>
      <p className={`truncate text-base font-bold tabular-nums sm:text-xl ${tone ?? 'text-foreground'}`}>{value}</p>
    </div>
  )
}

/** Month totals of card bills: targets, paid, remaining, next due, limit and available. */
export function BillSummaryCard({ bills, cards, currency }: Props) {
  const { t } = useTranslation()
  const locale = useDisplayLocale()
  const dateLocale = useDateLocale()
  const { mask } = usePrivacyMode()
  const s = summarizeBills(bills, cards)
  const money = (n: number | null) => (n == null ? '—' : mask(formatCurrency(n, currency, locale)))

  return (
    <div
      role="group"
      aria-label={t('bills.summary.title')}
      className="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-4"
    >
      <Tile label={t('bills.summary.target')} value={money(s.target)} />
      <Tile label={t('bills.summary.paid')} value={money(s.paid)} tone="text-emerald-600" />
      <Tile label={t('bills.summary.remaining')} value={money(s.remaining)} tone={s.remaining > 0 ? 'text-rose-500' : undefined} />
      <Tile
        label={t('bills.summary.nextDue')}
        value={s.nextDue ? new Date(s.nextDue + 'T00:00:00').toLocaleDateString(dateLocale) : '—'}
      />
      <Tile label={t('bills.summary.limit')} value={money(s.limit)} />
      <Tile label={t('bills.summary.available')} value={money(s.available)} tone="text-emerald-600" />
    </div>
  )
}
