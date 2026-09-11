'use client';

import { useRouter } from 'next/navigation';
import { ShieldAlert } from 'lucide-react';
import { PageHeader } from '../../../../../components/ui/page-header';
import { PageContainer } from '../../../../../components/ui/container';
import { EmptyState } from '../../../../../components/EmptyState';

// Phase 4: wrapped in the shared PageContainer/PageHeader/EmptyState. Not
// part of the current build -- affected-contract impact tracking lives on
// the Compliance Command Center today.
export default function ComplianceViolations() {
  const router = useRouter();
  return (
    <PageContainer>
      <PageHeader eyebrow="Compliance" title="Compliance Violations" description="View and manage compliance violations." />
      <div className="mt-6">
        <EmptyState
          icon={<ShieldAlert className="h-6 w-6" />}
          title="Not part of the current build"
          description="Affected-contract impact tracking for regulatory changes is available today on the Compliance Command Center."
          actionLabel="Go to Compliance Command Center"
          onAction={() => router.push('/compliance-command-center')}
        />
      </div>
    </PageContainer>
  );
}
