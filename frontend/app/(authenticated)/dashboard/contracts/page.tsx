'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertTriangle, Search, UploadCloud } from 'lucide-react';
import { apiFetch } from '../../../../lib/api';
import { useOrg } from '../../../../components/OrgProvider';
import { EmptyState } from '../../../../components/EmptyState';
import { Skeleton } from '../../../../components/ui/skeleton';
import { SavedViews } from '../../../../components/SavedViews';
import { Badge } from '../../../../components/ui/badge';
import { Button } from '../../../../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../../../components/ui/card';
import { DataTable } from '../../../../components/ui/data-table';
import { PageHeader } from '../../../../components/ui/page-header';
import { PageContainer } from '../../../../components/ui/container';

interface ContractSummary {
  contract_id: string;
  name: string;
  status: string;
  version: number | null;
  analysis_status: string | null;
  passport_id: string | null;
  risk_score: number | null;
  risk_level: string | null;
  evidence_count: number | null;
  proof_status?: 'processing' | 'confirmed' | 'failed' | 'action_required' | null;
  recommended_action?: 'none' | 'wait' | 'retry' | null;
  // Already present on the /api/contracts response (see dashboard/page.tsx's
  // widened ContractSummary); reading it here is not a new request.
  updated_at?: string | null;
}

type BatchEntry = {
  filename: string;
  status: 'pending' | 'uploading' | 'analyzing' | 'done' | 'error';
  detail?: string;
  contractId?: string;
};

function riskVariant(level?: string | null) {
  const key = (level || '').toLowerCase();
  if (key === 'critical') return 'critical' as const;
  if (key === 'high') return 'high' as const;
  if (key === 'medium') return 'medium' as const;
  if (key === 'low') return 'low' as const;
  return 'secondary' as const;
}

function relativeDate(value?: string | null) {
  if (!value) return '—';
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return '—';
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(value).toLocaleDateString();
}

export default function AllContracts() {
  const router = useRouter();
  const { currentOrg, loading: orgLoading } = useOrg();
  const [files, setFiles] = useState<File[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [batch, setBatch] = useState<BatchEntry[]>([]);
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [loadingContracts, setLoadingContracts] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const canUpload = !orgLoading && Boolean(currentOrg?.org_id);

  async function loadContracts() {
    try {
      const response = await apiFetch('/api/contracts');
      if (!response.ok) throw new Error('Unable to load contracts');
      setContracts(await response.json());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to load contracts');
    } finally {
      setLoadingContracts(false);
    }
  }

  useEffect(() => {
    // Wait for OrgProvider so POST /api/contracts includes X-Org-Id. A first-paint
    // upload with no org header persists a contract without org_id, and
    // ProposalService.create() then fails with "Contract is not assigned to an
    // organization" -- the full-lifecycle E2E's Save proposal step.
    if (orgLoading) return;
    void loadContracts();
  }, [orgLoading, currentOrg?.org_id]);

  async function uploadSingleAndAnalyze(file: File) {
    setMessage('Uploading contract...');
    const form = new FormData();
    form.append('file', file);
    const upload = await apiFetch('/api/contracts', { method: 'POST', body: form });
    if (!upload.ok) throw new Error((await upload.json()).detail || 'Upload failed');
    const created = await upload.json();
    if (created.ocr_status === 'ocr_unavailable') {
      setMessage(
        'Contract uploaded. This looks like a scanned document and the OCR engine is not ' +
          'configured on the server yet, so analysis will run on limited or no extracted text. ' +
          'Ask an admin to install Tesseract OCR, then re-run analysis for full results.',
      );
    } else if (created.ocr_status === 'ocr_success') {
      setMessage('Contract uploaded. Text extracted via OCR. Running Gemini analysis...');
    } else {
      setMessage('Contract uploaded. Running Gemini analysis...');
    }
    const analysis = await apiFetch(`/api/contracts/${created.contract_id}/analyze`, { method: 'POST' });
    if (!analysis.ok) throw new Error((await analysis.json()).detail || 'Analysis failed');
    const passport = await analysis.json();
    router.push(`/legal-passport?contractId=${encodeURIComponent(created.contract_id)}&contractVersion=1`);
    setMessage(`Analysis complete. Passport ${passport.passport_id} created.`);
  }

  async function uploadBatchAndAnalyze(selected: File[]) {
    setBatch(selected.map((item) => ({ filename: item.name, status: 'pending' })));
    setMessage(`Uploading ${selected.length} contracts...`);
    const form = new FormData();
    selected.forEach((item) => form.append('files', item));
    const upload = await apiFetch('/api/contracts/bulk', { method: 'POST', body: form });
    if (!upload.ok && upload.status !== 207) throw new Error((await upload.json().catch(() => null))?.detail || 'Bulk upload failed');
    const body: { results: Array<{ filename: string; ok: boolean; detail?: string; contract_id?: string }> } = await upload.json();
    setBatch(body.results.map((item) => ({
      filename: item.filename,
      status: item.ok ? 'analyzing' : 'error',
      detail: item.detail,
      contractId: item.contract_id,
    })));

    let analyzed = 0;
    let failed = 0;
    // Analyze sequentially, not in parallel -- avoids hammering the Gemini rate limit
    // with a burst of simultaneous requests when someone uploads a large batch.
    for (const item of body.results) {
      if (!item.ok || !item.contract_id) { failed += 1; continue; }
      try {
        const analysis = await apiFetch(`/api/contracts/${item.contract_id}/analyze`, { method: 'POST' });
        if (!analysis.ok) throw new Error((await analysis.json().catch(() => null))?.detail || 'Analysis failed');
        analyzed += 1;
        setBatch((current) => current.map((entry) => (entry.filename === item.filename ? { ...entry, status: 'done' } : entry)));
      } catch (error) {
        failed += 1;
        setBatch((current) => current.map((entry) => (entry.filename === item.filename
          ? { ...entry, status: 'error', detail: error instanceof Error ? error.message : 'Analysis failed' }
          : entry)));
      }
    }
    const uploadFailures = body.results.filter((item) => !item.ok).length;
    setMessage(
      `Batch complete: ${analyzed} analyzed, ${failed} failed` +
        (uploadFailures ? ` (${uploadFailures} rejected at upload).` : '.'),
    );
  }

  async function uploadAndAnalyze() {
    if (files.length === 0) return setMessage('Choose one or more PDF, DOCX, TXT, JPG, PNG, or TIFF contracts.');
    if (!canUpload) return setMessage('Select an organization before uploading a contract.');
    setBusy(true);
    setBatch([]);
    try {
      if (files.length === 1) {
        await uploadSingleAndAnalyze(files[0]);
      } else {
        await uploadBatchAndAnalyze(files);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Contract flow failed');
    } finally { setBusy(false); }
  }

  const failed = contracts.filter((item) => item.analysis_status === 'failed');

  const statusOptions = useMemo(
    () => Array.from(new Set(contracts.map((item) => item.status).filter((value): value is string => Boolean(value)))),
    [contracts],
  );
  const riskOptions = useMemo(
    () => Array.from(new Set(contracts.map((item) => item.risk_level).filter((value): value is string => Boolean(value)))),
    [contracts],
  );
  const filteredContracts = useMemo(() => {
    const query = search.trim().toLowerCase();
    return contracts.filter((item) => {
      if (query && !item.name.toLowerCase().includes(query) && !item.contract_id.toLowerCase().includes(query)) return false;
      if (statusFilter && item.status !== statusFilter) return false;
      if (riskFilter && item.risk_level !== riskFilter) return false;
      return true;
    });
  }, [contracts, search, statusFilter, riskFilter]);

  function applySavedFilters(filters: Record<string, unknown>) {
    if (typeof filters.search === 'string') setSearch(filters.search);
    if (typeof filters.statusFilter === 'string') setStatusFilter(filters.statusFilter);
    if (typeof filters.riskFilter === 'string') setRiskFilter(filters.riskFilter);
  }

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Workspace"
        title="Contracts"
        description="Upload, analyze, and track every contract in this organization."
      />

      <div className="mt-6 space-y-6">
        {failed.length > 0 && (
          <div className="flex items-start gap-3 rounded-[var(--radius-lg,0.75rem)] border border-amber-300 bg-amber-50 p-4 dark:border-amber-900/50 dark:bg-amber-950/30">
            <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-700 dark:text-amber-500" />
            <div>
              <p className="font-semibold text-amber-900 dark:text-amber-300">{failed.length} contract{failed.length === 1 ? '' : 's'} need attention</p>
              <p className="mt-1 text-sm text-amber-800 dark:text-amber-400">Analysis failed. Open the contract lifecycle page and use Retry so they do not sit silently on a failed badge.</p>
            </div>
          </div>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Analyze a contract</CardTitle>
            <CardDescription className="mt-1">
              Upload one or more fictional contracts (PDF, DOCX, TXT, or a scanned image/JPG/PNG/TIFF) to generate
              findings and a legal passport for each. Scanned documents and images are extracted with OCR automatically.
              Select more than one file for batch upload and analysis (up to 20 at a time).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
              <input
                type="file"
                multiple
                accept=".pdf,.docx,.txt,.jpg,.jpeg,.png,.tif,.tiff"
                onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                className="text-sm text-gray-700 dark:text-gray-300"
              />
              <Button onClick={uploadAndAnalyze} disabled={busy || !canUpload}>
                <UploadCloud className="h-4 w-4" />
                {busy ? 'Processing...' : files.length > 1 ? `Upload and analyze ${files.length} contracts` : 'Upload and analyze'}
              </Button>
            </div>
            {message && <p role="status" className="mt-4 text-sm text-gray-600 dark:text-gray-400">{message}</p>}
            {batch.length > 0 && (
              <ul className="mt-4 divide-y divide-gray-100 rounded border border-gray-200 dark:divide-gray-700 dark:border-gray-700">
                {batch.map((entry) => (
                  <li key={entry.filename} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                    <span className="truncate text-gray-700 dark:text-gray-300">{entry.filename}</span>
                    <span
                      className={
                        entry.status === 'done'
                          ? 'font-semibold uppercase text-green-700 dark:text-green-400'
                          : entry.status === 'error'
                            ? 'font-semibold uppercase text-red-700 dark:text-red-400'
                            : 'font-semibold uppercase text-gray-500 dark:text-gray-400'
                      }
                      title={entry.detail}
                    >
                      {entry.status}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>Your contracts</CardTitle>
              <CardDescription className="mt-1">Open a contract&apos;s lifecycle, or jump to its Legal Passport when one exists.</CardDescription>
            </div>
            <button type="button" onClick={() => void loadContracts()} className="text-sm font-medium text-[var(--brand-primary,#2563eb)] hover:underline">
              Refresh
            </button>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-3 border-b border-gray-100 pb-4 dark:border-gray-700 sm:flex-row sm:items-center">
              <label className="flex flex-1 items-center gap-2 rounded-[var(--radius-md,0.5rem)] border border-gray-300 px-3 dark:border-gray-600">
                <Search className="h-4 w-4 text-gray-400" />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search by name or contract ID"
                  className="w-full bg-transparent py-2 text-sm text-gray-900 outline-none dark:text-gray-100"
                />
              </label>
              <select
                aria-label="Filter by status"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
                className="rounded-[var(--radius-md,0.5rem)] border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-200"
              >
                <option value="">All statuses</option>
                {statusOptions.map((status) => (
                  <option key={status} value={status}>{status}</option>
                ))}
              </select>
              <select
                aria-label="Filter by risk level"
                value={riskFilter}
                onChange={(event) => setRiskFilter(event.target.value)}
                className="rounded-[var(--radius-md,0.5rem)] border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-200"
              >
                <option value="">All risk levels</option>
                {riskOptions.map((risk) => (
                  <option key={risk} value={risk}>{risk}</option>
                ))}
              </select>
            </div>
            <div className="mt-3 border-b border-gray-100 pb-3 dark:border-gray-700">
              <SavedViews page="contracts" currentFilters={{ search, statusFilter, riskFilter }} onApply={applySavedFilters} />
            </div>

            {loadingContracts && (
              <div className="mt-4 space-y-3">
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
              </div>
            )}
            {!loadingContracts && contracts.length === 0 && (
              <div className="mt-4">
                <EmptyState
                  title="No contracts yet"
                  description="Upload a PDF, DOCX, or TXT file above and run analysis. That creates findings, a Legal Passport, and evidence you can later anchor."
                />
              </div>
            )}
            {!loadingContracts && contracts.length > 0 && filteredContracts.length === 0 && (
              <div className="mt-4 rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-gray-50 p-8 text-center text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
                No contracts match the current filters.
              </div>
            )}

            {!loadingContracts && filteredContracts.length > 0 && (
              <div className="mt-4">
                <DataTable
                  columns={[
                    {
                      key: 'contract',
                      header: 'Contract',
                      className: 'w-[28%] min-w-[180px] max-w-[280px]',
                      render: (contract: ContractSummary) => (
                        <div className="min-w-0">
                          <p className="truncate font-medium text-gray-900 dark:text-gray-100">{contract.name}</p>
                          <p className="mt-0.5 truncate font-mono text-[11px] text-gray-400 dark:text-gray-500">{contract.contract_id}</p>
                        </div>
                      ),
                    },
                    {
                      key: 'version',
                      header: 'Version',
                      className: 'w-[8%] min-w-[72px] whitespace-nowrap',
                      render: (contract: ContractSummary) => <span className="text-gray-600 dark:text-gray-400">{contract.version ?? '—'}</span>,
                    },
                    {
                      key: 'risk',
                      header: 'Risk',
                      className: 'w-[12%] min-w-[110px] whitespace-nowrap',
                      render: (contract: ContractSummary) => (
                        contract.risk_level ? (
                          <Badge variant={riskVariant(contract.risk_level)}>
                            {contract.risk_score != null ? `${contract.risk_score} · ` : ''}{contract.risk_level}
                          </Badge>
                        ) : (
                          <span className="text-gray-400 dark:text-gray-500">—</span>
                        )
                      ),
                    },
                    {
                      key: 'status',
                      header: 'Status',
                      className: 'w-[14%] min-w-[120px] whitespace-nowrap',
                      render: (contract: ContractSummary) => {
                        const canOpenPassport = Boolean(contract.passport_id && contract.version != null);
                        const failedAnalysis = contract.analysis_status === 'failed';
                        if (contract.proof_status === 'confirmed') return <Badge variant="verified">Confirmed</Badge>;
                        if (contract.proof_status === 'processing') return <Badge variant="pending">Processing</Badge>;
                        if (contract.proof_status === 'action_required') return <Badge variant="pending">Action required</Badge>;
                        return failedAnalysis ? (
                          <Badge variant="tampered">Failed — retry</Badge>
                        ) : canOpenPassport ? (
                          <Badge variant="verified">Passport ready</Badge>
                        ) : (
                          <Badge variant="pending">{contract.analysis_status || contract.status}</Badge>
                        );
                      },
                    },
                    {
                      key: 'evidence',
                      header: 'Evidence',
                      className: 'w-[9%] min-w-[80px] whitespace-nowrap',
                      render: (contract: ContractSummary) => <span className="text-gray-600 dark:text-gray-400">{contract.evidence_count ?? '—'}</span>,
                    },
                    {
                      key: 'updated',
                      header: 'Updated',
                      className: 'w-[12%] min-w-[90px] whitespace-nowrap',
                      render: (contract: ContractSummary) => <span className="text-gray-500 dark:text-gray-400">{relativeDate(contract.updated_at)}</span>,
                    },
                    {
                      key: 'action',
                      header: 'Action',
                      className: 'w-[12%] min-w-[110px] text-right whitespace-nowrap',
                      render: (contract: ContractSummary) => {
                        const canOpenPassport = Boolean(contract.passport_id && contract.version != null);
                        const failedAnalysis = contract.analysis_status === 'failed';
                        if (contract.proof_status === 'confirmed' || contract.recommended_action !== 'retry') return <span className="font-medium text-gray-500">Open lifecycle</span>;
                        return (
                          <span className="font-medium text-[var(--brand-primary,#2563eb)]">
                            {failedAnalysis ? 'Retry' : canOpenPassport ? 'Open lifecycle' : 'View'}
                          </span>
                        );
                      },
                    },
                  ]}
                  data={filteredContracts}
                  rowKey={(contract) => contract.contract_id}
                  pageSize={10}
                  onRowClick={(contract) => router.push(`/dashboard/contracts/${encodeURIComponent(contract.contract_id)}`)}
                />
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
