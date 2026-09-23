"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiFetch } from "../../../lib/api";
import { Card, CardContent } from "../../../components/ui/card";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { PageHeader } from "../../../components/ui/page-header";
import { PageContainer } from "../../../components/ui/container";

// Phase 4 (2026-09-11, gold-standard visual consistency pass): rebuilt onto
// the shared light PageContainer/PageHeader/Card/Badge system -- the prior
// version was a full-bleed dark slate-950 page with its own cyan accent and
// border-only panels, the single most off-system screen in the app
// (flagged explicitly in the Phase 4 screen inventory). Every fetch,
// handler, and piece of state below is unchanged; this is a
// presentation-only rewrite.

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
    <PageContainer>
      <PageHeader
        eyebrow="Provenance"
        title="Contract Time Machine"
        description="Trace how a contract changed, what moved its risk, and whether every snapshot is anchored on-chain."
        actions={
          <div className="flex gap-2">
            <input
              aria-label="Contract identifier"
              value={contractId}
              onChange={(e) => setContractId(e.target.value)}
              placeholder="Contract identifier"
              className="w-56 rounded-[var(--radius-md,0.5rem)] border border-gray-300 px-3 py-2 text-sm outline-none focus:border-[var(--brand-primary,#2563eb)] dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
            />
            <Button type="button" onClick={() => void loadHistory()} disabled={loading}>Load history</Button>
          </div>
        }
      />

      <div className="mt-6 space-y-6">
        {message && (
          <p role="status" className="rounded-[var(--radius-lg,0.75rem)] border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
            {message}
          </p>
        )}

        {versions.length > 0 && (
          <>
            <Card>
              <CardContent className="overflow-x-auto">
                <div className="flex min-w-max items-center gap-0">
                  {versions.map((version, index) => (
                    <div key={version.passport_id} className="flex items-center">
                      <button
                        onClick={() => setSelected(version)}
                        className={`group flex min-w-28 flex-col items-center gap-2 px-5 py-2 ${selected?.version === version.version ? "text-[var(--brand-primary,#2563eb)]" : "text-gray-500 dark:text-gray-400"}`}
                      >
                        <span className={`grid h-12 w-12 place-items-center rounded-full border text-lg font-bold ${selected?.version === version.version ? "border-[var(--brand-primary,#2563eb)] bg-blue-50 dark:bg-blue-950/40" : "border-gray-300 dark:border-gray-600"}`}>
                          V{version.version}
                        </span>
                        <span className="text-xs uppercase tracking-wider">{proofChecked ? (version.blockchain_proof_verified ? "Verified" : "Failed") : "Not checked"}</span>
                      </button>
                      {index < versions.length - 1 && <span className="text-gray-300 dark:text-gray-600">────</span>}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {selected && (
              <Card>
                <CardContent>
                  <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wide text-[var(--brand-primary,#2563eb)]">Selected snapshot</p>
                      <h2 className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">Version {selected.version}</h2>
                    </div>
                    <Badge variant={!proofChecked ? 'secondary' : selected.blockchain_proof_verified ? 'verified' : 'tampered'}>
                      {!proofChecked ? "Not checked on-chain" : selected.blockchain_proof_verified ? "Proof verified" : "Proof failed"}
                    </Badge>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    {[["Risk", selected.risk_score], ["Compliance", selected.compliance_score], ["Policy", selected.policy_version], ["Created", new Date(selected.created_at).toLocaleString()]].map(([label, value]) => (
                      <div key={String(label)} className="border-l-2 border-gray-200 pl-4 dark:border-gray-700">
                        <p className="text-xs uppercase tracking-wider text-gray-500 dark:text-gray-400">{label}</p>
                        <p className="mt-2 font-semibold text-gray-900 dark:text-gray-100">{value}</p>
                      </div>
                    ))}
                  </div>
                  <div className="mt-6 grid gap-3 text-xs text-gray-500 dark:text-gray-400 md:grid-cols-2">
                    {[["Document", selected.document_hash], ["Policy", selected.policy_hash], ["Analysis", selected.analysis_hash], ["Evidence", selected.evidence_hash]].map(([label, value]) => (
                      <div key={String(label)}>
                        <span className="text-gray-400 dark:text-gray-500">{label} hash</span>
                        <p className="mt-1 break-all font-mono text-gray-700 dark:text-gray-300">{value}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardContent>
                <div className="flex flex-wrap items-end justify-between gap-4">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wide text-[var(--brand-primary,#2563eb)]">Analysis</p>
                    <h2 className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">Compare versions</h2>
                  </div>
                  <div className="flex items-end gap-2">
                    <label className="text-xs text-gray-500 dark:text-gray-400">
                      From
                      <select value={from} onChange={(e) => setFrom(e.target.value)} className="mt-1 block rounded-[var(--radius-md,0.5rem)] border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100">
                        <option value="">Select</option>
                        {versions.map((v) => <option key={v.version} value={v.version}>V{v.version}</option>)}
                      </select>
                    </label>
                    <span className="pb-2 text-gray-400 dark:text-gray-500">to</span>
                    <label className="text-xs text-gray-500 dark:text-gray-400">
                      To
                      <select value={to} onChange={(e) => setTo(e.target.value)} className="mt-1 block rounded-[var(--radius-md,0.5rem)] border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100">
                        <option value="">Select</option>
                        {versions.map((v) => <option key={v.version} value={v.version}>V{v.version}</option>)}
                      </select>
                    </label>
                    <Button type="button" variant="secondary" onClick={compare}>Compare</Button>
                    <Button type="button" variant="outline" onClick={verifyHistory}>Verify Version History</Button>
                  </div>
                </div>
                {comparison && (
                  <div className="mt-8">
                    <div className="grid gap-4 sm:grid-cols-3">
                      <Metric label="Risk delta" value={comparison.risk_delta} />
                      <Metric label="Compliance delta" value={comparison.compliance_delta} />
                      <Metric label="On-chain proofs" value={proofChecked ? (versions.every((item) => item.blockchain_proof_verified) ? "Verified" : "Failed") : "Not checked"} />
                    </div>
                    <p className="mt-5 text-gray-700 dark:text-gray-300">{comparison.policy_delta} · {comparison.business_impact}</p>
                    <div className="mt-6 space-y-3">
                      {comparison.clause_changes.map((change, index) => (
                        <article key={index} className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 p-4 dark:border-gray-700">
                          <div className="flex justify-between">
                            <span className="font-bold uppercase text-[var(--brand-primary,#2563eb)]">{change.change_type}</span>
                            <span className="text-sm text-gray-500 dark:text-gray-400">Risk {change.risk_delta > 0 ? "+" : ""}{change.risk_delta} · Compliance {change.compliance_delta > 0 ? "+" : ""}{change.compliance_delta}</span>
                          </div>
                          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">{change.current_text ?? change.previous_text}</p>
                          <p className="mt-2 text-xs text-gray-500 dark:text-gray-500">{change.business_impact}</p>
                        </article>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </PageContainer>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-[var(--radius-md,0.5rem)] border border-gray-200 p-4 dark:border-gray-700">
      <p className="text-xs uppercase tracking-wider text-gray-500 dark:text-gray-400">{label}</p>
      <p className="mt-2 text-xl font-bold text-gray-900 dark:text-gray-100">{typeof value === "number" && value > 0 ? `+${value}` : value}</p>
    </div>
  );
}
