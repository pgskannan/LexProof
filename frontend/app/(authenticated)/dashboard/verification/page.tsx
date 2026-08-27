'use client';

import { useMemo, useState } from 'react';
import { AlertTriangle, ArrowLeft, CheckCircle2, ExternalLink, FileCheck2, Hash, Loader2, ShieldCheck } from 'lucide-react';
import { apiFetch } from '../../../../lib/api';
import { toStatusMeta, statusTone } from '../../../../lib/verificationStatus';

interface EvidenceVerificationResult {
  evidence_id: string;
  verified: boolean;
  status: string;
  evidence_hash_on_chain: string | null;
  computed_hash: string | null;
  blockchain_network: string | null;
  contract_address: string | null;
  transaction_hash: string | null;
  block_number: number | null;
  anchored_at: string | null;
  timestamp: string;
}

const SEPOLIA_EXPLORER = 'https://sepolia.etherscan.io';

const TONE_CLASSES: Record<'green' | 'red' | 'amber', { box: string; text: string; sub: string }> = {
  green: {
    box: 'bg-green-50 border-2 border-green-500',
    text: 'text-green-600',
    sub: 'text-green-700',
  },
  red: {
    box: 'bg-red-50 border-2 border-red-500',
    text: 'text-red-600',
    sub: 'text-red-700',
  },
  amber: {
    box: 'bg-amber-50 border-2 border-amber-500',
    text: 'text-amber-600',
    sub: 'text-amber-700',
  },
};

export default function DashboardVerificationPage() {
  const [evidenceId, setEvidenceId] = useState('');
  const [result, setResult] = useState<EvidenceVerificationResult | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleVerify = async () => {
    if (!evidenceId.trim()) {
      setError('Enter an evidence ID to verify.');
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);

    try {
      const response = await apiFetch(`/api/verify/${encodeURIComponent(evidenceId.trim())}`);
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || `Verification failed (${response.status})`);
      }
      const data = (await response.json()) as EvidenceVerificationResult;
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to verify evidence');
    } finally {
      setLoading(false);
    }
  };

  const statusMeta = useMemo(() => toStatusMeta(result?.status), [result?.status]);
  const toneKey = statusTone(result?.status) as 'green' | 'red' | 'amber';
  const toneClasses = TONE_CLASSES[toneKey] ?? TONE_CLASSES.amber;

  const copyHash = async (value?: string | null) => {
    if (!value) return;
    await navigator.clipboard.writeText(value);
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <button
              type="button"
              onClick={() => window.history.back()}
              className="inline-flex items-center gap-2 text-sm text-blue-600 hover:text-blue-700"
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </button>
            <h1 className="mt-3 text-3xl font-bold text-gray-900">Evidence Verification</h1>
            <p className="mt-2 text-gray-600">Validate evidence integrity against the on-chain Ethereum anchor.</p>
          </div>
          <div className="hidden md:flex items-center gap-2 rounded-full bg-white px-4 py-2 shadow-sm border border-gray-200 text-sm text-gray-700">
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
            Public verification contract
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
            <div>
              <label htmlFor="evidence-id" className="mb-2 block text-sm font-medium text-gray-700">
                Evidence ID
              </label>
              <input
                id="evidence-id"
                value={evidenceId}
                onChange={(event) => setEvidenceId(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void handleVerify();
                }}
                className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm outline-none ring-0 focus:border-blue-500"
                placeholder="e.g. evd_123 or the anchored record ID"
              />
            </div>
            <button
              type="button"
              onClick={() => void handleVerify()}
              disabled={loading || !evidenceId.trim()}
              className="inline-flex min-w-[180px] items-center justify-center gap-2 rounded-lg bg-blue-600 px-5 py-3 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileCheck2 className="h-4 w-4" />}
              {loading ? 'Verifying...' : 'Verify Evidence'}
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {result && (
          <div className="space-y-6">
            <div className={`rounded-xl border p-6 ${toneClasses.box}`}>
              <div className={`text-4xl font-bold ${toneClasses.text}`}>{statusMeta.label}</div>
              <p className={`mt-3 text-base ${toneClasses.sub}`}>
                {result.verified
                  ? 'The recomputed evidence hash matches the Ethereum anchor.'
                  : result.status === 'TAMPERED'
                    ? 'The stored evidence no longer matches the anchored hash. It was altered after anchoring.'
                    : 'No valid evidence record or Ethereum hash was found for this ID.'}
              </p>
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-700">
                  <Hash className="h-4 w-4 text-blue-600" />
                  Hash comparison
                </div>
                <div className="space-y-4 text-sm">
                  {result.evidence_hash_on_chain && (
                    <div>
                      <div className="mb-1 flex items-center justify-between">
                        <span className="text-gray-500">On-chain hash</span>
                        <button type="button" onClick={() => void copyHash(result.evidence_hash_on_chain)} className="text-blue-600 hover:text-blue-700">Copy</button>
                      </div>
                      <p className="break-all rounded-md bg-gray-50 p-3 font-mono text-xs">{result.evidence_hash_on_chain}</p>
                    </div>
                  )}
                  {result.computed_hash && (
                    <div>
                      <div className="mb-1 flex items-center justify-between">
                        <span className="text-gray-500">Recomputed hash</span>
                        <button type="button" onClick={() => void copyHash(result.computed_hash)} className="text-blue-600 hover:text-blue-700">Copy</button>
                      </div>
                      <p className="break-all rounded-md bg-gray-50 p-3 font-mono text-xs">{result.computed_hash}</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-700">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  Ethereum metadata
                </div>
                <dl className="space-y-3 text-sm text-gray-700">
                  <div className="flex justify-between gap-4">
                    <dt className="text-gray-500">Network</dt>
                    <dd>{result.blockchain_network ?? 'N/A'}</dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-gray-500">Contract</dt>
                    <dd className="break-all text-right">
                      {result.contract_address ? (
                        <a href={`${SEPOLIA_EXPLORER}/address/${result.contract_address}`} target="_blank" rel="noreferrer" className="text-blue-600 underline">
                          {result.contract_address}
                        </a>
                      ) : 'N/A'}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-gray-500">Anchor time</dt>
                    <dd>{result.anchored_at ? new Date(result.anchored_at).toLocaleString() : 'N/A'}</dd>
                  </div>
                  {result.transaction_hash && (
                    <div className="flex justify-between gap-4">
                      <dt className="text-gray-500">Transaction</dt>
                      <dd className="break-all text-right">
                        <a href={`${SEPOLIA_EXPLORER}/tx/${result.transaction_hash}`} target="_blank" rel="noreferrer" className="text-blue-600 underline">
                          {result.transaction_hash}
                        </a>
                      </dd>
                    </div>
                  )}
                  {result.block_number != null && (
                    <div className="flex justify-between gap-4">
                      <dt className="text-gray-500">Block</dt>
                      <dd>{result.block_number}</dd>
                    </div>
                  )}
                </dl>
              </div>
            </div>

            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-700">
                <AlertTriangle className="h-4 w-4 text-amber-600" />
                Evidence details
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <div className="text-xs uppercase tracking-wide text-gray-500">Evidence ID</div>
                  <div className="mt-1 break-all font-mono text-sm">{result.evidence_id}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-gray-500">Checked at</div>
                  <div className="mt-1 text-sm">{new Date(result.timestamp).toLocaleString()}</div>
                </div>
              </div>
            </div>

            {result.transaction_hash && (
              <div className="flex justify-end">
                <a
                  href={`${SEPOLIA_EXPLORER}/tx/${result.transaction_hash}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100"
                >
                  View on Etherscan
                  <ExternalLink className="h-4 w-4" />
                </a>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
