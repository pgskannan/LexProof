'use client';

import { useRouter } from 'next/navigation';
import { Gauge } from 'lucide-react';
import { PageHeader } from '../../../../../components/ui/page-header';
import { PageContainer } from '../../../../../components/ui/container';
import { EmptyState } from '../../../../../components/EmptyState';

// Phase 4: wrapped in the shared PageContainer/PageHeader/EmptyState. Not
// part of the current build -- portfolio-wide risk is available today on
// the Dashboard's Risk Overview, and per-contract risk on Reports.
export default function RiskAnalysis() {
  const router = useRouter();
  return (
    <PageContainer>
      <PageHeader eyebrow="AI Analysis" title="Risk Analysis" description="Detailed risk assessment for all contracts." />
      <div className="mt-6">
        <EmptyState
          icon={<Gauge className="h-6 w-6" />}
          title="Not part of the current build"
          description="Portfolio-wide risk is available today on the Dashboard's Risk Overview, and per-contract risk detail on Reports."
          actionLabel="Go to Dashboard"
          onAction={() => router.push('/dashboard')}
        />
      </div>
    </PageContainer>
  );
}
