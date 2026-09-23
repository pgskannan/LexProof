'use client'

import { useState } from 'react'
import { PackageCheck } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '../../../../components/ui/button'
import { buildAndDownloadEvidencePack, type EvidencePackEvidenceItem } from '../../../../lib/evidencePack'

type EvidencePackButtonProps = {
  passportId: string
  contractId: string
  contractVersion: number
  contractName: string
  passportStatus?: string | null
  riskScore?: number | null
  complianceScore?: number | null
  evidence: EvidencePackEvidenceItem[]
}

/**
 * One-click compliance evidence pack: a single ZIP with the cryptographic
 * proof bundle, offline verifier, and a human-readable PDF summary of
 * findings and anchoring status — everything an auditor needs, no manual
 * assembly of separate downloads and no anchoring prerequisite.
 */
export function EvidencePackButton({
  passportId,
  contractId,
  contractVersion,
  contractName,
  passportStatus,
  riskScore,
  complianceScore,
  evidence,
}: EvidencePackButtonProps) {
  const [exporting, setExporting] = useState(false)

  async function handleExport() {
    setExporting(true)
    try {
      await buildAndDownloadEvidencePack({
        passportId,
        contractId,
        contractVersion,
        contractName,
        passportStatus,
        riskScore,
        complianceScore,
        evidence,
      })
      toast.success('Compliance evidence pack downloaded')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Unable to build the evidence pack')
    } finally {
      setExporting(false)
    }
  }

  return (
    <Button type="button" size="sm" onClick={() => void handleExport()} disabled={exporting}>
      <PackageCheck className="h-4 w-4" />
      {exporting ? 'Building evidence pack…' : 'Export compliance evidence pack'}
    </Button>
  )
}
