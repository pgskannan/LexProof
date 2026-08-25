'use client';

import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { 
  Anchor, 
  CheckCircle2, 
  XCircle, 
  Clock, 
  Network, 
  FileText,
  Hash
} from 'lucide-react';
import { toast } from 'sonner';

interface ProofAnchoringResponse {
  proof_id: string;
  transaction_hash: string;
  block_number: number;
  status: string;
  timestamp: string;
  network: string;
  contract_address: string;
}

interface TransactionDetails {
  proof_id: string;
  transaction_hash: string;
  block_number: number;
  timestamp: number;
}

interface AnchorProofButtonProps {
  contractId: string;
  contractHash: string;
  policyHash: string;
  analysisHash: string;
  evidenceHash: string;
  riskScore: number;
  complianceScore: number;
  policyVersion: string;
  evidenceCount: number;
}

export default function AnchorProofButton({
  contractId,
  contractHash,
  policyHash,
  analysisHash,
  evidenceHash,
  riskScore,
  complianceScore,
  policyVersion,
  evidenceCount,
}: AnchorProofButtonProps) {
  const [isAnchoring, setIsAnchoring] = useState(false);
  const [anchoredProof, setAnchoredProof] = useState<ProofAnchoringResponse | null>(null);
  const [transactionDetails, setTransactionDetails] = useState<TransactionDetails | null>(null);
  const [verificationStatus, setVerificationStatus] = useState<'verifying' | 'verified' | 'failed' | null>(null);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const handleAnchorProof = async () => {
    if (!isMounted) return;

    setIsAnchoring(true);
    setAnchoredProof(null);
    setTransactionDetails(null);
    setVerificationStatus(null);

    try {
      const response = await fetch(`/api/passports/${contractId}/anchor`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          contract_id: contractId,
          contract_hash: contractHash,
          policy_hash: policyHash,
          analysis_hash: analysisHash,
          evidence_hash: evidenceHash,
          risk_score: riskScore,
          compliance_score: complianceScore,
          policy_version: policyVersion,
          evidence_count: evidenceCount,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to anchor proof');
      }

      const data: ProofAnchoringResponse = await response.json();
      setAnchoredProof(data);
      setTransactionDetails({
        proof_id: data.proof_id,
        transaction_hash: data.transaction_hash,
        block_number: data.block_number,
        timestamp: new Date(data.timestamp).getTime(),
      });

      toast.success('Proof anchored to blockchain successfully!', {
        description: `Transaction: ${data.transaction_hash.substring(0, 10)}...`,
      });

      // Start verification in background
      verifyProofOnChain(data.proof_id, contractHash, policyHash, analysisHash, evidenceHash);

    } catch (error) {
      console.error('Error anchoring proof:', error);
      toast.error('Failed to anchor proof to blockchain', {
        description: error instanceof Error ? error.message : 'Unknown error occurred',
      });
    } finally {
      setIsAnchoring(false);
    }
  };

  const verifyProofOnChain = async (
    proofId: string,
    contractHash: string,
    policyHash: string,
    analysisHash: string,
    evidenceHash: string
  ) => {
    setVerificationStatus('verifying');

    try {
      const response = await fetch(
        `/api/proofs/${proofId}/verify?${new URLSearchParams({
          contract_hash: contractHash,
          policy_hash: policyHash,
          analysis_hash: analysisHash,
          evidence_hash: evidenceHash,
        }).toString()}`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setVerificationStatus(data.is_valid ? 'verified' : 'failed');
        if (data.is_valid) {
          toast.success('Proof verified on blockchain!');
        } else {
          toast.error('Proof verification failed on blockchain');
        }
      } else {
        throw new Error('Verification failed');
      }
    } catch (error) {
      console.error('Error verifying proof:', error);
      setVerificationStatus('failed');
      toast.error('Error verifying proof on blockchain');
    }
  };

  const fetchTransactionDetails = async (proofId: string) => {
    try {
      const response = await fetch(`/api/proofs/${proofId}/transaction`);
      if (response.ok) {
        const data = await response.json();
        setTransactionDetails(data);
      }
    } catch (error) {
      console.error('Error fetching transaction details:', error);
    }
  };

  const getStatusBadge = () => {
    if (verificationStatus === 'verified') {
      return (
        <Badge variant="default" className="bg-green-500 hover:bg-green-600">
          <CheckCircle2 className="w-3 h-3 mr-1" />
          Verified
        </Badge>
      );
    }
    if (verificationStatus === 'failed') {
      return (
        <Badge variant="destructive">
          <XCircle className="w-3 h-3 mr-1" />
          Failed
        </Badge>
      );
    }
    if (verificationStatus === 'verifying') {
      return (
        <Badge variant="secondary" className="animate-pulse">
          <Clock className="w-3 h-3 mr-1" />
          Verifying...
        </Badge>
      );
    }
    if (anchoredProof) {
      return (
        <Badge variant="default">
          <CheckCircle2 className="w-3 h-3 mr-1" />
          Anchored
        </Badge>
      );
    }
    return <Badge variant="outline">Not Anchored</Badge>;
  };

  if (!isMounted) {
    return null;
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Anchor className="w-5 h-5 text-blue-500" />
          Blockchain Proof Registry
        </CardTitle>
        <CardDescription>
          Anchor legal evidence fingerprints to Ethereum Sepolia for immutable verification
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Anchor Button */}
        {!anchoredProof && (
          <div className="space-y-2">
            <Button
              onClick={handleAnchorProof}
              disabled={isAnchoring}
              className="w-full"
              size="lg"
            >
              <Anchor className="w-4 h-4 mr-2" />
              {isAnchoring ? 'Anchoring...' : 'Anchor Proof to Blockchain'}
            </Button>
            <p className="text-sm text-muted-foreground">
              Only hashes and non-sensitive metadata will be stored on-chain
            </p>
          </div>
        )}

        {/* Anchored Proof Details */}
        {anchoredProof && (
          <div className="space-y-4">
            {/* Status Badge */}
            <div className="flex justify-between items-center">
              {getStatusBadge()}
              <Button
                variant="outline"
                size="sm"
                onClick={() => fetchTransactionDetails(anchoredProof.proof_id)}
              >
                View Transaction
              </Button>
            </div>

            {/* Network and Contract Info */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm">
                <Network className="w-4 h-4 text-muted-foreground" />
                <span className="font-medium">Network:</span>
                <span className="text-muted-foreground">{anchoredProof.network}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <FileText className="w-4 h-4 text-muted-foreground" />
                <span className="font-medium">Contract:</span>
                <span className="text-muted-foreground font-mono text-xs">
                  {anchoredProof.contract_address}
                </span>
              </div>
            </div>

            {/* Transaction Details */}
            {transactionDetails && (
              <div className="space-y-3 pt-4 border-t">
                <div className="flex items-center gap-2 text-sm">
                  <Hash className="w-4 h-4 text-muted-foreground" />
                  <span className="font-medium">Transaction Hash:</span>
                  <span className="text-muted-foreground font-mono text-xs">
                    {transactionDetails.transaction_hash.substring(0, 10)}...
                    {transactionDetails.transaction_hash.substring(transactionDetails.transaction_hash.length - 10)}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Hash className="w-4 h-4 text-muted-foreground" />
                  <span className="font-medium">Block Number:</span>
                  <span className="text-muted-foreground font-mono">
                    {transactionDetails.block_number}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Clock className="w-4 h-4 text-muted-foreground" />
                  <span className="font-medium">Timestamp:</span>
                  <span className="text-muted-foreground">
                    {new Date(transactionDetails.timestamp).toLocaleString()}
                  </span>
                </div>
              </div>
            )}

            {/* Verification Status */}
            {verificationStatus && (
              <div className="space-y-2 pt-4 border-t">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">Verification Status:</span>
                  {getStatusBadge()}
                </div>
                {verificationStatus === 'verified' && (
                  <p className="text-sm text-green-600">
                    ✓ Proof successfully verified on blockchain
                  </p>
                )}
                {verificationStatus === 'failed' && (
                  <p className="text-sm text-red-600">
                    ✗ Proof verification failed on blockchain
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* Loading Skeleton */}
        {isAnchoring && (
          <div className="space-y-3 pt-4">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
