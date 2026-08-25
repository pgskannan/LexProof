"use client";

import { useState } from 'react';
import { apiFetch } from '../../lib/api';

interface VerificationResult {
  proof_id: string;
  contract_identifier: string;
  contract_version: string;
  document_hash: string;
  policy_hash: string;
  analysis_hash: string;
  evidence_hash: string;
  blockchain_network: string;
  transaction_hash: string | null;
  block_number: number | null;
  anchoring_timestamp: number | null;
  verification_status: string;
  is_verified: boolean;
  timestamp: string;
}

interface VerificationForm {
  documentContent: string;
}

export default function PublicVerifyPage() {
  const [proofId, setProofId] = useState('');
  const [documentContent, setDocumentContent] = useState('');
  const [verificationResult, setVerificationResult] = useState<VerificationResult | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [mode, setMode] = useState<'verify' | 'upload'>('verify');

  const handleVerify = async () => {
    if (!proofId.trim()) {
      setError('Please enter a proof ID');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const response = await apiFetch(`/api/verify/${proofId}${documentContent ? `?document_content=${encodeURIComponent(documentContent)}` : ''}`);
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Verification failed');
      }

      const result: VerificationResult = await response.json();
      setVerificationResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred during verification');
      setVerificationResult(null);
    } finally {
      setIsLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    alert('Copied to clipboard!');
  };

  const formatDate = (timestamp: number | null) => {
    if (!timestamp) return 'N/A';
    return new Date(timestamp * 1000).toLocaleString();
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">LexProof Verification Portal</h1>
          <p className="text-gray-600">Public verification of legal document proofs on blockchain</p>
        </div>

        {/* Mode Selection */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Verification Mode</h2>
          <div className="flex gap-4">
            <button
              onClick={() => setMode('verify')}
              className={`flex-1 py-3 px-6 rounded-lg font-medium transition-colors ${
                mode === 'verify'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Verify Registered Contract
            </button>
            <button
              onClick={() => setMode('upload')}
              className={`flex-1 py-3 px-6 rounded-lg font-medium transition-colors ${
                mode === 'upload'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Upload Document & Verify
            </button>
          </div>
        </div>

        {/* Verification Form */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">
            {mode === 'verify' ? 'Verify Registered Contract' : 'Upload Document for Verification'}
          </h2>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Proof ID
            </label>
            <input
              type="text"
              value={proofId}
              onChange={(e) => setProofId(e.target.value)}
              placeholder="Enter proof ID (e.g., 0x1234...)"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {mode === 'upload' && (
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Contract Document Content
              </label>
              <textarea
                value={documentContent}
                onChange={(e) => setDocumentContent(e.target.value)}
                placeholder="Paste the contract document content here..."
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent h-32"
              />
              <p className="text-sm text-gray-500 mt-2">
                The system will calculate the SHA-256 hash of your document and compare it with the registered hash.
              </p>
            </div>
          )}

          <button
            onClick={handleVerify}
            disabled={isLoading || !proofId.trim() || (mode === 'upload' && !documentContent.trim())}
            className="w-full bg-blue-600 text-white py-3 px-6 rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? 'Verifying...' : mode === 'verify' ? 'Verify Contract' : 'Upload & Verify'}
          </button>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-700">{error}</p>
          </div>
        )}

        {/* Verification Result */}
        {verificationResult && (
          <div className="bg-white rounded-lg shadow-md p-6">
            {/* Verification Status */}
            <div className={`text-center py-8 px-4 rounded-lg mb-6 ${
              verificationResult.is_verified
                ? 'bg-green-50 border-2 border-green-500'
                : 'bg-red-50 border-2 border-red-500'
            }`}>
              <div className={`text-6xl font-bold mb-2 ${
                verificationResult.is_verified ? 'text-green-600' : 'text-red-600'
              }`}>
                {verificationResult.is_verified ? 'VERIFIED' : 'VERIFICATION FAILED'}
              </div>
              <p className={`text-lg font-medium ${
                verificationResult.is_verified ? 'text-green-700' : 'text-red-700'
              }`}>
                {verificationResult.verification_status}
              </p>
            </div>

            {/* Verification Details */}
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-gray-50 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-500 mb-1">Proof ID</h3>
                  <p className="font-mono text-sm break-all">{verificationResult.proof_id}</p>
                </div>

                <div className="bg-gray-50 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-500 mb-1">Contract Identifier</h3>
                  <p className="font-medium">{verificationResult.contract_identifier}</p>
                </div>

                <div className="bg-gray-50 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-500 mb-1">Contract Version</h3>
                  <p className="font-medium">{verificationResult.contract_version}</p>
                </div>

                <div className="bg-gray-50 p-4 rounded-lg">
                  <h3 className="text-sm font-medium text-gray-500 mb-1">Blockchain Network</h3>
                  <p className="font-medium">{verificationResult.blockchain_network}</p>
                </div>

                {verificationResult.transaction_hash && (
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <h3 className="text-sm font-medium text-gray-500 mb-1">Transaction Hash</h3>
                    <p className="font-mono text-sm break-all">{verificationResult.transaction_hash}</p>
                  </div>
                )}

                {verificationResult.block_number && (
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <h3 className="text-sm font-medium text-gray-500 mb-1">Block Number</h3>
                    <p className="font-mono">{verificationResult.block_number}</p>
                  </div>
                )}

                {verificationResult.anchoring_timestamp && (
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <h3 className="text-sm font-medium text-gray-500 mb-1">Anchoring Timestamp</h3>
                    <p className="font-medium">{formatDate(verificationResult.anchoring_timestamp)}</p>
                  </div>
                )}
              </div>

              {/* Hashes */}
              <div className="border-t pt-4">
                <h3 className="text-sm font-medium text-gray-500 mb-3">Document Hashes</h3>
                <div className="space-y-3">
                  <div>
                    <div className="flex justify-between items-start mb-1">
                      <span className="text-sm font-medium text-gray-700">Document Hash</span>
                      <button
                        onClick={() => copyToClipboard(verificationResult.document_hash)}
                        className="text-sm text-blue-600 hover:text-blue-800"
                      >
                        Copy
                      </button>
                    </div>
                    <p className="font-mono text-xs break-all bg-gray-50 p-2 rounded">{verificationResult.document_hash}</p>
                  </div>

                  <div>
                    <div className="flex justify-between items-start mb-1">
                      <span className="text-sm font-medium text-gray-700">Policy Hash</span>
                      <button
                        onClick={() => copyToClipboard(verificationResult.policy_hash)}
                        className="text-sm text-blue-600 hover:text-blue-800"
                      >
                        Copy
                      </button>
                    </div>
                    <p className="font-mono text-xs break-all bg-gray-50 p-2 rounded">{verificationResult.policy_hash}</p>
                  </div>

                  <div>
                    <div className="flex justify-between items-start mb-1">
                      <span className="text-sm font-medium text-gray-700">Analysis Hash</span>
                      <button
                        onClick={() => copyToClipboard(verificationResult.analysis_hash)}
                        className="text-sm text-blue-600 hover:text-blue-800"
                      >
                        Copy
                      </button>
                    </div>
                    <p className="font-mono text-xs break-all bg-gray-50 p-2 rounded">{verificationResult.analysis_hash}</p>
                  </div>

                  <div>
                    <div className="flex justify-between items-start mb-1">
                      <span className="text-sm font-medium text-gray-700">Evidence Hash</span>
                      <button
                        onClick={() => copyToClipboard(verificationResult.evidence_hash)}
                        className="text-sm text-blue-600 hover:text-blue-800"
                      >
                        Copy
                      </button>
                    </div>
                    <p className="font-mono text-xs break-all bg-gray-50 p-2 rounded">{verificationResult.evidence_hash}</p>
                  </div>
                </div>
              </div>

              {/* Timestamp */}
              <div className="border-t pt-4">
                <h3 className="text-sm font-medium text-gray-500 mb-1">Verification Timestamp</h3>
                <p className="font-mono text-sm">{new Date(verificationResult.timestamp).toLocaleString()}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
