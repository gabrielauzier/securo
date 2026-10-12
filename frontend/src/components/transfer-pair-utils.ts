import type { ProposedTransferPair, TransferPairRef } from '@/lib/api'

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
