"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiFetch } from "../../../lib/api";

type Version = {
  passport_id: string;
  version: number;
  document_hash: string;
  policy_hash: string;
  analysis_hash: string;
  evidence_hash: string;
  risk_score: number;
  compliance_score: number;
  policy_version: string;
  created_at: string;
  blockchain_proof_verified: boolean;
};

type Comparison = {
  version_from: number;
  version_to: number;
  clause_changes: Array<{ change_type: string; previous_text?: string; current_text?: string; risk_delta: number; compliance_delta: number; business_impact: string }>;
  risk_delta: number;
  compliance_delta: number;
  policy_delta: string;
  business_impact: string;
  blockchain_proof_verified: boolean;
};

export default function ContractTimeMachinePage() {
  const searchParams = useSearchParams();
  const [contractId, setContractId] = useState("");
  const [versions, setVersions] = useState<Version[]>([]);
  const [selected, setSelected] = useState<Version | null>(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [proofChecked, setProofChecked] = useState(false);

  async function loadHistory(idOverride?: string) {
    const id = (idOverride ?? contractId).trim();
    if (!id) return setMessage("Enter a contract identifier.");
    setLoading(true); setMessage(""); setComparison(null); setProofChecked(false);
    try {
      const response = await apiFetch(`/api/time-machine/history/${encodeURIComponent(id)}`);
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "History unavailable");
      const result = await response.json();
      setVersions(result.versions); setSelected(result.versions.at(-1) ?? null);
    } catch (error) { setMessage(error instanceof Error ? error.message : "History unavailable"); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    const queryId = searchParams.get("contractId");
    if (queryId) {
      setContractId(queryId);
      void loadHistory(queryId);
    }
    // Only run once on mount: this only exists to prefill and auto-load from
    // a link like "Open Time Machine" on the contract page; afterwards the
    // input and Load history button are the source of truth.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function compare() {
    if (!from || !to) return setMessage("Select two versions to compare.");
    setLoading(true); setMessage("");
    try {
      const query = new URLSearchParams({ contract_id: contractId, version_from: from, version_to: to });
      const response = await apiFetch(`/api/time-machine/compare?${query}`);
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "Comparison unavailable");
      setComparison(await response.json());
    } catch (error) { setMessage(error instanceof Error ? error.message : "Comparison unavailable"); }
    finally { setLoading(false); }
  }

  async function verifyHistory() {
    setLoading(true); setMessage("");
    try {
      const response = await apiFetch(`/api/time-machine/verify-version-history/${encodeURIComponent(contractId)}`, { method: "POST" });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "Blockchain verification unavailable");
      const result = await response.json();
      setMessage(result.verified ? "Every selected version is verified on-chain." : "One or more versions failed blockchain verification.");
      setVersions(result.versions); setSelected(result.versions.at(-1) ?? null);
      setProofChecked(true);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Blockchain verification unavailable"); }
    finally { setLoading(false); }
  }

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-12 text-slate-100">
      <div className="mx-auto max-w-6xl">
        <header className="mb-10 flex flex-col gap-5 border-b border-slate-800 pb-8 md:flex-row md:items-end md:justify-between">
          <div><p className="mb-2 text-sm font-semibold uppercase tracking-[0.24em] text-cyan-400">LexProof / provenance</p><h1 className="text-4xl font-bold tracking-tight">Contract Time Machine</h1><p className="mt-3 max-w-xl text-slate-400">Trace how a contract changed, what moved its risk, and whether every snapshot is anchored on-chain.</p></div>
          <div className="flex gap-2"><input aria-label="Contract identifier" value={contractId} onChange={e => setContractId(e.target.value)} placeholder="Contract identifier" className="w-56 border border-slate-700 bg-slate-900 px-4 py-3 text-sm outline-none focus:border-cyan-400" /><button onClick={() => void loadHistory()} disabled={loading} className="bg-cyan-400 px-5 py-3 text-sm font-bold text-slate-950 disabled:opacity-50">Load history</button></div>
        </header>

        {message && <div role="status" className="mb-6 border border-amber-400/40 bg-amber-400/10 px-4 py-3 text-amber-200">{message}</div>}
        {versions.length > 0 && <>
          <section className="mb-8 overflow-x-auto border border-slate-800 bg-slate-900 p-6"><div className="flex min-w-max items-center gap-0">
            {versions.map((version, index) => <div key={version.passport_id} className="flex items-center"><button onClick={() => setSelected(version)} className={`group flex min-w-28 flex-col items-center gap-2 px-5 py-2 ${selected?.version === version.version ? "text-cyan-300" : "text-slate-400"}`}><span className={`grid h-12 w-12 place-items-center border text-lg font-bold ${selected?.version === version.version ? "border-cyan-300 bg-cyan-300/10" : "border-slate-700"}`}>V{version.version}</span><span className="text-xs uppercase tracking-wider">{proofChecked ? (version.blockchain_proof_verified ? "Verified" : "Failed") : "Not checked"}</span></button>{index < versions.length - 1 && <span className="text-slate-700">────</span>}</div>)}
          </div></section>

          {selected && <section className="mb-8 border border-slate-800 bg-slate-900 p-6"><div className="mb-5 flex items-center justify-between"><div><p className="text-sm text-cyan-400">Selected snapshot</p><h2 className="text-2xl font-bold">Version {selected.version}</h2></div><span className={`border px-3 py-2 text-xs font-bold uppercase ${!proofChecked ? "border-slate-500 text-slate-300" : selected.blockchain_proof_verified ? "border-emerald-400/50 text-emerald-300" : "border-rose-400/50 text-rose-300"}`}>{!proofChecked ? "Not checked on-chain" : selected.blockchain_proof_verified ? "Proof verified" : "Proof failed"}</span></div><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[["Risk", selected.risk_score], ["Compliance", selected.compliance_score], ["Policy", selected.policy_version], ["Created", new Date(selected.created_at).toLocaleString()]].map(([label, value]) => <div key={String(label)} className="border-l-2 border-slate-700 pl-4"><p className="text-xs uppercase tracking-wider text-slate-500">{label}</p><p className="mt-2 font-semibold">{value}</p></div>)}</div><div className="mt-6 grid gap-3 text-xs text-slate-400 md:grid-cols-2">{[["Document", selected.document_hash], ["Policy", selected.policy_hash], ["Analysis", selected.analysis_hash], ["Evidence", selected.evidence_hash]].map(([label, value]) => <div key={String(label)}><span className="text-slate-500">{label} hash</span><p className="mt-1 break-all font-mono text-slate-300">{value}</p></div>)}</div></section>}

          <section className="border border-slate-800 bg-slate-900 p-6"><div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm text-cyan-400">Analysis</p><h2 className="text-2xl font-bold">Compare versions</h2></div><div className="flex items-end gap-2"><label className="text-xs text-slate-500">From<select value={from} onChange={e => setFrom(e.target.value)} className="mt-1 block border border-slate-700 bg-slate-950 px-3 py-2 text-slate-200"><option value="">Select</option>{versions.map(v => <option key={v.version} value={v.version}>V{v.version}</option>)}</select></label><span className="pb-2 text-slate-600">to</span><label className="text-xs text-slate-500">To<select value={to} onChange={e => setTo(e.target.value)} className="mt-1 block border border-slate-700 bg-slate-950 px-3 py-2 text-slate-200"><option value="">Select</option>{versions.map(v => <option key={v.version} value={v.version}>V{v.version}</option>)}</select></label><button onClick={compare} className="bg-slate-100 px-4 py-2 font-bold text-slate-950">Compare</button><button onClick={verifyHistory} className="border border-emerald-400 px-4 py-2 font-bold text-emerald-300">Verify Version History</button></div></div>
            {comparison && <div className="mt-8"><div className="grid gap-4 sm:grid-cols-3"><Metric label="Risk delta" value={comparison.risk_delta} /><Metric label="Compliance delta" value={comparison.compliance_delta} /><Metric label="On-chain proofs" value={proofChecked ? (versions.every((item) => item.blockchain_proof_verified) ? "Verified" : "Failed") : "Not checked"} /></div><p className="mt-5 text-slate-300">{comparison.policy_delta} · {comparison.business_impact}</p><div className="mt-6 space-y-3">{comparison.clause_changes.map((change, index) => <article key={index} className="border border-slate-800 p-4"><div className="flex justify-between"><span className="font-bold uppercase text-cyan-300">{change.change_type}</span><span className="text-sm text-slate-400">Risk {change.risk_delta > 0 ? "+" : ""}{change.risk_delta} · Compliance {change.compliance_delta > 0 ? "+" : ""}{change.compliance_delta}</span></div><p className="mt-2 text-sm text-slate-400">{change.current_text ?? change.previous_text}</p><p className="mt-2 text-xs text-slate-500">{change.business_impact}</p></article>)}</div></div>}
          </section>
        </>}
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) { return <div className="border border-slate-800 p-4"><p className="text-xs uppercase tracking-wider text-slate-500">{label}</p><p className="mt-2 text-xl font-bold text-slate-100">{typeof value === "number" && value > 0 ? `+${value}` : value}</p></div>; }
