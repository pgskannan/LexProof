'use client';

import { useEffect, useState } from 'react';
import { ExternalLink, RefreshCw, Server, ShieldCheck } from 'lucide-react';
import { apiFetch } from '../../../../lib/api';
import { Skeleton } from '../../../../components/ui/skeleton';
import { Card, CardContent } from '../../../../components/ui/card';
import { Badge } from '../../../../components/ui/badge';
import { Button } from '../../../../components/ui/button';
import { PageHeader } from '../../../../components/ui/page-header';
import { PageContainer } from '../../../../components/ui/container';

type HealthStatus = { status: string; service: string };
type SystemConfig = {
  network: string;
  chain_id: number;
  contract_address: string;
  gemini_model: string;
  ethereum_configured: boolean;
};

const EXPLORER = 'https://sepolia.etherscan.io';

export default function Administration() {
  const [health, setHealth] = useState<HealthStatus[]>([]);
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function loadStatus() {
    setLoading(true);
    setError('');
    try {
      const responses = await Promise.all([
        apiFetch('/health/firebase'),
        apiFetch('/health/gcp'),
        apiFetch('/health/ai'),
        apiFetch('/health/config'),
      ]);
      if (responses.some((response) => !response.ok)) throw new Error('Unable to load system status');
      setHealth(await Promise.all(responses.slice(0, 3).map((response) => response.json())));
      setConfig(await responses[3].json());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load system status');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadStatus(); }, []);

  return (
    <PageContainer>
      <PageHeader
        eyebrow="LexProof / operations"
        title="System & Anchoring Status"
        description="Live service readiness and the public Ethereum configuration used for evidence anchoring."
        actions={
          <Button type="button" variant="outline" onClick={() => void loadStatus()} disabled={loading}>
            <RefreshCw className="h-4 w-4" /> Refresh status
          </Button>
        }
      />

      <div className="mt-6 space-y-6">
        {loading && (
          <div className="grid gap-5 md:grid-cols-3">
            <Skeleton className="h-36 w-full" />
            <Skeleton className="h-36 w-full" />
            <Skeleton className="h-36 w-full" />
          </div>
        )}
        {error && <div className="rounded-[var(--radius-lg,0.75rem)] border border-red-200 bg-red-50 p-5 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400">{error}</div>}

        {!loading && !error && (
          <>
            <div className="grid gap-5 md:grid-cols-3">
              {health.map((item) => {
                const ready = item.status === 'ok';
                return (
                  <Card key={item.service}>
                    <CardContent>
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-3"><Server className="h-5 w-5 text-[var(--brand-primary,#2563eb)]" /><h2 className="font-semibold capitalize text-gray-900 dark:text-gray-100">{item.service.replace('_', ' ')}</h2></div>
                        <Badge variant={ready ? 'verified' : 'pending'}>{ready ? 'Configured' : 'Not configured'}</Badge>
                      </div>
                      <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">{ready ? 'Service is ready for the current environment.' : 'Service credentials or project configuration are not available.'}</p>
                    </CardContent>
                  </Card>
                );
              })}
            </div>

            {config && (
              <Card>
                <CardContent>
                  <div className="flex items-center gap-3"><ShieldCheck className="h-6 w-6 text-[var(--brand-primary,#2563eb)]" /><div><h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Ethereum anchoring</h2><p className="text-sm text-gray-500 dark:text-gray-400">The same deployed network and registry used by the evidence verification UI.</p></div></div>
                  <dl className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
                    <div><dt className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Network</dt><dd className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{config.network}</dd></div>
                    <div><dt className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Chain ID</dt><dd className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{config.chain_id}</dd></div>
                    <div className="sm:col-span-2"><dt className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Registry contract</dt><dd className="mt-1 break-all font-mono text-sm text-gray-900 dark:text-gray-100"><a href={`${EXPLORER}/address/${config.contract_address}`} target="_blank" rel="noreferrer" className="text-[var(--brand-primary,#1d4ed8)] underline">{config.contract_address}</a> <ExternalLink className="inline h-3.5 w-3.5" /></dd></div>
                    <div className="sm:col-span-2"><dt className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Gemini model</dt><dd className="mt-1 font-mono text-sm text-gray-900 dark:text-gray-100">{config.gemini_model}</dd></div>
                    <div><dt className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Ethereum config</dt><dd className="mt-1"><Badge variant={config.ethereum_configured ? 'verified' : 'pending'}>{config.ethereum_configured ? 'Configured' : 'Not configured'}</Badge></dd></div>
                  </dl>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </PageContainer>
  );
}
