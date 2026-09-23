'use client';

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import Link from 'next/link';
import {
  AlertOctagon,
  AlertTriangle,
  Anchor,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Clock,
  Eye,
  EyeOff,
  FileText,
  Gauge,
  ListChecks,
  Settings2,
  Shield,
} from 'lucide-react';
import { apiFetch } from '../../../lib/api';
import { EmptyState } from '../../../components/EmptyState';
import { Skeleton } from '../../../components/ui/skeleton';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { PageHeader } from '../../../components/ui/page-header';
import { PageContainer } from '../../../components/ui/container';
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
  // Optional fields: already present on the /api/contracts response body
  // (see dashboard/contracts/page.tsx's ContractSummary), just not
  // previously read by this screen's narrower type. Widening the type to
  // read them is not a new API call or a business-logic change -- it lets
  // the existing fetched payload drive the Portfolio Risk / Evidence
  // sections below without any new request.
  risk_score?: number | null;
  risk_level?: string | null;
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

type WidgetId = 'stat-contracts' | 'stat-passports' | 'stat-findings' | 'recent-activity';
type WidgetPref = { id: WidgetId; visible: boolean };

const WIDGET_META: Record<WidgetId, { label: string; icon: ReactNode }> = {
  'stat-contracts': { label: 'Contracts count', icon: <FileText className="h-4 w-4 text-blue-600" /> },
  'stat-passports': { label: 'Legal passports count', icon: <Shield className="h-4 w-4 text-emerald-600" /> },
  'stat-findings': { label: 'AI findings count', icon: <ListChecks className="h-4 w-4 text-red-600" /> },
  'recent-activity': { label: 'Recent activity feed', icon: <Clock className="h-4 w-4 text-gray-600" /> },
};

const DEFAULT_WIDGETS: WidgetPref[] = [
  { id: 'stat-contracts', visible: true },
  { id: 'stat-passports', visible: true },
  { id: 'stat-findings', visible: true },
  { id: 'recent-activity', visible: true },
];

const KNOWN_WIDGET_IDS = new Set<WidgetId>(['stat-contracts', 'stat-passports', 'stat-findings', 'recent-activity']);

function isValidWidgetList(value: unknown): value is WidgetPref[] {
  if (!Array.isArray(value) || value.length === 0) return false;
  return value.every(
    (entry) =>
      entry &&
      typeof entry === 'object' &&
      typeof (entry as WidgetPref).visible === 'boolean' &&
      KNOWN_WIDGET_IDS.has((entry as WidgetPref).id)
  );
}

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

function shortenEntityId(value?: string | null) {
  if (!value) return 'unknown';
  const trimmed = value.trim();
  if (trimmed.length <= 12) return trimmed;
  return `${trimmed.slice(0, 8)}…${trimmed.slice(-6)}`;
}

function workflowLabel(state: string) {
  return state.replace(/_/g, ' ').toLowerCase();
}

export default function Dashboard() {
  const { currentOrg, loading: orgLoading } = useOrg();
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowInstance[]>([]);
  const [loading, setLoading] = useState(true);

  const [widgets, setWidgets] = useState<WidgetPref[]>(DEFAULT_WIDGETS);
  const [customizeOpen, setCustomizeOpen] = useState(false);
  const customizeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    async function load() {
      // Wait for OrgProvider: a first-paint fetch with no org still called
      // unscoped GET /api/findings (full collection scan). Login lands on
      // /dashboard, so that scan was in flight before the golden-path test
      // navigated to the contract-scoped findings page and blocked it.
      if (orgLoading) return;
      if (!currentOrg?.org_id) {
        setContracts([]);
        setFindings([]);
        setWorkflows([]);
        setLoading(false);
        return;
      }
      setLoading(true);
      try {
        const orgId = currentOrg.org_id;
        const [contractResponse, findingResponse, workflowResponse] = await Promise.all([
          apiFetch('/api/contracts', { signal: controller.signal }),
          apiFetch('/api/findings', { signal: controller.signal }),
          apiFetch(`/api/orgs/${encodeURIComponent(orgId)}/workflow-instances?limit=50`, { signal: controller.signal }),
        ]);
        const nextContracts = contractResponse.ok ? await contractResponse.json() : [];
        const nextFindings = findingResponse.ok ? await findingResponse.json() : [];
        const workflowPayload = workflowResponse.ok ? await workflowResponse.json() : { items: [] };
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
      controller.abort();
    };
  }, [currentOrg?.org_id, orgLoading]);

  // Per-user dashboard widget layout (order + visibility), persisted via the
  // same GET/PATCH /api/preferences/ui endpoint as the theme setting. Loaded
  // once on mount, independent of org (like theme) -- this is a personal
  // layout preference, not an org-scoped setting.
  useEffect(() => {
    let cancelled = false;
    void apiFetch('/api/preferences/ui')
      .then(async (response) => {
        if (!response.ok || cancelled) return;
        const body = await response.json();
        if (isValidWidgetList(body?.dashboard_widgets)) {
          setWidgets(body.dashboard_widgets);
        }
      })
      .catch(() => {
        // Offline / signed out / server down -- the default layout stands.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!customizeOpen) return;
    function onPointerDown(event: MouseEvent) {
      if (customizeRef.current && !customizeRef.current.contains(event.target as Node)) {
        setCustomizeOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setCustomizeOpen(false);
    }
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [customizeOpen]);

  function persistWidgets(next: WidgetPref[]) {
    void apiFetch('/api/preferences/ui', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dashboard_widgets: next }),
    }).catch(() => {
      // Best-effort sync; the local layout already applied regardless.
    });
  }

  function moveWidget(id: WidgetId, direction: -1 | 1) {
    setWidgets((prev) => {
      const index = prev.findIndex((w) => w.id === id);
      const swapIndex = index + direction;
      if (index < 0 || swapIndex < 0 || swapIndex >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[swapIndex]] = [next[swapIndex], next[index]];
      persistWidgets(next);
      return next;
    });
  }

  function toggleWidget(id: WidgetId) {
    setWidgets((prev) => {
      const next = prev.map((w) => (w.id === id ? { ...w, visible: !w.visible } : w));
      persistWidgets(next);
      return next;
    });
  }

  function resetWidgets() {
    setWidgets(DEFAULT_WIDGETS);
    persistWidgets(DEFAULT_WIDGETS);
  }

  const failed = contracts.filter((item) => item.analysis_status === 'failed');
  const passportCount = contracts.filter((item) => item.passport_id).length;

  // Portfolio Risk / Evidence & Verification: derived entirely from the
  // `contracts` array already fetched above (same /api/contracts response
  // dashboard/contracts/page.tsx reads risk_score/risk_level from). No new
  // request, no new business logic -- just a glanceable rollup of data this
  // screen already has in memory.
  const riskScored = contracts.filter((item) => typeof item.risk_score === 'number');
  const avgRiskScore = riskScored.length
    ? Math.round(riskScored.reduce((sum, item) => sum + (item.risk_score ?? 0), 0) / riskScored.length)
    : null;
  const highRiskCount = contracts.filter((item) => {
    const level = (item.risk_level || '').toLowerCase();
    return level === 'high' || level === 'critical';
  }).length;

  // Risk Overview distribution -- same `contracts` array, just bucketed by
  // risk_level for the segmented bar. Same coloring convention as Portfolio
  // Trends' findings-by-severity chart, for one consistent risk-color
  // language across the app.
  const RISK_LEVEL_COLOR: Record<string, string> = {
    critical: '#ef4444',
    high: '#f97316',
    medium: '#fbbf24',
    low: '#94a3b8',
  };
  const riskLevelCounts = (['critical', 'high', 'medium', 'low'] as const).map((level) => ({
    level,
    count: contracts.filter((item) => (item.risk_level || '').toLowerCase() === level).length,
  }));
  const unscoredCount = contracts.length - riskLevelCounts.reduce((sum, item) => sum + item.count, 0);

  // Attention Required -- every item below reads from data this screen
  // already has in memory (contracts, findings, workflows); no new request.
  // "Reviews awaiting approval" uses the same workflow-instance status this
  // page's own Recent Activity feed already reads (`status`), interpreted
  // as "active" meaning the instance has not reached a terminal state --
  // the same status value shown verbatim on the Contract Lifecycle page.
  const criticalHighFindings = findings.filter((item) => {
    const severity = (item.severity || '').toLowerCase();
    return severity === 'critical' || severity === 'high';
  });
  const reviewsAwaiting = workflows.filter((item) => item.status === 'active');
  const contractsWithoutPassport = contracts.filter((item) => !item.passport_id && item.analysis_status !== 'failed');

  const attentionItems: { id: string; label: string; count: number; detail: string; href: string; severity: 'critical' | 'high' | 'medium' }[] = [
    ...(failed.length > 0
      ? [{
          id: 'failed-analysis',
          label: 'Contracts stuck on failed analysis',
          count: failed.length,
          detail: 'AI analysis did not finish -- open the contract to retry.',
          href: '/dashboard/contracts',
          severity: 'critical' as const,
        }]
      : []),
    ...(criticalHighFindings.length > 0
      ? [{
          id: 'high-risk-findings',
          label: 'High or critical-risk findings',
          count: criticalHighFindings.length,
          detail: 'Findings that have not yet moved through review.',
          href: '/dashboard/ai-analysis/findings',
          severity: 'critical' as const,
        }]
      : []),
    ...(reviewsAwaiting.length > 0
      ? [{
          id: 'reviews-awaiting',
          label: 'Reviews awaiting approval',
          count: reviewsAwaiting.length,
          detail: 'Redline proposals with an open approval workflow.',
          href: '/dashboard/contracts/reviews',
          severity: 'high' as const,
        }]
      : []),
    ...(contractsWithoutPassport.length > 0
      ? [{
          id: 'no-passport',
          label: 'Contracts without a Legal Passport yet',
          count: contractsWithoutPassport.length,
          detail: 'No evidence-anchored passport has been created for these.',
          href: '/dashboard/contracts',
          severity: 'medium' as const,
        }]
      : []),
  ];
  const ATTENTION_SEVERITY_CLASSES: Record<'critical' | 'high' | 'medium', string> = {
    critical: 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400',
    high: 'bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-400',
    medium: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400',
  };

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
        title: contract.name || shortenEntityId(contract.contract_id),
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
        detail: `${finding.severity || 'unspecified'} · ${shortenEntityId(finding.contract_id)}`,
        href: `/dashboard/ai-analysis/findings?finding_id=${encodeURIComponent(finding.finding_id)}`,
        at: finding.created_at,
      });
    }
    return items.sort((a, b) => b.at.localeCompare(a.at));
  }, [contracts, findings, workflows]);

  const ACTIVITY_LIMIT = 6;
  const recentActivity = activity.slice(0, ACTIVITY_LIMIT);
  const hasMoreActivity = activity.length > ACTIVITY_LIMIT;

  const statValues: Record<Exclude<WidgetId, 'recent-activity'>, { label: string; value: number | null; href: string; icon: ReactNode; tone: 'blue' | 'emerald' | 'red' }> = {
    'stat-contracts': {
      label: 'Contracts',
      value: loading ? null : contracts.length,
      href: '/dashboard/contracts',
      icon: <FileText className="h-5 w-5 text-blue-600" />,
      tone: 'blue',
    },
    'stat-passports': {
      label: 'Legal passports',
      value: loading ? null : passportCount,
      href: '/legal-passport',
      icon: <Shield className="h-5 w-5 text-emerald-600" />,
      tone: 'emerald',
    },
    'stat-findings': {
      label: 'AI findings',
      value: loading ? null : findings.length,
      href: '/dashboard/ai-analysis/findings',
      icon: <ListChecks className="h-5 w-5 text-red-600" />,
      tone: 'red',
    },
  };

  // Render widgets in the user's chosen order, grouping consecutive visible
  // stat-card widgets into one grid row so the layout still reads cleanly
  // however they're reordered relative to the activity feed.
  const visibleWidgets = widgets.filter((w) => w.visible);
  type Group = { type: 'stats'; ids: Exclude<WidgetId, 'recent-activity'>[] } | { type: 'activity' };
  const groups: Group[] = [];
  for (const widget of visibleWidgets) {
    if (widget.id === 'recent-activity') {
      groups.push({ type: 'activity' });
    } else {
      const last = groups[groups.length - 1];
      if (last && last.type === 'stats') {
        last.ids.push(widget.id);
      } else {
        groups.push({ type: 'stats', ids: [widget.id] });
      }
    }
  }
  const statsGroups = groups.filter((group): group is Extract<Group, { type: 'stats' }> => group.type === 'stats');
  const activityGroups = groups.filter((group) => group.type === 'activity');

  const customizeButton = (
    <div className="relative" ref={customizeRef}>
      <button
        type="button"
        onClick={() => setCustomizeOpen((open) => !open)}
        aria-expanded={customizeOpen}
        aria-label="Customize dashboard widgets"
        className="inline-flex items-center gap-2 rounded-[var(--radius-md,0.5rem)] border border-gray-300 bg-white px-3.5 py-2 text-sm font-medium text-gray-700 shadow-[var(--shadow-xs)] hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary,#2563eb)] dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
      >
        <Settings2 className="h-4 w-4" />
        Customize
      </button>
      {customizeOpen && (
        <div className="absolute right-0 z-20 mt-2 w-80 rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-white p-3 shadow-[var(--shadow-lg)] dark:border-gray-700 dark:bg-gray-800">
          <div className="mb-2 flex items-center justify-between px-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
              Dashboard widgets
            </p>
            <button
              type="button"
              onClick={resetWidgets}
              className="text-xs font-medium text-[var(--brand-primary,#2563eb)] hover:underline"
            >
              Reset
            </button>
          </div>
          <ul className="space-y-1">
            {widgets.map((widget, index) => (
              <li
                key={widget.id}
                className="flex items-center gap-2 rounded-md px-1 py-1.5 hover:bg-gray-50 dark:hover:bg-gray-700/50"
              >
                <div className="flex flex-col">
                  <button
                    type="button"
                    aria-label={`Move ${WIDGET_META[widget.id].label} up`}
                    disabled={index === 0}
                    onClick={() => moveWidget(widget.id, -1)}
                    className="text-gray-400 hover:text-gray-700 disabled:opacity-30 disabled:hover:text-gray-400 dark:hover:text-gray-200"
                  >
                    <ChevronUp className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    aria-label={`Move ${WIDGET_META[widget.id].label} down`}
                    disabled={index === widgets.length - 1}
                    onClick={() => moveWidget(widget.id, 1)}
                    className="text-gray-400 hover:text-gray-700 disabled:opacity-30 disabled:hover:text-gray-400 dark:hover:text-gray-200"
                  >
                    <ChevronDown className="h-3.5 w-3.5" />
                  </button>
                </div>
                {WIDGET_META[widget.id].icon}
                <span className="flex-1 text-sm text-gray-700 dark:text-gray-200">
                  {WIDGET_META[widget.id].label}
                </span>
                <button
                  type="button"
                  aria-label={`${widget.visible ? 'Hide' : 'Show'} ${WIDGET_META[widget.id].label}`}
                  aria-pressed={widget.visible}
                  onClick={() => toggleWidget(widget.id)}
                  className={`rounded p-1 ${widget.visible ? 'text-[var(--brand-primary,#2563eb)]' : 'text-gray-300 dark:text-gray-600'}`}
                >
                  {widget.visible ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Workspace"
        title="Dashboard"
        description="Live activity for this organization — contracts, findings, and passports."
        actions={customizeButton}
      />

      <div className="mt-6 space-y-6">
        {statsGroups.length > 0 && (
          <div className="space-y-6">
            {statsGroups.map((group, groupIndex) => (
              <div key={`stats-${groupIndex}`}>
                <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Key Metrics</h2>
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
                  {group.ids.map((id) => {
                    const stat = statValues[id];
                    return (
                      <StatCard
                        key={id}
                        label={stat.label}
                        value={stat.value}
                        href={stat.href}
                        icon={stat.icon}
                        tone={stat.tone}
                      />
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        {!loading && attentionItems.length > 0 && (
          <Card className="border-red-200 dark:border-red-900/50">
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle className="flex items-center gap-2 text-base text-red-800 dark:text-red-400">
                <AlertOctagon className="h-4 w-4" />
                Attention Required
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {attentionItems.map((item) => (
                <Link
                  key={item.id}
                  href={item.href}
                  className="flex items-center justify-between gap-3 rounded-[var(--radius-md,0.5rem)] border border-gray-100 p-3 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-700/40"
                >
                  <div className="flex items-center gap-3">
                    <span className={`inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-sm font-bold tabular-nums ${ATTENTION_SEVERITY_CLASSES[item.severity]}`}>
                      {item.count}
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{item.label}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{item.detail}</p>
                    </div>
                  </div>
                  <ArrowRight className="h-4 w-4 flex-shrink-0 text-gray-400" />
                </Link>
              ))}
            </CardContent>
          </Card>
        )}

        {!loading && contracts.length > 0 && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Gauge className="h-4 w-4 text-red-600" />
                  Risk Overview
                </CardTitle>
                <Link href="/dashboard/contracts" className="text-xs font-medium text-[var(--brand-primary,#2563eb)] hover:underline">
                  View contracts
                </Link>
              </CardHeader>
              <CardContent>
                <div className="flex items-end justify-between gap-4">
                  <div>
                    <p className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                      {avgRiskScore === null ? '—' : avgRiskScore}
                    </p>
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Average risk score across scored contracts</p>
                  </div>
                  <p className="whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                    <span className="font-semibold text-gray-900 dark:text-gray-100">{highRiskCount}</span>{' '}
                    {highRiskCount === 1 ? 'contract is' : 'contracts are'} high or critical risk
                  </p>
                </div>
                {contracts.length > 0 && (
                  <div className="mt-4">
                    <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700">
                      {riskLevelCounts.filter((item) => item.count > 0).map((item) => (
                        <div
                          key={item.level}
                          style={{ width: `${(item.count / contracts.length) * 100}%`, backgroundColor: RISK_LEVEL_COLOR[item.level] }}
                          title={`${item.level}: ${item.count}`}
                        />
                      ))}
                      {unscoredCount > 0 && (
                        <div
                          className="bg-gray-200 dark:bg-gray-600"
                          style={{ width: `${(unscoredCount / contracts.length) * 100}%` }}
                          title={`Not yet scored: ${unscoredCount}`}
                        />
                      )}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                      {riskLevelCounts.filter((item) => item.count > 0).map((item) => (
                        <span key={item.level} className="flex items-center gap-1.5">
                          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: RISK_LEVEL_COLOR[item.level] }} />
                          {item.level.charAt(0).toUpperCase() + item.level.slice(1)}: {item.count}
                        </span>
                      ))}
                      {unscoredCount > 0 && (
                        <span className="flex items-center gap-1.5">
                          <span className="h-2 w-2 rounded-full bg-gray-300 dark:bg-gray-600" />
                          Not yet scored: {unscoredCount}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Anchor className="h-4 w-4 text-purple-600" />
                  Evidence &amp; Verification
                </CardTitle>
                <Link href="/legal-passport" className="text-xs font-medium text-[var(--brand-primary,#2563eb)] hover:underline">
                  Open passports
                </Link>
              </CardHeader>
              <CardContent>
                <div className="flex items-end justify-between gap-4">
                  <div>
                    <p className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                      {passportCount}/{contracts.length}
                    </p>
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Contracts with an evidence-anchored Legal Passport</p>
                  </div>
                  <p className="whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                    {contracts.length - passportCount} awaiting a passport
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {groups.length === 0 && (
          <div className="rounded-[var(--radius-lg,0.75rem)] border border-dashed border-gray-300 p-6 text-center dark:border-gray-700">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              All dashboard widgets are hidden. Use Customize above to bring one back.
            </p>
          </div>
        )}

        {activityGroups.length > 0 && activityGroups.map((group, groupIndex) => (
          <Card key={`activity-${groupIndex}`}>
            <CardHeader>
              <CardTitle>Recent Activity</CardTitle>
            </CardHeader>
            <CardContent>
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
                  {recentActivity.map((item) => (
                    <Link
                      key={item.id}
                      href={item.href}
                      className="flex items-center justify-between rounded-[var(--radius-md,0.5rem)] bg-gray-50 p-4 hover:bg-blue-50 dark:bg-gray-700/50 dark:hover:bg-blue-900/30"
                    >
                      <div>
                        <p className="font-medium text-gray-900 dark:text-gray-100">{item.title}</p>
                        <p className="text-sm text-gray-600 dark:text-gray-400">{item.detail}</p>
                      </div>
                      <span className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                        {relativeTime(item.at)}
                        <ArrowRight className="h-4 w-4" />
                      </span>
                    </Link>
                  ))}
                  {hasMoreActivity && (
                    <Link
                      href="/dashboard/contracts"
                      className="inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand-primary,#2563eb)] hover:underline"
                    >
                      View all activity →
                    </Link>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </PageContainer>
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
    blue: 'bg-blue-50 dark:bg-blue-950',
    emerald: 'bg-emerald-50 dark:bg-emerald-950',
    red: 'bg-red-50 dark:bg-red-950',
  }
  return (
    <Link
      href={href}
      className="block rounded-[var(--radius-lg,0.75rem)] border border-gray-200 bg-white p-6 shadow-[var(--shadow-sm)] transition-shadow duration-[var(--duration-base,200ms)] hover:shadow-[var(--shadow-md)] dark:border-gray-700 dark:bg-gray-800"
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-600 dark:text-gray-400">{label}</p>
          {value === null ? <Skeleton className="mt-2 h-9 w-16" /> : <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-gray-100">{value}</p>}
        </div>
        <div className={`${tones[tone]} rounded-full p-3`}>{icon}</div>
      </div>
    </Link>
  )
}
