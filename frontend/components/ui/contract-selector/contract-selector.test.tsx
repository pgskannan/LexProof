import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ContractSelector } from './contract-selector';

vi.mock('../../OrgProvider', () => ({
  useOrg: () => ({ currentOrg: { org_id: 'org-1' }, loading: false }),
}));

describe('ContractSelector', () => {
  it('renders the empty selection prompt', () => {
    const markup = renderToStaticMarkup(
      <ContractSelector selectedContractId="" onContractSelect={() => {}} />,
    );
    expect(markup).toContain('Select a contract to view findings and redlines');
  });

  it('renders the selected contract ID before contract metadata loads', () => {
    const markup = renderToStaticMarkup(
      <ContractSelector selectedContractId="demo-msa" onContractSelect={() => {}} />,
    );
    expect(markup).toContain('demo-msa');
  });
});
