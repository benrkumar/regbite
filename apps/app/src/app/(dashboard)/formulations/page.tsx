'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, FlaskConical } from 'lucide-react';
import { ComplianceScoreBadge } from '@/components/compliance-score-badge';

interface Formulation {
  id: string;
  productName: string;
  productType: string;
  status: string;
  complianceScore: number | null;
  updatedAt: string;
}

const STATUS_STYLES: Record<string, string> = {
  DRAFT: 'bg-gray-100 text-gray-600',
  UNDER_REVIEW: 'bg-yellow-100 text-yellow-800',
  COMPLIANT: 'bg-green-100 text-green-800',
  NON_COMPLIANT: 'bg-red-100 text-red-800',
  ARCHIVED: 'bg-gray-100 text-gray-400',
};

export default function FormulationsPage() {
  const router = useRouter();
  const [formulations, setFormulations] = useState<Formulation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/formulations')
      .then((r) => r.json())
      .then((d) => setFormulations(d.formulations ?? []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Formulations</h1>
          <p className="mt-1 text-sm text-gray-500">
            Create and manage supplement formulations. Run compliance checks for FDA/DSHEA analysis.
          </p>
        </div>
        <button
          onClick={() => router.push('/formulations/new')}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          <Plus className="h-4 w-4" />
          New Formulation
        </button>
      </div>

      {loading ? (
        <div className="text-sm text-gray-500">Loading...</div>
      ) : formulations.length === 0 ? (
        <div className="rounded-lg border bg-gray-50 px-6 py-16 text-center">
          <FlaskConical className="mx-auto mb-3 h-10 w-10 text-gray-300" />
          <p className="font-medium text-gray-700">No formulations yet</p>
          <p className="mt-1 text-sm text-gray-500 mb-4">
            Create your first formulation to run an FDA compliance check.
          </p>
          <button
            onClick={() => router.push('/formulations/new')}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            <Plus className="h-4 w-4" />
            Create Formulation
          </button>
        </div>
      ) : (
        <div className="rounded-lg border bg-white divide-y">
          {formulations.map((f) => (
            <button
              key={f.id}
              onClick={() => router.push(`/formulations/${f.id}`)}
              className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-50 transition-colors"
            >
              <div>
                <p className="font-medium text-gray-900">{f.productName}</p>
                <p className="mt-0.5 text-xs text-gray-500">
                  {f.productType.replace(/_/g, ' ')} · Updated {new Date(f.updatedAt).toLocaleDateString()}
                </p>
              </div>
              <div className="flex items-center gap-3">
                {f.complianceScore != null && (
                  <ComplianceScoreBadge score={f.complianceScore} size="sm" />
                )}
                <span className={`rounded px-2 py-0.5 text-xs font-semibold ${STATUS_STYLES[f.status] ?? STATUS_STYLES.DRAFT}`}>
                  {f.status.replace(/_/g, ' ')}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
