'use client';

import { useRouter } from 'next/navigation';
import { ScrollText } from 'lucide-react';
import { PageHeader } from '../../../../../components/ui/page-header';
import { PageContainer } from '../../../../../components/ui/container';
import { EmptyState } from '../../../../../components/EmptyState';

// Phase 4: wrapped in the shared PageContainer/PageHeader/EmptyState. Not
// part of the current build -- playbook policy positions are configured
// today from Organization Settings, and regulation citations appear on the
// Regulation Map.
export default function CompliancePolicies() {
  const router = useRouter();
  return (
    <PageContainer>
      <PageHeader eyebrow="Compliance" title="Compliance Policies" description="Manage compliance policies and rules." />
      <div className="mt-6">
        <EmptyState
          icon={<ScrollText className="h-6 w-6" />}
          title="Not part of the current build"
          description="Playbook policy positions are configured today from Organization Settings; regulation-level citations appear on the Regulation Map."
          actionLabel="Go to Regulation Map"
          onAction={() => router.push('/dashboard/compliance/regulations')}
        />
      </div>
    </PageContainer>
  );
}
