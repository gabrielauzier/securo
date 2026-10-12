import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { transactions as transactionsApi } from '@/lib/api'
import { extractApiError } from '@/lib/api-errors'
import type { Transaction } from '@/types'
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
import { TransferPairPreview } from '@/components/transfer-pair-preview'
import { selectedPairRefs } from '@/components/transfer-pair-utils'

function IdList({ title, ids, rows }: { title: string; ids: string[]; rows: Transaction[] }) {
  if (ids.length === 0) return null
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground">
        {title} ({ids.length})
      </p>
      <ul className="max-h-32 overflow-auto rounded-lg border border-border divide-y divide-border text-sm">
        {ids.map((id) => {
          const row = rows.find((tx) => tx.id === id)
          return (
            <li key={id} className="flex justify-between gap-3 px-3 py-1.5">
              <span className="min-w-0 flex-1 truncate" title={row?.description ?? id}>{row?.description ?? id}</span>
              {row && <span className="shrink-0 text-xs text-muted-foreground">{row.date}</span>}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

type Props = {
  open: boolean
  onClose: () => void
  transactionIds: string[]
  /** The rows on screen, used only to show descriptions for the leftover lists. */
  rows: Transaction[]
  /** Called after a confirm succeeds, so the page can refresh and clear the selection. */
  onLinked: () => void
}

/**
 * Pairs the selected transactions with each other. Opening it only reads;
 * nothing is linked until the user confirms, and only the checked pairs.
 */
export function BulkTransferDialog({ open, onClose, transactionIds, rows, onLinked }: Props) {
  const { t } = useTranslation()
  const [deselected, setDeselected] = useState<Set<string>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['bulk-transfer-preview', transactionIds],
    queryFn: () => transactionsApi.bulkTransferPreview(transactionIds),
    enabled: open,
    gcTime: 0,
    staleTime: 0,
  })

  const close = () => {
    setDeselected(new Set())
    onClose()
  }

  const confirm = useMutation({
    mutationFn: (pairs: { a: string; b: string }[]) => transactionsApi.bulkTransfer(pairs),
    onSuccess: (result) => {
      toast.success(
        t('transactions.bulkTransferSuccess', {
          linked: result.linked,
          skipped: result.skipped.length,
        }),
      )
      onLinked()
      close()
    },
    onError: (error) => toast.error(extractApiError(error)),
  })

  const pairs = data?.pairs ?? []
  const chosen = selectedPairRefs(pairs, deselected)

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) close() }}>
      <DialogContent className="sm:max-w-3xl [&>*]:min-w-0">
        <DialogHeader>
          <DialogTitle>{t('transactions.bulkTransferTitle')}</DialogTitle>
          <DialogDescription>{t('transactions.bulkTransferDescription')}</DialogDescription>
        </DialogHeader>
        {isLoading || !data ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <div className="space-y-4">
            <TransferPairPreview
              pairs={pairs}
              deselected={deselected}
              onDeselectedChange={setDeselected}
            />
            <IdList title={t('transactions.bulkTransferAmbiguous')} ids={data.ambiguous} rows={rows} />
            <IdList title={t('transactions.bulkTransferUnmatched')} ids={data.unmatched} rows={rows} />
            <IdList
              title={t('transactions.bulkTransferAlreadyLinked')}
              ids={data.already_linked}
              rows={rows}
            />
          </div>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={close} disabled={confirm.isPending}>
            {t('common.cancel')}
          </Button>
          <Button
            type="button"
            onClick={() => confirm.mutate(chosen)}
            disabled={chosen.length === 0 || confirm.isPending}
          >
            {t('transactions.bulkTransferConfirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
