export type LifecycleStageStatus = 'complete' | 'active' | 'pending' | 'failed' | 'unavailable'
export type PublishedProofStatus = 'processing' | 'confirmed' | 'failed' | 'action_required'
export type RecommendedAction = 'none' | 'wait' | 'retry'

export type PublishedVersionStatus = {
  publication_status?: string | null
  analysis_status?: string | null
  passport_status?: string | null
  evidence_count?: number | null
  anchored_evidence_count?: number | null
  proof_status?: PublishedProofStatus | null
  recommended_action?: RecommendedAction | null
}

export type ContractVersion = {
  version_id: string
  version_number: number
  parent_version_id?: string | null
  created_at?: string | null
  created_by?: string | null
  analysis_status?: string | null
  passport_id?: string | null
  passport_status?: string | null
  published?: boolean
  is_current?: boolean
} & PublishedVersionStatus

export type LifecycleProposal = {
  proposal_id: string
  status: string
  source_version_id?: string | null
  published_version_id?: string | null
  workflow_instance_id?: string | null
  review?: {
    decision: string
    reviewer_id?: string | null
    comment?: string | null
    created_at?: string | null
  } | null
} & PublishedVersionStatus

export type LifecyclePassport = {
  passport_id: string
  contract_version: number
  status?: string | null
  evidence_count?: number | null
} & PublishedVersionStatus

export type LifecycleAnchor = {
  evidence_id: string
  transaction_hash?: string | null
  block_number?: number | null
  blockchain_network?: string | null
  evidence_hash?: string | null
  // Hybrid Anchoring (proposed architecture, see hackathon-polish-roadmap.md #1).
  // Real anchors are always 'SINGLE_HASH'; 'MERKLE_BATCH' only comes from the
  // demo script (scripts/create_merkle_batch_demo_anchor.py) and is is_mock: true.
  anchoring_method?: 'SINGLE_HASH' | 'MERKLE_BATCH' | null
  is_mock?: boolean
  batch_id?: string | null
  batch_size?: number | null
  merkle_root?: string | null
}

export type LifecycleData = {
  contract: {
    contract_id: string
    name?: string | null
    version?: number | null
    analysis_status?: string | null
    passport_id?: string | null
    evidence_count?: number | null
  } & PublishedVersionStatus
  versions: ContractVersion[]
  findingsCount: number
  proposals: LifecycleProposal[]
  passports: LifecyclePassport[]
  anchoredEvidenceCount: number
  evidenceCount: number
  anchors: LifecycleAnchor[]
}

export type LifecycleStage = {
  key: string
  label: string
  status: LifecycleStageStatus
  detail: string
  href?: string
}

function statusForAnalysis(status?: string | null): LifecycleStageStatus {
  if (status === 'complete') return 'complete'
  if (status === 'processing') return 'active'
  if (status === 'failed') return 'failed'
  return 'pending'
}

export function publishedProofStatus(data: LifecycleData): PublishedProofStatus {
  const current = data.versions.find((version) => version.is_current) ?? data.versions.at(-1)
  const proposal = data.proposals.find((item) => item.published_version_id === current?.version_id)
  return current?.proof_status ?? proposal?.proof_status ?? data.contract.proof_status ?? 'action_required'
}

export function proofStatusLabel(status: PublishedProofStatus): string {
  if (status === 'confirmed') return 'Confirmed'
  if (status === 'processing') return 'Processing'
  if (status === 'failed') return 'Failed'
  return 'Action Required'
}

export function lifecycleStages(data: LifecycleData): LifecycleStage[] {
  const current = data.versions.find((version) => version.is_current) ?? data.versions.at(-1)
  const currentAnalysis = current?.analysis_status ?? data.contract.analysis_status
  const currentPassport = data.passports.find((passport) => passport.contract_version === current?.version_number)
  const normalizedProposalStatus = (status?: string | null) => (status ?? '').toUpperCase()
  const openProposal = data.proposals.find((proposal) => !['PUBLISHED', 'REJECTED'].includes(normalizedProposalStatus(proposal.status)))
  const approvedProposal = data.proposals.find((proposal) => normalizedProposalStatus(proposal.status) === 'APPROVED' || normalizedProposalStatus(proposal.review?.decision) === 'APPROVED')
  const rejectedProposal = data.proposals.find((proposal) => normalizedProposalStatus(proposal.status) === 'REJECTED' || normalizedProposalStatus(proposal.review?.decision) === 'REJECTED')
  const publishedProposal = data.proposals.find((proposal) => proposal.published_version_id || normalizedProposalStatus(proposal.status) === 'PUBLISHED')
  const inReviewProposal = data.proposals.find((proposal) => normalizedProposalStatus(proposal.status) === 'PROPOSED' || normalizedProposalStatus(proposal.status) === 'DRAFT' || (!proposal.review?.decision && !!proposal.workflow_instance_id))
  const reviewStatus = publishedProposal || approvedProposal || rejectedProposal ? 'complete' : inReviewProposal ? 'active' : data.proposals.length ? 'pending' : 'pending'
  const reviewDetail = publishedProposal?.published_version_id
    || approvedProposal?.review?.decision
    || rejectedProposal?.review?.decision
    || (inReviewProposal ? 'Pending review' : 'Pending review')
  const analysisStatus = statusForAnalysis(currentAnalysis)
  const proofStatus = publishedProofStatus(data)
  const evidenceComplete = data.evidenceCount > 0 || (currentPassport?.evidence_count ?? 0) > 0

  return [
    { key: 'uploaded', label: 'Contract uploaded', status: data.contract.contract_id ? 'complete' : 'unavailable', detail: data.contract.name || 'Name not available', href: '/dashboard/contracts' },
    { key: 'analysis', label: 'AI analysis', status: statusForAnalysis(data.versions[0]?.analysis_status ?? data.contract.analysis_status), detail: data.versions[0]?.analysis_status || 'Status not available', href: `/dashboard/contracts/versions?contractId=${encodeURIComponent(data.contract.contract_id)}` },
    { key: 'findings', label: 'Findings', status: data.findingsCount > 0 ? 'complete' : 'pending', detail: data.findingsCount ? `${data.findingsCount} persisted finding${data.findingsCount === 1 ? '' : 's'}` : 'No findings recorded', href: `/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(data.contract.contract_id)}` },
    { key: 'redline', label: 'Redline', status: openProposal || data.proposals.length ? 'complete' : 'pending', detail: openProposal ? openProposal.status : 'No proposal recorded', href: `/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(data.contract.contract_id)}` },
    { key: 'review', label: 'Human review', status: reviewStatus, detail: reviewDetail, href: '/dashboard/contracts/reviews' },
    { key: 'publication', label: 'Published V2', status: publishedProposal ? 'complete' : approvedProposal ? 'active' : 'pending', detail: publishedProposal?.published_version_id || (approvedProposal ? 'Ready to publish' : 'Not published'), href: publishedProposal ? `/dashboard/contracts/versions?contractId=${encodeURIComponent(data.contract.contract_id)}` : '/dashboard/contracts/reviews' },
    { key: 'v2-analysis', label: 'V2 analysis', status: current?.version_number && current.version_number > 1 ? proofStatus === 'confirmed' ? 'complete' : proofStatus === 'processing' ? 'active' : proofStatus === 'failed' ? 'failed' : analysisStatus : 'pending', detail: current?.version_number && current.version_number > 1 ? proofStatusLabel(proofStatus) : 'Waiting for V2', href: `/dashboard/contracts/versions?contractId=${encodeURIComponent(data.contract.contract_id)}` },
    { key: 'passport', label: 'Legal Passport', status: currentPassport?.status === 'created' || currentPassport?.passport_status === 'created' || data.contract.passport_status === 'created' ? 'complete' : 'pending', detail: currentPassport?.passport_id || data.contract.passport_id || 'Not created', href: currentPassport ? `/legal-passport?contractId=${encodeURIComponent(data.contract.contract_id)}&contractVersion=${currentPassport.contract_version}` : undefined },
    { key: 'evidence', label: 'Evidence', status: evidenceComplete ? 'complete' : 'pending', detail: evidenceComplete ? `${data.evidenceCount} evidence records` : 'Not available', href: currentPassport ? `/legal-passport?contractId=${encodeURIComponent(data.contract.contract_id)}&contractVersion=${currentPassport.contract_version}` : undefined },
    { key: 'anchor', label: 'Blockchain anchored', status: proofStatus === 'confirmed' ? 'complete' : proofStatus === 'processing' ? 'active' : proofStatus === 'failed' ? 'failed' : data.evidenceCount ? 'pending' : 'pending', detail: data.evidenceCount ? `${data.anchoredEvidenceCount}/${data.evidenceCount} anchored` : 'Not available', href: '/dashboard/verification' },
    { key: 'verify', label: 'Public verification', status: data.anchoredEvidenceCount > 0 ? 'complete' : 'pending', detail: data.anchoredEvidenceCount > 0 ? 'Anchored evidence can be verified' : 'Waiting for an anchor', href: '/public-verify' },
  ]
}
