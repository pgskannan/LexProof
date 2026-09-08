export type Finding = {
  finding_id: string;
  contract_id: string | null;
  version_id: string | null;
  title: string;
  severity: string | null;
  description: string;
  risk_impact: number | null;
  compliance_impact: number | null;
  evidence: unknown;
  evidence_quote: string | null;
  source_section: string | null;
  recommendation: string | null;
  created_at: string | null;
};

export const severityOrder = ['critical', 'high', 'medium', 'low'];
export const severityStyles: Record<string, string> = {
  critical: 'border-red-200 bg-red-50 text-red-700',
  high: 'border-orange-200 bg-orange-50 text-orange-700',
  medium: 'border-amber-200 bg-amber-50 text-amber-700',
  low: 'border-slate-200 bg-slate-50 text-slate-600',
};

export function displayEvidence(finding: Finding) {
  if (finding.evidence_quote) return finding.evidence_quote;
  if (typeof finding.evidence === 'string') return finding.evidence;
  return finding.evidence ? JSON.stringify(finding.evidence) : 'Evidence not recorded.';
}
export function filterFindings(findings: Finding[], search: string, severity: string) {
  const query = search.trim().toLowerCase();
  return findings.filter((finding) => {
    const matchesSearch = !query || [finding.title, finding.description, finding.evidence, finding.recommendation]
      .some((value) => String(value ?? '').toLowerCase().includes(query));
    const matchesSeverity = !severity || finding.severity?.toLowerCase() === severity;
    return matchesSearch && matchesSeverity;
  });
}

export function findingCounts(findings: Finding[]) {
  return severityOrder.reduce<Record<string, number>>((result, severity) => {
    result[severity] = findings.filter((finding) => finding.severity?.toLowerCase() === severity).length;
    return result;
  }, {});
}
