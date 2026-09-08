'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertTriangle } from 'lucide-react';
import { apiFetch } from '../../../../lib/api';
import { EmptyState } from '../../../../components/EmptyState';
import { Skeleton } from '../../../../components/ui/skeleton';

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
}

export default function AllContracts() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [loadingContracts, setLoadingContracts] = useState(true);

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
    void loadContracts();
  }, []);

  async function uploadAndAnalyze() {
    if (!file) return setMessage('Choose a PDF, DOCX, or TXT contract.');
    setBusy(true); setMessage('Uploading contract...');
    try {
      const form = new FormData();
      form.append('file', file);
      const upload = await apiFetch('/api/contracts', { method: 'POST', body: form });
      if (!upload.ok) throw new Error((await upload.json()).detail || 'Upload failed');
      const created = await upload.json();
      setMessage('Contract uploaded. Running Gemini analysis...');
      const analysis = await apiFetch(`/api/contracts/${created.contract_id}/analyze`, { method: 'POST' });
      if (!analysis.ok) throw new Error((await analysis.json()).detail || 'Analysis failed');
      const passport = await analysis.json();
      router.push(`/legal-passport?contractId=${encodeURIComponent(created.contract_id)}&contractVersion=1`);
      setMessage(`Analysis complete. Passport ${passport.passport_id} created.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Contract flow failed');
    } finally { setBusy(false); }
  }

  const failed = contracts.filter((item) => item.analysis_status === 'failed');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">All Contracts</h1>
        <p className="text-gray-600 mt-2">View and manage all contracts in the system</p>
      </div>

      {failed.length > 0 && (
        <div className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-700" />
          <div>
            <p className="font-semibold text-amber-900">{failed.length} contract{failed.length === 1 ? '' : 's'} need attention</p>
            <p className="mt-1 text-sm text-amber-800">Analysis failed. Open the contract lifecycle page and use Retry so they do not sit silently on a failed badge.</p>
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold text-gray-900">Analyze a contract</h2>
        <p className="mt-2 text-gray-600">Upload a fictional contract to generate findings and a legal passport.</p>
        <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-center">
          <input type="file" accept=".pdf,.docx,.txt" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          <button onClick={uploadAndAnalyze} disabled={busy} className="rounded bg-blue-600 px-5 py-3 font-medium text-white disabled:opacity-50">
            {busy ? 'Processing...' : 'Upload and analyze'}
          </button>
        </div>
        {message && <p role="status" className="mt-4 text-sm text-gray-600">{message}</p>}
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Your contracts</h2>
            <p className="mt-1 text-sm text-gray-600">Open a contract&apos;s lifecycle, or jump to its Legal Passport when one exists.</p>
          </div>
          <button type="button" onClick={() => void loadContracts()} className="text-sm font-medium text-blue-700 hover:text-blue-900">
            Refresh
          </button>
        </div>

        {loadingContracts && (
          <div className="mt-6 space-y-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        )}
        {!loadingContracts && contracts.length === 0 && (
          <div className="mt-6">
            <EmptyState
              title="No contracts yet"
              description="Upload a PDF, DOCX, or TXT file above and run analysis. That creates findings, a Legal Passport, and evidence you can later anchor."
            />
          </div>
        )}
        <div className="mt-6 space-y-3">
          {contracts.map((contract) => {
            const canOpenPassport = Boolean(contract.passport_id && contract.version != null);
            const failedAnalysis = contract.analysis_status === 'failed';
            return (
              <button
                key={contract.contract_id}
                type="button"
                onClick={() => router.push(`/dashboard/contracts/${encodeURIComponent(contract.contract_id)}`)}
                className="w-full rounded-lg border border-gray-200 p-4 text-left transition hover:border-blue-400 hover:bg-blue-50"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="font-semibold text-gray-900">{contract.name}</h3>
                    <p className="mt-1 font-mono text-xs text-gray-600">Contract ID: {contract.contract_id}</p>
                  </div>
                  <span className={`rounded px-2 py-1 text-xs font-medium ${failedAnalysis ? 'bg-amber-100 text-amber-800' : 'bg-gray-100 text-gray-700'}`}>
                    {failedAnalysis ? 'Analysis failed — retry' : canOpenPassport ? 'Open lifecycle' : contract.analysis_status || contract.status}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-gray-600">
                  <span>Version: {contract.version ?? '—'}</span>
                  <span>Risk: {contract.risk_score ?? '—'}{contract.risk_level ? ` (${contract.risk_level})` : ''}</span>
                  <span>Passport ID: {contract.passport_id ?? 'Not created'}</span>
                  <span>Evidence: {contract.evidence_count ?? '—'}</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
