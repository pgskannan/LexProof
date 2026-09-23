'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { apiFetch } from '../../../../../lib/api';
import { analyzeVersionRequest } from '../../../../../lib/redlineProposals';
import { EmptyState } from '../../../../../components/EmptyState';
import { Skeleton } from '../../../../../components/ui/skeleton';
import { Badge } from '../../../../../components/ui/badge';
import { Button } from '../../../../../components/ui/button';
import { Card, CardContent } from '../../../../../components/ui/card';
import { PageHeader } from '../../../../../components/ui/page-header';
import { PageContainer } from '../../../../../components/ui/container';

type AnalysisResult = {
  version_number: number;
  passport_id: string;
  finding_count: number;
  evidence_count: number;
};

type VersionRecord = {
  version_id: string;
  version_number: number;
  parent_version_id?: string | null;
  created_at?: string | null;
  created_by?: string | null;
  analysis_status?: string | null;
  passport_id?: string | null;
  published?: boolean;
  is_current?: boolean;
  ocr_status?: string | null;
  contains_pii?: boolean;
};

export default function ContractVersions() {
  const searchParams = useSearchParams();
  const [contractId, setContractId] = useState('');
  const [versionId, setVersionId] = useState('');
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [versions, setVersions] = useState<VersionRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => {
    const id = searchParams.get('contractId') ?? '';
    setContractId(id);
    if (!id) return;
    setHistoryLoading(true);
    void apiFetch(`/api/contracts/${encodeURIComponent(id)}/versions`)
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load version history');
        setVersions(await response.json());
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Unable to load version history'))
      .finally(() => setHistoryLoading(false));
  }, [searchParams]);

  async function analyzeVersion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!contractId.trim() || !versionId.trim()) {
      setError('Contract ID and version ID are required.');
      return;
    }
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const request = analyzeVersionRequest(contractId.trim(), versionId.trim());
      const response = await apiFetch(request.path, { method: request.method });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to analyze version');
      setResult(await response.json());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to analyze version');
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Contracts"
        title="Contract Versions"
        description="Analyze one persisted contract version without changing historical records."
      />

      <div className="mt-6 space-y-6">
      <Card>
        <CardContent>
          <form onSubmit={analyzeVersion} className="space-y-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Analyze Version</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Contract ID<input value={contractId} onChange={(event) => setContractId(event.target.value)} className="mt-2 block w-full rounded border border-gray-300 px-3 py-2 font-normal dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100" placeholder="Contract identifier" /></label>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Version ID<input value={versionId} onChange={(event) => setVersionId(event.target.value)} className="mt-2 block w-full rounded border border-gray-300 px-3 py-2 font-normal dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100" placeholder="Persisted version identifier" /></label>
            </div>
            <Button type="submit" disabled={loading}>{loading ? 'Analyzing...' : 'Analyze Version'}</Button>
            {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
          </form>
        </CardContent>
      </Card>

      {result && (
        <Card className="border-green-200 bg-green-50 dark:border-green-900/50 dark:bg-green-950/20">
          <CardContent>
            <p className="text-xs font-bold uppercase tracking-wider text-green-700 dark:text-green-400">Analysis Complete</p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div><p className="text-xs uppercase text-gray-500 dark:text-gray-400">Version</p><p className="mt-1 font-semibold text-gray-900 dark:text-gray-100">v{result.version_number}</p></div>
              <div><p className="text-xs uppercase text-gray-500 dark:text-gray-400">Passport</p><p className="mt-1 break-all font-mono text-sm text-gray-900 dark:text-gray-100">{result.passport_id}</p></div>
              <div><p className="text-xs uppercase text-gray-500 dark:text-gray-400">Findings</p><p className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{result.finding_count}</p></div>
              <div><p className="text-xs uppercase text-gray-500 dark:text-gray-400">Evidence</p><p className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{result.evidence_count}</p></div>
            </div>
          </CardContent>
        </Card>
      )}

      {contractId && (
        <Card>
          <CardContent className="space-y-4">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Version history</h2>
              <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">Read-only records for this contract.</p>
            </div>
            {historyLoading && (
              <div className="space-y-3">
                <Skeleton className="h-28 w-full" />
                <Skeleton className="h-28 w-full" />
              </div>
            )}
            {!historyLoading && versions.length === 0 && (
              <EmptyState
                title="No version history yet"
                description="Analyze a contract to create version 1. Publishing an approved redline adds later versions you can inspect here."
              />
            )}
            <div className="space-y-3">
              {versions.map((version) => (
                <div key={version.version_id} className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 p-4 dark:border-gray-700">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100">V{version.version_number}</h3>
                      <Badge variant={version.is_current ? 'verified' : 'secondary'}>{version.is_current ? 'Current version' : 'Superseded version'}</Badge>
                      {version.ocr_status === 'ocr_success' && <Badge variant="verified">OCR extracted</Badge>}
                      {version.ocr_status === 'ocr_unavailable' && <Badge variant="pending">OCR pending (Tesseract not installed)</Badge>}
                      {version.contains_pii && <Badge variant="high">Contains PII</Badge>}
                    </div>
                    <Badge variant="secondary">{version.analysis_status || 'Not available'}</Badge>
                  </div>
                  <dl className="mt-3 grid gap-2 text-xs text-gray-600 dark:text-gray-400 sm:grid-cols-2">
                    <div><dt className="font-semibold text-gray-700 dark:text-gray-300">Version ID</dt><dd className="break-all font-mono">{version.version_id}</dd></div>
                    <div><dt className="font-semibold text-gray-700 dark:text-gray-300">Parent</dt><dd className="break-all font-mono">{version.parent_version_id || 'Not available'}</dd></div>
                    <div><dt className="font-semibold text-gray-700 dark:text-gray-300">Created by</dt><dd>{version.created_by || 'Not available'}</dd></div>
                    <div><dt className="font-semibold text-gray-700 dark:text-gray-300">Created</dt><dd>{version.created_at ? new Date(version.created_at).toLocaleString() : 'Not available'}</dd></div>
                    <div><dt className="font-semibold text-gray-700 dark:text-gray-300">Passport</dt><dd className="break-all font-mono">{version.passport_id || 'Not available'}</dd></div>
                    <div><dt className="font-semibold text-gray-700 dark:text-gray-300">Publication</dt><dd>{version.published ? 'Published' : 'Not published'}</dd></div>
                  </dl>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
      </div>
    </PageContainer>
  );
}
