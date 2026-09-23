export const COUNTERPARTY_ATTESTATION =
  'I have reviewed this redline and agree to be bound by it'

export type CreateCounterpartyLinkBody = {
  redline_proposal_id: string
  counterparty_name: string
  counterparty_email: string
  expires_in_days?: number
}

export function createCounterpartyLinkRequest(
  orgId: string,
  contractId: string,
  body: CreateCounterpartyLinkBody,
) {
  return {
    path: `/api/orgs/${encodeURIComponent(orgId)}/contracts/${encodeURIComponent(contractId)}/counterparty-links`,
    method: 'POST' as const,
    body,
  }
}

export function listCounterpartyLinksPath(orgId: string, contractId: string, proposalId: string) {
  const query = new URLSearchParams({ redline_proposal_id: proposalId })
  return `/api/orgs/${encodeURIComponent(orgId)}/contracts/${encodeURIComponent(contractId)}/counterparty-links?${query.toString()}`
}

export function counterpartyShareUrl(token: string, origin?: string): string {
  const base = (origin || (typeof window !== 'undefined' ? window.location.origin : '')).replace(/\/$/, '')
  return `${base}/counterparty/${encodeURIComponent(token)}`
}

export function externalAccessPath(token: string): string {
  return `/api/external/${encodeURIComponent(token)}`
}

export function externalCommentPath(token: string): string {
  return `/api/external/${encodeURIComponent(token)}/comment`
}

export function externalCountersignPath(token: string): string {
  return `/api/external/${encodeURIComponent(token)}/countersign`
}

export function sendCounterpartyEsignatureRequest(orgId: string, contractId: string, tokenId: string) {
  return {
    path: `/api/orgs/${encodeURIComponent(orgId)}/contracts/${encodeURIComponent(contractId)}/counterparty-links/${encodeURIComponent(tokenId)}/esignature`,
    method: 'POST' as const,
  }
}

export function simulateCounterpartyEsignatureRequest(
  orgId: string,
  contractId: string,
  tokenId: string,
  decline = false,
) {
  return {
    path: `/api/orgs/${encodeURIComponent(orgId)}/contracts/${encodeURIComponent(contractId)}/counterparty-links/${encodeURIComponent(tokenId)}/esignature/simulate`,
    method: 'POST' as const,
    body: { decline },
  }
}
