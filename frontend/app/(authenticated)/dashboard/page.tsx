'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowRight, FileText, ListChecks, Shield } from 'lucide-react';
import { apiFetch } from '../../../lib/api';
import { EmptyState } from '../../../components/EmptyState';
import { Skeleton } from '../../../components/ui/skeleton';
import { useOrg } from '../../../components/OrgProvider';
import type { WorkflowInstance } from '../../../lib/org';

type ContractSummary = {
  contract_id: string;
  name?: string | null;
  version?: number | null;
  analysis_status?: string | null;
  passport_id?: string | null;
  updated_at?: string | null;
  created_at?: string | null;
};

type Finding = {
  finding_id: string;
  title?: string | null;
  severity?: string | null;
  contract_id?: string | null;
  created_at?: string | null;
};

type ActivityItem = {
  id: string;
  title: string;
  detail: string;
  href: string;
  at: string;
};

function relativeTime(value: string) {
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return value;
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? '' : 's'} ago`;
  return new Date(value).toLocaleDateString();
}

function workflowLabel(state: string) {
  return state.replace(/_/g, ' ').toLowerCase();
}

export default function Dashboard() {
  const { currentOrg } = useOrg();
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowInstance[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const orgId = currentOrg?.org_id;
        const [contractResponse, findingResponse, workflowResponse] = await Promise.all([
          apiFetch('/api/contracts'),
          apiFetch('/api/findings'),
          orgId
            ? apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/workflow-instances?limit=50`)
            : Promise.resolve(null),
        ]);
        const nextContracts = contractResponse.ok ? await contractResponse.json() : [];
        const nextFindings = findingResponse.ok ? await findingResponse.json() : [];
        const workflowPayload = workflowResponse && workflowResponse.ok ? await workflowResponse.json() : { items: [] };
        const nextWorkflows = Array.isArray(workflowPayload) ? workflowPayload : workflowPayload.items || [];
        if (!cancelled) {
          setContracts(nextContracts);
          setFindings(nextFindings);
          setWorkflows(nextWorkflows);
        }
      } catch {
        if (!cancelled) {
          setContracts([]);
          setFindings([]);
          setWorkflows([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [currentOrg?.org_id]);

  const failed = contracts.filter((item) => item.analysis_status === 'failed');
  const passportCount = contracts.filter((item) => item.passport_id).length;
  const activity = useMemo(() => {
    const items: ActivityItem[] = [];
    for (const instance of workflows) {
      const at = instance.updated_at || instance.created_at;
      if (!at) continue;
      const contractId = instance.metadata?.contract_id;
      items.push({
        id: `workflow-${instance.instance_id}`,
        title: `Review ${workflowLabel(instance.current_state || 'updated')}`,
        detail: `${(instance.entity_type || 'workflow').replace(/_/g, ' ')} · ${instance.status}`,
        href: contractId
          ? `/dashboard/contracts/reviews?contractId=${encodeURIComponent(contractId)}`
          : '/dashboard/contracts/reviews',
        at,
      });
    }
    for (const contract of contracts) {
      const at = contract.updated_at || contract.created_at;
      if (!at) continue;
      items.push({
        id: `contract-${contract.contract_id}`,
        title: contract.name || contract.contract_id,
        detail: contract.analysis_status === 'failed'
          ? 'Analysis failed — retry from the contract page'
          : contract.passport_id
            ? `Passport ready · v${contract.version ?? '—'}`
            : `Status: ${contract.analysis_status || 'recorded'}`,
        href: `/dashboard/contracts/${encodeURIComponent(contract.contract_id)}`,
        at,
      });
    }
    for (const finding of findings) {
      if (!finding.created_at) continue;
      items.push({
        id: `finding-${finding.finding_id}`,
        title: finding.title || 'AI finding',
        detail: `${finding.severity || 'unspecified'} · ${finding.contract_id || 'contract'}`,
        href: `/dashboard/ai-analysis/findings?finding_id=${encodeURIComponent(finding.finding_id)}`,
        at: finding.created_at,
      });
    }
    return items.sort((a, b) => b.at.localeCompare(a.at)).slice(0, 10);
  }, [contracts, findings, workflows]);

  return (
    <main className="min-h-screen p-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8">
          <h2 className="text-3xl font-bold text-gray-900">Dashboard</h2>
          <p className="mt-2 text-gray-600">Live activity for this organization — contracts, findings, and passports.</p>
        </div>

        {failed.length > 0 && (
          <div className="mb-6 flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4">
            <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-700" />
            <div>
              <p className="font-semibold text-amber-900">
                {failed.length} contract{failed.length === 1 ? '' : 's'} stuck on failed analysis
              </p>
              <p className="mt-1 text-sm text-amber-800">
                These versions did not finish AI analysis. Open the contract to retry rather than leaving a silent failed badge.
              </p>
              <ul className="mt-2 space-y-1 text-sm">
                {failed.map((item) => (
                  <li key={item.contract_id}>
                    <Link
                      href={`/dashboard/contracts/${encodeURIComponent(item.contract_id)}`}
                      className="font-medium text-amber-900 underline"
                    >
                      {item.name || item.contract_id}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          <StatCard label="Contracts" value={loading ? null : contracts.length} href="/dashboard/contracts" icon={<FileText className="h-6 w-6 text-blue-600" />} tone="blue" />
          <StatCard label="Legal passports" value={loading ? null : passportCount} href="/legal-passport" icon={<Shield className="h-6 w-6 text-emerald-600" />} tone="emerald" />
          <StatCard label="AI findings" value={loading ? null : findings.length} href="/dashboard/ai-analysis/findings" icon={<ListChecks className="h-6 w-6 text-red-600" />} tone="red" />
        </div>

        <div className="mt-8 rounded-lg bg-white shadow">
          <div className="border-b border-gray-200 p-6">
            <h3 className="text-xl font-semibold text-gray-900">Recent Activity</h3>
          </div>
          <div className="p-6">
            {loading && (
              <div className="space-y-3">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            )}
            {!loading && activity.length === 0 && (
              <EmptyState
                title="No activity yet"
                description="Upload a contract, run analysis, or record a review decision to see live events here. Approvals and workflow transitions appear as soon as they are saved."
                actionLabel="Go to contracts"
                onAction={() => {
                  window.location.href = '/dashboard/contracts';
                }}
              />
            )}
            {!loading && activity.length > 0 && (
              <div className="space-y-3">
                {activity.map((item) => (
                  <Link
                    key={item.id}
                    href={item.href}
                    className="flex items-center justify-between rounded-lg bg-gray-50 p-4 hover:bg-blue-50"
                  >
                    <div>
                      <p className="font-medium text-gray-900">{item.title}</p>
                      <p className="text-sm text-gray-600">{item.detail}</p>
                    </div>
                    <span className="flex items-center gap-2 text-sm text-gray-500">
                      {relativeTime(item.at)}
                      <ArrowRight className="h-4 w-4" />
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

function StatCard({
  label,
  value,
  href,
  icon,
  tone,
}: {
  label: string
  value: number | null
  href: string
  icon: ReactNode
  tone: 'blue' | 'emerald' | 'red'
}) {
  const tones = {
    blue: 'bg-blue-100',
    emerald: 'bg-emerald-100',
    red: 'bg-red-100',
  }
  return (
    <Link href={href} className="rounded-lg bg-white p-6 shadow hover:shadow-md">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-600">{label}</p>
          {value === null ? <Skeleton className="mt-2 h-9 w-16" /> : <p className="mt-2 text-3xl font-bold text-gray-900">{value}</p>}
        </div>
        <div className={`${tones[tone]} rounded-full p-3`}>{icon}</div>
      </div>
    </Link>
  )
}
