'use client';

import { Fragment, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowRight, ChevronDown, Search } from 'lucide-react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { apiFetch } from '../../../../../lib/api';
import { displayEvidence, filterFindings, findingCountLabel, findingCounts, findingsLoadState, getVisibleFindings, playbookAlignmentStyles, severityOrder, severityStyles, type Finding } from '../../../../../lib/findings';
import { listSupportedLanguagesPath, translateFindingsRequest, translationCacheKey, type FindingTranslation } from '../../../../../lib/translation';
import { EmptyState } from '../../../../../components/EmptyState';
import { Skeleton } from '../../../../../components/ui/skeleton';
import { SavedViews } from '../../../../../components/SavedViews';
import { Badge } from '../../../../../components/ui/badge';
import { Button } from '../../../../../components/ui/button';
import { Card, CardContent } from '../../../../../components/ui/card';
import { DataTable } from '../../../../../components/ui/data-table';
import { PageHeader } from '../../../../../components/ui/page-header';
import { PageContainer } from '../../../../../components/ui/container';
import { ContractSelector } from '../../../../../components/ui/contract-selector/contract-selector';
import { contractSelectionUrl } from '../../../../../lib/contractSelector';

type TranslatableField = 'title' | 'description' | 'recommendation' | 'playbook_notes';

type ContractFindingSummary = {
  contract_id: string;
  name?: string | null;
  total: number;
  severities: Record<string, number>;
};

function severityVariant(severity: string) {
  if (severity === 'critical') return 'critical' as const;
  if (severity === 'high') return 'high' as const;
  if (severity === 'medium') return 'medium' as const;
  return 'low' as const;
}

export default function FindingsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [findings, setFindings] = useState<Finding[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [revealedPii, setRevealedPii] = useState<Record<string, boolean>>({});
  const [search, setSearch] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const [targetLanguage, setTargetLanguage] = useState('');
  const [translationsCache, setTranslationsCache] = useState<Record<string, FindingTranslation>>({});
  const [translating, setTranslating] = useState(false);
  const [translateError, setTranslateError] = useState('');
  const [activeTab, setActiveTab] = useState<'findings' | 'redlines'>('findings');
  const [redlines, setRedlines] = useState<Array<{ proposal_id: string; finding_id: string; title?: string | null; severity?: string | null; proposed_text: string; status: string }>>([]);
  const [redlinesLoading, setRedlinesLoading] = useState(false);
  const [redlinesError, setRedlinesError] = useState('');
  const [contractSummaries, setContractSummaries] = useState<ContractFindingSummary[]>([]);
  const [contractSearch, setContractSearch] = useState('');
  const [contractsLoading, setContractsLoading] = useState(false);
  const [contractsError, setContractsError] = useState('');
  const contractFilter = searchParams.get('contract_id') ?? '';
  const versionFilter = searchParams.get('version_id') ?? '';
  const findingIdFromUrl = searchParams.get('finding_id') ?? '';
  const pageSize = 25;

  useEffect(() => {
    if (!contractFilter) {
      setFindings([]);
      setLoading(false);
      setContractsLoading(true);
      setContractsError('');
      const controller = new AbortController();
      void Promise.all([
        apiFetch('/api/contracts', { signal: controller.signal }),
        apiFetch('/api/findings', { signal: controller.signal }),
      ])
        .then(async ([contractsResponse, findingsResponse]) => {
          if (!contractsResponse.ok) throw new Error('Unable to load contracts');
          if (!findingsResponse.ok) throw new Error('Unable to load finding counts');
          const contracts: Array<{ contract_id: string; name?: string | null }> = await contractsResponse.json();
          const allFindings: Finding[] = await findingsResponse.json();
          const counts = new Map<string, { total: number; severities: Record<string, number> }>();
          for (const finding of allFindings) {
            if (!finding.contract_id) continue;
            const current = counts.get(finding.contract_id) ?? { total: 0, severities: {} };
            const severity = (finding.severity || 'unknown').toLowerCase();
            current.total += 1;
            current.severities[severity] = (current.severities[severity] || 0) + 1;
            counts.set(finding.contract_id, current);
          }
          setContractSummaries(contracts.map((contract) => ({
            ...contract,
            total: counts.get(contract.contract_id)?.total ?? 0,
            severities: counts.get(contract.contract_id)?.severities ?? {},
          })));
        })
        .catch((reason) => {
          if (reason instanceof DOMException && reason.name === 'AbortError') return;
          setContractsError(reason instanceof Error ? reason.message : 'Unable to load contracts');
          setContractSummaries([]);
        })
        .finally(() => {
          if (!controller.signal.aborted) setContractsLoading(false);
        });
      return () => controller.abort();
    }
    setContractSummaries([]);
    setContractsError('');
  }, [contractFilter]);

  useEffect(() => {
    if (!contractFilter) return;
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

  useEffect(() => {
    if (!contractFilter) {
      setRedlines([]);
      setRedlinesLoading(false);
      return;
    }
    setRedlinesLoading(true);
    setRedlinesError('');
    void apiFetch(`/api/contracts/${encodeURIComponent(contractFilter)}/redline-proposals`)
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load redlines');
        setRedlines(await response.json());
      })
      .catch((reason) => setRedlinesError(reason instanceof Error ? reason.message : 'Unable to load redlines'))
      .finally(() => setRedlinesLoading(false));
  }, [contractFilter]);

  useEffect(() => {
    void apiFetch(listSupportedLanguagesPath())
      .then(async (response) => {
        if (!response.ok) return;
        const data = await response.json().catch(() => null);
        if (data?.languages) setLanguages(data.languages);
      })
      .catch(() => {});
  }, []);

  const counts = useMemo(() => findingCounts(findings), [findings]);

  function applySavedFilters(filters: Record<string, unknown>) {
    if (typeof filters.search === 'string') setSearch(filters.search);
    if (typeof filters.severityFilter === 'string') setSeverityFilter(filters.severityFilter);
  }
  const filteredFindings = useMemo(() => filterFindings(findings, search, severityFilter), [findings, search, severityFilter]);
  const filteredContractSummaries = useMemo(() => {
    const query = contractSearch.trim().toLowerCase();
    if (!query) return contractSummaries;
    return contractSummaries.filter((contract) => `${contract.name || ''} ${contract.contract_id}`.toLowerCase().includes(query));
  }, [contractSearch, contractSummaries]);
  const pageCount = Math.max(1, Math.ceil(filteredFindings.length / pageSize));
  const findingsState = findingsLoadState(loading, error, findings.length);
  const visibleFindings = useMemo(
    () => getVisibleFindings(filteredFindings, page, pageSize),
    [filteredFindings, page, pageSize],
  );

  useEffect(() => {
    if (!targetLanguage) return;
    const idsNeeded = visibleFindings
      .map((finding) => finding.finding_id)
      .filter((id) => !(translationCacheKey(id, targetLanguage) in translationsCache));
    if (idsNeeded.length === 0) return;
    setTranslating(true);
    setTranslateError('');
    const request = translateFindingsRequest(idsNeeded, targetLanguage);
    void apiFetch(request.path, {
      method: request.method,
      headers: { 'Content-Type': 'application/json' },
      body: request.body,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to translate findings');
        const data: Record<string, FindingTranslation> = await response.json();
        setTranslationsCache((current) => {
          const next = { ...current };
          for (const [findingId, translation] of Object.entries(data)) {
            next[translationCacheKey(findingId, targetLanguage)] = translation;
          }
          return next;
        });
      })
      .catch((reason) => setTranslateError(reason instanceof Error ? reason.message : 'Unable to translate findings'))
      .finally(() => setTranslating(false));
  }, [targetLanguage, visibleFindings, translationsCache]);

  function translatedText(finding: Finding, field: TranslatableField): { value: string; isTranslated: boolean } {
    const original = finding[field] ?? '';
    if (!targetLanguage) return { value: original, isTranslated: false };
    const cached = translationsCache[translationCacheKey(finding.finding_id, targetLanguage)];
    const value = cached?.[field];
    return value ? { value, isTranslated: true } : { value: original, isTranslated: false };
  }

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

  function selectContract(contractId: string) {
    router.push(contractSelectionUrl(searchParams.toString(), contractId));
  }

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Workspace"
        title="Findings & Redlines"
        description={
          contractFilter
            ? `Contract-scoped review for ${contractFilter}. Each finding stays tied to its source contract version and evidence.`
            : 'Review persisted AI findings, their supporting contract language, and the recommended next action.'
        }
        actions={
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <Search className="h-4 w-4" />
            {contractFilter ? `Contract filter: ${contractFilter}` : 'All analyzed contracts'}
          </div>
        }
      />

      <div className="mt-6 space-y-6">
        <Card>
          <CardContent className="space-y-3 py-4">
            <ContractSelector selectedContractId={contractFilter} onContractSelect={selectContract} />
            {contractFilter && <p className="text-xs text-gray-500 dark:text-gray-400">Contract ID: <span className="font-mono">{contractFilter}</span></p>}
          </CardContent>
        </Card>

        {!contractFilter && (
          <div className="space-y-4">
            <Card>
              <CardContent className="space-y-3 py-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Browse contract findings</h2>
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Choose a contract to review its persisted findings and redline proposals.</p>
                  </div>
                  <div className="relative sm:w-80">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                    <input
                      aria-label="Search contracts"
                      value={contractSearch}
                      onChange={(event) => setContractSearch(event.target.value)}
                      placeholder="Search contracts"
                      className="w-full rounded-[var(--radius-md,0.5rem)] border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
                    />
                  </div>
                </div>
              </CardContent>
            </Card>
            {contractsLoading && <div className="space-y-3"><Skeleton className="h-20 w-full" /><Skeleton className="h-20 w-full" /></div>}
            {contractsError && <p role="alert" className="text-sm text-red-700 dark:text-red-400">{contractsError}</p>}
            {!contractsLoading && !contractsError && filteredContractSummaries.length === 0 && (
              <EmptyState title="No contracts found" description="Upload a contract and run analysis to create findings." />
            )}
            {!contractsLoading && !contractsError && filteredContractSummaries.length > 0 && (
              <Card>
                <div className="overflow-hidden rounded-[var(--radius-lg,0.75rem)]">
                  <DataTable
                    columns={[
                      {
                        key: 'contract',
                        header: 'Contract',
                        className: 'min-w-[260px]',
                        render: (contract: ContractFindingSummary) => (
                          <div className="min-w-0">
                            <p className="truncate font-medium text-gray-900 dark:text-gray-100">{contract.name || contract.contract_id}</p>
                            <p className="mt-1 truncate font-mono text-xs text-gray-500 dark:text-gray-400">{contract.contract_id}</p>
                          </div>
                        ),
                      },
                      {
                        key: 'total',
                        header: 'Findings',
                        className: 'w-[110px] text-center',
                        render: (contract: ContractFindingSummary) => <span className="font-semibold text-gray-900 dark:text-gray-100">{contract.total}</span>,
                      },
                      {
                        key: 'severity',
                        header: 'Severity',
                        className: 'min-w-[260px]',
                        render: (contract: ContractFindingSummary) => (
                          <div className="flex flex-wrap gap-1.5">
                            {severityOrder.map((severity) => <Badge key={severity} variant={severityVariant(severity)}>{severity}: {contract.severities[severity] ?? 0}</Badge>)}
                          </div>
                        ),
                      },
                      {
                        key: 'action',
                        header: 'Action',
                        className: 'w-[140px] text-right',
                        render: (contract: ContractFindingSummary) => <Link className="text-sm font-semibold text-[var(--brand-primary,#2563eb)] hover:underline" href={contractSelectionUrl('', contract.contract_id)}>Review findings</Link>,
                      },
                    ]}
                    data={filteredContractSummaries}
                    rowKey={(contract) => contract.contract_id}
                    pageSize={10}
                    onRowClick={(contract) => selectContract(contract.contract_id)}
                  />
                </div>
              </Card>
            )}
          </div>
        )}

        {contractFilter && (
          <>
            <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
              <button type="button" onClick={() => setActiveTab('findings')} className={`border-b-2 px-4 py-2 text-sm font-medium ${activeTab === 'findings' ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-500'}`}>Findings</button>
              <button type="button" onClick={() => setActiveTab('redlines')} className={`border-b-2 px-4 py-2 text-sm font-medium ${activeTab === 'redlines' ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-500'}`}>Redlines</button>
            </div>

            {activeTab === 'redlines' ? (
              <Card>
                <CardContent className="py-6">
                  {redlinesLoading && <Skeleton className="h-20 w-full" />}
                  {redlinesError && <p role="alert" className="text-sm text-red-700">{redlinesError}</p>}
                  {!redlinesLoading && !redlinesError && redlines.length === 0 && <p className="text-sm text-gray-500">No redline proposals recorded for this contract.</p>}
                  {!redlinesLoading && !redlinesError && redlines.length > 0 && (
                    <div className="space-y-3">
                      {redlines.map((redline) => (
                        <div key={redline.proposal_id} className="rounded border border-gray-200 p-4 dark:border-gray-700">
                          <div className="flex items-center justify-between gap-3">
                            <p className="font-medium text-gray-900 dark:text-gray-100">{redline.title || `Finding ${redline.finding_id}`}</p>
                            <Badge variant={severityVariant((redline.severity || 'medium').toLowerCase())}>{redline.status}</Badge>
                          </div>
                          <p className="mt-2 whitespace-pre-wrap text-sm text-gray-600 dark:text-gray-300">{redline.proposed_text || 'No proposed text recorded.'}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            ) : (
              <>
        {findingsState !== 'error' && <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Card>
            <CardContent className="px-4 py-4">
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Total</p>
              <p className="mt-1.5 text-2xl font-bold text-gray-900 dark:text-gray-100">{findingCountLabel(findings.length, loading)}</p>
            </CardContent>
          </Card>
          {severityOrder.map((severity) => (
            <Card key={severity}>
              <CardContent className="px-4 py-4">
                <p className="text-xs font-medium capitalize uppercase tracking-wide text-gray-500 dark:text-gray-400">{severity}</p>
                <p className="mt-1.5 text-2xl font-bold text-gray-900 dark:text-gray-100">{findingCountLabel(counts[severity], loading)}</p>
              </CardContent>
            </Card>
          ))}
        </div>}

        <Card>
          <CardContent className="flex flex-col gap-3 py-4 sm:flex-row">
            <label className="flex flex-1 items-center gap-2 rounded-[var(--radius-md,0.5rem)] border border-gray-300 px-3 dark:border-gray-600">
              <Search className="h-4 w-4 text-gray-400" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search title, description, evidence, or recommendation"
                className="w-full bg-transparent py-2 text-sm text-gray-900 outline-none dark:text-gray-100"
              />
            </label>
            <select
              aria-label="Filter by severity"
              value={severityFilter}
              onChange={(event) => setSeverityFilter(event.target.value)}
              className="rounded-[var(--radius-md,0.5rem)] border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-200"
            >
              <option value="">All severities</option>
              {severityOrder.map((severity) => <option key={severity} value={severity}>{severity}</option>)}
            </select>
            <select
              aria-label="Translate findings"
              value={targetLanguage}
              onChange={(event) => setTargetLanguage(event.target.value)}
              className="rounded-[var(--radius-md,0.5rem)] border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-200"
            >
              <option value="">Original language</option>
              {Object.entries(languages).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
            </select>
          </CardContent>
          {targetLanguage && (translating || translateError) && (
            <div className="border-t border-gray-100 px-6 py-2.5 text-sm dark:border-gray-700">
              {translating && <span className="text-gray-500 dark:text-gray-400">Translating visible findings…</span>}
              {translateError && <span role="alert" className="text-red-700 dark:text-red-400">{translateError}</span>}
            </div>
          )}
          <div className="border-t border-gray-100 px-6 py-3 dark:border-gray-700">
            <SavedViews page="findings" currentFilters={{ search, severityFilter }} onApply={applySavedFilters} />
          </div>
        </Card>

        {findingsState === 'loading' && (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        )}
        {findingsState === 'error' && (
          <div role="alert" className="rounded-[var(--radius-lg,0.75rem)] border border-red-200 bg-red-50 p-5 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400">
            <div className="flex items-center gap-2 font-semibold"><AlertTriangle className="h-5 w-5" /> Unable to load findings</div>
            <p className="mt-2 text-sm">{error}</p>
          </div>
        )}
        {findingsState === 'empty' && (
          <EmptyState
            title="No findings yet"
            description="Run analysis on a contract to persist AI findings here. Each finding keeps its contract version and supporting clause language."
          />
        )}
        {findingsState === 'success' && filteredFindings.length === 0 && (
          <Card><CardContent className="py-12 text-center text-gray-500 dark:text-gray-400">No findings match the current filters.</CardContent></Card>
        )}

        {findingsState === 'success' && visibleFindings.length > 0 && (
          <div className="space-y-4">
            <Card>
              <div className="overflow-hidden rounded-[var(--radius-lg,0.75rem)]">
                <DataTable
                  showPagination={false}
                  columns={[
                    {
                      key: 'severity',
                      header: 'Severity',
                      className: 'w-[115px] whitespace-nowrap',
                      render: (finding: Finding) => <Badge variant={severityVariant((finding.severity ?? 'medium').toLowerCase())}>{(finding.severity ?? 'medium').toLowerCase()}</Badge>,
                    },
                    {
                      key: 'finding',
                      header: 'Finding',
                      className: 'min-w-[320px]',
                      render: (finding: Finding) => (
                        <div>
                          <p className="font-medium text-gray-900 dark:text-gray-100">
                            {translatedText(finding, 'title').value || 'Untitled finding'}
                            {translatedText(finding, 'title').isTranslated && (
                              <span className="ml-2 text-[11px] font-normal italic text-gray-400 dark:text-gray-500">(machine-translated)</span>
                            )}
                          </p>
                          <p className="mt-1 max-w-md text-sm text-gray-500 dark:text-gray-400">
                            {translatedText(finding, 'description').value || 'No description recorded.'}
                          </p>
                        </div>
                      ),
                    },
                    {
                      key: 'contract',
                      header: 'Contract / Version',
                      className: 'whitespace-nowrap',
                      render: (finding: Finding) => (
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                          <p className="font-mono">{finding.contract_id ?? '—'}</p>
                          <p className="mt-0.5">v{finding.version_id ?? '—'}</p>
                        </div>
                      ),
                    },
                    {
                      key: 'tags',
                      header: 'Tags',
                      className: 'min-w-[170px]',
                      render: (finding: Finding) => (
                        <div className="flex flex-wrap gap-1.5">
                          {finding.playbook_alignment && (
                            <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-semibold capitalize ${playbookAlignmentStyles[finding.playbook_alignment] ?? playbookAlignmentStyles.NOT_COVERED}`}>
                              {finding.playbook_alignment.replace('_', ' ').toLowerCase()}
                            </span>
                          )}
                          {finding.contains_pii && <Badge variant="secondary">PII</Badge>}
                          {finding.detected_language_name && finding.detected_language !== 'en' && (
                            <Badge variant="secondary">{finding.detected_language_name}</Badge>
                          )}
                        </div>
                      ),
                    },
                    {
                      key: 'action',
                      header: 'Action',
                      className: 'w-[110px] text-right whitespace-nowrap',
                      render: (finding: Finding) => (
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            setExpandedId((current) => current === finding.finding_id ? null : finding.finding_id);
                          }}
                          className="inline-flex items-center gap-1 text-sm font-medium text-[var(--brand-primary,#2563eb)] hover:underline"
                        >
                          {expandedId === finding.finding_id ? 'Hide' : 'View'}
                          <ChevronDown className={`h-4 w-4 transition-transform ${expandedId === finding.finding_id ? 'rotate-180' : ''}`} />
                        </button>
                      ),
                    },
                  ]}
                  data={visibleFindings}
                  rowKey={(finding) => finding.finding_id}
                  pageSize={pageSize}
                  onRowClick={(finding) => setExpandedId((current) => current === finding.finding_id ? null : finding.finding_id)}
                />
              </div>
            </Card>

            {visibleFindings.length > 0 && expandedId && (() => {
              const selectedFinding = visibleFindings.find((finding) => finding.finding_id === expandedId) ?? null;
              if (!selectedFinding) return null;
              return (
                <Card className="overflow-hidden">
                  <div className="grid gap-5 p-5 md:grid-cols-[1fr_auto]">
                    <div className="space-y-4">
                      <div>
                        <p className="findings-label">
                          Evidence
                          {selectedFinding.contains_pii && (
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                setRevealedPii((current) => ({ ...current, [selectedFinding.finding_id]: !current[selectedFinding.finding_id] }));
                              }}
                              className="ml-2 text-xs font-semibold normal-case text-[var(--brand-primary,#2563eb)] hover:underline"
                            >
                              {revealedPii[selectedFinding.finding_id] ? 'Mask PII' : 'Show original (contains PII)'}
                            </button>
                          )}
                        </p>
                        <p className="findings-quote">
                          &ldquo;{selectedFinding.contains_pii && !revealedPii[selectedFinding.finding_id]
                            ? (selectedFinding.evidence_quote_masked ?? displayEvidence(selectedFinding))
                            : displayEvidence(selectedFinding)}&rdquo;
                        </p>
                      </div>
                      <div>
                        <p className="findings-label">Source</p>
                        <p className="findings-value">{selectedFinding.source_section ?? 'Source location not recorded'}</p>
                      </div>
                      <div>
                        <p className="findings-label">Recommendation</p>
                        <p className="findings-value">
                          {translatedText(selectedFinding, 'recommendation').value || 'Recommendation not recorded'}
                          {translatedText(selectedFinding, 'recommendation').isTranslated && (
                            <span className="ml-2 text-xs font-normal italic text-gray-400 dark:text-gray-500">(machine-translated)</span>
                          )}
                        </p>
                      </div>
                      {selectedFinding.reasoning && (
                        <div>
                          <p className="findings-label">Why this was flagged</p>
                          <p className="findings-value">{selectedFinding.reasoning}</p>
                        </div>
                      )}
                      {selectedFinding.playbook_notes && (
                        <div>
                          <p className="findings-label">Playbook comparison{selectedFinding.clause_type ? ` (${selectedFinding.clause_type})` : ''}</p>
                          <p className="findings-value">
                            {translatedText(selectedFinding, 'playbook_notes').value}
                            {translatedText(selectedFinding, 'playbook_notes').isTranslated && (
                              <span className="ml-2 text-xs font-normal italic text-gray-400 dark:text-gray-500">(machine-translated)</span>
                            )}
                          </p>
                        </div>
                      )}
                      {selectedFinding.regulatory_citations && selectedFinding.regulatory_citations.length > 0 && (
                        <div>
                          <p className="findings-label">Regulations implicated</p>
                          <p className="findings-value">{selectedFinding.regulatory_citations.join(', ')}</p>
                        </div>
                      )}
                    </div>
                    <div className="flex min-w-48 flex-col gap-3">
                      {selectedFinding.confidence != null && (
                        <div className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-white p-3.5 dark:border-gray-700 dark:bg-gray-800">
                          <p className="findings-label">AI confidence</p>
                          <p className="mt-1 text-lg font-bold text-gray-700 dark:text-gray-200">{Math.round(selectedFinding.confidence * 100)}%</p>
                          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700">
                            <div className="h-full rounded-full bg-[var(--brand-primary,#2563eb)]" style={{ width: `${Math.round(selectedFinding.confidence * 100)}%` }} />
                          </div>
                        </div>
                      )}
                      <div className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-white p-3.5 dark:border-gray-700 dark:bg-gray-800">
                        <p className="findings-label">Risk impact</p>
                        <p className="mt-1 text-lg font-bold text-gray-700 dark:text-gray-200">{selectedFinding.risk_impact ?? 'Not recorded'}</p>
                      </div>
                      <div className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-white p-3.5 dark:border-gray-700 dark:bg-gray-800">
                        <p className="findings-label">Compliance impact</p>
                        <p className="mt-1 text-lg font-bold text-gray-700 dark:text-gray-200">{selectedFinding.compliance_impact ?? 'Not recorded'}</p>
                      </div>
                      <Button onClick={(event) => { event.stopPropagation(); reviewFinding(selectedFinding); }}>
                        Review Finding <ArrowRight className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </Card>
              );
            })()}

            {!loading && !error && filteredFindings.length > 0 && (
              <nav aria-label="Findings pagination" className="flex items-center justify-between rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-white p-3 text-sm dark:border-gray-700 dark:bg-gray-800">
                <span className="text-gray-500 dark:text-gray-400">Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, filteredFindings.length)} of {filteredFindings.length}</span>
                <div className="flex gap-2">
                  <button type="button" disabled={page === 1} onClick={() => setPage(page - 1)} className="rounded-[var(--radius-md,0.5rem)] border border-gray-300 px-3 py-2 text-gray-700 disabled:opacity-40 dark:border-gray-600 dark:text-gray-300">Previous</button>
                  <span className="px-2 py-2 text-gray-600 dark:text-gray-400">Page {page} of {pageCount}</span>
                  <button type="button" disabled={page === pageCount} onClick={() => setPage(page + 1)} className="rounded-[var(--radius-md,0.5rem)] border border-gray-300 px-3 py-2 text-gray-700 disabled:opacity-40 dark:border-gray-600 dark:text-gray-300">Next</button>
                </div>
              </nav>
            )}
          </div>
        )}

              </>
            )}
          </>
        )}

      </div>
      <style jsx>{`.findings-label{font-size:.68rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#64748b}.findings-quote{margin-top:.4rem;border-left:3px solid var(--brand-primary,#2563eb);background:#fff;padding:.75rem;color:#334155;white-space:pre-wrap}.findings-value{margin-top:.4rem;color:#334155;white-space:pre-wrap}`}</style>
    </PageContainer>
  );
}
