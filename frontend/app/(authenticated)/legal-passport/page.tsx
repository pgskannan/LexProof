"use client"

import { useState, useEffect, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { Shield, FileText, CheckCircle, AlertTriangle, Info, Clock, ArrowLeft, Copy, ExternalLink, XCircle } from 'lucide-react'
import AnchorProofButton from './components/AnchorProofButton'
import { apiFetch } from '../../../lib/api'
import {
  countLegalEvidenceFindings,
  filterLegalEvidenceFindings,
} from '../../../lib/passport/evidence'

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

interface PassportIntegrityResult {
  verified: boolean
  document_verified: boolean
  policy_verified: boolean
  analysis_verified: boolean
  evidence_verified: boolean
  passport_hash_verified: boolean
}

export default function LegalPassportPage() {
  const router = useRouter()
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

  const legalEvidence = useMemo(() => filterLegalEvidenceFindings(evidence), [evidence])
  const legalEvidenceCount = useMemo(
    () => passport?.evidence_count ?? countLegalEvidenceFindings(evidence),
    [passport?.evidence_count, evidence],
  )

  // Check if contract ID is provided in URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const contractId = params.get('contractId')
    const contractVersion = params.get('contractVersion')

    if (!contractId || !contractVersion) {
      router.push('/dashboard/contracts')
      return
    }

    const version = parseInt(contractVersion, 10)
    setPassportRequest({ contractId, contractVersion: version })
    fetchPassport(contractId, version)
  }, [router])

  const fetchPassport = async (contractId: string, contractVersion: number) => {
    setLoading(true)
    setError('')
    try {
      const response = await apiFetch(`/api/contracts/${contractId}/passport?contract_version=${contractVersion}`)
      if (response.ok) {
        const data = await response.json()
        setPassport(data)
        fetchContract(contractId)
        fetchEvidence(data.passport_id)
        fetchStatistics(data.passport_id)
        fetchIntegrity(data.passport_id)
      } else if (response.status === 401) {
        setError('Your session is still initializing. Please sign in again.')
      } else if (response.status === 404) {
        setError('The legal passport for this contract does not exist.')
      } else {
        const body = await response.json().catch(() => null)
        setError(body?.detail || `Unable to load passport (${response.status})`)
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Unable to load passport')
    } finally {
      setLoading(false)
    }
  }

  const fetchContract = async (contractId: string) => {
    try {
      const response = await apiFetch(`/api/contracts/${contractId}`)
      if (response.ok) setContract(await response.json())
    } catch (error) {
      console.error('Error fetching contract:', error)
    }
  }

  const fetchEvidence = async (passportId: string) => {
    setEvidenceLoading(true)
    setEvidenceError('')
    try {
      const response = await apiFetch(`/api/passports/${passportId}/evidence`)
      if (response.ok) {
        const data = await response.json()
        setEvidence(data)
      } else {
        const body = await response.json().catch(() => null)
        setEvidenceError(body?.detail || `Unable to load evidence (${response.status})`)
      }
    } catch (error) {
      setEvidenceError(error instanceof Error ? error.message : 'Unable to load evidence')
    } finally {
      setEvidenceLoading(false)
    }
  }

  const fetchStatistics = async (passportId: string) => {
    try {
      const response = await apiFetch(`/api/passports/${passportId}/evidence/statistics`)
      if (response.ok) {
        const data = await response.json()
        setStatistics(data)
      }
    } catch (error) {
      console.error('Error fetching statistics:', error)
    }
  }
  const fetchIntegrity = async (passportId: string) => {
    setIntegrityLoading(true)
    setIntegrityError('')
    try {
      const response = await apiFetch(`/api/passports/${passportId}/verify`, {
        method: 'POST',
      })
      if (response.ok) {
        const data = await response.json()
        setIntegrity(data)
      } else {
        const body = await response.json().catch(() => null)
        setIntegrityError(body?.detail || `Integrity check failed (${response.status})`)
      }
    } catch (error) {
      setIntegrityError(error instanceof Error ? error.message : 'Integrity check failed')
    } finally {
      setIntegrityLoading(false)
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

  const copyEvidenceId = async (evidenceId: string) => {
    try {
      await navigator.clipboard.writeText(evidenceId)
      setCopiedEvidenceId(evidenceId)
      window.setTimeout(() => setCopiedEvidenceId(current => current === evidenceId ? null : current), 2000)
    } catch (error) {
      console.error('Unable to copy evidence ID:', error)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading Legal Passport...</p>
        </div>
      </div>
    )
  }

  if (!passport) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <Shield className="w-16 h-16 text-gray-400 mx-auto mb-4" />
          <h2 className="text-2xl font-semibold text-gray-700 mb-2">{error || 'Passport unavailable'}</h2>
          <p className="text-gray-600 mb-4">Check your session or try loading the contract again.</p>
          {passportRequest && (
            <button
              type="button"
              onClick={() => void fetchPassport(passportRequest.contractId, passportRequest.contractVersion)}
              className="px-4 py-2 mr-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
            >
              Retry
            </button>
          )}
          <button
            onClick={() => router.push('/dashboard/contracts')}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
          >
            Back to Contracts
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <button
                onClick={() => router.push('/dashboard/contracts')}
                className="text-blue-600 hover:text-blue-700 mb-2 inline-flex items-center"
              >
                <ArrowLeft className="w-4 h-4 mr-1" />
                Back to Contracts
              </button>
              <h1 className="text-3xl font-bold text-gray-900">Legal Passport</h1>
              <p className="text-gray-600 mt-1">{contract?.name || 'Cryptographically verifiable legal intelligence record'}</p>
            </div>
            <div className="flex items-center space-x-4">
              <div className={`flex items-center space-x-2 px-4 py-2 rounded-lg ${getStatusColor(passport.status)}`}>
                {getStatusIcon(passport.status)}
                <span className={`font-medium capitalize ${getStatusColor(passport.status)}`}>
                  {passport.status}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Score Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-medium text-gray-500">Risk Score</h3>
              <Shield className="w-5 h-5 text-red-500" />
            </div>
            <div className="text-4xl font-bold text-gray-900">{passport.risk_score}</div>
            <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-red-500 rounded-full transition-all duration-500"
                style={{ width: `${passport.risk_score}%` }}
              />
            </div>
            <p className="text-sm text-gray-600 mt-2">Out of 100</p>
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-medium text-gray-500">Compliance Score</h3>
              <CheckCircle className="w-5 h-5 text-green-500" />
            </div>
            <div className="text-4xl font-bold text-gray-900">{passport.compliance_score}</div>
            <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-green-500 rounded-full transition-all duration-500"
                style={{ width: `${passport.compliance_score}%` }}
              />
            </div>
            <p className="text-sm text-gray-600 mt-2">Out of 100</p>
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-medium text-gray-500">Evidence Items</h3>
              <FileText className="w-5 h-5 text-blue-500" />
            </div>
            <div className="text-4xl font-bold text-gray-900">{legalEvidenceCount}</div>
            <p className="text-sm text-gray-600 mt-2">Supporting artifacts</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200">
          <div className="border-b border-gray-200">
            <nav className="flex space-x-8 px-6">
              <button
                onClick={() => setActiveTab('overview')}
                className={`py-4 px-1 border-b-2 font-medium text-sm transition ${
                  activeTab === 'overview'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                Overview
              </button>
              <button
                onClick={() => setActiveTab('evidence')}
                className={`py-4 px-1 border-b-2 font-medium text-sm transition ${
                  activeTab === 'evidence'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                Evidence ({legalEvidenceCount})
              </button>
              <button
                onClick={() => setActiveTab('fingerprint')}
                className={`py-4 px-1 border-b-2 font-medium text-sm transition ${
                  activeTab === 'fingerprint'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
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
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">Passport Integrity</h2>
                  {integrityLoading && (
                    <div className="p-4 bg-gray-50 rounded-lg text-sm text-gray-600">
                      Verifying passport integrity...
                    </div>
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
                        All passport components match the canonical SHA-256 fingerprint.
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm text-green-800">
                        <div>Document ✓</div>
                        <div>Policy ✓</div>
                        <div>Analysis ✓</div>
                        <div>Evidence ✓</div>
                        <div className="sm:col-span-2">Full Passport ✓</div>
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
                        <div className={integrity.document_verified ? 'text-green-700' : 'text-red-700 font-medium'}>
                          Document {integrity.document_verified ? '✓' : '✗ — fingerprint mismatch'}
                        </div>
                        <div className={integrity.policy_verified ? 'text-green-700' : 'text-red-700 font-medium'}>
                          Policy {integrity.policy_verified ? '✓' : '✗ — fingerprint mismatch'}
                        </div>
                        <div className={integrity.analysis_verified ? 'text-green-700' : 'text-red-700 font-medium'}>
                          Analysis {integrity.analysis_verified ? '✓' : '✗ — fingerprint mismatch'}
                        </div>
                        <div className={integrity.evidence_verified ? 'text-green-700' : 'text-red-700 font-medium'}>
                          Evidence {integrity.evidence_verified ? '✓' : '✗ — package mismatch'}
                        </div>
                        <div className={integrity.passport_hash_verified ? 'text-green-700' : 'text-red-700 font-medium'}>
                          Full Passport {integrity.passport_hash_verified ? '✓' : '✗ — passport hash mismatch'}
                        </div>
                      </div>
                    </div>
                  )}
                </div>

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
                      <p className="text-sm text-gray-900 mt-1">{contract?.name || 'Loading contract name...'}</p>
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
                  <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-600">
                    Loading evidence...
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
        </div>

      </div>
    </div>
  )
}

