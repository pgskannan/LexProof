"use client"

import { useState, useEffect, useMemo } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Shield, FileText, CheckCircle, AlertTriangle, Info, Clock, ArrowLeft, Copy, ExternalLink, XCircle, Anchor, Scale, Sparkles, UserCheck, UploadCloud, Fingerprint, BadgeCheck, Search } from 'lucide-react'
import AnchorProofButton from './components/AnchorProofButton'
import PassportRootAnchorPanel, {
  type PassportRootAnchorStatus,
} from './components/PassportRootAnchorPanel'
import { IndependentVerificationPanel } from './components/IndependentVerificationPanel'
import { EvidencePackButton } from './components/EvidencePackButton'
import { apiFetch } from '../../../lib/api'
import {
  countLegalEvidenceFindings,
  filterLegalEvidenceFindings,
} from '../../../lib/passport/evidence'
import { EmptyState } from '../../../components/EmptyState'
import { Skeleton } from '../../../components/ui/skeleton'
import { Button } from '../../../components/ui/button'
import { Card, CardContent } from '../../../components/ui/card'
import { DataTable } from '../../../components/ui/data-table'
import { PageHeader } from '../../../components/ui/page-header'
import { PageContainer } from '../../../components/ui/container'

interface ContractPassport {
  passport_id: string
  contract_id: string
  contract_version: number
  document_hash: string
  policy_hash: string
  analysis_hash: string
  evidence_hash: string
  metadata?: {
    passport_hash?: string
    risk_level?: string
  }
  risk_score: number
  compliance_score: number
  policy_version: string
  evidence_count: number
  created_at: string
  created_by: string
  status: string
  audit_events: Array<{
    event_type: string
    timestamp: string
    created_by: string
  }>
}

interface ContractSummary {
  contract_id: string
  name: string
  version?: number | null
  passport_id?: string | null
}

interface EvidenceItem {
  evidence_id: string
  passport_id: string
  evidence_type: string
  title: string
  description?: string
  risk_impact?: number | null
  compliance_impact?: number | null
  evidence_status: string
  contract_reference?: string | null
  metadata?: Record<string, any>
  created_at: string
}

interface Statistics {
  total_count: number
  legal_findings_count?: number
  type_counts: Record<string, number>
  status_counts: Record<string, number>
  avg_risk_impact: number
  avg_compliance_impact: number
}

type IntegrityComponentStatus = 'PASS' | 'FAIL' | 'UNVERIFIABLE'

interface PassportIntegrityResult {
  verified: boolean
  document_verified: boolean
  policy_verified: boolean
  analysis_verified: boolean
  evidence_verified: boolean
  passport_hash_verified: boolean
  document_status?: IntegrityComponentStatus
  policy_status?: IntegrityComponentStatus
  analysis_status?: IntegrityComponentStatus
  evidence_status?: IntegrityComponentStatus
  passport_hash_status?: IntegrityComponentStatus
  // Additive Sepolia passport-ROOT anchor state (see
  // docs/PASSPORT_ROOT_ANCHOR_ARCHITECTURE.md §16, §23). Populated by the
  // extended POST /passports/{id}/verify response; never derived locally --
  // this is always the server's own recomputation, and a blockchain match
  // can never turn a FAIL/UNVERIFIABLE component above into a PASS here.
  anchor_status?: PassportRootAnchorStatus
  anchor_ineligible_reasons?: string[]
  anchor_error?: string
  blockchain_network?: string | null
  contract_address?: string | null
  chain_id?: number | null
  transaction_hash?: string | null
  block_number?: number | null
  on_chain_root?: string | null
}

function integrityStatusLabel(
  verified: boolean,
  status: IntegrityComponentStatus | undefined,
  mismatchLabel: string,
): { className: string; text: string } {
  const resolved = status ?? (verified ? 'PASS' : 'FAIL')
  if (resolved === 'PASS') {
    return { className: 'text-green-700', text: '✓' }
  }
  if (resolved === 'UNVERIFIABLE') {
    return { className: 'text-amber-800', text: '— not claimed in snapshot' }
  }
  return { className: 'text-red-700 font-medium', text: mismatchLabel }
}

export default function LegalPassportPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [passport, setPassport] = useState<ContractPassport | null>(null)
  const [contract, setContract] = useState<ContractSummary | null>(null)
  const [evidence, setEvidence] = useState<EvidenceItem[]>([])
  const [statistics, setStatistics] = useState<Statistics | null>(null)
  const [loading, setLoading] = useState(true)
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [evidenceError, setEvidenceError] = useState('')
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'overview' | 'evidence' | 'fingerprint'>('overview')
  const [expandedEvidenceId, setExpandedEvidenceId] = useState<string | null>(null)
  const [copiedEvidenceId, setCopiedEvidenceId] = useState<string | null>(null)
  const [integrity, setIntegrity] = useState<PassportIntegrityResult | null>(null)
  const [integrityLoading, setIntegrityLoading] = useState(false)
  const [integrityError, setIntegrityError] = useState('')
  const [passportRequest, setPassportRequest] = useState<{ contractId: string; contractVersion: number } | null>(null)
  const [pickerContracts, setPickerContracts] = useState<ContractSummary[]>([])
  const [pickerLoading, setPickerLoading] = useState(false)
  const [needsPicker, setNeedsPicker] = useState(false)
  // Hardening item #6 (Polish Legal Passport as centerpiece): the passport
  // previously buried Ethereum anchor status inside each individual,
  // collapsed evidence row -- a viewer had to expand every item to learn
  // how much of this passport was actually anchored on-chain. Surfacing an
  // "N/M anchored" count as its own headline stat (alongside risk score,
  // compliance score, and evidence count) makes the passport read as one
  // connected artifact at a glance, matching the Contract Lifecycle page's
  // existing "Evidence N/M anchored" metric.
  const [anchoredCount, setAnchoredCount] = useState<number | null>(null)

  const legalEvidence = useMemo(() => filterLegalEvidenceFindings(evidence), [evidence])
  const legalEvidenceCount = useMemo(
    () => passport?.evidence_count ?? countLegalEvidenceFindings(evidence),
    [passport?.evidence_count, evidence],
  )
  const [search, setSearch] = useState('')

  const filteredPickerContracts = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return pickerContracts
    return pickerContracts.filter((item) => {
      const name = (item.name || item.contract_id).toLowerCase()
      const passportId = (item.passport_id || '').toLowerCase()
      return name.includes(query) || passportId.includes(query)
    })
  }, [pickerContracts, search])

  useEffect(() => {
    if (legalEvidence.length === 0) {
      setAnchoredCount(evidenceLoading ? null : 0)
      return
    }
    let cancelled = false
    void Promise.all(
      legalEvidence.map(async (item) => {
        try {
          const response = await apiFetch(`/api/evidence/${encodeURIComponent(item.evidence_id)}/status`)
          if (!response.ok) return false
          const body: { anchored?: boolean } = await response.json()
          return Boolean(body.anchored)
        } catch {
          return false
        }
      }),
    ).then((results) => {
      if (!cancelled) setAnchoredCount(results.filter(Boolean).length)
    })
    return () => {
      cancelled = true
    }
  }, [legalEvidence, evidenceLoading])

  // Load a specific passport when the URL has contract + version; otherwise
  // show a picker so the sidebar Legal Passport link is never a dead stub.
  // Depends on `searchParams` (not `router`, and not a manual
  // window.location.search read) so this re-runs on a same-page,
  // client-side navigation between picker rows -- router.push() to a new
  // ?contractId=...&contractVersion=... does not change `router` identity,
  // so keying the effect on `router` alone left it stuck showing the
  // picker after a row click until a hard reload.
  useEffect(() => {
    const contractId = searchParams.get('contractId')
    const contractVersion = searchParams.get('contractVersion')

    // A contract-only link (?contractId=... with no version: bookmarked,
    // shared, or typed) used to fall through to the picker silently. Resolve
    // the contract's current version and open that passport instead; only
    // fall back to the picker if the contract can't be resolved.
    if (contractId && !contractVersion) {
      const controller = new AbortController()
      setLoading(true)
      void apiFetch(`/api/contracts/${encodeURIComponent(contractId)}`, { signal: controller.signal })
        .then(async (response) => {
          const contract: { version?: number | null } | null = response.ok ? await response.json() : null
          if (contract?.version != null) {
            router.replace(
              `/legal-passport?contractId=${encodeURIComponent(contractId)}&contractVersion=${contract.version}`,
            )
            return
          }
          router.replace('/legal-passport')
        })
        .catch((error) => {
          if (!isAbortError(error)) router.replace('/legal-passport')
        })
      return () => controller.abort()
    }

    if (!contractId || !contractVersion) {
      setNeedsPicker(true)
      setLoading(false)
      setPickerLoading(true)
      void apiFetch('/api/contracts')
        .then(async (response) => {
          if (!response.ok) throw new Error('Unable to load contracts')
          const records: ContractSummary[] = await response.json()
          setPickerContracts(records.filter((item) => item.passport_id && item.version != null))
        })
        .catch(() => setPickerContracts([]))
        .finally(() => setPickerLoading(false))
      return
    }

    setNeedsPicker(false)
    const version = parseInt(contractVersion, 10)
    setPassportRequest({ contractId, contractVersion: version })
    const controller = new AbortController()
    void fetchPassport(contractId, version, controller.signal)
    return () => controller.abort()
  }, [searchParams])

  const isAbortError = (error: unknown) => error instanceof DOMException && error.name === 'AbortError'

  const fetchPassport = async (contractId: string, contractVersion: number, signal?: AbortSignal) => {
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch(`/api/contracts/${contractId}/passport?contract_version=${contractVersion}`, { signal })
      if (response.ok) {
        const data = await response.json()
        setPassport(data)
        fetchContract(contractId, signal)
        fetchEvidence(data.passport_id, signal)
        fetchStatistics(data.passport_id, signal)
        fetchIntegrity(data.passport_id, signal)
      } else if (response.status === 401) {
        setError('Your session is still initializing. Please sign in again.')
      } else if (response.status === 404) {
        setError('The legal passport for this contract does not exist.')
      } else {
        const body = await response.json().catch(() => null)
        setError(body?.detail || `Unable to load passport (${response.status})`)
      }
    } catch (error) {
      if (isAbortError(error)) return
      setError(error instanceof Error ? error.message : 'Unable to load passport')
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }

  const fetchContract = async (contractId: string, signal?: AbortSignal) => {
    try {
      const response = await apiFetch(`/api/contracts/${contractId}`, { signal })
      if (response.ok) setContract(await response.json())
    } catch (error) {
      if (isAbortError(error)) return
      console.error('Error fetching contract:', error)
    }
  }

  const fetchEvidence = async (passportId: string, signal?: AbortSignal) => {
    setEvidenceLoading(true)
    setEvidenceError('')
    try {
      const response = await apiFetch(`/api/passports/${passportId}/evidence`, { signal })
      if (response.ok) {
        const data = await response.json()
        setEvidence(data)
      } else {
        const body = await response.json().catch(() => null)
        setEvidenceError(body?.detail || `Unable to load evidence (${response.status})`)
      }
    } catch (error) {
      if (isAbortError(error)) return
      setEvidenceError(error instanceof Error ? error.message : 'Unable to load evidence')
    } finally {
      if (!signal?.aborted) setEvidenceLoading(false)
    }
  }

  const fetchStatistics = async (passportId: string, signal?: AbortSignal) => {
    try {
      const response = await apiFetch(`/api/passports/${passportId}/evidence/statistics`, { signal })
      if (response.ok) {
        const data = await response.json()
        setStatistics(data)
      }
    } catch (error) {
      if (isAbortError(error)) return
      console.error('Error fetching statistics:', error)
    }
  }
  const fetchIntegrity = async (passportId: string, signal?: AbortSignal) => {
    setIntegrityLoading(true)
    setIntegrityError('')
    try {
      const response = await apiFetch(`/api/passports/${passportId}/verify`, {
        method: 'POST',
        signal,
      })
      if (response.ok) {
        const data = await response.json()
        setIntegrity(data)
      } else {
        const body = await response.json().catch(() => null)
        setIntegrityError(body?.detail || `Integrity check failed (${response.status})`)
      }
    } catch (error) {
      if (isAbortError(error)) return
      setIntegrityError(error instanceof Error ? error.message : 'Integrity check failed')
    } finally {
      if (!signal?.aborted) setIntegrityLoading(false)
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'created':
        return <CheckCircle className="w-5 h-5 text-green-500" />
      case 'pending':
        return <Clock className="w-5 h-5 text-yellow-500" />
      case 'revoked':
        return <AlertTriangle className="w-5 h-5 text-red-500" />
      case 'expired':
        return <Info className="w-5 h-5 text-gray-500" />
      default:
        return <Info className="w-5 h-5 text-gray-500" />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'created':
        return 'text-green-500'
      case 'pending':
        return 'text-yellow-500'
      case 'revoked':
        return 'text-red-500'
      case 'expired':
        return 'text-gray-500'
      default:
        return 'text-gray-500'
    }
  }

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString()
  }

  const truncateHash = (hash: string) => {
    if (hash.length <= 16) return hash
    return `${hash.substring(0, 8)}...${hash.substring(hash.length - 8)}`
  }

  const formatPassportId = (value?: string | null) => {
    if (!value) return '—'
    if (value.length <= 16) return value
    return `${value.slice(0, 8)}…${value.slice(-6)}`
  }

  const copyEvidenceId = async (evidenceId: string) => {
    try {
      await navigator.clipboard.writeText(evidenceId)
      setCopiedEvidenceId(evidenceId)
      window.setTimeout(() => setCopiedEvidenceId(current => current === evidenceId ? null : current), 2000)
    } catch (error) {
      console.error('Unable to copy evidence ID:', error)
    }
  }

  if (needsPicker) {
    return (
      <PageContainer>
        <PageHeader
          eyebrow="Evidence"
          title="Legal Passport"
          description="Open the cryptographically verifiable record for a contract that has already been analyzed."
        />
        <div className="mt-6">
          {pickerLoading && (
            <div className="space-y-3">
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </div>
          )}
          {!pickerLoading && pickerContracts.length === 0 && (
            <EmptyState
              compact
              title="No Legal Passports yet"
              description="Upload a contract and run analysis to create a passport. The namesake record is created at the end of that workflow."
              actionLabel="Go to contracts"
              onAction={() => router.push('/dashboard/contracts')}
              icon={<Shield className="h-6 w-6" />}
            />
          )}
          {!pickerLoading && pickerContracts.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3 rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-white px-3 py-2 dark:border-gray-700 dark:bg-gray-900">
                <div className="relative flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                  <input
                    aria-label="Search contract or passport ID"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search contract or passport ID"
                    className="w-full rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-gray-50 py-2 pl-9 pr-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-[var(--brand-primary,#2563eb)] focus:outline-none dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
                  />
                </div>
                <div className="whitespace-nowrap text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  {filteredPickerContracts.length} {filteredPickerContracts.length === 1 ? 'PASSPORT' : 'PASSPORTS'}
                </div>
              </div>

              {filteredPickerContracts.length === 0 ? (
                <EmptyState
                  compact
                  title="No matching passports"
                  description="Try a different contract name or passport ID."
                />
              ) : (
                <DataTable
                  columns={[
                    {
                      key: 'contract',
                      header: 'Contract',
                      className: 'min-w-[220px]',
                      render: (item) => (
                        <div className="min-w-0">
                          <div className="truncate font-medium text-gray-900 dark:text-gray-100">{item.name || item.contract_id}</div>
                          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{item.contract_id}</div>
                        </div>
                      ),
                    },
                    {
                      key: 'version',
                      header: 'Version',
                      className: 'w-[110px] text-center',
                      render: (item) => (
                        <span className="inline-flex rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                          V{item.version ?? '—'}
                        </span>
                      ),
                    },
                    {
                      key: 'passport',
                      header: 'Passport ID',
                      className: 'min-w-[180px]',
                      render: (item) => (
                        <span
                          title={item.passport_id || '—'}
                          className="block max-w-full truncate font-mono text-xs text-gray-500 dark:text-gray-400"
                        >
                          {formatPassportId(item.passport_id)}
                        </span>
                      ),
                    },
                    {
                      key: 'action',
                      header: 'Action',
                      className: 'w-[160px] text-right',
                      render: (item) => (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="justify-center"
                          onClick={(event) => {
                            event.stopPropagation();
                            router.push(
                              `/legal-passport?contractId=${encodeURIComponent(item.contract_id)}&contractVersion=${item.version ?? 1}`,
                            );
                          }}
                        >
                          Open passport →
                        </Button>
                      ),
                    },
                  ]}
                  data={filteredPickerContracts}
                  rowKey={(item) => `${item.contract_id}:${item.version ?? 'unknown'}`}
                  pageSize={10}
                  onRowClick={(item) =>
                    router.push(
                      `/legal-passport?contractId=${encodeURIComponent(item.contract_id)}&contractVersion=${item.version ?? 1}`,
                    )
                  }
                  emptyTitle="No matching passports"
                  emptyDescription="Try a different contract name or passport ID."
                />
              )}
            </div>
          )}
        </div>
      </PageContainer>
    )
  }

  if (loading) {
    return (
      <PageContainer>
        <div className="space-y-6">
          <div className="space-y-2">
            <Skeleton className="h-3 w-28" />
            <Skeleton className="h-8 w-72" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
          </div>
          <Skeleton className="h-32 w-full" />
        </div>
      </PageContainer>
    )
  }

  if (!passport) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center">
          <Shield className="w-16 h-16 text-gray-400 mx-auto mb-4" />
          <h2 className="text-2xl font-semibold text-gray-700 dark:text-gray-200 mb-2">{error || 'Passport unavailable'}</h2>
          <p className="text-gray-600 dark:text-gray-400 mb-4">Check your session or try loading the contract again.</p>
          {passportRequest && (
            <Button
              type="button"
              onClick={() => void fetchPassport(passportRequest.contractId, passportRequest.contractVersion)}
              className="mr-2"
            >
              Retry
            </Button>
          )}
          <Button onClick={() => router.push('/dashboard/contracts')}>
            Back to Contracts
          </Button>
        </div>
      </div>
    )
  }

  const provenanceSteps = [
    { key: 'contract', label: 'Contract', icon: FileText, done: true, detail: contract?.name || passport.contract_id },
    { key: 'analysis', label: 'AI Analysis', icon: Sparkles, done: true, detail: `Risk ${passport.risk_score} · Compliance ${passport.compliance_score}` },
    { key: 'finding', label: 'Risk Finding', icon: AlertTriangle, done: legalEvidenceCount > 0, detail: `${legalEvidenceCount} finding${legalEvidenceCount === 1 ? '' : 's'} recorded` },
    { key: 'review', label: 'Human Review', icon: UserCheck, done: passport.audit_events.some((event) => /review|approve/i.test(event.event_type)), detail: `${passport.audit_events.length} audit event${passport.audit_events.length === 1 ? '' : 's'}` },
    { key: 'published', label: 'Published Version', icon: UploadCloud, done: passport.status === 'created' || passport.status === 'pending' || Boolean(passport.contract_version), detail: `Version ${passport.contract_version} · ${passport.status}` },
    { key: 'fingerprint', label: 'Evidence Fingerprint', icon: Fingerprint, done: Boolean(passport.metadata?.passport_hash), detail: passport.metadata?.passport_hash ? 'SHA-256 sealed' : 'Pending' },
    { key: 'anchor', label: 'Ethereum Anchor', icon: Anchor, done: (anchoredCount ?? 0) > 0, detail: anchoredCount === null ? 'Checking…' : `${anchoredCount}/${legalEvidenceCount} anchored` },
    { key: 'verify', label: 'Independent Verification', icon: BadgeCheck, done: integrity?.verified === true, detail: integrityLoading ? 'Checking…' : integrity ? (integrity.verified ? 'Verified' : 'Needs attention') : 'Not yet run' },
  ]

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Evidence"
        title="Legal Passport"
        description={contract?.name || 'Cryptographically verifiable legal intelligence record'}
        actions={
          <>
            <EvidencePackButton
              passportId={passport.passport_id}
              contractId={passport.contract_id}
              contractVersion={passport.contract_version}
              contractName={contract?.name || passport.contract_id}
              passportStatus={passport.status}
              riskScore={passport.risk_score}
              complianceScore={passport.compliance_score}
              evidence={legalEvidence}
            />
            <div className={`flex items-center gap-2 rounded-[var(--radius-md,0.5rem)] px-3.5 py-2 text-sm ${getStatusColor(passport.status)}`}>
              {getStatusIcon(passport.status)}
              <span className={`font-medium capitalize ${getStatusColor(passport.status)}`}>
                {passport.status}
              </span>
            </div>
          </>
        }
      />
      <button
        onClick={() => router.push('/dashboard/contracts')}
        className="mt-4 inline-flex items-center text-sm text-[var(--brand-primary,#2563eb)] hover:underline"
      >
        <ArrowLeft className="w-4 h-4 mr-1" />
        Back to Contracts
      </button>
      <p className="mt-2 max-w-3xl text-xs text-gray-400 dark:text-gray-500">
        One record tying together AI risk analysis, human-reviewed findings, regulatory citations, a SHA-256 fingerprint, and an independently verifiable Ethereum anchor.
      </p>

      <div className="mt-6 space-y-6">
        {/* Score Cards -- risk, compliance, evidence, and on-chain anchor
            status together, so the passport reads as one connected record
            rather than four separate facts a viewer has to piece together. */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
          <Card>
            <CardContent className="py-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Risk Score</h3>
                <Shield className="w-5 h-5 text-red-500" />
              </div>
              <div className="text-4xl font-bold text-gray-900 dark:text-gray-100">{passport.risk_score}</div>
              <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden dark:bg-gray-700">
                <div
                  className="h-full bg-red-500 rounded-full transition-all duration-500"
                  style={{ width: `${passport.risk_score}%` }}
                />
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">Out of 100</p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="py-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Compliance Score</h3>
                <CheckCircle className="w-5 h-5 text-green-500" />
              </div>
              <div className="text-4xl font-bold text-gray-900 dark:text-gray-100">{passport.compliance_score}</div>
              <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden dark:bg-gray-700">
                <div
                  className="h-full bg-green-500 rounded-full transition-all duration-500"
                  style={{ width: `${passport.compliance_score}%` }}
                />
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">Out of 100</p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="py-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Evidence Items</h3>
                <FileText className="w-5 h-5 text-blue-500" />
              </div>
              <div className="text-4xl font-bold text-gray-900 dark:text-gray-100">{legalEvidenceCount}</div>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">Supporting artifacts</p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="py-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Ethereum Anchored</h3>
                <Anchor className="w-5 h-5 text-purple-500" />
              </div>
              <div className="text-4xl font-bold text-gray-900 dark:text-gray-100">
                {anchoredCount === null ? '—' : `${anchoredCount}/${legalEvidenceCount}`}
              </div>
              <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden dark:bg-gray-700">
                <div
                  className="h-full bg-purple-500 rounded-full transition-all duration-500"
                  style={{
                    width: `${anchoredCount === null || legalEvidenceCount === 0 ? 0 : (anchoredCount / legalEvidenceCount) * 100}%`,
                  }}
                />
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">Verifiable on Sepolia</p>
            </CardContent>
          </Card>
        </div>

        {/* Provenance chain -- a subtle, business-meaning-first timeline
            (not a crypto-explorer table) connecting every stage this
            passport already represents, using only data already fetched
            above (passport / integrity / anchoredCount). Purely
            presentational: no new requests, no new state. */}
        <Card>
          <CardContent className="py-6">
            <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-5">Provenance Chain</h2>
            <div className="flex flex-wrap gap-x-2 gap-y-4 sm:flex-nowrap sm:overflow-x-auto">
              {provenanceSteps.map((step, index) => {
                const StepIcon = step.icon
                return (
                  <div key={step.key} className="flex items-center">
                    <div className="flex flex-col items-center text-center" style={{ width: '108px' }}>
                      <div
                        className={`flex h-10 w-10 items-center justify-center rounded-full border-2 ${
                          step.done
                            ? 'border-emerald-400 bg-emerald-50 text-emerald-600 dark:border-emerald-600 dark:bg-emerald-950 dark:text-emerald-400'
                            : 'border-gray-200 bg-gray-50 text-gray-400 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-500'
                        }`}
                      >
                        <StepIcon className="h-4.5 w-4.5" />
                      </div>
                      <p className="mt-2 text-xs font-semibold text-gray-800 dark:text-gray-200">{step.label}</p>
                      <p className="mt-0.5 text-[11px] leading-snug text-gray-500 dark:text-gray-400">{step.detail}</p>
                    </div>
                    {index < provenanceSteps.length - 1 && (
                      <div className={`mx-1 h-0.5 w-6 flex-shrink-0 sm:w-10 ${step.done ? 'bg-emerald-300 dark:bg-emerald-700' : 'bg-gray-200 dark:bg-gray-700'}`} />
                    )}
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>

        {/* Tabs */}
        <Card className="overflow-hidden">
          <div className="border-b border-gray-200 dark:border-gray-700">
            <nav className="flex space-x-8 px-6">
              <button
                onClick={() => setActiveTab('overview')}
                className={`py-4 px-1 border-b-2 font-medium text-sm transition ${
                  activeTab === 'overview'
                    ? 'border-[var(--brand-primary,#2563eb)] text-[var(--brand-primary,#1d4ed8)]'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                }`}
              >
                Overview
              </button>
              <button
                onClick={() => setActiveTab('evidence')}
                className={`py-4 px-1 border-b-2 font-medium text-sm transition ${
                  activeTab === 'evidence'
                    ? 'border-[var(--brand-primary,#2563eb)] text-[var(--brand-primary,#1d4ed8)]'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                }`}
              >
                Evidence ({legalEvidenceCount})
              </button>
              <button
                onClick={() => setActiveTab('fingerprint')}
                className={`py-4 px-1 border-b-2 font-medium text-sm transition ${
                  activeTab === 'fingerprint'
                    ? 'border-[var(--brand-primary,#2563eb)] text-[var(--brand-primary,#1d4ed8)]'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                }`}
              >
                Fingerprint
              </button>
            </nav>
          </div>

          <div className="p-6">
            {activeTab === 'overview' && (
              <div className="space-y-6">
                {/* Passport Integrity */}
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Passport Integrity</h2>
                  {integrityLoading && (
                    <Skeleton className="h-24 w-full" />
                  )}
                  {!integrityLoading && integrityError && (
                    <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                      <div className="flex items-center space-x-2 text-red-700 font-semibold">
                        <XCircle className="w-5 h-5" />
                        <span>INTEGRITY CHECK UNAVAILABLE</span>
                      </div>
                      <p className="text-sm text-red-600 mt-2">{integrityError}</p>
                    </div>
                  )}
                  {!integrityLoading && integrity && integrity.verified && (
                    <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                      <div className="flex items-center space-x-2 text-green-700 font-semibold mb-3">
                        <CheckCircle className="w-5 h-5" />
                        <span>PASS / VERIFIED</span>
                      </div>
                      <p className="text-sm text-green-700 mb-4">
                        No claimed snapshot component failed. PASS means the stored fingerprint matched; “not claimed in snapshot” is legacy/unrecomputable, not a silent pass.
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm text-green-800">
                        <div>Document {integrityStatusLabel(integrity.document_verified, integrity.document_status, '').text}</div>
                        <div>Policy {integrityStatusLabel(integrity.policy_verified, integrity.policy_status, '').text}</div>
                        <div>Analysis {integrityStatusLabel(integrity.analysis_verified, integrity.analysis_status, '').text}</div>
                        <div>Evidence {integrityStatusLabel(integrity.evidence_verified, integrity.evidence_status, '').text}</div>
                        <div className="sm:col-span-2">Full Passport {integrityStatusLabel(integrity.passport_hash_verified, integrity.passport_hash_status, '').text}</div>
                      </div>
                    </div>
                  )}
                  {!integrityLoading && integrity && !integrity.verified && (
                    <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                      <div className="flex items-center space-x-2 text-red-700 font-semibold mb-3">
                        <XCircle className="w-5 h-5" />
                        <span>FAIL / INTEGRITY CHECK FAILED</span>
                      </div>
                      <div className="space-y-1 text-sm">
                        {([
                          ['Document', integrity.document_verified, integrity.document_status, '✗ — fingerprint mismatch'],
                          ['Policy', integrity.policy_verified, integrity.policy_status, '✗ — fingerprint mismatch'],
                          ['Analysis', integrity.analysis_verified, integrity.analysis_status, '✗ — fingerprint mismatch'],
                          ['Evidence', integrity.evidence_verified, integrity.evidence_status, '✗ — package mismatch'],
                          ['Full Passport', integrity.passport_hash_verified, integrity.passport_hash_status, '✗ — passport hash mismatch'],
                        ] as const).map(([label, verified, status, mismatch]) => {
                          const line = integrityStatusLabel(verified, status, mismatch)
                          return (
                            <div key={label} className={line.className}>
                              {label} {line.text}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  <PassportRootAnchorPanel
                    passportId={passport.passport_id}
                    integrity={integrity}
                    integrityLoading={integrityLoading}
                    onAnchored={() => fetchIntegrity(passport.passport_id)}
                  />
                </div>

                <IndependentVerificationPanel
                  passportId={passport.passport_id}
                  contractId={passport.contract_id}
                  contractVersion={passport.contract_version}
                  evidence={legalEvidence}
                />

                {/* Passport Info */}
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">Passport Information</h2>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-sm font-medium text-gray-500">Passport ID</label>
                      <p className="text-sm text-gray-900 mt-1 font-mono">{passport.passport_id}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-gray-500">Contract ID</label>
                      <p className="text-sm text-gray-900 mt-1">{passport.contract_id}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-gray-500">Contract Name</label>
                      <p className="text-sm text-gray-900 mt-1">{contract?.name || '—'}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-gray-500">Contract Version</label>
                      <p className="text-sm text-gray-900 mt-1">{passport.contract_version}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-gray-500">Risk Information</label>
                      <p className="text-sm text-gray-900 mt-1">
                        {passport.risk_score}/100{passport.metadata?.risk_level ? ` (${passport.metadata.risk_level})` : ''}
                      </p>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-gray-500">Evidence Count</label>
                      <p className="text-sm text-gray-900 mt-1">{legalEvidenceCount}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-gray-500">Policy Version</label>
                      <p className="text-sm text-gray-900 mt-1">{passport.policy_version}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-gray-500">Created By</label>
                      <p className="text-sm text-gray-900 mt-1">{passport.created_by}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-gray-500">Created At</label>
                      <p className="text-sm text-gray-900 mt-1">{formatTimestamp(passport.created_at)}</p>
                    </div>
                  </div>
                </div>

                {/* Audit Events */}
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">Audit Trail</h2>
                  <div className="space-y-3">
                    {passport.audit_events.map((event, index) => (
                      <div key={index} className="flex items-start space-x-3 p-4 bg-gray-50 rounded-lg">
                        <Clock className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                        <div>
                          <p className="text-sm font-medium text-gray-900">{event.event_type}</p>
                          <p className="text-xs text-gray-500 mt-1">
                            {formatTimestamp(event.timestamp)} • {event.created_by}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'evidence' && (
              <div className="space-y-3">
                <div className="text-sm text-gray-600 mb-4">
                  Evidence ({legalEvidenceCount})
                </div>
                {evidenceLoading && (
                  <div className="space-y-3">
                    <Skeleton className="h-20 w-full" />
                    <Skeleton className="h-20 w-full" />
                  </div>
                )}
                {!evidenceLoading && evidenceError && (
                  <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                    <p className="text-sm text-red-700">{evidenceError}</p>
                    <button
                      type="button"
                      onClick={() => void fetchEvidence(passport.passport_id)}
                      className="mt-3 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
                    >
                      Retry evidence
                    </button>
                  </div>
                )}
                {!evidenceLoading && !evidenceError && legalEvidence.map((item) => {
                  const isExpanded = expandedEvidenceId === item.evidence_id
                  const severity = item.metadata?.finding_severity || 'medium'
                  const sourceSection = item.metadata?.source_section || item.contract_reference
                  const evidenceQuote = item.metadata?.evidence_quote
                  const recommendation = item.metadata?.recommendation
                  const regulatoryCitations: string[] = Array.isArray(item.metadata?.regulatory_citations)
                    ? item.metadata.regulatory_citations
                    : []

                  return (
                    <div
                      key={item.evidence_id}
                      className="border border-gray-200 rounded-lg overflow-hidden hover:border-gray-300 transition-colors"
                    >
                      <button
                        onClick={() => setExpandedEvidenceId(isExpanded ? null : item.evidence_id)}
                        className="w-full p-4 text-left hover:bg-gray-50 transition-colors"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <h3 className="text-base font-semibold text-gray-900">{item.title}</h3>
                            <div className="flex items-center space-x-3 mt-2 flex-wrap gap-2">
                              <span className={`text-xs px-2 py-1 rounded font-medium ${
                                severity === 'high' || severity === 'CRITICAL' ? 'bg-red-100 text-red-800' :
                                severity === 'medium' || severity === 'MEDIUM' ? 'bg-yellow-100 text-yellow-800' :
                                'bg-blue-100 text-blue-800'
                              }`}>
                                {severity}
                              </span>
                              {item.risk_impact != null && (
                                <span className="text-xs px-2.5 py-1 bg-red-50 text-red-700 rounded border border-red-200 font-medium">
                                  Risk Impact: {item.risk_impact.toFixed(0)}
                                </span>
                              )}
                              {item.compliance_impact != null && (
                                <span className="text-xs px-2.5 py-1 bg-green-50 text-green-700 rounded border border-green-200 font-medium">
                                  Compliance Impact: {item.compliance_impact.toFixed(0)}
                                </span>
                              )}
                              {regulatoryCitations.map((citation) => (
                                <span
                                  key={citation}
                                  className="inline-flex items-center gap-1 text-xs px-2.5 py-1 bg-purple-50 text-purple-700 rounded border border-purple-200 font-medium"
                                >
                                  <Scale className="h-3 w-3" />
                                  {citation}
                                </span>
                              ))}
                            </div>
                          </div>
                          <div className="ml-4 text-gray-400">
                            {isExpanded ? '−' : '+'}
                          </div>
                        </div>
                      </button>

                      <div className="flex flex-wrap items-center gap-2 border-t border-gray-100 px-4 py-3 text-xs">
                        <span className="font-medium text-gray-600">Evidence ID:</span>
                        <span className="min-w-0 flex-1 break-all font-mono text-gray-900">{item.evidence_id}</span>
                        <button
                          type="button"
                          onClick={() => void copyEvidenceId(item.evidence_id)}
                          className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-2 py-1 font-medium text-gray-700 hover:bg-gray-100"
                        >
                          <Copy className="h-3.5 w-3.5" />
                          {copiedEvidenceId === item.evidence_id ? 'Copied' : 'Copy Evidence ID'}
                        </button>
                        <button
                          type="button"
                          onClick={() => router.push(`/public-verify?evidence_id=${encodeURIComponent(item.evidence_id)}`)}
                          className="inline-flex items-center gap-1 rounded bg-blue-600 px-2 py-1 font-medium text-white hover:bg-blue-700"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                          Verify Publicly
                        </button>
                      </div>

                      <AnchorProofButton evidenceId={item.evidence_id} />
                      
                      {isExpanded && (
                        <div className="border-t border-gray-200 bg-gray-50 p-4 space-y-4">
                          {item.description && (
                            <div>
                              <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                                Why this is risky
                              </h4>
                              <p className="text-sm text-gray-700 leading-relaxed">{item.description}</p>
                            </div>
                          )}
                          
                          {evidenceQuote && (
                            <div>
                              <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                                Contract Evidence
                              </h4>
                              <p className="text-sm text-gray-700 bg-white p-3 rounded border-l-4 border-blue-300 italic">
                                "{evidenceQuote}"
                              </p>
                            </div>
                          )}
                          
                          {sourceSection && (
                            <div>
                              <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                                Contract Location
                              </h4>
                              <p className="text-sm text-gray-700 font-mono bg-white p-2 rounded">
                                {sourceSection}
                              </p>
                            </div>
                          )}
                          
                          {recommendation && (
                            <div>
                              <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                                Recommendation
                              </h4>
                              <p className="text-sm text-gray-700 leading-relaxed">{recommendation}</p>
                            </div>
                          )}
                          
                          <div className="pt-2 text-xs text-gray-500">
                            <div className="mt-1"><span className="font-medium text-gray-700">Evidence type:</span> {item.evidence_type}</div>
                            <div className="mt-1"><span className="font-medium text-gray-700">Risk / severity:</span> {severity}{item.risk_impact != null ? ` (${item.risk_impact.toFixed(0)}/100)` : ''}</div>
                            <div className="mt-1"><span className="font-medium text-gray-700">Evidence status:</span> {item.evidence_status}</div>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}

                {legalEvidence.length === 0 && (
                  <div className="text-center py-12">
                    <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                    <p className="text-gray-600">No evidence items found</p>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'fingerprint' && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">Document Fingerprint</h2>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <label className="text-sm font-medium text-gray-500">SHA-256 Hash</label>
                    <p className="text-sm text-gray-900 mt-1 font-mono break-all">{passport.document_hash}</p>
                  </div>
                </div>

                <div>
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">Policy Fingerprint</h2>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <label className="text-sm font-medium text-gray-500">SHA-256 Hash</label>
                    <p className="text-sm text-gray-900 mt-1 font-mono break-all">{passport.policy_hash}</p>
                  </div>
                </div>

                <div>
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">Analysis Fingerprint</h2>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <label className="text-sm font-medium text-gray-500">SHA-256 Hash</label>
                    <p className="text-sm text-gray-900 mt-1 font-mono break-all">{passport.analysis_hash}</p>
                  </div>
                </div>

                <div>
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">Evidence Package Fingerprint</h2>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <label className="text-sm font-medium text-gray-500">SHA-256 Hash</label>
                    <p className="text-sm text-gray-900 mt-1 font-mono break-all">{passport.evidence_hash}</p>
                  </div>
                </div>

                <div>
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">Full Passport Hash</h2>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <label className="text-sm font-medium text-gray-500">SHA-256 Hash</label>
                    <p className="text-sm text-gray-900 mt-1 font-mono break-all">
                      {passport.metadata?.passport_hash || 'Unavailable'}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </Card>

      </div>
    </PageContainer>
  )
}

