import { useTranslation } from 'react-i18next'
import { ArrowRight } from 'lucide-react'
import { useDateLocale, useDisplayLocale } from '@/hooks/use-display-locale'
import { formatCurrency } from '@/lib/format'
import type { ProposedTransferPair, TransferLeg, TransferPairRef } from '@/lib/api'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export function pairKey(pair: ProposedTransferPair): string {
  return `${pair.a.id}:${pair.b.id}`
}

/** The pairs still checked, as the references the apply endpoints take. */
export function selectedPairRefs(
  pairs: ProposedTransferPair[],
  deselected: ReadonlySet<string>,
): TransferPairRef[] {
  return pairs
    .filter((pair) => !deselected.has(pairKey(pair)))
    .map((pair) => ({ a: pair.a.id, b: pair.b.id }))
}

function Leg({ leg, sign }: { leg: TransferLeg; sign: '+' | '−' }) {
  const locale = useDisplayLocale()
  const dateLocale = useDateLocale()
  const color = sign === '+' ? 'text-emerald-600' : 'text-rose-500'
  return (
    <div className="min-w-0">
      <p className="truncate text-sm font-medium text-foreground" title={leg.description}>
        {leg.description}
      </p>
      <p className="truncate text-xs text-muted-foreground">
        {leg.account_name ?? '—'} · {new Date(leg.date + 'T00:00:00').toLocaleDateString(dateLocale)}
      </p>
      <p className={`text-sm font-semibold tabular-nums ${color}`}>
        {sign}
        {formatCurrency(Math.abs(Number(leg.amount)), leg.currency, locale)}
      </p>
    </div>
  )
}

type Props = {
  pairs: ProposedTransferPair[]
  /** Keys of the pairs the user unchecked. Everything is checked by default. */
  deselected: ReadonlySet<string>
  onDeselectedChange: (next: Set<string>) => void
}

/**
 * Proposed transfer pairs with a checkbox each. State is held as the
 * **unchecked** keys so a freshly loaded preview needs no initialising:
 * nothing unchecked means everything is selected.
 */
export function TransferPairPreview({ pairs, deselected, onDeselectedChange }: Props) {
  const { t } = useTranslation()

  if (pairs.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        {t('transferPreview.empty')}
      </p>
    )
  }

  const selected = pairs.filter((pair) => !deselected.has(pairKey(pair))).length

  const toggle = (key: string) => {
    const next = new Set(deselected)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    onDeselectedChange(next)
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground">
        {t('transferPreview.title')} ·{' '}
        {t('transferPreview.selectedCount', { selected, total: pairs.length })}
      </p>
      <div className="max-h-[50vh] overflow-auto rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10" />
              <TableHead>{t('transferPreview.from')}</TableHead>
              <TableHead className="w-6" />
              <TableHead>{t('transferPreview.to')}</TableHead>
              <TableHead>{t('transferPreview.strategy')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pairs.map((pair) => {
              const key = pairKey(pair)
              return (
                <TableRow key={key}>
                  <TableCell>
                    <input
                      type="checkbox"
                      aria-label={t('transferPreview.selectPair')}
                      checked={!deselected.has(key)}
                      onChange={() => toggle(key)}
                      className="h-4 w-4 rounded border-border accent-primary cursor-pointer"
                    />
                  </TableCell>
                  <TableCell className="max-w-[16rem]">
                    <Leg leg={pair.a} sign="−" />
                  </TableCell>
                  <TableCell className="px-0 text-muted-foreground">
                    <ArrowRight className="h-4 w-4" />
                  </TableCell>
                  <TableCell className="max-w-[16rem]">
                    <Leg leg={pair.b} sign="+" />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {pair.strategy ?? '—'}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
