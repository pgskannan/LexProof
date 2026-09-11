'use client';

import { useRouter } from 'next/navigation';
import { FileSearch } from 'lucide-react';
import { PageHeader } from '../../../../../components/ui/page-header';
import { PageContainer } from '../../../../../components/ui/container';
import { EmptyState } from '../../../../../components/EmptyState';

// Phase 4: wrapped in the shared PageContainer/PageHeader/EmptyState
// instead of a raw placeholder div. This view is not part of the current
// build -- clause-level detail lives on the Findings &amp; Redlines screen
// today, which this links to rather than showing a vague "coming soon".
export default function ClauseAnalysis() {
  const router = useRouter();
  return (
    <PageContainer>
      <PageHeader eyebrow="AI Analysis" title="Clause Analysis" description="Detailed clause-by-clause analysis." />
      <div className="mt-6">
        <EmptyState
          icon={<FileSearch className="h-6 w-6" />}
          title="Not part of the current build"
          description="Clause-level detail is available today on the Findings & Redlines screen, grouped by finding rather than a standalone clause browser."
          actionLabel="Go to Findings & Redlines"
          onAction={() => router.push('/dashboard/ai-analysis/findings')}
        />
      </div>
    </PageContainer>
  );
}
