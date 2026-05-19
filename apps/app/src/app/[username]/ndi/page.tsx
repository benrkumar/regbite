'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Search, CheckCircle, AlertTriangle, ShieldAlert, BookOpen, ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';
import { CheckResultList } from '@/components/check-result-card';

type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

interface NDIChecklistStep {
  stepNumber: number;
  title: string;
  description: string;
  status: 'REQUIRED' | 'OPTIONAL' | 'N_A';
  resourceUrl?: string;
  citation?: string;
}

interface NDIResult {
  ingredientName: string;
  notificationRequired: boolean;
  eligibilityReason: string;
  riskLevel: RiskLevel;
  checks: {
    ruleId: string;
    ruleName: string;
    status: string;
    severity: string;
    message: string;
    remediation?: string;
    regulatoryCitation?: string;
  }[];
  submissionChecklist: NDIChecklistStep[];
  estimatedReviewDays: number;
  keyFacts: string[];
}

const RISK_BADGE: Record<RiskLevel, string> = {
  LOW: 'bg-green-100 text-green-800',
  MEDIUM: 'bg-yellow-100 text-yellow-800',
  HIGH: 'bg-orange-100 text-orange-800',
  CRITICAL: 'bg-red-100 text-red-800',
};

const RISK_ICON: Record<RiskLevel, React.ReactNode> = {
  LOW: <CheckCircle className="h-5 w-5 text-green-500" />,
  MEDIUM: <AlertTriangle className="h-5 w-5 text-yellow-500" />,
  HIGH: <AlertTriangle className="h-5 w-5 text-orange-500" />,
  CRITICAL: <ShieldAlert className="h-5 w-5 text-red-500" />,
};

function ChecklistStep({ step, index }: { step: NDIChecklistStep; index: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`rounded-lg border bg-white ${step.status === 'OPTIONAL' ? 'opacity-80' : ''}`}>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
      >
        <span className={`flex-shrink-0 flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
          step.status === 'REQUIRED' ? 'bg-brand-600 text-white' : 'bg-gray-200 text-gray-600'
        }`}>
          {index + 1}
        </span>
        <span className="flex-1 text-sm font-medium text-gray-900">{step.title}</span>
        {step.status === 'OPTIONAL' && (
          <span className="text-xs text-gray-400 mr-2">Optional</span>
        )}
        {open ? <ChevronDown className="h-4 w-4 text-gray-400 flex-shrink-0" /> : <ChevronRight className="h-4 w-4 text-gray-400 flex-shrink-0" />}
      </button>
      {open && (
        <div className="px-4 pb-4 pt-0 border-t">
          <p className="text-sm text-gray-700 mt-3">{step.description}</p>
          {step.citation && (
            <p className="mt-2 text-xs text-gray-500 font-mono">{step.citation}</p>
          )}
          {step.resourceUrl && (
            <a
              href={step.resourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"
            >
              FDA Resource <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      )}
    </div>
  );
}

export default function NDINavigatorPage() {
  const [ingredientName, setIngredientName] = useState('');
  const [casNumber, setCasNumber] = useState('');
  const [preMarketDSHEA, setPreMarketDSHEA] = useState<boolean | null>(null);
  const [hasSafetyStudies, setHasSafetyStudies] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<NDIResult | null>(null);
  const [error, setError] = useState('');

  const assess = async () => {
    if (!ingredientName.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await fetch('/api/ndi/eligibility', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ingredientName: ingredientName.trim(),
          casNumber: casNumber.trim() || undefined,
          preMarketDSHEA: preMarketDSHEA ?? undefined,
          hasSafetyStudies: hasSafetyStudies ?? undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) { setError('Assessment failed — please try again.'); return; }
      setResult(data.result);
    } catch {
      setError('Network error — please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">NDI Navigator</h1>
          <p className="mt-1 text-sm text-gray-500">
            Determine whether your ingredient requires a New Dietary Ingredient (NDI) notification under DSHEA § 8
            and walk through the 15-step FDA submission process.
          </p>
        </div>
        <Link
          href="/ndi/search"
          className="inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          <Search className="h-3.5 w-3.5" />
          Search NDI Database
        </Link>
      </div>

      {/* Input form */}
      <div className="rounded-lg border bg-white p-5 space-y-4 mb-6">
        <h2 className="font-semibold text-gray-800">Ingredient Details</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Ingredient Name *</label>
            <input
              type="text"
              value={ingredientName}
              onChange={(e) => setIngredientName(e.target.value)}
              placeholder="e.g. Ashwagandha Extract, 5-HTP"
              className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">CAS Number (optional)</label>
            <input
              type="text"
              value={casNumber}
              onChange={(e) => setCasNumber(e.target.value)}
              placeholder="e.g. 7695-91-2"
              className="w-full rounded-md border px-3 py-2 text-sm font-mono focus:border-brand-500 focus:outline-none"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Was this ingredient marketed in the US before October 15, 1994?
            </label>
            <div className="flex gap-3">
              {([true, false, null] as const).map((val) => (
                <button
                  key={String(val)}
                  onClick={() => setPreMarketDSHEA(val)}
                  className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                    preMarketDSHEA === val
                      ? 'bg-brand-600 text-white border-brand-600'
                      : 'text-gray-600 hover:border-gray-400'
                  }`}
                >
                  {val === true ? 'Yes' : val === false ? 'No' : "Don't know"}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Do you have safety studies (toxicology, clinical)?
            </label>
            <div className="flex gap-3">
              {([true, false, null] as const).map((val) => (
                <button
                  key={String(val)}
                  onClick={() => setHasSafetyStudies(val)}
                  className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                    hasSafetyStudies === val
                      ? 'bg-brand-600 text-white border-brand-600'
                      : 'text-gray-600 hover:border-gray-400'
                  }`}
                >
                  {val === true ? 'Yes' : val === false ? 'No' : "Don't know"}
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        <div className="flex justify-end">
          <button
            onClick={assess}
            disabled={loading || !ingredientName.trim()}
            className="rounded-lg bg-brand-600 px-6 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {loading ? 'Assessing…' : 'Assess NDI Eligibility'}
          </button>
        </div>
      </div>

      {/* Results */}
      {result && (
        <div className="space-y-6">
          {/* Eligibility banner */}
          <div className={`rounded-lg border p-5 ${
            result.notificationRequired ? 'border-orange-200 bg-orange-50' : 'border-green-200 bg-green-50'
          }`}>
            <div className="flex items-start gap-3">
              {RISK_ICON[result.riskLevel]}
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <p className="font-semibold text-gray-900">
                    {result.notificationRequired ? 'NDI Notification Required' : 'No NDI Notification Required'}
                  </p>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${RISK_BADGE[result.riskLevel]}`}>
                    {result.riskLevel} RISK
                  </span>
                  {result.notificationRequired && (
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-800">
                      {result.estimatedReviewDays}-day wait
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-700">{result.eligibilityReason}</p>
              </div>
            </div>
          </div>

          {/* Key facts */}
          {result.keyFacts.length > 0 && (
            <div className="rounded-lg border bg-white p-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                <BookOpen className="h-4 w-4" /> Key Facts
              </h3>
              <ul className="space-y-1.5">
                {result.keyFacts.map((fact, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                    <span className="mt-1 h-1.5 w-1.5 rounded-full bg-gray-400 flex-shrink-0" />
                    {fact}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Compliance checks */}
          <div>
            <h2 className="mb-3 text-base font-semibold text-gray-900">Compliance Assessment</h2>
            <CheckResultList checks={result.checks as Parameters<typeof CheckResultList>[0]['checks']} />
          </div>

          {/* Submission checklist */}
          {result.submissionChecklist.length > 0 && (
            <div>
              <h2 className="mb-3 text-base font-semibold text-gray-900">
                {result.notificationRequired ? 'NDI Submission Checklist (15 steps)' : 'Verification Steps'}
              </h2>
              <div className="space-y-2">
                {result.submissionChecklist.map((step, i) => (
                  <ChecklistStep key={step.stepNumber} step={step} index={i} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
