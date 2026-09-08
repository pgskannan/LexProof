'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { apiFetch } from '../../../../../lib/api';
import { analyzeVersionRequest } from '../../../../../lib/redlineProposals';
import { EmptyState } from '../../../../../components/EmptyState';
import { Skeleton } from '../../../../../components/ui/skeleton';

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
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Contract Versions</h1>
        <p className="mt-2 text-gray-600">Analyze one persisted contract version without changing historical records.</p>
      </div>

      <form onSubmit={analyzeVersion} className="space-y-4 rounded-lg bg-white p-6 shadow">
        <h2 className="text-xl font-semibold text-gray-900">Analyze Version</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium text-gray-700">Contract ID<input value={contractId} onChange={(event) => setContractId(event.target.value)} className="mt-2 block w-full rounded border border-gray-300 px-3 py-2 font-normal" placeholder="Contract identifier" /></label>
          <label className="text-sm font-medium text-gray-700">Version ID<input value={versionId} onChange={(event) => setVersionId(event.target.value)} className="mt-2 block w-full rounded border border-gray-300 px-3 py-2 font-normal" placeholder="Persisted version identifier" /></label>
        </div>
        <button type="submit" disabled={loading} className="rounded bg-blue-600 px-5 py-3 font-medium text-white disabled:opacity-50">{loading ? 'Analyzing...' : 'Analyze Version'}</button>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      </form>

      {result && <section className="rounded-lg border border-emerald-200 bg-emerald-50 p-6">
        <p className="text-xs font-bold uppercase tracking-wider text-emerald-700">Analysis Complete</p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div><p className="text-xs uppercase text-gray-500">Version</p><p className="mt-1 font-semibold text-gray-900">v{result.version_number}</p></div>
          <div><p className="text-xs uppercase text-gray-500">Passport</p><p className="mt-1 break-all font-mono text-sm text-gray-900">{result.passport_id}</p></div>
          <div><p className="text-xs uppercase text-gray-500">Findings</p><p className="mt-1 font-semibold text-gray-900">{result.finding_count}</p></div>
          <div><p className="text-xs uppercase text-gray-500">Evidence</p><p className="mt-1 font-semibold text-gray-900">{result.evidence_count}</p></div>
        </div>
      </section>}

      {contractId && <section className="space-y-4 rounded-lg border border-gray-200 bg-white p-6 shadow">
        <div><h2 className="text-xl font-semibold text-gray-900">Version history</h2><p className="mt-1 text-sm text-gray-600">Read-only records for this contract.</p></div>
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
        <div className="space-y-3">{versions.map((version) => <article key={version.version_id} className="border border-gray-200 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold text-gray-900">V{version.version_number} <span className="ml-2 text-xs font-bold uppercase text-blue-700">{version.is_current ? 'Current version' : 'Superseded version'}</span></h3><span className="text-xs font-bold uppercase text-gray-500">{version.analysis_status || 'Not available'}</span></div><dl className="mt-3 grid gap-2 text-xs text-gray-600 sm:grid-cols-2"><div><dt className="font-semibold">Version ID</dt><dd className="break-all font-mono">{version.version_id}</dd></div><div><dt className="font-semibold">Parent</dt><dd className="break-all font-mono">{version.parent_version_id || 'Not available'}</dd></div><div><dt className="font-semibold">Created by</dt><dd>{version.created_by || 'Not available'}</dd></div><div><dt className="font-semibold">Created</dt><dd>{version.created_at ? new Date(version.created_at).toLocaleString() : 'Not available'}</dd></div><div><dt className="font-semibold">Passport</dt><dd className="break-all font-mono">{version.passport_id || 'Not available'}</dd></div><div><dt className="font-semibold">Publication</dt><dd>{version.published ? 'Published' : 'Not published'}</dd></div></dl></article>)}</div>
      </section>}
    </div>
  );
}
