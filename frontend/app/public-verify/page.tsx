"use client";

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import { apiFetch } from '../../lib/api';
import {
  verifyOnChainIndependently,
  type ChainCheckResult,
} from '../../lib/independentChainVerify';

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

const STATUS_COPY: Record<string, { label: string; tone: 'green' | 'red' | 'amber' }> = {
  VERIFIED: { label: 'VERIFIED', tone: 'green' },
  TAMPERED: { label: 'TAMPERED', tone: 'red' },
  EVIDENCE_NOT_FOUND: { label: 'EVIDENCE NOT FOUND', tone: 'amber' },
  ANCHOR_NOT_FOUND: { label: 'NOT YET ANCHORED', tone: 'amber' },
};

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

const CHAIN_TONE_CLASSES: Record<'green' | 'red' | 'amber' | 'gray', { box: string; text: string }> = {
  green: { box: 'bg-green-50 border border-green-400', text: 'text-green-700' },
  red: { box: 'bg-red-50 border border-red-400', text: 'text-red-700' },
  amber: { box: 'bg-amber-50 border border-amber-400', text: 'text-amber-700' },
  gray: { box: 'bg-gray-50 border border-gray-300', text: 'text-gray-600' },
};

function sepoliaTxUrl(txHash: string): string {
  return `https://sepolia.etherscan.io/tx/${txHash}`;
}

function sepoliaAddressUrl(address: string): string {
  return `https://sepolia.etherscan.io/address/${address}`;
}

export default function PublicVerifyPage() {
  const searchParams = useSearchParams();
  const evidenceIdFromUrl = searchParams.get('evidence_id')?.trim();
  const [evidenceId, setEvidenceId] = useState('');
  const [result, setResult] = useState<EvidenceVerificationResult | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [chainCheck, setChainCheck] = useState<ChainCheckResult | null>(null);

  const handleVerify = async (id = evidenceId) => {
    const requestedEvidenceId = id.trim();
    if (!requestedEvidenceId) {
      setError('Please enter an evidence ID');
      return;
    }

    setIsLoading(true);
    setError('');
    setResult(null);
    setChainCheck(null);

    try {
      const response = await apiFetch(`/api/verify/${encodeURIComponent(requestedEvidenceId)}`);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Verification failed');
      }

      const data: EvidenceVerificationResult = await response.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred during verification');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (!evidenceIdFromUrl) return;
    setEvidenceId(evidenceIdFromUrl);
    void handleVerify(evidenceIdFromUrl);
    // The URL is the source of truth for this one-time deep-link verification.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evidenceIdFromUrl]);

  const runChainCheck = useCallback(async () => {
    if (!result) return;
    setChainCheck({ status: 'loading', onChainHash: null, onChainTimestamp: null, anchoredBy: null, message: '' });
    const outcome = await verifyOnChainIndependently(result.evidence_id, result.computed_hash);
    setChainCheck(outcome);
  }, [result]);

  // Automatically run the independent on-chain check as soon as a backend
  // result comes back that has something to compare against — this is what
  // makes it a check the visitor doesn't have to remember to ask for.
  useEffect(() => {
    if (result && (result.status === 'VERIFIED' || result.status === 'TAMPERED')) {
      runChainCheck();
    }
  }, [result, runChainCheck]);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    alert('Copied to clipboard!');
  };

  const formatDate = (value: string | null) => {
    if (!value) return 'N/A';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
  };

  const statusInfo = result ? STATUS_COPY[result.status] ?? { label: result.status, tone: 'amber' as const } : null;
  const toneClasses = statusInfo ? TONE_CLASSES[statusInfo.tone] : null;

  const chainToneKey: 'green' | 'red' | 'amber' | 'gray' =
    chainCheck?.status === 'match'
      ? 'green'
      : chainCheck?.status === 'mismatch'
      ? 'red'
      : chainCheck?.status === 'not_anchored' || chainCheck?.status === 'error'
      ? 'amber'
      : 'gray';
  const chainToneClasses = CHAIN_TONE_CLASSES[chainToneKey];

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-block mb-4">
            <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-blue-100">
              <svg className="w-7 h-7 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
                <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
                <path fillRule="evenodd" d="M4 5a2 2 0 012-2 1 1 0 000-2H6a4 4 0 00-4 4v10a4 4 0 004 4h8a4 4 0 004-4V5a1 1 0 100 2h2a2 2 0 012 2v7a2 2 0 11-4 0V9a1 1 0 10-2 0v3a4 4 0 11-8 0V5z" clipRule="evenodd" />
              </svg>
            </div>
          </div>
          <h1 className="text-4xl sm:text-5xl font-bold text-gray-900 mb-3">LexProof Verification Portal</h1>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto">
            Public cryptographic verification of legal evidence anchored on Ethereum Sepolia
          </p>
        </div>

        {/* Verification Form */}
        <div className="bg-white rounded-xl shadow-lg p-8 mb-8 border border-gray-200">
          <div className="mb-6">
            <label htmlFor="evidence-id" className="block text-sm font-semibold text-gray-900 mb-3">Evidence ID</label>
            <div className="flex gap-3">
              <input
                id="evidence-id"
                type="text"
                value={evidenceId}
                onChange={(e) => setEvidenceId(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleVerify();
                }}
                placeholder="Enter evidence ID to verify"
                className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-base transition-colors"
              />
              <button
                onClick={() => void handleVerify()}
                disabled={isLoading || !evidenceId.trim()}
                className="px-8 py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
              >
                {isLoading ? 'Verifying...' : 'Verify'}
              </button>
            </div>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border-l-4 border-red-500 rounded-lg p-5 mb-8">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg className="w-6 h-6 text-red-500" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm font-medium text-red-800">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Verification Result */}
        {result && statusInfo && toneClasses && (
          <div className="space-y-6">
            {/* Main Status Card */}
            <div className={`rounded-xl shadow-xl overflow-hidden border-2 ${toneClasses.box}`}>
              <div className="px-8 py-12 sm:px-12 sm:py-16 text-center">
                <div className="mb-4">
                  {statusInfo.tone === 'green' && (
                    <svg className="w-16 h-16 mx-auto text-green-600" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                  )}
                  {statusInfo.tone === 'red' && (
                    <svg className="w-16 h-16 mx-auto text-red-600" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                  )}
                  {statusInfo.tone === 'amber' && (
                    <svg className="w-16 h-16 mx-auto text-amber-600" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                  )}
                </div>
                <div className={`text-6xl font-bold mb-3 ${toneClasses.text}`}>{statusInfo.label}</div>
                <p className={`text-xl ${toneClasses.sub} max-w-2xl mx-auto`}>
                  {result.verified
                    ? 'Recomputed hash matches the hash anchored on Ethereum.'
                    : result.status === 'TAMPERED'
                    ? 'Recomputed hash does NOT match the on-chain hash. This evidence has been altered since it was anchored.'
                    : 'No matching evidence and/or Ethereum anchor was found for this ID.'}
                </p>
                {/* Hardening item #7 (Polish public verification -- the
                    VERIFIED/TAMPERED "money shot"): the transaction link
                    previously only appeared buried in the Proof Metadata
                    grid below. The review specifically asked for a "View
                    Ethereum Proof" link to be part of the headline moment,
                    not something a visitor has to scroll to find. */}
                {result.transaction_hash && (
                  <a
                    href={sepoliaTxUrl(result.transaction_hash)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`mt-6 inline-flex items-center gap-2 rounded-lg border-2 px-6 py-3 text-base font-bold transition-colors ${
                      statusInfo.tone === 'green'
                        ? 'border-green-600 bg-white text-green-700 hover:bg-green-50'
                        : statusInfo.tone === 'red'
                        ? 'border-red-600 bg-white text-red-700 hover:bg-red-50'
                        : 'border-amber-600 bg-white text-amber-700 hover:bg-amber-50'
                    }`}
                  >
                    View Ethereum Proof ↗
                  </a>
                )}
              </div>
            </div>

            {/* Independent on-chain check */}
            {(result.status === 'VERIFIED' || result.status === 'TAMPERED') && (
              <div className={`rounded-xl shadow-lg overflow-hidden border-2 ${chainToneClasses.box}`}>
                <div className="px-8 py-8 sm:px-10 sm:py-10">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6 gap-4">
                    <div>
                      <h2 className="text-2xl font-bold text-gray-900 mb-1">Independent Ethereum Verification</h2>
                      <p className="text-sm text-gray-600">
                        Your browser directly queries the blockchain
                      </p>
                    </div>
                    <button
                      onClick={runChainCheck}
                      disabled={chainCheck?.status === 'loading'}
                      className="px-4 py-2 text-sm font-medium text-blue-600 hover:text-blue-700 disabled:text-gray-400 transition-colors self-start sm:self-auto"
                    >
                      {chainCheck?.status === 'loading' ? 'Checking…' : 'Re-check'}
                    </button>
                  </div>

                  <p className="text-sm text-gray-600 mb-6 pb-6 border-b border-gray-200">
                    This verification reads the LexProofRegistry contract <strong>directly from Ethereum Sepolia</strong> using a public RPC endpoint. <strong>It does not go through the LexProof backend</strong>, ensuring you don't have to trust this website's word for what is actually anchored on-chain.
                  </p>

                  {chainCheck?.status === 'loading' && (
                    <div className="flex items-center justify-center py-8">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mr-3"></div>
                      <p className="text-gray-600 font-medium">Querying Ethereum Sepolia…</p>
                    </div>
                  )}

                  {chainCheck && chainCheck.status !== 'loading' && (
                    <div className="space-y-4">
                      <div className="flex items-start gap-3">
                        {chainCheck.status === 'match' && (
                          <>
                            <svg className="w-6 h-6 text-green-600 flex-shrink-0 mt-1" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                            </svg>
                            <div>
                              <p className="text-lg font-bold text-green-700">ON-CHAIN MATCH — independently confirmed</p>
                              <p className="text-sm text-green-600 mt-1">{chainCheck.message}</p>
                            </div>
                          </>
                        )}
                        {chainCheck.status === 'mismatch' && (
                          <>
                            <svg className="w-6 h-6 text-red-600 flex-shrink-0 mt-1" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                            </svg>
                            <div>
                              <p className="text-lg font-bold text-red-700">HASH MISMATCH</p>
                              <p className="text-sm text-red-600 mt-1">{chainCheck.message}</p>
                            </div>
                          </>
                        )}
                        {chainCheck.status === 'not_anchored' && (
                          <>
                            <svg className="w-6 h-6 text-amber-600 flex-shrink-0 mt-1" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                            </svg>
                            <div>
                              <p className="text-lg font-bold text-amber-700">NOT YET ANCHORED</p>
                              <p className="text-sm text-amber-600 mt-1">{chainCheck.message}</p>
                            </div>
                          </>
                        )}
                        {chainCheck.status === 'error' && (
                          <>
                            <svg className="w-6 h-6 text-gray-600 flex-shrink-0 mt-1" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                            </svg>
                            <div>
                              <p className="text-lg font-bold text-gray-700">Could not verify</p>
                              <p className="text-sm text-gray-600 mt-1">{chainCheck.message}</p>
                            </div>
                          </>
                        )}
                      </div>

                      {chainCheck.onChainHash && (
                        <div className="mt-6 pt-6 border-t border-gray-200">
                          <p className="text-sm font-medium text-gray-700 mb-2">On-chain hash</p>
                          <p className="font-mono text-xs break-all bg-white/60 p-3 rounded-lg border border-gray-200">
                            {chainCheck.onChainHash}
                          </p>
                        </div>
                      )}

                      {chainCheck.anchoredBy && (
                        <div className="text-xs text-gray-600 space-y-1">
                          <p>
                            Anchored by{' '}
                            <a
                              href={sepoliaAddressUrl(chainCheck.anchoredBy)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="font-mono text-blue-600 hover:text-blue-800 underline break-all"
                            >
                              {chainCheck.anchoredBy}
                            </a>
                          </p>
                          {chainCheck.onChainTimestamp && (
                            <p>at {chainCheck.onChainTimestamp}</p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Proof Metadata */}
            <div className="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
              <div className="px-8 py-6 border-b border-gray-200 bg-gray-50">
                <h3 className="text-lg font-bold text-gray-900">Proof Metadata</h3>
              </div>
              <div className="p-8">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Evidence ID</h4>
                    <p className="font-mono text-sm break-all text-gray-900 bg-gray-50 p-3 rounded-lg">{result.evidence_id}</p>
                  </div>

                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Network</h4>
                    <p className="font-medium text-gray-900">{result.blockchain_network ?? 'N/A'}</p>
                  </div>

                  {result.contract_address && (
                    <div>
                      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Registry Contract</h4>
                      <a
                        href={sepoliaAddressUrl(result.contract_address)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-mono text-sm break-all text-blue-600 hover:text-blue-800 underline bg-blue-50 p-3 rounded-lg block"
                      >
                        {result.contract_address}
                      </a>
                    </div>
                  )}

                  {result.transaction_hash && (
                    <div>
                      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Transaction</h4>
                      <a
                        href={sepoliaTxUrl(result.transaction_hash)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-mono text-sm break-all text-blue-600 hover:text-blue-800 underline bg-blue-50 p-3 rounded-lg block"
                      >
                        {result.transaction_hash}
                      </a>
                      <p className="text-xs text-gray-500 mt-2">View on Sepolia Etherscan ↗</p>
                    </div>
                  )}

                  {result.block_number != null && (
                    <div>
                      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Block Number</h4>
                      <p className="font-mono text-sm font-medium text-gray-900">{result.block_number}</p>
                    </div>
                  )}

                  {result.anchored_at && (
                    <div>
                      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Anchored At</h4>
                      <p className="font-medium text-gray-900">{formatDate(result.anchored_at)}</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Fingerprint Comparison -- the review's explicit "money shot":
                document fingerprint vs. blockchain fingerprint, shown side
                by side with an unmissable MATCH/MISMATCH verdict between
                them, rather than two same-looking boxes a visitor has to
                read and compare by eye. */}
            {(result.evidence_hash_on_chain || result.computed_hash) && (
              <div className="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
                <div className="px-8 py-6 border-b border-gray-200 bg-gray-50">
                  <h3 className="text-lg font-bold text-gray-900">Fingerprint Comparison</h3>
                  <p className="text-sm text-gray-600 mt-1">
                    {result.status === 'ANCHOR_NOT_FOUND'
                      ? 'This evidence has never been anchored on-chain, so there is nothing to compare the document fingerprint against.'
                      : result.verified
                      ? 'The document fingerprint and the blockchain fingerprint match — the evidence has not been tampered with.'
                      : 'The document fingerprint does NOT match the blockchain fingerprint — the stored evidence has been altered since anchoring.'}
                  </p>
                </div>
                <div className="p-8">
                  <div className="grid items-center gap-4 lg:grid-cols-[1fr_auto_1fr]">
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <h4 className="text-sm font-semibold text-gray-900">Document Fingerprint</h4>
                        {result.computed_hash && (
                          <button
                            onClick={() => copyToClipboard(result.computed_hash!)}
                            className="text-xs px-3 py-1 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded transition-colors"
                          >
                            Copy
                          </button>
                        )}
                      </div>
                      <p className="font-mono text-xs break-all bg-amber-50 p-4 rounded-lg border-2 border-amber-200 text-gray-900 min-h-[4.5rem]">
                        {result.computed_hash ?? 'Not available'}
                      </p>
                      <p className="mt-1 text-xs text-gray-500">Recomputed from the evidence as stored today</p>
                    </div>

                    <div className="flex justify-center py-2 lg:py-0">
                      {result.status === 'ANCHOR_NOT_FOUND' || !result.evidence_hash_on_chain || !result.computed_hash ? (
                        <div className="flex flex-col items-center text-gray-400">
                          <span className="text-3xl font-bold">?</span>
                          <span className="text-xs font-semibold uppercase tracking-wide">No comparison</span>
                        </div>
                      ) : result.verified ? (
                        <div className="flex flex-col items-center text-green-600">
                          <span className="text-4xl font-bold leading-none">=</span>
                          <span className="mt-1 rounded-full bg-green-100 px-3 py-1 text-xs font-bold uppercase tracking-wide text-green-800">Match</span>
                        </div>
                      ) : (
                        <div className="flex flex-col items-center text-red-600">
                          <span className="text-4xl font-bold leading-none">≠</span>
                          <span className="mt-1 rounded-full bg-red-100 px-3 py-1 text-xs font-bold uppercase tracking-wide text-red-800">Mismatch</span>
                        </div>
                      )}
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <h4 className="text-sm font-semibold text-gray-900">Blockchain Fingerprint</h4>
                        {result.evidence_hash_on_chain && (
                          <button
                            onClick={() => copyToClipboard(result.evidence_hash_on_chain!)}
                            className="text-xs px-3 py-1 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded transition-colors"
                          >
                            Copy
                          </button>
                        )}
                      </div>
                      <p className="font-mono text-xs break-all bg-green-50 p-4 rounded-lg border-2 border-green-200 text-gray-900 min-h-[4.5rem]">
                        {result.evidence_hash_on_chain ?? 'Not available'}
                      </p>
                      <p className="mt-1 text-xs text-gray-500">Read from the Ethereum Sepolia anchor</p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Verification Timestamp */}
            <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-8">
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Verification Timestamp</h4>
              <p className="font-mono text-sm text-gray-900">{formatDate(result.timestamp)}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
