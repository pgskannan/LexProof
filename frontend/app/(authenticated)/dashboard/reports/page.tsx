'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { BarChart3, Clock, Coins, ShieldCheck } from 'lucide-react';
import { apiFetch } from '../../../../lib/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Skeleton } from '../../../../components/ui/skeleton';

// Evidence and per-evidence anchor lookups can transiently 503 under this
// dev backend's known event-loop-blocking load (see status-and-plan.md's
// notes on the datetime-sort/§2c-class hang). Swallowing a single failed
// lookup as "no evidence" would silently understate this contract's real,
// on-chain-anchored evidence -- and drag down the audit-readiness score --
// with no error shown. Retry once after a short delay before giving up.
async function fetchWithRetry(path: string, attempts = 2): Promise<Response> {
  let lastResponse: Response | null = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const response = await apiFetch(path);
    if (response.ok || response.status < 500 || attempt === attempts - 1) return response;
    lastResponse = response;
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  return lastResponse as Response;
}

// "Metrics that Matter" — see hackathon-polish-roadmap.md initiative #5.
// Every number here is computed either from real, live data already stored for
// the selected contract (findings, evidence, anchors, review/publish records),
// or from an assumption the viewer can see and edit inline. Nothing is a fixed,
// hidden, or fabricated constant presented as measured fact.

type ContractSummary = {
  contract_id: string;
  name?: string | null;
  version?: number | null;
};

type ContractVersion = {
  version_id: string;
  version_number: number;
  created_at?: string | null;
  analysis_status?: string | null;
  passport_id?: string | null;
  is_current?: boolean;
};

type Finding = { finding_id: string };

type Proposal = {
  proposal_id: string;
  status: string;
  review?: { decision: string } | null;
  published_version_id?: string | null;
};

type PassportSummary = {
  passport_id: string;
  contract_version: number;
  evidence_count: number;
  risk_score?: number;
  compliance_score?: number;
  created_at?: string;
  status?: string;
};

type EvidenceRow = { evidence_id: string };

function minutesBetween(a?: string | null, b?: string | null): number | null {
  if (!a || !b) return null;
  const start = new Date(a).getTime();
  const end = new Date(b).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null;
  return (end - start) / 60000;
}

function formatMinutes(minutes: number): string {
  if (minutes < 1) return `${Math.max(1, Math.round(minutes * 60))} sec`;
  if (minutes < 60) return `${minutes.toFixed(1)} min`;
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  return `${hours} hr ${rest} min`;
}

// Enterprise-grade input styling shared by every editable assumption field on
// this page, so the whole panel reads as one deliberately-designed system.
const EYEBROW = 'text-xs font-bold uppercase tracking-wide text-gray-500';
const NUMBER_INPUT =
  'mt-1 block w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm font-normal text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30';

export default function Reports() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [contractsLoading, setContractsLoading] = useState(true);
  const [contractId, setContractId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [versions, setVersions] = useState<ContractVersion[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [passports, setPassports] = useState<PassportSummary[]>([]);
  const [evidenceCount, setEvidenceCount] = useState(0);
  const [anchoredCount, setAnchoredCount] = useState(0);

  // Editable assumptions. Defaults are round, clearly-labeled starting points —
  // not asserted as measured or authoritative. Adjust them to match your own
  // benchmarks or current market rates before presenting.
  const [minutesPerFinding, setMinutesPerFinding] = useState(12);
  const [gasPerAnchor, setGasPerAnchor] = useState(150000);
  const [gasPriceGwei, setGasPriceGwei] = useState(15);
  const [ethUsd, setEthUsd] = useState(3000);
  const [l2DiscountPercent, setL2DiscountPercent] = useState(97);

  useEffect(() => {
    setContractsLoading(true);
    void apiFetch('/api/contracts')
      .then(async (response) => {
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load contracts');
        const records: ContractSummary[] = await response.json();
        setContracts(records);
        const queryId = searchParams.get('contractId');
        if (queryId) setContractId(queryId);
        else if (records.length) setContractId(records[0].contract_id);
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Unable to load contracts'))
      .finally(() => setContractsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadMetrics = useCallback(async (id: string) => {
    if (!id) {
      setVersions([]); setFindings([]); setProposals([]); setPassports([]); setEvidenceCount(0); setAnchoredCount(0);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const [versionsRes, findingsRes, proposalsRes, passportsRes] = await Promise.all([
        apiFetch(`/api/contracts/${encodeURIComponent(id)}/versions`),
        apiFetch(`/api/findings?contract_id=${encodeURIComponent(id)}`),
        apiFetch(`/api/contracts/${encodeURIComponent(id)}/redline-proposals`),
        apiFetch(`/api/passports?contract_id=${encodeURIComponent(id)}&limit=100`),
      ]);
      for (const response of [versionsRes, findingsRes, proposalsRes, passportsRes]) {
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Unable to load contract metrics');
      }
      const versionRows: ContractVersion[] = await versionsRes.json();
      const findingRows: Finding[] = await findingsRes.json();
      const proposalRows: Proposal[] = await proposalsRes.json();
      const passportPayload = await passportsRes.json();
      const passportRows: PassportSummary[] = Array.isArray(passportPayload) ? passportPayload : passportPayload.passports ?? [];

      setVersions(versionRows);
      setFindings(findingRows);
      setProposals(proposalRows);
      setPassports(passportRows);

      // Evidence + anchor counts, same aggregation approach as the contract
      // lifecycle page, so the two pages always agree on these numbers.
      const evidenceGroups = await Promise.all(passportRows.map(async (passport) => {
        const response = await fetchWithRetry(`/api/passports/${encodeURIComponent(passport.passport_id)}/evidence`);
        if (!response.ok) return { evidence: [] as EvidenceRow[], anchored: 0 };
        const evidence: EvidenceRow[] = await response.json();
        const anchorFlags = await Promise.all(evidence.map(async (item) => {
          const anchorResponse = await fetchWithRetry(`/api/evidence/${encodeURIComponent(item.evidence_id)}/anchor`);
          return anchorResponse.ok;
        }));
        return { evidence, anchored: anchorFlags.filter(Boolean).length };
      }));
      setEvidenceCount(evidenceGroups.reduce((sum, group) => sum + group.evidence.length, 0));
      setAnchoredCount(evidenceGroups.reduce((sum, group) => sum + group.anchored, 0));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load contract metrics');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadMetrics(contractId); }, [contractId, loadMetrics]);

  function selectContract(id: string) {
    setContractId(id);
    const params = new URLSearchParams(Array.from(searchParams.entries()));
    if (id) params.set('contractId', id); else params.delete('contractId');
    router.replace(`/dashboard/reports?${params.toString()}`);
  }

  const current = useMemo(() => versions.find((v) => v.is_current) ?? versions.at(-1), [versions]);
  const currentPassport = useMemo(
    () => passports.find((p) => p.contract_version === current?.version_number),
    [passports, current],
  );

  // 1. Review-time savings ---------------------------------------------------
  const manualEstimateMinutes = findings.length * minutesPerFinding;
  const measuredAiMinutes = current && currentPassport ? minutesBetween(current.created_at, currentPassport.created_at) : null;
  const savingsPercent = measuredAiMinutes !== null && manualEstimateMinutes > 0
    ? Math.max(0, Math.min(100, 100 * (1 - measuredAiMinutes / manualEstimateMinutes)))
    : null;

  // 2. Anchoring cost model (L1 vs. L2) ---------------------------------------
  const l1CostPerAnchorUsd = (gasPerAnchor * gasPriceGwei * 1e-9) * ethUsd;
  const l2CostPerAnchorUsd = l1CostPerAnchorUsd * (1 - l2DiscountPercent / 100);
  const l1TotalUsd = l1CostPerAnchorUsd * evidenceCount;
  const l2TotalUsd = l2CostPerAnchorUsd * evidenceCount;

  // 3. Audit-readiness score ---------------------------------------------------
  const evidenceAnchoredPct = evidenceCount > 0 ? (anchoredCount / evidenceCount) * 100 : 0;
  const reviewedProposals = proposals.filter((p) => p.review).length;
  const proposalsReviewedPct = proposals.length > 0 ? (reviewedProposals / proposals.length) * 100 : 100;
  const publishedPct = proposals.some((p) => p.published_version_id) ? 100 : (proposals.some((p) => p.status === 'APPROVED') ? 50 : 0);
  const analysisCompletePct = current?.analysis_status === 'complete' ? 100 : 0;
  const auditReadinessScore = Math.round(
    evidenceAnchoredPct * 0.4 + proposalsReviewedPct * 0.3 + publishedPct * 0.15 + analysisCompletePct * 0.15,
  );

  // Score band drives the audit-readiness dial's color and label, the same
  // three-tier severity language (strong / developing / needs attention) an
  // audit-readiness metric should read at a glance, without a legend.
  const scoreBand = auditReadinessScore >= 80
    ? { ring: 'border-green-300', bg: 'bg-green-50', text: 'text-green-700', label: 'Strong' }
    : auditReadinessScore >= 50
      ? { ring: 'border-amber-300', bg: 'bg-amber-50', text: 'text-amber-700', label: 'Developing' }
      : { ring: 'border-red-300', bg: 'bg-red-50', text: 'text-red-700', label: 'Needs attention' };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Reports</h1>
        <p className="mt-2 text-base text-gray-600">
          Metrics that matter: what LexProof&apos;s AI analysis and blockchain anchoring are actually worth, computed from
          this contract&apos;s real data plus assumptions you can see and edit.
        </p>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <label className={EYEBROW}>
          Contract
          <select
            value={contractId}
            onChange={(event) => selectContract(event.target.value)}
            className="mt-2 block w-full max-w-xl rounded-lg border border-gray-300 px-3 py-2.5 text-sm font-normal text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
            disabled={contractsLoading || contracts.length === 0}
          >
            {contracts.length === 0 && <option value="">No contracts available</option>}
            {contracts.map((contract) => (
              <option key={contract.contract_id} value={contract.contract_id}>
                {(contract.name || contract.contract_id) + (contract.version ? ` (V${contract.version})` : '')}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</p>}

      {loading ? (
        <div className="grid gap-6 xl:grid-cols-3">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : contractId ? (
        <div className="grid gap-6 xl:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-3">
                <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50"><Clock className="h-5 w-5 text-blue-600" /></span>
                Review-time savings
              </CardTitle>
              <CardDescription>Estimated manual review time vs. LexProof&apos;s measured AI analysis time.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div>
                <label className={`flex items-center justify-between ${EYEBROW}`}>
                  Assumed manual review time per finding (editable)
                  <input
                    type="number"
                    min={1}
                    value={minutesPerFinding}
                    onChange={(event) => setMinutesPerFinding(Math.max(1, Number(event.target.value) || 1))}
                    className="ml-2 w-20 rounded-md border border-gray-300 px-2 py-1.5 text-right text-sm font-normal text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                  /> min
                </label>
              </div>
              <div className="rounded-lg border border-gray-200 p-4">
                <p className={EYEBROW}>Estimated manual review</p>
                <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-gray-900">{formatMinutes(manualEstimateMinutes)}</p>
                <p className="mt-1 text-xs text-gray-500">{findings.length} finding{findings.length === 1 ? '' : 's'} × {minutesPerFinding} min (your assumption)</p>
              </div>
              <div className="rounded-lg border border-green-200 bg-green-50 p-4">
                <p className={`text-xs font-bold uppercase tracking-wide text-green-700`}>LexProof AI analysis (measured)</p>
                <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-green-900">{measuredAiMinutes !== null ? formatMinutes(measuredAiMinutes) : 'Not available'}</p>
                <p className="mt-1 text-xs text-green-700">
                  {measuredAiMinutes !== null
                    ? 'Real elapsed time from version upload to Legal Passport creation.'
                    : 'Needs both a version timestamp and a Legal Passport for the current version.'}
                </p>
              </div>
              {savingsPercent !== null && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
                  <p className="text-xs font-bold uppercase tracking-wide text-blue-700">Estimated time saved</p>
                  <p className="mt-1 text-3xl font-bold tabular-nums tracking-tight text-blue-900">{savingsPercent.toFixed(0)}%</p>
                </div>
              )}
              <p className="text-xs italic text-gray-500">
                The manual-review figure is your own adjustable assumption, not a measured baseline — set it to match
                your organization&apos;s actual review benchmarks before citing it.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-3">
                <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-50"><Coins className="h-5 w-5 text-amber-600" /></span>
                Anchoring cost: L1 vs. L2
              </CardTitle>
              <CardDescription>Illustrative cost model — edit the gas price and ETH/USD rate to match current market conditions.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-4">
                <label className={EYEBROW}>Gas per anchor
                  <input type="number" min={1} value={gasPerAnchor} onChange={(e) => setGasPerAnchor(Math.max(1, Number(e.target.value) || 1))} className={NUMBER_INPUT} />
                </label>
                <label className={EYEBROW}>Gas price (gwei)
                  <input type="number" min={0} step="0.1" value={gasPriceGwei} onChange={(e) => setGasPriceGwei(Math.max(0, Number(e.target.value) || 0))} className={NUMBER_INPUT} />
                </label>
                <label className={EYEBROW}>ETH/USD
                  <input type="number" min={0} value={ethUsd} onChange={(e) => setEthUsd(Math.max(0, Number(e.target.value) || 0))} className={NUMBER_INPUT} />
                </label>
                <label className={EYEBROW}>L2 discount %
                  <input type="number" min={0} max={99} value={l2DiscountPercent} onChange={(e) => setL2DiscountPercent(Math.min(99, Math.max(0, Number(e.target.value) || 0)))} className={NUMBER_INPUT} />
                </label>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-lg border border-gray-200 p-4">
                  <p className={EYEBROW}>L1 (e.g. Ethereum mainnet)</p>
                  <p className="mt-1 text-2xl font-bold tabular-nums tracking-tight text-gray-900">${l1CostPerAnchorUsd.toFixed(2)}<span className="text-xs font-normal text-gray-500"> / anchor</span></p>
                  <p className="text-xs text-gray-500">${l1TotalUsd.toFixed(2)} for this contract&apos;s {evidenceCount} evidence item{evidenceCount === 1 ? '' : 's'}</p>
                </div>
                <div className="rounded-lg border border-green-200 bg-green-50 p-4">
                  <p className="text-xs font-bold uppercase tracking-wide text-green-700">L2 (e.g. Base / Polygon)</p>
                  <p className="mt-1 text-2xl font-bold tabular-nums tracking-tight text-green-900">${l2CostPerAnchorUsd.toFixed(4)}<span className="text-xs font-normal text-green-700"> / anchor</span></p>
                  <p className="text-xs text-green-700">${l2TotalUsd.toFixed(2)} for this contract&apos;s {evidenceCount} evidence item{evidenceCount === 1 ? '' : 's'}</p>
                </div>
              </div>
              <p className="text-xs italic text-gray-500">
                This demo anchors to Ethereum Sepolia (testnet, no real cost). The figures above model what a
                production mainnet/L2 deployment would cost, using the gas price, ETH price, and L2 discount you
                enter — check a live source (e.g. etherscan.io/gastracker) for current rates before presenting.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-3">
                <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-green-50"><ShieldCheck className="h-5 w-5 text-green-600" /></span>
                Audit-readiness score
              </CardTitle>
              <CardDescription>Composite score from this contract&apos;s real anchoring, review, and publication state.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="flex items-center gap-5">
                <div className={`flex h-24 w-24 shrink-0 flex-col items-center justify-center rounded-full border-4 ${scoreBand.ring} ${scoreBand.bg}`}>
                  <span className={`text-3xl font-extrabold tabular-nums tracking-tight ${scoreBand.text}`}>{auditReadinessScore}</span>
                  <span className={`text-[10px] font-bold uppercase tracking-wide ${scoreBand.text}`}>/ 100</span>
                </div>
                <div>
                  <p className={`text-sm font-bold ${scoreBand.text}`}>{scoreBand.label}</p>
                  <p className="mt-1 text-xs text-gray-500">Weighted: evidence anchored (40%), proposals reviewed (30%), publication status (15%), analysis completeness (15%).</p>
                </div>
              </div>
              <dl className="space-y-2.5">
                <div className="flex items-center justify-between border-t border-gray-100 pt-2.5">
                  <dt className="text-sm text-gray-600">Evidence anchored</dt>
                  <dd className="text-base font-semibold tabular-nums text-gray-900">{anchoredCount}/{evidenceCount} ({evidenceAnchoredPct.toFixed(0)}%)</dd>
                </div>
                <div className="flex items-center justify-between border-t border-gray-100 pt-2.5">
                  <dt className="text-sm text-gray-600">Redline proposals reviewed</dt>
                  <dd className="text-base font-semibold tabular-nums text-gray-900">{reviewedProposals}/{proposals.length} ({proposalsReviewedPct.toFixed(0)}%)</dd>
                </div>
                <div className="flex items-center justify-between border-t border-gray-100 pt-2.5">
                  <dt className="text-sm text-gray-600">Publication status</dt>
                  <dd className="text-base font-semibold text-gray-900">{publishedPct === 100 ? 'Published' : publishedPct === 50 ? 'Approved, unpublished' : 'Not published'}</dd>
                </div>
                <div className="flex items-center justify-between border-t border-gray-100 pt-2.5">
                  <dt className="text-sm text-gray-600">Current version analysis</dt>
                  <dd className="text-base font-semibold text-gray-900">{current?.analysis_status || 'Not available'}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        </div>
      ) : (
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <p className="flex items-center gap-2 text-sm text-gray-500"><BarChart3 className="h-4 w-4" /> Select a contract above to see its metrics.</p>
        </div>
      )}
    </div>
  );
}
