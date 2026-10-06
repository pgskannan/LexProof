export type PaymentChainReceipt = {
  canonical: string
  receipt_hash: string
  time: string
  tool: string
}

export type PaymentChainCheckpoint = {
  checkpoint_id?: string
  count: number
  chain_head: string
  transaction_hash: string
  etherscan_url?: string
}

export type PaymentChainVerification =
  | { status: 'matched'; checkpoint: PaymentChainCheckpoint }
  | { status: 'no_checkpoint' }
  | { status: 'receipt_mismatch'; receipt: PaymentChainReceipt; index: number }
  | { status: 'missing_receipts'; index: number }
  | { status: 'chain_mismatch'; checkpoint: PaymentChainCheckpoint }

const CHAIN_VERSION = 'lexproof-payments-v1'

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('')
}

export async function verifyPaymentChain(
  contractId: string,
  receipts: PaymentChainReceipt[],
  checkpoints: PaymentChainCheckpoint[],
): Promise<PaymentChainVerification> {
  const hashes: string[] = []
  for (const [index, receipt] of receipts.entries()) {
    const actual = await sha256Hex(receipt.canonical)
    if (actual !== receipt.receipt_hash.toLowerCase()) {
      return { status: 'receipt_mismatch', receipt, index: index + 1 }
    }
    hashes.push(actual)
  }

  const checkpoint = checkpoints
    .filter((item) => Boolean(item.transaction_hash))
    .sort((left, right) => right.count - left.count)[0]
  if (!checkpoint) return { status: 'no_checkpoint' }
  if (checkpoint.count > hashes.length) return { status: 'missing_receipts', index: hashes.length + 1 }

  let head = await sha256Hex(`${CHAIN_VERSION}:${contractId}`)
  for (const digest of hashes.slice(0, checkpoint.count)) {
    head = await sha256Hex(`${head}${digest}`)
  }
  if (head !== checkpoint.chain_head.toLowerCase()) {
    return { status: 'chain_mismatch', checkpoint }
  }
  return { status: 'matched', checkpoint }
}