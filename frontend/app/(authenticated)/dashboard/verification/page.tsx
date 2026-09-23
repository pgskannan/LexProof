'use client';

import { useMemo, useState } from 'react';
import { AlertTriangle, ChevronDown, ExternalLink, FileCheck2, Hash, Loader2, ShieldCheck } from 'lucide-react';
import { apiFetch } from '../../../../lib/api';
import { toStatusMeta, statusTone } from '../../../../lib/verificationStatus';
import { Button } from '../../../../components/ui/button';
import { Card, CardContent } from '../../../../components/ui/card';
import { PageHeader } from '../../../../components/ui/page-header';
import { PageContainer } from '../../../../components/ui/container';

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

const TONE_CLASSES: Record<'green' | 'red' | 'amber', { box: string; text: string; sub: string; icon: string }> = {
  green: {
    box: 'bg-emerald-50 border-emerald-300 dark:bg-emerald-950/30 dark:border-emerald-800',
    text: 'text-emerald-700 dark:text-emerald-400',
    sub: 'text-emerald-800 dark:text-emerald-300',
    icon: 'text-emerald-500',
  },
  red: {
    box: 'bg-red-50 border-red-300 dark:bg-red-950/30 dark:border-red-800',
    text: 'text-red-700 dark:text-red-400',
    sub: 'text-red-800 dark:text-red-300',
    icon: 'text-red-500',
  },
  amber: {
    box: 'bg-amber-50 border-amber-300 dark:bg-amber-950/30 dark:border-amber-800',
    text: 'text-amber-700 dark:text-amber-400',
    sub: 'text-amber-800 dark:text-amber-300',
    icon: 'text-amber-500',
  },
};

export default function DashboardVerificationPage() {
  const [evidenceId, setEvidenceId] = useState('');
  const [result, setResult] = useState<EvidenceVerificationResult | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showTechnical, setShowTechnical] = useState(false);

  const handleVerify = async () => {
    if (!evidenceId.trim()) {
      setError('Enter an evidence ID to verify.');
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);
    setShowTechnical(false);

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
  const ResultIcon = result?.verified ? ShieldCheck : AlertTriangle;

  const copyHash = async (value?: string | null) => {
    if (!value) return;
    await navigator.clipboard.writeText(value);
  };

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Evidence"
        title="Verification"
        description="Validate evidence integrity against the on-chain Ethereum anchor — the same public proof anyone outside LexProof can check independently."
        actions={
          <div className="hidden md:flex items-center gap-2 rounded-full bg-white px-4 py-2 shadow-[var(--shadow-xs)] border border-gray-200 text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
            Public verification contract
          </div>
        }
      />

      <div className="mt-6 space-y-6">
        <Card>
          <CardContent className="py-6">
            <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
              <div>
                <label htmlFor="evidence-id" className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Evidence ID
                </label>
                <input
                  id="evidence-id"
                  value={evidenceId}
                  onChange={(event) => setEvidenceId(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void handleVerify();
                  }}
                  className="w-full rounded-[var(--radius-md,0.5rem)] border border-gray-300 bg-white px-4 py-3 text-sm text-gray-900 outline-none focus:border-[var(--brand-primary,#2563eb)] dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
                  placeholder="e.g. evd_123 or the anchored record ID"
                />
              </div>
              <Button onClick={() => void handleVerify()} disabled={loading || !evidenceId.trim()} className="min-w-[180px]">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileCheck2 className="h-4 w-4" />}
                {loading ? 'Verifying...' : 'Verify Evidence'}
              </Button>
            </div>
          </CardContent>
        </Card>

        {!result && !error && (
          <div className="rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-gray-50/80 p-4 dark:border-gray-700 dark:bg-gray-900/60">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-gray-500 dark:text-gray-400">
              How verification works
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900/80">
                <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Evidence fingerprint</div>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  The stored evidence is recomputed into a fingerprint and compared with the anchored value.
                </p>
              </div>
              <div className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900/80">
                <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Ethereum anchor</div>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  The fingerprint is recorded to a public Ethereum anchor for later comparison.
                </p>
              </div>
              <div className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900/80">
                <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Verification result</div>
                <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                  LexProof compares the records and reports whether the evidence still matches the Ethereum anchor.
                </p>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-[var(--radius-lg,0.75rem)] border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400">
            {error}
          </div>
        )}

        {result && (
          <div className="space-y-6">
            {/* Lead with the result -- a viewer should know VERIFIED /
                TAMPERED / NOT FOUND before any technical detail. */}
            <div className={`rounded-[var(--radius-lg,0.75rem)] border-2 p-7 text-center sm:text-left ${toneClasses.box}`}>
              <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-start">
                <ResultIcon className={`h-10 w-10 flex-shrink-0 ${toneClasses.icon}`} />
                <div>
                  <div className={`text-3xl sm:text-4xl font-bold ${toneClasses.text}`}>{statusMeta.label}</div>
                  <p className={`mt-2 text-base ${toneClasses.sub}`}>
                    {result.verified
                      ? 'The recomputed evidence hash matches the Ethereum anchor. This record has not been altered since it was anchored.'
                      : result.status === 'TAMPERED'
                        ? 'The stored evidence no longer matches the anchored hash. It was altered after anchoring.'
                        : 'No valid evidence record or Ethereum hash was found for this ID.'}
                  </p>
                </div>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setShowTechnical((open) => !open)}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200"
            >
              <ChevronDown className={`h-4 w-4 transition-transform ${showTechnical ? 'rotate-180' : ''}`} />
              {showTechnical ? 'Hide' : 'Show'} technical details
            </button>

            {showTechnical && (
              <div className="space-y-6">
                <div className="grid gap-6 lg:grid-cols-2">
                  <Card>
                    <CardContent className="py-5">
                      <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
                        <Hash className="h-4 w-4 text-[var(--brand-primary,#2563eb)]" />
                        Hash comparison
                      </div>
                      <div className="space-y-4 text-sm">
                        {result.evidence_hash_on_chain && (
                          <div>
                            <div className="mb-1 flex items-center justify-between">
                              <span className="text-gray-500 dark:text-gray-400">On-chain hash</span>
                              <button type="button" onClick={() => void copyHash(result.evidence_hash_on_chain)} className="text-[var(--brand-primary,#2563eb)] hover:underline">Copy</button>
                            </div>
                            <p className="break-all rounded-[var(--radius-md,0.5rem)] bg-gray-50 p-3 font-mono text-xs dark:bg-gray-900">{result.evidence_hash_on_chain}</p>
                          </div>
                        )}
                        {result.computed_hash && (
                          <div>
                            <div className="mb-1 flex items-center justify-between">
                              <span className="text-gray-500 dark:text-gray-400">Recomputed hash</span>
                              <button type="button" onClick={() => void copyHash(result.computed_hash)} className="text-[var(--brand-primary,#2563eb)] hover:underline">Copy</button>
                            </div>
                            <p className="break-all rounded-[var(--radius-md,0.5rem)] bg-gray-50 p-3 font-mono text-xs dark:bg-gray-900">{result.computed_hash}</p>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardContent className="py-5">
                      <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
                        <ShieldCheck className="h-4 w-4 text-emerald-600" />
                        Ethereum metadata
                      </div>
                      <dl className="space-y-3 text-sm text-gray-700 dark:text-gray-300">
                        <div className="flex justify-between gap-4">
                          <dt className="text-gray-500 dark:text-gray-400">Network</dt>
                          <dd>{result.blockchain_network ?? 'N/A'}</dd>
                        </div>
                        <div className="flex justify-between gap-4">
                          <dt className="text-gray-500 dark:text-gray-400">Contract</dt>
                          <dd className="break-all text-right">
                            {result.contract_address ? (
                              <a href={`${SEPOLIA_EXPLORER}/address/${result.contract_address}`} target="_blank" rel="noreferrer" className="text-[var(--brand-primary,#2563eb)] underline">
                                {result.contract_address}
                              </a>
                            ) : 'N/A'}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-4">
                          <dt className="text-gray-500 dark:text-gray-400">Anchor time</dt>
                          <dd>{result.anchored_at ? new Date(result.anchored_at).toLocaleString() : 'N/A'}</dd>
                        </div>
                        {result.transaction_hash && (
                          <div className="flex justify-between gap-4">
                            <dt className="text-gray-500 dark:text-gray-400">Transaction</dt>
                            <dd className="break-all text-right">
                              <a href={`${SEPOLIA_EXPLORER}/tx/${result.transaction_hash}`} target="_blank" rel="noreferrer" className="text-[var(--brand-primary,#2563eb)] underline">
                                {result.transaction_hash}
                              </a>
                            </dd>
                          </div>
                        )}
                        {result.block_number != null && (
                          <div className="flex justify-between gap-4">
                            <dt className="text-gray-500 dark:text-gray-400">Block</dt>
                            <dd>{result.block_number}</dd>
                          </div>
                        )}
                      </dl>
                    </CardContent>
                  </Card>
                </div>

                <Card>
                  <CardContent className="py-5">
                    <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
                      <AlertTriangle className="h-4 w-4 text-amber-600" />
                      Evidence details
                    </div>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <div className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">Evidence ID</div>
                        <div className="mt-1 break-all font-mono text-sm dark:text-gray-200">{result.evidence_id}</div>
                      </div>
                      <div>
                        <div className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">Checked at</div>
                        <div className="mt-1 text-sm dark:text-gray-200">{new Date(result.timestamp).toLocaleString()}</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {result.transaction_hash && (
                  <div className="flex justify-end">
                    <a
                      href={`${SEPOLIA_EXPLORER}/tx/${result.transaction_hash}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-2 rounded-[var(--radius-md,0.5rem)] border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100 dark:border-blue-900/50 dark:bg-blue-950/30 dark:text-blue-300"
                    >
                      View on Etherscan
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </PageContainer>
  );
}
