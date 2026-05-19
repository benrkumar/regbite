'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, ClipboardCheck } from 'lucide-react';
import { ComplianceScoreBadge } from '@/components/compliance-score-badge';

interface CGMPAuditSummary {
  id: string;
  title: string;
  overallScore: number | null;
  completedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export default function CGMPListPage() {
  const router = useRouter();
  const [audits, setAudits] = useState<CGMPAuditSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/cgmp')
      .then((r) => r.json())
      .then((d) => setAudits(d.audits ?? []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">cGMP Readiness</h1>
          <p className="mt-1 text-sm text-gray-500">
            Assess your manufacturing operations against 21 CFR Part 111 — FDA&apos;s Current Good Manufacturing
            Practice for dietary supplements.
          </p>
        </div>
        <button
          onClick={() => router.push('/cgmp/new')}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          <Plus className="h-4 w-4" />
          New Audit
        </button>
      </div>

      {loading ? (
        <div className="text-sm text-gray-500">Loading…</div>
      ) : audits.length === 0 ? (
        <div className="rounded-lg border bg-gray-50 px-6 py-16 text-center">
          <ClipboardCheck className="mx-auto mb-3 h-10 w-10 text-gray-300" />
          <p className="font-medium text-gray-700">No cGMP audits yet</p>
          <p className="mt-1 text-sm text-gray-500 mb-4">
            Run your first readiness assessment against 21 CFR Part 111.
          </p>
          <button
            onClick={() => router.push('/cgmp/new')}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            <Plus className="h-4 w-4" />
            Start Audit
          </button>
        </div>
      ) : (
        <div className="rounded-lg border bg-white divide-y">
          {audits.map((audit) => (
            <button
              key={audit.id}
              onClick={() => router.push(`/cgmp/${audit.id}`)}
              className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-50 transition-colors"
            >
              <div>
                <p className="font-medium text-gray-900">{audit.title}</p>
                <p className="mt-0.5 text-xs text-gray-500">
                  Updated {new Date(audit.updatedAt).toLocaleDateString()}
                  {audit.completedAt && ` · Completed ${new Date(audit.completedAt).toLocaleDateString()}`}
                </p>
              </div>
              <div className="flex items-center gap-3">
                {audit.overallScore != null ? (
                  <ComplianceScoreBadge score={audit.overallScore} size="sm" />
                ) : (
                  <span className="rounded px-2 py-0.5 text-xs font-semibold bg-gray-100 text-gray-600">
                    In Progress
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
