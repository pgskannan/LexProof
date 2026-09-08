import { describe, expect, it } from 'vitest';
import { displayEvidence, filterFindings, findingCounts } from '../../../../../lib/findings';

const baseFinding = {
  finding_id: 'finding-1',
  contract_id: 'contract-1',
  version_id: 'version-1',
  title: 'Liability cap',
  severity: 'CRITICAL',
  description: 'The cap is too low.',
  risk_impact: 90,
  compliance_impact: 20,
  evidence: 'Clause text',
  evidence_quote: 'Exact clause text',
  source_section: 'Section 12',
  recommendation: 'Review the cap.',
  created_at: null,
};

describe('findings page helpers', () => {
  it('counts persisted findings by severity', () => {
    expect(findingCounts([baseFinding, { ...baseFinding, finding_id: 'finding-2', severity: 'high' }])).toEqual({
      critical: 1,
      high: 1,
      medium: 0,
      low: 0,
    });
  });

  it('prefers the exact evidence quote for finding detail', () => {
    expect(displayEvidence(baseFinding)).toBe('Exact clause text');
  });

  it('falls back to persisted evidence when no quote exists', () => {
    expect(displayEvidence({ ...baseFinding, evidence_quote: null })).toBe('Clause text');
  });

  it('filters findings by search text and severity', () => {
    expect(filterFindings([baseFinding, { ...baseFinding, finding_id: 'finding-2', severity: 'medium', title: 'Notice period' }], 'liability', 'critical')).toHaveLength(1);
    expect(filterFindings([baseFinding], 'missing', '')).toHaveLength(0);
  });
});