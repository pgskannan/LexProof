import { describe, expect, it } from 'vitest'
import { verifyPaymentChain } from './paymentChain'

const RECEIPT_FIXTURE = {
  canonical: '{"decision":"allow"}',
  time: '2026-10-01T00:00:00Z',
  tool: 'send_invoice',
}

async function digest(value: string): Promise<string> {
  const result = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return [...new Uint8Array(result)].map((byte) => byte.toString(16).padStart(2, '0')).join('')
}

describe('public PayPal chain verification', () => {
  it('recomputes the receipt hash and anchored chain head from a canonical fixture', async () => {
    const receiptHash = await digest(RECEIPT_FIXTURE.canonical)
    const initialHead = await digest('lexproof-payments-v1:contract-1')
    const chainHead = await digest(`${initialHead}${receiptHash}`)
    const result = await verifyPaymentChain(
      'contract-1',
      [{ ...RECEIPT_FIXTURE, receipt_hash: receiptHash }],
      [{ count: 1, chain_head: chainHead, transaction_hash: '0xconfirmed' }],
    )
    expect(result).toEqual({
      status: 'matched',
      checkpoint: { count: 1, chain_head: chainHead, transaction_hash: '0xconfirmed' },
    })
  })

  it('identifies the first receipt whose canonical hash was changed', async () => {
    const result = await verifyPaymentChain(
      'contract-1',
      [{ ...RECEIPT_FIXTURE, receipt_hash: '0'.repeat(64) }],
      [],
    )
    expect(result).toMatchObject({ status: 'receipt_mismatch', index: 1, receipt: RECEIPT_FIXTURE })
  })
})