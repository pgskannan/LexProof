'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { CheckCircle2, UploadCloud, XCircle } from 'lucide-react';
import { apiFetch } from '../../../../../lib/api';
import {
  analyzeVersionRequest,
  proposalPublishRequest,
  proposalReviewRequest,
} from '../../../../../lib/redlineProposals';
import { Badge } from '../../../../../components/ui/badge';
import { Button } from '../../../../../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../../../components/ui/card';
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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Contract Reviews</h1>
        <p className="mt-2 text-gray-600">
          Approve, reject, and publish AI-proposed redlines. Every decision is recorded against the proposal and
          becomes part of the contract&apos;s evidence trail.
        </p>
      </div>

      <div className="rounded-lg bg-white p-6 shadow">
        <label className="text-sm font-medium text-gray-700">
          Contract
          <select
            value={contractId}
            onChange={(event) => selectContract(event.target.value)}
            className="mt-2 block w-full max-w-xl rounded border border-gray-300 px-3 py-2 font-normal"
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
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
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
          title="No redline proposals yet"
          description="Open AI Findings for this contract, save a proposed clause, and it will appear here for human review."
          actionLabel="Open findings"
          onAction={() => router.push(`/dashboard/ai-analysis/findings?contract_id=${encodeURIComponent(contractId)}`)}
        />
      )}

      <div className="space-y-4">
        {proposals.map((proposal) => (
          <Card key={proposal.proposal_id}>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>{proposal.title || 'Untitled finding'}</CardTitle>
                  <CardDescription className="mt-1 break-all font-mono">{proposal.proposal_id}</CardDescription>
                </div>
                <div className="flex flex-wrap gap-2">
                  {proposal.severity && <Badge variant={severityVariant(proposal.severity)}>{proposal.severity}</Badge>}
                  <Badge variant={statusVariant(proposal.status)}>{proposal.status}</Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {(proposal.reason || proposal.recommendation) && (
                <div className="space-y-1 text-sm text-gray-700">
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

              <ClauseDiff originalText={proposal.original_text} proposedText={proposal.proposed_text} />

              {proposal.evidence_id && (
                <p className="break-all font-mono text-xs text-gray-500">Evidence: {proposal.evidence_id}</p>
              )}

              {proposal.review && (
                <div className="rounded border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">
                  <p>
                    <span className="font-semibold">{proposal.review.decision}</span> by {proposal.review.reviewer_id}{' '}
                    on {new Date(proposal.review.created_at).toLocaleString()}
                  </p>
                  {proposal.review.comment && <p className="mt-1 italic">&quot;{proposal.review.comment}&quot;</p>}
                </div>
              )}

              {proposal.published_version_id && proposal.analysis_status === 'complete' && (
                <div className="rounded border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
                  Published as version <span className="font-mono">{proposal.published_version_id}</span> by{' '}
                  {proposal.published_by || 'an unknown publisher'} on{' '}
                  {proposal.published_at ? new Date(proposal.published_at).toLocaleString() : 'an unknown date'}. Evidence
                  anchored on-chain.
                </div>
              )}

              {proposal.published_version_id && proposal.analysis_status !== 'complete' && (
                <div className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                  <p>
                    Published as version <span className="font-mono">{proposal.published_version_id}</span> by{' '}
                    {proposal.published_by || 'an unknown publisher'} on{' '}
                    {proposal.published_at ? new Date(proposal.published_at).toLocaleString() : 'an unknown date'}.
                  </p>
                  <p className="mt-1 font-medium">
                    Published successfully. Evidence anchoring is processing.
                  </p>
                  <Button
                    variant="outline"
                    className="mt-3"
                    disabled={busyId === proposal.proposal_id}
                    onClick={() => void retryAnalysis(proposal)}
                  >
                    {busyId === proposal.proposal_id ? 'Retrying...' : 'Retry evidence anchoring'}
                  </Button>
                </div>
              )}

              {isReviewable(proposal) && canReview && (
                <div className="space-y-3 border-t border-gray-100 pt-4">
                  <label className="block text-sm font-medium text-gray-700">
                    Review comment (optional)
                    <textarea
                      value={comments[proposal.proposal_id] || ''}
                      onChange={(event) =>
                        setComments((prev) => ({ ...prev, [proposal.proposal_id]: event.target.value }))
                      }
                      className="mt-2 block w-full rounded border border-gray-300 px-3 py-2 text-sm font-normal"
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

              {isPublishable(proposal) && canPublish && (
                <div className="border-t border-gray-100 pt-4">
                  <Button
                    variant="default"
                    disabled={busyId === proposal.proposal_id}
                    onClick={() => void publishProposal(proposal)}
                  >
                    <UploadCloud className="h-4 w-4" />
                    {busyId === proposal.proposal_id ? 'Publishing...' : 'Publish as new version'}
                  </Button>
                </div>
              )}

              {canShare && currentOrg?.org_id && (
                <ShareWithCounterparty
                  orgId={currentOrg.org_id}
                  contractId={proposal.contract_id}
                  proposalId={proposal.proposal_id}
                />
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
