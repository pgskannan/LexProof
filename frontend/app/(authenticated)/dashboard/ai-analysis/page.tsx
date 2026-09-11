'use client';

import Link from 'next/link';
import { PageHeader } from '../../../../components/ui/page-header';
import { PageContainer } from '../../../../components/ui/container';
import { Card, CardContent } from '../../../../components/ui/card';

// This index route has no content of its own -- the real AI-analysis
// screens are Findings, Clauses, and Risk (see the links below). Phase 4:
// wrapped in the shared PageContainer/PageHeader/Card instead of raw divs;
// no behavior change.
export default function AIAnalysis() {
  return (
    <PageContainer>
      <PageHeader eyebrow="AI Analysis" title="AI Analysis" description="AI-powered contract analysis and insights." />
      <div className="mt-6">
        <Card>
          <CardContent className="space-y-2 text-sm">
            <p className="text-gray-500 dark:text-gray-400">Choose a view:</p>
            <div className="flex flex-wrap gap-3">
              <Link href="/dashboard/ai-analysis/findings" className="font-medium text-[var(--brand-primary,#2563eb)] hover:underline">Findings &amp; Redlines</Link>
              <Link href="/dashboard/ai-analysis/clauses" className="font-medium text-[var(--brand-primary,#2563eb)] hover:underline">Clauses</Link>
              <Link href="/dashboard/ai-analysis/risk" className="font-medium text-[var(--brand-primary,#2563eb)] hover:underline">Risk</Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
