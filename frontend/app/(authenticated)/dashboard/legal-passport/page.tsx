'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function LegalPassport() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/legal-passport');
  }, [router]);

  return <p className="text-gray-600">Opening Legal Passport…</p>;
}
