'use client'

import { useEffect, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { Copy, ExternalLink } from 'lucide-react'
import { toast } from 'sonner'
import { publicVerifyUrl } from '../lib/verifyLink'
import { Button } from './ui/button'
import { EmptyState } from './EmptyState'

type QrVerifyBadgeProps = {
  evidenceId: string
  size?: number
}

export function QrVerifyBadge({ evidenceId, size = 180 }: QrVerifyBadgeProps) {
  const [origin, setOrigin] = useState('')

  useEffect(() => {
    setOrigin(window.location.origin)
  }, [])

  if (!evidenceId) {
    return (
      <EmptyState
        compact
        title="No QR code yet"
        description="Anchor evidence on-chain to generate a public verification link and QR code a counterparty can scan."
      />
    )
  }

  const url = origin ? publicVerifyUrl(evidenceId, origin) : ''

  async function copyLink() {
    if (!url) return
    await navigator.clipboard.writeText(url)
    toast.success('Verification link copied')
  }

  return (
    <div className="flex flex-col items-start gap-3">
      <div className="rounded-lg border border-gray-200 bg-white p-3">
        {url ? (
          <QRCodeSVG value={url} size={size} level="M" includeMargin={false} />
        ) : (
          <div className="bg-gray-100" style={{ width: size, height: size }} />
        )}
      </div>
      <p className="max-w-sm break-all font-mono text-xs text-gray-600">{url || 'Preparing verification URL…'}</p>
      <div className="flex flex-wrap gap-2 no-print">
        <Button type="button" size="sm" variant="outline" onClick={() => void copyLink()} disabled={!url}>
          <Copy className="h-4 w-4" />
          Copy verification link
        </Button>
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-700"
          >
            Open public verify
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        ) : null}
      </div>
    </div>
  )
}
