import { describe, expect, it } from 'vitest';
import { analyzeVersionRequest } from '../../../../../lib/redlineProposals';

describe('version analysis request', () => {
  it('targets an explicit contract version', () => {
    expect(analyzeVersionRequest('contract 1', 'version/2')).toEqual({
      path: '/api/contracts/contract%201/versions/version%2F2/analyze',
      method: 'POST',
    });
  });
});