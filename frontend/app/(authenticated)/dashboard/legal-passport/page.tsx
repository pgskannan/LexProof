'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function LegalPassport() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/dashboard/contracts');
  }, [router]);

  return <p className="text-gray-600">Opening your contracts…</p>;
}
