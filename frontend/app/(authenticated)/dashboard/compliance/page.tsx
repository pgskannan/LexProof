'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function Compliance() {
  const router = useRouter();
  useEffect(() => router.replace('/compliance-command-center'), [router]);
  return <p className="text-gray-600">Opening Compliance Command Center...</p>;
}
