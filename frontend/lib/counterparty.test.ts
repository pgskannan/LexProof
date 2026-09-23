import { describe, expect, it } from 'vitest'
import {
  COUNTERPARTY_ATTESTATION,
  counterpartyShareUrl,
  createCounterpartyLinkRequest,
  externalAccessPath,
  externalCommentPath,
  externalCountersignPath,
  listCounterpartyLinksPath,
  sendCounterpartyEsignatureRequest,
  simulateCounterpartyEsignatureRequest,
} from './counterparty'

describe('counterparty access helpers', () => {
  it('builds an org-scoped create request', () => {
    expect(
      createCounterpartyLinkRequest('org 1', 'contract 1', {
        redline_proposal_id: 'proposal-1',
        counterparty_name: 'Jordan Chen',
        counterparty_email: 'jordan@example.com',
        expires_in_days: 7,
      }),
    ).toEqual({
      path: '/api/orgs/org%201/contracts/contract%201/counterparty-links',
      method: 'POST',
      body: {
        redline_proposal_id: 'proposal-1',
        counterparty_name: 'Jordan Chen',
        counterparty_email: 'jordan@example.com',
        expires_in_days: 7,
      },
    })
  })

  it('lists links for a proposal without exposing a new auth model', () => {
    expect(listCounterpartyLinksPath('org-1', 'contract-1', 'proposal 1')).toBe(
      '/api/orgs/org-1/contracts/contract-1/counterparty-links?redline_proposal_id=proposal+1',
    )
  })

  it('builds the public counterparty URL from the opaque token', () => {
    expect(counterpartyShareUrl('abc+token', 'https://lexproof.example')).toBe(
      'https://lexproof.example/counterparty/abc%2Btoken',
    )
  })

  it('targets unauthenticated external endpoints by token', () => {
    expect(externalAccessPath('tok/1')).toBe('/api/external/tok%2F1')
    expect(externalCommentPath('tok 1')).toBe('/api/external/tok%201/comment')
    expect(externalCountersignPath('tok 1')).toBe('/api/external/tok%201/countersign')
  })

  it('keeps the attestation wording explicit and stable', () => {
    expect(COUNTERPARTY_ATTESTATION).toBe('I have reviewed this redline and agree to be bound by it')
  })

  it('builds the internal request to send a link for e-signature', () => {
    expect(sendCounterpartyEsignatureRequest('org 1', 'contract 1', 'token-id 1')).toEqual({
      path: '/api/orgs/org%201/contracts/contract%201/counterparty-links/token-id%201/esignature',
      method: 'POST',
    })
  })

  it('builds the stub-only simulate-completion request, defaulting to completion not decline', () => {
    expect(simulateCounterpartyEsignatureRequest('org-1', 'contract-1', 'token-1')).toEqual({
      path: '/api/orgs/org-1/contracts/contract-1/counterparty-links/token-1/esignature/simulate',
      method: 'POST',
      body: { decline: false },
    })
    expect(simulateCounterpartyEsignatureRequest('org-1', 'contract-1', 'token-1', true)).toEqual({
      path: '/api/orgs/org-1/contracts/contract-1/counterparty-links/token-1/esignature/simulate',
      method: 'POST',
      body: { decline: true },
    })
  })
})
