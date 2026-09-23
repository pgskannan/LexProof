'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { CheckCircle2, Link2, UploadCloud, XCircle } from 'lucide-react';
import { apiFetch } from '../../../../../lib/api';
import {
  analyzeVersionRequest,
  escalateOverdueWorkflowsRequest,
  proposalPublishRequest,
  proposalReviewRequest,
} from '../../../../../lib/redlineProposals';
import { Badge } from '../../../../../components/ui/badge';
import { Button } from '../../../../../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../../../components/ui/card';
import { PageHeader } from '../../../../../components/ui/page-header';
import { PageContainer } from '../../../../../components/ui/container';
import { ClauseDiff } from '../../../../../components/ClauseDiff';
import { EmptyState } from '../../../../../components/EmptyState';
import { ShareWithCounterparty } from '../../../../../components/ShareWithCounterparty';
import { Skeleton } from '../../../../../components/ui/skeleton';
import { hasRole, isAdmin } from '../../../../../lib/roles';
import { useOrg } from '../../../../../components/OrgProvider';
import { toast } from 'sonner';

type ContractSummary = {
  contract_id: string;
  name?: string | null;
  version?: number | null;
};

type ProposalReview = {
  review_id: string;
  decision: string;
  reviewer_id: string;
  comment?: string | null;
  created_at: string;
};

type Proposal = {
  proposal_id: string;
  contract_id: string;
  source_version_id: string;
  finding_id: string;
  evidence_id?: string | null;
  title?: string | null;
  severity?: string | null;
  original_text: string;
  proposed_text: string;
  recommendation?: string | null;
  reason?: string | null;
  status: string;
  created_by: string;
  created_at: string;
  review?: ProposalReview | null;
  published_version_id?: string | null;
  published_by?: string | null;
  published_at?: string | null;
  analysis_status?: string | null;
  sla_due_at?: string | null;
  is_overdue?: boolean;
  publication_status?: string | null;
  passport_status?: string | null;
  evidence_count?: number;
  anchored_evidence_count?: number;
  proof_status?: 'processing' | 'confirmed' | 'failed' | 'action_required' | null;
  recommended_action?: 'none' | 'wait' | 'retry' | null;
};

function severityVariant(severity?: string | null) {
  const key = (severity || '').toLowerCase();
  if (key === 'critical') return 'critical' as const;
  if (key === 'high') return 'high' as const;
  if (key === 'medium') return 'medium' as const;
  if (key === 'low') return 'low' as const;
  return 'secondary' as const;
}

function statusVariant(status: string) {
  if (status === 'APPROVED' || status === 'PUBLISHED') return 'verified' as const;
  if (status === 'REJECTED') return 'tampered' as const;
  return 'pending' as const;
}

function isReviewable(proposal: Proposal) {
  return !['APPROVED', 'REJECTED', 'PUBLISHED'].includes(proposal.status);
}

function isPublishable(proposal: Proposal) {
  return proposal.status === 'APPROVED' && !proposal.published_version_id;
}

function dueLabel(proposal: Proposal): string | null {
  if (!proposal.sla_due_at || !isReviewable(proposal)) return null;
  const due = new Date(proposal.sla_due_at);
  if (Number.isNaN(due.getTime())) return null;
  return due.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function formatContractId(value: string) {
  if (!value || value.length <= 16) return value;
  return `${value.slice(0, 8)}…${value.slice(-6)}`;
}

export default function ContractReviews() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { roles, currentOrg } = useOrg();
  const canReview = isAdmin(roles) || hasRole(roles, 'reviewer');
  const canPublish = isAdmin(roles) || hasRole(roles, 'approver');
  const canShare = isAdmin(roles) || hasRole(roles, 'contract_owner');
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [contractsLoading, setContractsLoading] = useState(true);
  const [contractId, setContractId] = useState('');
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [proposalsLoading, setProposalsLoading] = useState(false);
  const [error, setError] = useState('');
  const [comments, setComments] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    setContractsLoading(true);
    void apiFetch('/api/contracts')
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load contracts');
        const records: ContractSummary[] = await response.json();
        setContracts(records);
        const queryId = searchParams.get('contractId');
        if (queryId) {
          setContractId(queryId);
        } else if (records.length) {
          setContractId(records[0].contract_id);
        }
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Unable to load contracts'))
      .finally(() => setContractsLoading(false));
    // Only run once on mount: the picker below is the source of truth for
    // subsequent changes, and re-running this on every searchParams change
    // would stomp a manual selection back to the URL's original contractId.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadProposals = useCallback(async (id: string) => {
    if (!id) {
      setProposals([]);
      return;
    }
    setProposalsLoading(true);
    setError('');
    try {
      const response = await apiFetch(`/api/contracts/${encodeURIComponent(id)}/redline-proposals`);
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load redline proposals');
      setProposals(await response.json());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load redline proposals');
    } finally {
      setProposalsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProposals(contractId);
  }, [contractId, loadProposals]);

  useEffect(() => {
    // Best-effort SLA-escalation sweep: this page is where a reviewer looks
    // for pending approvals, so opening it doubles as the trigger for
    // notifying admins about anything overdue. Never blocks or errors the
    // page -- a production deployment would instead (or additionally) have
    // an external scheduler hit this same endpoint on a timer.
    const orgId = currentOrg?.org_id;
    if (!orgId) return;
    const request = escalateOverdueWorkflowsRequest(orgId);
    void apiFetch(request.path, { method: request.method })
      .then(async (response) => {
        if (!response.ok) return;
        const body: { count?: number } = await response.json().catch(() => ({}));
        if (body.count) {
          toast.warning(`${body.count} overdue review${body.count === 1 ? '' : 's'} escalated to admins`);
        }
      })
      .catch(() => {
        /* background convenience only */
      });
  }, [currentOrg?.org_id]);

  function selectContract(id: string) {
    setContractId(id);
    const params = new URLSearchParams(Array.from(searchParams.entries()));
    if (id) params.set('contractId', id);
    else params.delete('contractId');
    router.replace(`/dashboard/contracts/reviews?${params.toString()}`);
  }

  async function submitReview(proposal: Proposal, decision: 'APPROVED' | 'REJECTED') {
    if (decision === 'REJECTED') {
      const confirmed = window.confirm(
        'Reject this redline proposal? This is a final decision and cannot be undone from this screen.',
      );
      if (!confirmed) return;
    }
    setBusyId(proposal.proposal_id);
    setError('');
    try {
      const request = proposalReviewRequest(proposal.proposal_id, decision, comments[proposal.proposal_id] || '');
      const response = await apiFetch(request.path, {
        method: request.method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request.body),
      });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to record review decision');
      toast.success(decision === 'APPROVED' ? 'Redline approved' : 'Redline rejected');
      await loadProposals(contractId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to record review decision');
    } finally {
      setBusyId(null);
    }
  }

  async function publishProposal(proposal: Proposal) {
    const confirmed = window.confirm(
      'Publish this approved redline as a new contract version? This creates an immutable version and cannot be undone from this screen.',
    );
    if (!confirmed) return;
    setBusyId(proposal.proposal_id);
    setError('');
    try {
      const request = proposalPublishRequest(proposal.proposal_id);
      const response = await apiFetch(request.path, { method: request.method });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to publish proposal');
      toast.success('Redline published as a new version');
      // A successful publish response means the new version and the proposal's
      // PUBLISHED status are already committed, even if response.analysis_status
      // comes back 'failed' (evidence anchoring can be slow/unreliable on Sepolia).
      // That is surfaced as an informational state below, never as an error here.
      await loadProposals(contractId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to publish proposal');
    } finally {
      setBusyId(null);
    }
  }

  async function retryAnalysis(proposal: Proposal) {
    if (!proposal.published_version_id) return;
    const confirmed = window.confirm(
      'Re-run analysis and evidence anchoring for this published version? This can take a while.',
    );
    if (!confirmed) return;
    setBusyId(proposal.proposal_id);
    setError('');
    try {
      const request = analyzeVersionRequest(proposal.contract_id, proposal.published_version_id);
      const response = await apiFetch(request.path, { method: request.method });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to retry evidence anchoring');
      await loadProposals(contractId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to retry evidence anchoring');
    } finally {
      setBusyId(null);
    }
  }

  const selectedContract = contracts.find((item) => item.contract_id === contractId) || null;

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Workspace"
        title="Contract Review"
        description="Approve, reject, and publish AI-proposed redlines. Every decision is recorded against the proposal and becomes part of the contract's evidence trail."
      />

      <div className="mt-6 space-y-6">
        <Card>
          <CardContent className="py-4">
            <label className="space-y-1 text-sm font-medium text-gray-700 dark:text-gray-300">
              <span>Contract</span>
              <select
                value={contractId}
                onChange={(event) => selectContract(event.target.value)}
                className="block w-full max-w-xl rounded-[var(--radius-md,0.5rem)] border border-gray-300 bg-white px-3 py-2 font-normal text-gray-900 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
                disabled={contractsLoading || contracts.length === 0}
              >
                {contractsLoading && <option value="">Loading contracts…</option>}
                {!contractsLoading && contracts.length === 0 && <option value="">No contracts available</option>}
                {contracts.map((contract) => (
                  <option key={contract.contract_id} value={contract.contract_id}>
                    {(contract.name || contract.contract_id) + (contract.version ? ` (V${contract.version})` : '')}
                  </option>
                ))}
              </select>
            </label>
            {selectedContract && (
              <p className="mt-2 font-mono text-[11px] text-gray-400 dark:text-gray-500" title={selectedContract.contract_id}>
                {formatContractId(selectedContract.contract_id)}
              </p>
            )}
          </CardContent>
        </Card>

        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}

        {proposalsLoading && (
          <div className="space-y-3">
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-48 w-full" />
          </div>
        )}

        {!proposalsLoading && contractId && proposals.length === 0 && (
          <EmptyState
            compact
            title="No redline proposals yet"
            description="Open AI Findings for this contract and save a proposed clause. Approved proposals will appear here for human review."
            actionLabel="Open findings"
            onAction={() => router.push(`/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(contractId)}`)}
          />
        )}

        <div className="space-y-6">
          {proposals.map((proposal) => (
            <Card key={proposal.proposal_id}>
              <CardHeader>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Finding</p>
                    <CardTitle>{proposal.title || 'Untitled finding'}</CardTitle>
                    <CardDescription className="mt-1 break-all font-mono">{proposal.proposal_id}</CardDescription>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {proposal.severity && <Badge variant={severityVariant(proposal.severity)}>{proposal.severity}</Badge>}
                    <Badge variant={statusVariant(proposal.status)}>{proposal.status}</Badge>
                    {proposal.is_overdue && <Badge variant="tampered">Overdue</Badge>}
                    {!proposal.is_overdue && dueLabel(proposal) && (
                      <Badge variant="pending">Due {dueLabel(proposal)}</Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-6">
                {(proposal.reason || proposal.recommendation) && (
                  <div className="space-y-1 text-sm text-gray-700 dark:text-gray-300">
                    {proposal.reason && (
                      <p>
                        <span className="font-semibold">Why it matters: </span>
                        {proposal.reason}
                      </p>
                    )}
                    {proposal.recommendation && (
                      <p>
                        <span className="font-semibold">Recommendation: </span>
                        {proposal.recommendation}
                      </p>
                    )}
                  </div>
                )}

                <div>
                  <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
                    <Link2 className="h-3.5 w-3.5" />
                    Source Evidence
                  </p>
                  {proposal.evidence_id ? (
                    <p className="break-all font-mono text-xs text-gray-500 dark:text-gray-400">{proposal.evidence_id}</p>
                  ) : (
                    <p className="text-xs text-gray-400 dark:text-gray-500">No evidence record linked to this finding yet.</p>
                  )}
                </div>

                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
                    Original Clause vs. Proposed Redline
                  </p>
                  <ClauseDiff originalText={proposal.original_text} proposedText={proposal.proposed_text} />
                </div>

                {proposal.review && (
                  <div className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-900/40 dark:text-gray-300">
                    <p>
                      <span className="font-semibold">{proposal.review.decision}</span> by {proposal.review.reviewer_id}{' '}
                      on {new Date(proposal.review.created_at).toLocaleString()}
                    </p>
                    {proposal.review.comment && <p className="mt-1 italic">&quot;{proposal.review.comment}&quot;</p>}
                  </div>
                )}

                {(proposal.published_version_id || isPublishable(proposal)) && (
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
                      Publication &amp; Evidence
                    </p>
                    {proposal.published_version_id && proposal.proof_status === 'confirmed' && (
                      <div className="rounded-[var(--radius-md,0.5rem)] border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 dark:border-blue-900/50 dark:bg-blue-950/30 dark:text-blue-300">
                        Published as version <span className="font-mono">{proposal.published_version_id}</span> by{' '}
                        {proposal.published_by || 'an unknown publisher'} on{' '}
                        {proposal.published_at ? new Date(proposal.published_at).toLocaleString() : 'an unknown date'}. Evidence
                        <span className="mt-1 block font-medium">Confirmed. Proof verified from persisted evidence anchors.</span>
                      </div>
                    )}

                    {proposal.published_version_id && proposal.proof_status !== 'confirmed' && (
                      <div className="rounded-[var(--radius-md,0.5rem)] border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
                        <p>
                          Published as version <span className="font-mono">{proposal.published_version_id}</span> by{' '}
                          {proposal.published_by || 'an unknown publisher'} on{' '}
                          {proposal.published_at ? new Date(proposal.published_at).toLocaleString() : 'an unknown date'}.
                        </p>
                        <p className="mt-1 font-medium">
                          {proposal.proof_status === 'processing'
                            ? 'Published successfully. Analysis and evidence verification are processing.'
                            : proposal.proof_status === 'failed'
                              ? 'Published successfully, but processing failed before proof confirmation.'
                              : 'Published successfully, but proof is incomplete or inconsistent.'}
                        </p>
                        {proposal.recommended_action === 'retry' && (
                          <Button
                            variant="outline"
                            className="mt-3"
                            disabled={busyId === proposal.proposal_id}
                            onClick={() => void retryAnalysis(proposal)}
                          >
                            {busyId === proposal.proposal_id ? 'Retrying...' : 'Retry analysis'}
                          </Button>
                        )}
                      </div>
                    )}

                    {isPublishable(proposal) && canPublish && (
                      <Button
                        variant="default"
                        disabled={busyId === proposal.proposal_id}
                        onClick={() => void publishProposal(proposal)}
                      >
                        <UploadCloud className="h-4 w-4" />
                        {busyId === proposal.proposal_id ? 'Publishing...' : 'Publish as new version'}
                      </Button>
                    )}
                  </div>
                )}

                {isReviewable(proposal) && canReview && (
                  <div className="space-y-3 border-t border-gray-100 pt-5 dark:border-gray-700">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Review Decision</p>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      Review comment (optional)
                      <textarea
                        value={comments[proposal.proposal_id] || ''}
                        onChange={(event) =>
                          setComments((prev) => ({ ...prev, [proposal.proposal_id]: event.target.value }))
                        }
                        className="mt-2 block w-full rounded-[var(--radius-md,0.5rem)] border border-gray-300 px-3 py-2 text-sm font-normal text-gray-900 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
                        rows={2}
                        placeholder="Add context for this decision (optional)"
                      />
                    </label>
                    <div className="flex flex-wrap gap-3">
                      <Button
                        variant="default"
                        disabled={busyId === proposal.proposal_id}
                        onClick={() => void submitReview(proposal, 'APPROVED')}
                      >
                        <CheckCircle2 className="h-4 w-4" />
                        {busyId === proposal.proposal_id ? 'Saving...' : 'Approve'}
                      </Button>
                      <Button
                        variant="destructive"
                        disabled={busyId === proposal.proposal_id}
                        onClick={() => void submitReview(proposal, 'REJECTED')}
                      >
                        <XCircle className="h-4 w-4" />
                        {busyId === proposal.proposal_id ? 'Saving...' : 'Reject'}
                      </Button>
                    </div>
                  </div>
                )}

                {canShare && currentOrg?.org_id && (
                  <div className="border-t border-gray-100 pt-5 dark:border-gray-700">
                    <ShareWithCounterparty
                      orgId={currentOrg.org_id}
                      contractId={proposal.contract_id}
                      proposalId={proposal.proposal_id}
                    />
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </PageContainer>
  );
}
