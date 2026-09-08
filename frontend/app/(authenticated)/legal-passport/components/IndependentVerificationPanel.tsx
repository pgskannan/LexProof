'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { Download, Printer, QrCode } from 'lucide-react'
import { toast } from 'sonner'
import { apiFetch } from '../../../../lib/api'
import { QrVerifyBadge } from '../../../../components/QrVerifyBadge'
import { Button } from '../../../../components/ui/button'

type EvidenceItem = {
  evidence_id: string
  title: string
}

type AnchorRecord = {
  evidence_id: string
  transaction_hash?: string
  block_number?: number
  blockchain_network?: string
}

type IndependentVerificationPanelProps = {
  passportId: string
  contractId: string
  contractVersion: number
  evidence: EvidenceItem[]
}

export function IndependentVerificationPanel({
  passportId,
  contractId,
  contractVersion,
  evidence,
}: IndependentVerificationPanelProps) {
  const [anchors, setAnchors] = useState<Record<string, AnchorRecord>>({})
  const [selectedId, setSelectedId] = useState('')
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    if (!evidence.length) return
    let cancelled = false
    void Promise.all(
      evidence.map(async (item) => {
        const response = await apiFetch(`/api/evidence/${encodeURIComponent(item.evidence_id)}/anchor`)
        if (!response.ok) return null
        return (await response.json()) as AnchorRecord
      }),
    ).then((results) => {
      if (cancelled) return
      const next: Record<string, AnchorRecord> = {}
      for (const record of results) {
        if (record?.evidence_id && record.transaction_hash) {
          next[record.evidence_id] = record
        }
      }
      setAnchors(next)
    })
    return () => {
      cancelled = true
    }
  }, [evidence])

  const anchoredItems = useMemo(
    () => evidence.filter((item) => anchors[item.evidence_id]),
    [evidence, anchors],
  )

  useEffect(() => {
    if (!anchoredItems.length) {
      setSelectedId('')
      return
    }
    if (!anchoredItems.some((item) => item.evidence_id === selectedId)) {
      setSelectedId(anchoredItems[0].evidence_id)
    }
  }, [anchoredItems, selectedId])

  const certificateHref = `/legal-passport/certificate?contractId=${encodeURIComponent(contractId)}&contractVersion=${contractVersion}`

  async function downloadBundle() {
    setDownloading(true)
    try {
      const response = await apiFetch(`/api/passports/${encodeURIComponent(passportId)}/proof-package`)
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.detail || 'Unable to download verification bundle')
      }
      const payload = await response.json()
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `bundle-${passportId}.json`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
      toast.success('Verification bundle downloaded')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Unable to download verification bundle')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold text-gray-900">Independent verification</h2>
      <p className="mb-4 text-sm text-gray-600">
        Scan the QR code with any phone to open the public verifier. No login, and the on-chain check
        reads Sepolia directly from that device.
      </p>

      {anchoredItems.length === 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          Anchor at least one evidence item to generate a scannable verification QR.
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[auto_1fr]">
          <div className="flex items-start gap-3">
            <QrCode className="mt-1 h-5 w-5 text-blue-600" />
            <QrVerifyBadge evidenceId={selectedId} />
          </div>
          <div className="space-y-4">
            {anchoredItems.length > 1 ? (
              <label className="block text-sm font-medium text-gray-700">
                Anchored evidence
                <select
                  value={selectedId}
                  onChange={(event) => setSelectedId(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                >
                  {anchoredItems.map((item) => (
                    <option key={item.evidence_id} value={item.evidence_id}>
                      {item.title}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <p className="text-sm text-gray-700">{anchoredItems[0]?.title}</p>
            )}
            {selectedId && anchors[selectedId]?.transaction_hash ? (
              <p className="break-all font-mono text-xs text-gray-500">
                tx {anchors[selectedId].transaction_hash}
                {anchors[selectedId].block_number != null ? ` · block ${anchors[selectedId].block_number}` : ''}
              </p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Link
                href={certificateHref}
                className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                <Printer className="h-4 w-4" />
                Printable certificate
              </Link>
              <Button type="button" variant="outline" size="sm" onClick={() => void downloadBundle()} disabled={downloading}>
                <Download className="h-4 w-4" />
                {downloading ? 'Preparing bundle…' : 'Download verification bundle'}
              </Button>
              <a
                href="/verify-offline.html"
                download="verify-offline.html"
                className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                <Download className="h-4 w-4" />
                Download offline verifier
              </a>
            </div>
            <p className="text-xs text-gray-500">
              The offline verifier works from disk with this bundle. Confirming the Sepolia anchor still
              needs a public RPC call — not a call to LexProof.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
