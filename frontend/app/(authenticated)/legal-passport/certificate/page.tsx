'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Printer, Shield } from 'lucide-react'
import { apiFetch } from '../../../../lib/api'
import { QrVerifyBadge } from '../../../../components/QrVerifyBadge'
import { Button } from '../../../../components/ui/button'
import { filterLegalEvidenceFindings } from '../../../../lib/passport/evidence'

type Passport = {
  passport_id: string
  contract_id: string
  contract_version: number
  risk_score: number
  compliance_score: number
  metadata?: { risk_level?: string }
}

type EvidenceItem = {
  evidence_id: string
  title: string
  evidence_type?: string
  metadata?: Record<string, unknown>
}

type AnchorRecord = {
  evidence_id: string
  transaction_hash?: string
  block_number?: number
  blockchain_network?: string
}

export default function VerificationCertificatePage() {
  const router = useRouter()
  const [passport, setPassport] = useState<Passport | null>(null)
  const [contractName, setContractName] = useState('')
  const [evidence, setEvidence] = useState<EvidenceItem[]>([])
  const [anchors, setAnchors] = useState<Record<string, AnchorRecord>>({})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const contractId = params.get('contractId')
    const contractVersion = params.get('contractVersion')
    if (!contractId || !contractVersion) {
      router.push('/dashboard/contracts')
      return
    }
    const controller = new AbortController()
    void (async () => {
      try {
        const response = await apiFetch(
          `/api/contracts/${contractId}/passport?contract_version=${contractVersion}`,
          { signal: controller.signal },
        )
        if (!response.ok) throw new Error('Unable to load passport')
        const data: Passport = await response.json()
        setPassport(data)
        const [contractRes, evidenceRes] = await Promise.all([
          apiFetch(`/api/contracts/${contractId}`, { signal: controller.signal }),
          apiFetch(`/api/passports/${data.passport_id}/evidence`, { signal: controller.signal }),
        ])
        if (contractRes.ok) {
          const contract = await contractRes.json()
          setContractName(contract.name || contractId)
        }
        if (evidenceRes.ok) {
          setEvidence(await evidenceRes.json())
        }
      } catch (reason) {
        if (reason instanceof DOMException && reason.name === 'AbortError') return
        setError(reason instanceof Error ? reason.message : 'Unable to load certificate')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [router])

  const legalEvidence = useMemo(
    () =>
      filterLegalEvidenceFindings(
        evidence.map((item) => ({ ...item, evidence_type: item.evidence_type || 'clause' })),
      ),
    [evidence],
  )

  useEffect(() => {
    if (!legalEvidence.length) return
    let cancelled = false
    void Promise.all(
      legalEvidence.map(async (item) => {
        const response = await apiFetch(`/api/evidence/${encodeURIComponent(item.evidence_id)}/anchor`)
        if (!response.ok) return null
        return (await response.json()) as AnchorRecord
      }),
    ).then((results) => {
      if (cancelled) return
      const next: Record<string, AnchorRecord> = {}
      for (const record of results) {
        if (record?.evidence_id && record.transaction_hash) next[record.evidence_id] = record
      }
      setAnchors(next)
    })
    return () => {
      cancelled = true
    }
  }, [legalEvidence])

  const anchored = legalEvidence.filter((item) => anchors[item.evidence_id])

  if (loading) {
    return <div className="p-10 text-sm text-gray-600">Preparing verification certificate…</div>
  }
  if (error || !passport) {
    return <div className="p-10 text-sm text-red-700">{error || 'Passport not found'}</div>
  }

  return (
    <div className="min-h-screen bg-gray-50 px-6 py-8">
      <div className="no-print mx-auto mb-6 flex max-w-3xl items-center justify-between">
        <button
          type="button"
          onClick={() => router.back()}
          className="inline-flex items-center text-sm text-blue-600 hover:text-blue-700"
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back
        </button>
        <Button type="button" onClick={() => window.print()}>
          <Printer className="h-4 w-4" />
          Print / Save as PDF
        </Button>
      </div>

      <article className="certificate-sheet mx-auto max-w-3xl border-2 border-slate-800 bg-white p-10 shadow-sm">
        <header className="mb-8 flex items-start justify-between border-b border-slate-300 pb-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-700">LexProof</p>
            <h1 className="mt-2 text-3xl font-bold text-slate-900">Verification Certificate</h1>
            <p className="mt-2 text-sm text-slate-600">Independently verifiable legal intelligence snapshot</p>
          </div>
          <Shield className="h-10 w-10 text-blue-700" />
        </header>

        <section className="mb-8 grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">Contract</p>
            <p className="mt-1 font-semibold text-slate-900">{contractName || passport.contract_id}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">Version</p>
            <p className="mt-1 font-semibold text-slate-900">{passport.contract_version}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">Passport ID</p>
            <p className="mt-1 break-all font-mono text-xs text-slate-800">{passport.passport_id}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">Scores</p>
            <p className="mt-1 text-slate-900">
              Risk {passport.risk_score}/100 · Compliance {passport.compliance_score}/100
              {passport.metadata?.risk_level ? ` · ${passport.metadata.risk_level}` : ''}
            </p>
          </div>
        </section>

        <section className="mb-8">
          <h2 className="mb-3 text-lg font-semibold text-slate-900">Anchored evidence</h2>
          {anchored.length === 0 ? (
            <p className="text-sm text-slate-600">No anchored evidence on this passport yet.</p>
          ) : (
            <div className="space-y-3">
              {anchored.map((item) => (
                <div key={item.evidence_id} className="rounded border border-slate-200 p-3 text-sm">
                  <p className="font-medium text-slate-900">{item.title}</p>
                  <p className="mt-1 break-all font-mono text-xs text-slate-600">Evidence ID: {item.evidence_id}</p>
                  <p className="mt-1 break-all font-mono text-xs text-slate-600">
                    Tx: {anchors[item.evidence_id].transaction_hash}
                    {anchors[item.evidence_id].block_number != null
                      ? ` · Block ${anchors[item.evidence_id].block_number}`
                      : ''}
                  </p>
                </div>
              ))}
            </div>
          )}
        </section>

        {anchored[0] ? (
          <section className="flex flex-col items-center border-t border-slate-300 pt-6">
            <p className="mb-3 text-sm font-medium text-slate-700">Scan to verify independently on Sepolia</p>
            <QrVerifyBadge evidenceId={anchored[0].evidence_id} size={160} />
          </section>
        ) : null}

        <footer className="mt-8 text-center text-xs text-slate-500">
          Scan the QR or open the link on any device. Verification reads Ethereum Sepolia directly and does
          not require a LexProof login.
        </footer>
      </article>
    </div>
  )
}
