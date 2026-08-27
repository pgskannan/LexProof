'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function BlockchainProof() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/dashboard/verification');
  }, [router]);

  return <p className="text-gray-600">Opening verification…</p>;
}
