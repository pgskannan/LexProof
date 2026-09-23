import { describe, expect, it } from 'vitest';
import { contractSelectionUrl, filterContracts } from './contractSelector';

const contracts = [
  { contract_id: 'demo-msa', name: 'Demo Master Services Agreement' },
  { contract_id: 'other-nda', name: 'Other Non-Disclosure Agreement' },
];

describe('contract selector helpers', () => {
  it('matches contract names case-insensitively', () => {
    expect(filterContracts(contracts, 'master services')).toEqual([contracts[0]]);
  });

  it('matches contract IDs', () => {
    expect(filterContracts(contracts, 'other-nda')).toEqual([contracts[1]]);
  });

  it('only returns contracts supplied by the contracts API', () => {
    expect(filterContracts(contracts, 'hidden')).toEqual([]);
  });

  it('writes the selected contract_id and clears stale finding context', () => {
    expect(contractSelectionUrl('version_id=v1&finding_id=f1', 'demo-msa'))
      .toBe('/dashboard/ai-analysis/findings?contract_id=demo-msa');
  });
});
