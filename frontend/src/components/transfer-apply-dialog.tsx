import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { connections } from '@/lib/api'
import { extractApiError } from '@/lib/api-errors'
import { invalidateFinancialQueries } from '@/lib/invalidate-queries'
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

/**
 * Runs the transfer rule on demand. Opening it only reads: the preview
 * endpoint writes nothing, and the pairs are linked only when the user
 * confirms, and only the ones still checked.
 */
export function TransferApplyDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [deselected, setDeselected] = useState<Set<string>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['transfer-rule-preview'],
    queryFn: connections.previewTransfers,
    enabled: open,
    // A preview is a statement about the books right now.
    gcTime: 0,
    staleTime: 0,
  })

  const close = () => {
    setDeselected(new Set())
    onClose()
  }

  const apply = useMutation({
    mutationFn: (pairs: { a: string; b: string }[]) => connections.applyTransfers(pairs),
    onSuccess: (result) => {
      invalidateFinancialQueries(queryClient)
      toast.success(
        t('reconciliation.applyNowSuccess', {
          linked: result.linked,
          skipped: result.skipped.length,
        }),
      )
      close()
    },
    onError: (error) => toast.error(extractApiError(error, t('common.error'))),
  })

  const pairs = data?.pairs ?? []
  const chosen = selectedPairRefs(pairs, deselected)

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) close() }}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t('reconciliation.applyNowTitle')}</DialogTitle>
          <DialogDescription>{t('reconciliation.applyNowDescription')}</DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <TransferPairPreview
            pairs={pairs}
            deselected={deselected}
            onDeselectedChange={setDeselected}
          />
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={close} disabled={apply.isPending}>
            {t('common.cancel')}
          </Button>
          <Button
            type="button"
            onClick={() => apply.mutate(chosen)}
            disabled={chosen.length === 0 || apply.isPending}
          >
            {t('reconciliation.applyNowConfirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
