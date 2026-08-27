'use client';

import { useEffect, useState } from 'react';
import { ExternalLink, RefreshCw, Server, ShieldCheck } from 'lucide-react';
import { apiFetch } from '../../../../lib/api';

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
    <div className="min-h-screen bg-slate-50 p-6 lg:p-8">
      <div className="mx-auto max-w-6xl space-y-8">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-200 pb-6">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-blue-700">LexProof / operations</p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-950">System &amp; Anchoring Status</h1>
            <p className="mt-2 max-w-2xl text-slate-600">Live service readiness and the public Ethereum configuration used for evidence anchoring.</p>
          </div>
          <button type="button" onClick={() => void loadStatus()} disabled={loading} className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50">
            <RefreshCw className="h-4 w-4" /> Refresh status
          </button>
        </header>

        {loading && <div className="rounded-xl border border-slate-200 bg-white p-6 text-slate-600">Loading system status...</div>}
        {error && <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-red-700">{error}</div>}

        {!loading && !error && (
          <>
            <section className="grid gap-5 md:grid-cols-3">
              {health.map((item) => {
                const ready = item.status === 'ok';
                return (
                  <article key={item.service} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3"><Server className="h-5 w-5 text-blue-700" /><h2 className="font-semibold capitalize text-slate-900">{item.service.replace('_', ' ')}</h2></div>
                      <span className={`rounded-full px-2.5 py-1 text-xs font-bold uppercase ${ready ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>{ready ? 'Configured' : 'Not configured'}</span>
                    </div>
                    <p className="mt-4 text-sm text-slate-500">{ready ? 'Service is ready for the current environment.' : 'Service credentials or project configuration are not available.'}</p>
                  </article>
                );
              })}
            </section>

            {config && <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center gap-3"><ShieldCheck className="h-6 w-6 text-blue-700" /><div><h2 className="text-xl font-semibold text-slate-950">Ethereum anchoring</h2><p className="text-sm text-slate-500">The same deployed network and registry used by the evidence verification UI.</p></div></div>
              <dl className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
                <div><dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Network</dt><dd className="mt-1 font-semibold text-slate-900">{config.network}</dd></div>
                <div><dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Chain ID</dt><dd className="mt-1 font-semibold text-slate-900">{config.chain_id}</dd></div>
                <div className="sm:col-span-2"><dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Registry contract</dt><dd className="mt-1 break-all font-mono text-sm text-slate-900"><a href={`${EXPLORER}/address/${config.contract_address}`} target="_blank" rel="noreferrer" className="text-blue-700 underline">{config.contract_address}</a> <ExternalLink className="inline h-3.5 w-3.5" /></dd></div>
                <div className="sm:col-span-2"><dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Gemini model</dt><dd className="mt-1 font-mono text-sm text-slate-900">{config.gemini_model}</dd></div>
                <div><dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">Ethereum config</dt><dd className={`mt-1 font-semibold ${config.ethereum_configured ? 'text-emerald-700' : 'text-amber-700'}`}>{config.ethereum_configured ? 'Configured' : 'Not configured'}</dd></div>
              </dl>
            </section>}
          </>
        )}
      </div>
    </div>
  );
}
