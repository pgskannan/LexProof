import { describe, expect, it } from 'vitest';
import { displayEvidence, filterFindings, findingCountLabel, findingCounts, findingsLoadState, getVisibleFindings } from '../../../../../lib/findings';

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
  reasoning: null,
  confidence: null,
  clause_type: null,
  playbook_alignment: null,
  playbook_notes: null,
  regulatory_citations: [],
  evidence_quote_masked: null,
  contains_pii: false,
  detected_language: null,
  detected_language_name: null,
  created_at: null,
};

describe('findings page helpers', () => {
  it('does not present loading findings as zero', () => {
    expect(findingCountLabel(0, true)).toBe('—');
    expect(findingCountLabel(14, true)).toBe('—');
  });

  it('shows zero only after an empty response has completed', () => {
    expect(findingCountLabel(0, false)).toBe('0');
  });

  it('shows the actual count after a successful 14-finding response', () => {
    expect(findingCountLabel(14, false)).toBe('14');
  });

  it('classifies an error separately from an empty successful response', () => {
    expect(findingsLoadState(false, 'Unable to load findings', 0)).toBe('error');
    expect(findingsLoadState(false, '', 0)).toBe('empty');
    expect(findingsLoadState(false, '', 14)).toBe('success');
  });

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

  it('keeps all 14 findings in state when the page size is 25', () => {
    const findings = Array.from({ length: 14 }, (_, index) => ({
      ...baseFinding,
      finding_id: `finding-${index + 1}`,
      title: `Finding ${index + 1}`,
      severity: index % 3 === 0 ? 'critical' : index % 3 === 1 ? 'high' : 'medium',
    }));

    const filtered = filterFindings(findings, '', '');
    const visible = getVisibleFindings(filtered, 1, 25);

    expect(filtered).toHaveLength(14);
    expect(visible).toHaveLength(14);
    expect(visible.map((finding) => finding.finding_id)).toEqual(findings.map((finding) => finding.finding_id));
  });
});