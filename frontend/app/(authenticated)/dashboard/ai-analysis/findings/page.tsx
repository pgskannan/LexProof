'use client';

import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowRight, ChevronDown, Search } from 'lucide-react';
import { useRouter, useSearchParams } from 'next/navigation';
import { apiFetch } from '../../../../../lib/api';
import { displayEvidence, filterFindings, findingCounts, severityOrder, severityStyles, type Finding } from '../../../../../lib/findings';
import { EmptyState } from '../../../../../components/EmptyState';
import { Skeleton } from '../../../../../components/ui/skeleton';

export default function FindingsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [findings, setFindings] = useState<Finding[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const contractFilter = searchParams.get('contract_id') ?? '';
  const versionFilter = searchParams.get('version_id') ?? '';
  const findingIdFromUrl = searchParams.get('finding_id') ?? '';
  const pageSize = 10;

  useEffect(() => {
    const query = new URLSearchParams();
    if (contractFilter) query.set('contract_id', contractFilter);
    if (versionFilter) query.set('version_id', versionFilter);
    setLoading(true);
    setError('');
    void apiFetch(`/api/findings${query.toString() ? `?${query}` : ''}`)
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load findings');
        setFindings(await response.json());
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : 'Unable to load findings'))
      .finally(() => setLoading(false));
  }, [contractFilter, versionFilter]);

  const counts = useMemo(() => findingCounts(findings), [findings]);
  const filteredFindings = useMemo(() => filterFindings(findings, search, severityFilter), [findings, search, severityFilter]);
  const pageCount = Math.max(1, Math.ceil(filteredFindings.length / pageSize));
  const visibleFindings = filteredFindings.slice((page - 1) * pageSize, page * pageSize);

  useEffect(() => { setPage(1); }, [search, severityFilter]);
  useEffect(() => { if (page > pageCount) setPage(pageCount); }, [page, pageCount]);
  useEffect(() => {
    if (findingIdFromUrl) setExpandedId(findingIdFromUrl);
  }, [findingIdFromUrl]);
  useEffect(() => {
    if (!findingIdFromUrl || !filteredFindings.length) return;
    const index = filteredFindings.findIndex((finding) => finding.finding_id === findingIdFromUrl);
    if (index >= 0) setPage(Math.floor(index / pageSize) + 1);
  }, [findingIdFromUrl, filteredFindings, pageSize]);

  function reviewFinding(finding: Finding) {
    const params = new URLSearchParams({
      finding_id: finding.finding_id,
      contract_id: finding.contract_id ?? '',
      version_id: finding.version_id ?? '',
      title: finding.title,
      severity: finding.severity ?? '',
      risk_impact: finding.risk_impact == null ? '' : String(finding.risk_impact),
      affected_clause: finding.source_section ?? '',
      current_language: displayEvidence(finding),
      regulatory_requirement: finding.recommendation ?? '',
      amendment_reason: finding.description,
      evidence_quote: finding.evidence_quote ?? '',
      source_section: finding.source_section ?? '',
    });
    router.push(`/compliance-command-center/remediation?${params}`);
  }

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-10 text-slate-900">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 border-b border-slate-200 pb-7">
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.24em] text-blue-700">LexProof / AI analysis</p>
          <div className="flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-4xl font-bold tracking-tight">AI Findings</h1><p className="mt-2 max-w-2xl text-slate-600">Review persisted findings, their supporting contract language, and the recommended next action.</p></div><div className="flex items-center gap-2 text-sm text-slate-500"><Search className="h-4 w-4" />{contractFilter ? `Filtered: ${contractFilter}` : 'All analyzed contracts'}</div></div>
        </header>

        <section className="mb-8 grid grid-cols-2 gap-px overflow-hidden border border-slate-200 bg-slate-200 sm:grid-cols-5"><div className="bg-white p-4"><p className="text-xs uppercase tracking-wider text-slate-500">Total</p><p className="mt-2 text-2xl font-bold">{findings.length}</p></div>{severityOrder.map((severity) => <div key={severity} className="bg-white p-4"><p className="text-xs uppercase tracking-wider text-slate-500">{severity}</p><p className="mt-2 text-2xl font-bold">{counts[severity]}</p></div>)}</section>
        <section className="mb-5 flex flex-col gap-3 border border-slate-200 bg-white p-4 sm:flex-row"><label className="flex flex-1 items-center gap-2 border border-slate-200 px-3 text-sm text-slate-500"><Search className="h-4 w-4" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search title, description, evidence, or recommendation" className="w-full py-2 text-slate-900 outline-none" /></label><select aria-label="Filter by severity" value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)} className="border border-slate-200 bg-white px-3 py-2 text-sm"><option value="">All severities</option>{severityOrder.map((severity) => <option key={severity} value={severity}>{severity}</option>)}</select></section>

        {loading && (
          <div className="space-y-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        )}
        {error && <div role="alert" className="border border-red-200 bg-red-50 p-5 text-red-700"><div className="flex items-center gap-2 font-semibold"><AlertTriangle className="h-5 w-5" /> Unable to load findings</div><p className="mt-2 text-sm">{error}</p></div>}
        {!loading && !error && findings.length === 0 && (
          <EmptyState
            title="No findings yet"
            description="Run analysis on a contract to persist AI findings here. Each finding keeps its contract version and supporting clause language."
          />
        )}
        {!loading && !error && findings.length > 0 && filteredFindings.length === 0 && <div className="border border-slate-200 bg-white p-12 text-center text-slate-500">No findings match the current filters.</div>}
        {!loading && !error && visibleFindings.length > 0 && <div className="space-y-3">{visibleFindings.map((finding) => { const expanded = expandedId === finding.finding_id; const severity = finding.severity?.toLowerCase() ?? 'medium'; return <article key={finding.finding_id} className="border border-slate-200 bg-white shadow-sm"><button type="button" onClick={() => setExpandedId(expanded ? null : finding.finding_id)} className="flex w-full items-start gap-4 p-5 text-left hover:bg-slate-50"><span className={`mt-0.5 shrink-0 border px-2.5 py-1 text-xs font-bold uppercase ${severityStyles[severity] ?? severityStyles.medium}`}>{severity}</span><span className="min-w-0 flex-1"><span className="block text-lg font-semibold">{finding.title || 'Untitled finding'}</span><span className="mt-1 block text-sm text-slate-600">{finding.description || 'No description recorded.'}</span><span className="mt-3 block text-xs text-slate-500">Contract: {finding.contract_id ?? '—'} · Version: {finding.version_id ?? '—'}</span></span><ChevronDown className={`h-5 w-5 shrink-0 text-slate-400 transition-transform ${expanded ? 'rotate-180' : ''}`} /></button>{expanded && <div className="border-t border-slate-200 bg-slate-50 p-5"><div className="grid gap-5 md:grid-cols-[1fr_auto]"><div className="space-y-4"><div><p className="label">Evidence</p><p className="quote">“{displayEvidence(finding)}”</p></div><div><p className="label">Source</p><p className="value">{finding.source_section ?? 'Source location not recorded'}</p></div><div><p className="label">Recommendation</p><p className="value">{finding.recommendation ?? 'Recommendation not recorded'}</p></div></div><div className="flex min-w-48 flex-col gap-3"><div className="border border-slate-200 bg-white p-4"><p className="label">Risk impact</p><p className="mt-1 text-lg font-bold text-slate-600">{finding.risk_impact ?? 'Not recorded'}</p></div><div className="border border-slate-200 bg-white p-4"><p className="label">Compliance impact</p><p className="mt-1 text-lg font-bold text-slate-600">{finding.compliance_impact ?? 'Not recorded'}</p></div><button type="button" onClick={() => reviewFinding(finding)} className="inline-flex items-center justify-center gap-2 bg-slate-900 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-800">Review Finding <ArrowRight className="h-4 w-4" /></button></div></div></div>}</article>; })}</div>}
        {!loading && !error && filteredFindings.length > 0 && <nav aria-label="Findings pagination" className="mt-5 flex items-center justify-between border border-slate-200 bg-white p-3 text-sm"><span className="text-slate-500">Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, filteredFindings.length)} of {filteredFindings.length}</span><div className="flex gap-2"><button type="button" disabled={page === 1} onClick={() => setPage(page - 1)} className="border border-slate-300 px-3 py-2 disabled:opacity-40">Previous</button><span className="px-2 py-2 text-slate-600">Page {page} of {pageCount}</span><button type="button" disabled={page === pageCount} onClick={() => setPage(page + 1)} className="border border-slate-300 px-3 py-2 disabled:opacity-40">Next</button></div></nav>}
      </div>
      <style jsx>{`.label{font-size:.68rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#64748b}.quote{margin-top:.4rem;border-left:3px solid #2563eb;background:#fff;padding:.75rem;color:#334155;white-space:pre-wrap}.value{margin-top:.4rem;color:#334155;white-space:pre-wrap}`}</style>
    </main>
  );
}
