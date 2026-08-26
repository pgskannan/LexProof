"use client";

import { useState } from 'react';
import { apiFetch } from '../../lib/api';

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

function sepoliaTxUrl(txHash: string): string {
  return `https://sepolia.etherscan.io/tx/${txHash}`;
}

function sepoliaAddressUrl(address: string): string {
  return `https://sepolia.etherscan.io/address/${address}`;
}

export default function PublicVerifyPage() {
  const [evidenceId, setEvidenceId] = useState('');
  const [result, setResult] = useState<EvidenceVerificationResult | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleVerify = async () => {
    if (!evidenceId.trim()) {
      setError('Please enter an evidence ID');
      return;
    }

    setIsLoading(true);
    setError('');
    setResult(null);

    try {
      const response = await apiFetch(`/api/verify/${encodeURIComponent(evidenceId.trim())}`);

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

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">LexProof Verification Portal</h1>
          <p className="text-gray-600">
            Public, cryptographic verification of legal evidence anchored on Ethereum Sepolia
          </p>
        </div>

        {/* Verification Form */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Verify Evidence</h2>
          <p className="text-sm text-gray-500 mb-4">
            Enter an Evidence ID to recompute its hash from the stored evidence record and compare it
            against the hash anchored on Ethereum. If the stored evidence has changed since it was
            anchored, verification will fail.
          </p>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">Evidence ID</label>
            <input
              type="text"
              value={evidenceId}
              onChange={(e) => setEvidenceId(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleVerify();
              }}
              placeholder="Enter evidence ID"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          <button
            onClick={handleVerify}
            disabled={isLoading || !evidenceId.trim()}
            className="w-full bg-blue-600 text-white py-3 px-6 rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? 'Verifying...' : 'Verify Evidence'}
          </button>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-700">{error}</p>
          </div>
        )}

        {/* Verification Result */}
        {result && statusInfo && toneClasses && (
          <div className="bg-white rounded-lg shadow-md p-6">
            {/* Verification Status */}
            <div className={`text-center py-8 px-4 rounded-lg mb-6 ${toneClasses.box}`}>
              <div className={`text-5xl font-bold mb-2 ${toneClasses.text}`}>{statusInfo.label}</div>
              <p className={`text-lg font-medium ${toneClasses.sub}`}>
                {result.verified
                  ? 'Recomputed hash matches the hash anchored on Ethereum.'
                  : result.status === 'TAMPERED'
                  ? 'Recomputed hash does NOT match the on-chain hash. This evidence has been altered since it was anchored.'
                  : 'No matching evidence and/or Ethereum anchor was found for this ID.'}
              </p>
            </div>

            {/* Verification Details */}
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-gray-50 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-500 mb-1">Evidence ID</h3>
                  <p className="font-mono text-sm break-all">{result.evidence_id}</p>
                </div>

                <div className="bg-gray-50 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-500 mb-1">Blockchain Network</h3>
                  <p className="font-medium">{result.blockchain_network ?? 'N/A'}</p>
                </div>

                {result.contract_address && (
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <h3 className="text-sm font-medium text-gray-500 mb-1">Registry Contract</h3>
                    <a
                      href={sepoliaAddressUrl(result.contract_address)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-sm break-all text-blue-600 hover:text-blue-800 underline"
                    >
                      {result.contract_address}
                    </a>
                  </div>
                )}

                {result.transaction_hash && (
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <h3 className="text-sm font-medium text-gray-500 mb-1">Transaction</h3>
                    <a
                      href={sepoliaTxUrl(result.transaction_hash)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-sm break-all text-blue-600 hover:text-blue-800 underline"
                    >
                      {result.transaction_hash}
                    </a>
                    <p className="text-xs text-gray-400 mt-1">View on Sepolia Etherscan ↗</p>
                  </div>
                )}

                {result.block_number != null && (
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <h3 className="text-sm font-medium text-gray-500 mb-1">Block Number</h3>
                    <p className="font-mono">{result.block_number}</p>
                  </div>
                )}

                {result.anchored_at && (
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <h3 className="text-sm font-medium text-gray-500 mb-1">Anchored At</h3>
                    <p className="font-medium">{formatDate(result.anchored_at)}</p>
                  </div>
                )}
              </div>

              {/* Hashes */}
              {(result.evidence_hash_on_chain || result.computed_hash) && (
                <div className="border-t pt-4">
                  <h3 className="text-sm font-medium text-gray-500 mb-3">Hash Comparison</h3>
                  <div className="space-y-3">
                    {result.evidence_hash_on_chain && (
                      <div>
                        <div className="flex justify-between items-start mb-1">
                          <span className="text-sm font-medium text-gray-700">On-Chain Hash</span>
                          <button
                            onClick={() => copyToClipboard(result.evidence_hash_on_chain!)}
                            className="text-sm text-blue-600 hover:text-blue-800"
                          >
                            Copy
                          </button>
                        </div>
                        <p className="font-mono text-xs break-all bg-gray-50 p-2 rounded">
                          {result.evidence_hash_on_chain}
                        </p>
                      </div>
                    )}

                    {result.computed_hash && (
                      <div>
                        <div className="flex justify-between items-start mb-1">
                          <span className="text-sm font-medium text-gray-700">Recomputed Hash (from stored evidence)</span>
                          <button
                            onClick={() => copyToClipboard(result.computed_hash!)}
                            className="text-sm text-blue-600 hover:text-blue-800"
                          >
                            Copy
                          </button>
                        </div>
                        <p className="font-mono text-xs break-all bg-gray-50 p-2 rounded">
                          {result.computed_hash}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Timestamp */}
              <div className="border-t pt-4">
                <h3 className="text-sm font-medium text-gray-500 mb-1">Verification Timestamp</h3>
                <p className="font-mono text-sm">{formatDate(result.timestamp)}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
