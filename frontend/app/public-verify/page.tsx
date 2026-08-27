"use client";

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
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

type ChainCheckStatus = 'idle' | 'loading' | 'match' | 'mismatch' | 'not_anchored' | 'error';

interface ChainCheckResult {
  status: ChainCheckStatus;
  onChainHash: string | null;
  onChainTimestamp: string | null;
  anchoredBy: string | null;
  message: string;
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

const SEPOLIA_RPC_URL =
  process.env.NEXT_PUBLIC_ETHEREUM_SEPOLIA_RPC_URL || 'https://ethereum-sepolia-rpc.publicnode.com';
const REGISTRY_CONTRACT_ADDRESS = process.env.NEXT_PUBLIC_LEXPROOF_CONTRACT_ADDRESS || '';
const REGISTRY_ABI = [
  'function getEvidenceAnchor(string) view returns (bytes32 evidenceHash, uint256 timestamp, address anchoredBy)',
];

function sepoliaTxUrl(txHash: string): string {
  return `https://sepolia.etherscan.io/tx/${txHash}`;
}

function sepoliaAddressUrl(address: string): string {
  return `https://sepolia.etherscan.io/address/${address}`;
}

/**
 * Independently verify an evidence hash directly against the LexProofRegistry
 * contract on Ethereum Sepolia, from the browser, using a public RPC endpoint.
 *
 * This does NOT go through the LexProof backend at all — it is a second,
 * independent path to the same on-chain fact, so a visitor doesn't have to
 * trust the backend's word for what is (or isn't) anchored on-chain.
 */
async function verifyOnChainIndependently(
  evidenceId: string,
  expectedHash: string | null
): Promise<ChainCheckResult> {
  if (!REGISTRY_CONTRACT_ADDRESS) {
    return {
      status: 'error',
      onChainHash: null,
      onChainTimestamp: null,
      anchoredBy: null,
      message: 'Registry contract address is not configured on this deployment.',
    };
  }

  try {
    const { ethers } = await import('ethers');
    const provider = new ethers.JsonRpcProvider(SEPOLIA_RPC_URL);
    const contract = new ethers.Contract(REGISTRY_CONTRACT_ADDRESS, REGISTRY_ABI, provider);

    const [evidenceHash, timestamp, anchoredBy] = await contract.getEvidenceAnchor(evidenceId);
    const onChainHash: string = evidenceHash.toString().toLowerCase();
    const zeroHash = '0x' + '0'.repeat(64);

    if (!onChainHash || onChainHash === zeroHash) {
      return {
        status: 'not_anchored',
        onChainHash: null,
        onChainTimestamp: null,
        anchoredBy: null,
        message: 'The contract has no anchor for this evidence ID.',
      };
    }

    const onChainTimestamp = new Date(Number(timestamp) * 1000).toLocaleString();
    const normalizedExpected = expectedHash ? `0x${expectedHash.replace(/^0x/i, '').toLowerCase()}` : null;

    if (normalizedExpected && normalizedExpected === onChainHash) {
      return {
        status: 'match',
        onChainHash,
        onChainTimestamp,
        anchoredBy,
        message: 'The hash read directly from the smart contract matches the recomputed evidence hash.',
      };
    }

    return {
      status: 'mismatch',
      onChainHash,
      onChainTimestamp,
      anchoredBy,
      message: normalizedExpected
        ? 'The hash read directly from the smart contract does NOT match the recomputed evidence hash.'
        : 'Read an on-chain hash, but no recomputed hash was available to compare it against.',
    };
  } catch (err) {
    const reason =
      (err as { shortMessage?: string; reason?: string; message?: string })?.shortMessage ||
      (err as { reason?: string })?.reason ||
      (err instanceof Error ? err.message : String(err));

    if (typeof reason === 'string' && reason.toLowerCase().includes('evidence anchor does not exist')) {
      return {
        status: 'not_anchored',
        onChainHash: null,
        onChainTimestamp: null,
        anchoredBy: null,
        message: 'The contract has no anchor for this evidence ID.',
      };
    }

    return {
      status: 'error',
      onChainHash: null,
      onChainTimestamp: null,
      anchoredBy: null,
      message: `Could not reach Ethereum Sepolia directly from your browser: ${reason}`,
    };
  }
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
            onClick={() => void handleVerify()}
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

            {/* Independent on-chain check */}
            {(result.status === 'VERIFIED' || result.status === 'TAMPERED') && (
              <div className={`rounded-lg p-4 mb-6 ${chainToneClasses.box}`}>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold text-gray-700">
                    Independent check &mdash; read directly from Ethereum Sepolia by your browser
                  </h3>
                  <button
                    onClick={runChainCheck}
                    disabled={chainCheck?.status === 'loading'}
                    className="text-xs text-blue-600 hover:text-blue-800 disabled:text-gray-400"
                  >
                    {chainCheck?.status === 'loading' ? 'Checking…' : 'Re-check'}
                  </button>
                </div>
                <p className="text-xs text-gray-500 mb-2">
                  This calls the LexProofRegistry contract directly from your browser using a public
                  Sepolia RPC endpoint &mdash; it does not go through the LexProof backend, so it isn&apos;t
                  relying on this site to honestly report what is on-chain.
                </p>

                {chainCheck?.status === 'loading' && (
                  <p className="text-sm text-gray-500">Querying the smart contract…</p>
                )}

                {chainCheck && chainCheck.status !== 'loading' && (
                  <div>
                    <p className={`text-sm font-medium mb-2 ${chainToneClasses.text}`}>
                      {chainCheck.status === 'match' && '✓ ON-CHAIN MATCH — independently confirmed.'}
                      {chainCheck.status === 'mismatch' && '✗ Mismatch: on-chain hash does not match.'}
                      {chainCheck.status === 'not_anchored' && '○ No on-chain anchor found for this ID.'}
                      {chainCheck.status === 'error' && '⚠ Could not complete the independent check.'}
                    </p>
                    <p className="text-xs text-gray-600 mb-2">{chainCheck.message}</p>
                    {chainCheck.onChainHash && (
                      <p className="font-mono text-xs break-all bg-white/60 p-2 rounded">
                        on-chain hash: {chainCheck.onChainHash}
                      </p>
                    )}
                    {chainCheck.anchoredBy && (
                      <p className="text-xs text-gray-600 mt-2">
                        Anchored by{' '}
                        <a
                          href={sepoliaAddressUrl(chainCheck.anchoredBy)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-mono text-blue-600 hover:text-blue-800 underline"
                        >
                          {chainCheck.anchoredBy}
                        </a>{' '}
                        at {chainCheck.onChainTimestamp}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

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
