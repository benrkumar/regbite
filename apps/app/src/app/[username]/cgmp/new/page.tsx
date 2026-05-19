'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

export default function NewCGMPAuditPage() {
  const router = useRouter();
  const [title, setTitle] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const handleCreate = async () => {
    if (!title.trim()) { setError('Audit title is required'); return; }
    setCreating(true);
    setError('');
    try {
      const res = await fetch('/api/cgmp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title.trim() }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.error?.message ?? 'Failed to create audit'); return; }
      router.push(`/cgmp/${data.audit.id}`);
    } catch {
      setError('Network error — please try again.');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="max-w-2xl">
      <Link href="/cgmp" className="mb-6 inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900">
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to audits
      </Link>

      <h1 className="mb-6 text-2xl font-bold text-gray-900">New cGMP Audit</h1>

      <div className="rounded-lg border bg-white p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Audit Title *</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Q2 2026 cGMP Readiness Assessment"
            className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        <div className="rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 text-sm text-blue-800">
          <p className="font-semibold mb-1">What this audit covers</p>
          <ul className="space-y-0.5 list-disc list-inside text-blue-700">
            <li>Personnel qualifications (21 CFR §§ 111.12–111.16)</li>
            <li>Physical plant &amp; grounds (21 CFR §§ 111.15–111.20)</li>
            <li>Equipment &amp; utensils (21 CFR §§ 111.25–111.35)</li>
            <li>Production &amp; process controls (21 CFR §§ 111.55–111.140)</li>
            <li>Laboratory operations (21 CFR §§ 111.303–111.325)</li>
            <li>Records &amp; recordkeeping (21 CFR §§ 111.375–111.415)</li>
            <li>Complaints &amp; adverse events (21 CFR §§ 111.553–111.570)</li>
          </ul>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        <div className="flex justify-end gap-3">
          <Link href="/cgmp" className="rounded-lg border px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
            Cancel
          </Link>
          <button
            onClick={handleCreate}
            disabled={creating}
            className="rounded-lg bg-brand-600 px-6 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {creating ? 'Creating…' : 'Start Audit'}
          </button>
        </div>
      </div>
    </div>
  );
}
