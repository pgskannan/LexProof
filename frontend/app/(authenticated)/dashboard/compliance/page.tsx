'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Skeleton } from '../../../../components/ui/skeleton';

export default function Compliance() {
  const router = useRouter();
  useEffect(() => router.replace('/compliance-command-center'), [router]);
  return (
    <div className="space-y-4 p-8">
      <Skeleton className="h-10 w-72" />
      <Skeleton className="h-40 w-full" />
    </div>
  );
}
