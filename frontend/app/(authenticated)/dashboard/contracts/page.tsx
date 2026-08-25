'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { apiFetch } from '../../../../lib/api';

export default function AllContracts() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  async function uploadAndAnalyze() {
    if (!file) return setMessage('Choose a PDF, DOCX, or TXT contract.');
    setBusy(true); setMessage('Uploading contract...');
    try {
      const form = new FormData();
      form.append('file', file);
      const upload = await apiFetch('/api/contracts', { method: 'POST', body: form });
      if (!upload.ok) throw new Error((await upload.json()).detail || 'Upload failed');
      const created = await upload.json();
      setMessage('Contract uploaded. Running Gemini analysis...');
      const analysis = await apiFetch(`/api/contracts/${created.contract_id}/analyze`, { method: 'POST' });
      if (!analysis.ok) throw new Error((await analysis.json()).detail || 'Analysis failed');
      const passport = await analysis.json();
      router.push(`/legal-passport?contractId=${encodeURIComponent(created.contract_id)}&contractVersion=1`);
      setMessage(`Analysis complete. Passport ${passport.passport_id} created.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Contract flow failed');
    } finally { setBusy(false); }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">All Contracts</h1>
        <p className="text-gray-600 mt-2">View and manage all contracts in the system</p>
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold text-gray-900">Analyze a contract</h2>
        <p className="mt-2 text-gray-600">Upload a fictional contract to generate findings and a legal passport.</p>
        <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-center">
          <input type="file" accept=".pdf,.docx,.txt" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          <button onClick={uploadAndAnalyze} disabled={busy} className="rounded bg-blue-600 px-5 py-3 font-medium text-white disabled:opacity-50">
            {busy ? 'Processing...' : 'Upload and analyze'}
          </button>
        </div>
        {message && <p role="status" className="mt-4 text-sm text-gray-600">{message}</p>}
      </div>
    </div>
  );
}
