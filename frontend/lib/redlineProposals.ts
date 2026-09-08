export function proposalQuery(findingId: string, versionId: string): string {
  const query = new URLSearchParams({ finding_id: findingId });
  if (versionId) query.set('version_id', versionId);
  return query.toString();
}

export function proposalSaveRequest(proposalId: string | null, proposedText: string) {
  return proposalId
    ? { path: `/api/redline-proposals/${encodeURIComponent(proposalId)}`, method: 'PATCH', body: { proposed_text: proposedText } }
    : { path: '/api/contracts/{contract_id}/redline-proposals', method: 'POST', body: { proposed_text: proposedText } };
}

export function proposalReviewRequest(proposalId: string, decision: 'APPROVED' | 'REJECTED', comment: string) {
  return {
    path: `/api/redline-proposals/${encodeURIComponent(proposalId)}/review`,
    method: 'POST',
    body: { decision, comment },
  };
}

export function proposalPublishRequest(proposalId: string) {
  return { path: `/api/redline-proposals/${encodeURIComponent(proposalId)}/publish`, method: 'POST' };
}

export function analyzeVersionRequest(contractId: string, versionId: string) {
  return { path: `/api/contracts/${encodeURIComponent(contractId)}/versions/${encodeURIComponent(versionId)}/analyze`, method: 'POST' };
}