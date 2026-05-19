'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Play, RefreshCw } from 'lucide-react';
import { ComplianceScoreBadge } from '@/components/compliance-score-badge';
import { CheckResultList } from '@/components/check-result-card';

interface FormulationDetail {
  id: string;
  productName: string;
  productType: string;
  servingSize: string | null;
  servingsPerContainer: string | null;
  ingredients: { name: string; amount: number; unit: string; casNumber?: string }[];
  claims: string[];
  complianceScore: number | null;
  status: string;
  complianceChecks: {
    id: string;
    checkType: string;
    status: string;
    overallScore: number | null;
    results: unknown;
    createdAt: string;
  }[];
}

export default function FormulationDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [formulation, setFormulation] = useState<FormulationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);

  const load = () => {
    setLoading(true);
    fetch(`/api/formulations/${id}`)
      .then((r) => r.json())
      .then((d) => setFormulation(d.formulation))
      .finally(() => setLoading(false));
  };

  useEffect(load, [id]);

  const runCheck = async () => {
    setChecking(true);
    try {
      await fetch(`/api/formulations/${id}/check`, { method: 'POST' });
      load();
    } finally {
      setChecking(false);
    }
  };

  if (loading) return <div className="text-sm text-gray-500">Loading...</div>;
  if (!formulation) return <div className="text-sm text-red-500">Formulation not found</div>;

  const latestCheck = formulation.complianceChecks[0];
  const checkResults = latestCheck?.results as {
    checks?: unknown[];
    ingredientResults?: unknown[];
    overallScore?: number;
  } | null;

  return (
    <div className="max-w-4xl">
      <Link href="/formulations" className="mb-6 inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900">
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to formulations
      </Link>

      {/* Header */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{formulation.productName}</h1>
          <p className="mt-1 text-sm text-gray-500">
            {formulation.productType.replace(/_/g, ' ')}
            {formulation.servingSize && ` · ${formulation.servingSize}`}
            {formulation.servingsPerContainer && ` · ${formulation.servingsPerContainer} servings`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {formulation.complianceScore != null && (
            <ComplianceScoreBadge score={formulation.complianceScore} />
          )}
          <button
            onClick={runCheck}
            disabled={checking}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {checking ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {checking ? 'Running...' : 'Run Compliance Check'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Ingredients panel */}
        <div className="lg:col-span-1 space-y-4">
          <div className="rounded-lg border bg-white p-4">
            <h3 className="mb-3 text-sm font-semibold text-gray-700 uppercase tracking-wide">
              Ingredients ({formulation.ingredients.length})
            </h3>
            <div className="space-y-1.5">
              {formulation.ingredients.map((ing, i) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <span className="text-gray-800 truncate mr-2">{ing.name}</span>
                  <span className="text-gray-500 flex-shrink-0 font-mono text-xs">
                    {ing.amount} {ing.unit}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {formulation.claims.length > 0 && (
            <div className="rounded-lg border bg-white p-4">
              <h3 className="mb-3 text-sm font-semibold text-gray-700 uppercase tracking-wide">
                Claims ({formulation.claims.length})
              </h3>
              <ul className="space-y-1.5">
                {formulation.claims.map((claim, i) => (
                  <li key={i} className="text-sm text-gray-700 italic">&ldquo;{claim}&rdquo;</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Compliance results */}
        <div className="lg:col-span-2">
          {checkResults?.checks ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-gray-900">Compliance Results</h2>
                {checkResults.overallScore != null && (
                  <ComplianceScoreBadge score={checkResults.overallScore} size="sm" />
                )}
              </div>
              <CheckResultList checks={checkResults.checks as Parameters<typeof CheckResultList>[0]['checks']} />
            </div>
          ) : (
            <div className="rounded-lg border bg-gray-50 px-6 py-16 text-center">
              <Play className="mx-auto mb-3 h-10 w-10 text-gray-300" />
              <p className="font-medium text-gray-700">No compliance check run yet</p>
              <p className="mt-1 text-sm text-gray-500">
                Click &ldquo;Run Compliance Check&rdquo; to analyze this formulation against FDA/DSHEA requirements.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
