'use client';

import { useRouter } from 'next/navigation';
import { Activity } from 'lucide-react';
import { PageHeader } from '../../../../../components/ui/page-header';
import { PageContainer } from '../../../../../components/ui/container';
import { EmptyState } from '../../../../../components/EmptyState';

// Phase 4: wrapped in the shared PageContainer/PageHeader/EmptyState. Not
// part of the current build -- live regulatory monitoring events are
// available today on the Compliance Command Center.
export default function ComplianceMonitoring() {
  const router = useRouter();
  return (
    <PageContainer>
      <PageHeader eyebrow="Compliance" title="Compliance Monitoring" description="Continuous compliance monitoring dashboard." />
      <div className="mt-6">
        <EmptyState
          icon={<Activity className="h-6 w-6" />}
          title="Not part of the current build"
          description="Live regulatory-change monitoring is available today on the Compliance Command Center."
          actionLabel="Go to Compliance Command Center"
          onAction={() => router.push('/compliance-command-center')}
        />
      </div>
    </PageContainer>
  );
}
