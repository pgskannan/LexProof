import { describe, expect, it } from 'vitest';
import { proposalPublishRequest, proposalQuery, proposalReviewRequest, proposalSaveRequest } from './redlineProposals';

describe('redline proposal request helpers', () => {
  it('loads proposals scoped to finding and source version', () => {
    expect(proposalQuery('finding 1', 'version-1')).toBe('finding_id=finding+1&version_id=version-1');
  });

  it('builds a create request with editable proposed text', () => {
    expect(proposalSaveRequest(null, 'Revised clause')).toEqual({
      path: '/api/contracts/{contract_id}/redline-proposals',
      method: 'POST',
      body: { proposed_text: 'Revised clause' },
    });
  });

  it('builds an update request for an existing persisted proposal', () => {
    expect(proposalSaveRequest('proposal-1', 'Edited clause')).toEqual({
      path: '/api/redline-proposals/proposal-1',
      method: 'PATCH',
      body: { proposed_text: 'Edited clause' },
    });
  });

  it('builds an explicit human review request with comment', () => {
    expect(proposalReviewRequest('proposal 1', 'APPROVED', 'Reviewed by counsel')).toEqual({
      path: '/api/redline-proposals/proposal%201/review',
      method: 'POST',
      body: { decision: 'APPROVED', comment: 'Reviewed by counsel' },
    });
  });

  it('builds a publish request for an approved proposal', () => {
    expect(proposalPublishRequest('proposal 1')).toEqual({
      path: '/api/redline-proposals/proposal%201/publish',
      method: 'POST',
    });
  });
});