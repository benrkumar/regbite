'use client';

import { useState } from 'react';
import { AlertTriangle, CheckCircle, ShieldAlert, Info, Copy, Check } from 'lucide-react';
import { CheckResultList } from '@/components/check-result-card';
import { ComplianceScoreBadge } from '@/components/compliance-score-badge';

type Classification = 'STRUCTURE_FUNCTION' | 'DISEASE' | 'HEALTH' | 'NUTRIENT_CONTENT';
type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

interface ClaimResult {
  claim: string;
  classification: Classification;
  isCompliant: boolean;
  riskLevel: RiskLevel;
  requiredDisclaimer?: string;
  ftcSubstantiationRequired: boolean;
  suggestedRewrite?: string;
  checks: {
    ruleId: string;
    ruleName: string;
    status: string;
    severity: string;
    message: string;
    remediation?: string;
    regulatoryCitation?: string;
  }[];
}

const CLASSIFICATION_META: Record<Classification, { label: string; color: string; icon: React.ReactNode; description: string }> = {
  DISEASE: {
    label: 'Disease Claim',
    color: 'bg-red-100 text-red-800 border-red-200',
    icon: <ShieldAlert className="h-4 w-4" />,
    description: 'This claim implies the product diagnoses, treats, cures, or prevents a disease — which makes it an unapproved drug under the FD&C Act.',
  },
  STRUCTURE_FUNCTION: {
    label: 'Structure/Function',
    color: 'bg-green-100 text-green-800 border-green-200',
    icon: <CheckCircle className="h-4 w-4" />,
    description: 'Describes how a nutrient affects normal body structure or function. Permitted for dietary supplements with the required FDA disclaimer.',
  },
  HEALTH: {
    label: 'Health Claim',
    color: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    icon: <AlertTriangle className="h-4 w-4" />,
    description: 'Relates a nutrient to a disease or health condition. Must be pre-authorized by FDA or qualify as a qualified health claim.',
  },
  NUTRIENT_CONTENT: {
    label: 'Nutrient Content',
    color: 'bg-blue-100 text-blue-800 border-blue-200',
    icon: <Info className="h-4 w-4" />,
    description: 'Characterizes the level of a nutrient in the product (e.g., "high in Vitamin C"). Must meet FDA definitions for the descriptor used.',
  },
};

const RISK_BADGE: Record<RiskLevel, string> = {
  LOW: 'bg-green-100 text-green-700',
  MEDIUM: 'bg-yellow-100 text-yellow-700',
  HIGH: 'bg-orange-100 text-orange-700',
  CRITICAL: 'bg-red-100 text-red-700',
};

const EXAMPLE_CLAIMS = [
  'Supports healthy immune function',
  'Cures diabetes naturally',
  'Promotes cardiovascular health',
  'Clinically proven to treat arthritis',
  'Helps maintain healthy blood sugar levels already within normal range',
  'Prevents Alzheimer\'s disease',
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={copy} className="ml-2 text-gray-400 hover:text-gray-700 flex-shrink-0" title="Copy">
      {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

export default function ClaimsCheckerPage() {
  const [claim, setClaim] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ClaimResult | null>(null);
  const [error, setError] = useState('');

  const validate = async (text: string) => {
    if (!text.trim() || text.trim().length < 3) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await fetch('/api/claims/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ claim: text.trim() }),
      });
      const data = await res.json();
      if (!res.ok) { setError('Validation failed — please try again.'); return; }
      setResult(data.result);
    } catch {
      setError('Network error — please try again.');
    } finally {
      setLoading(false);
    }
  };

  const meta = result ? CLASSIFICATION_META[result.classification] : null;

  return (
    <div className="max-w-3xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Claims Checker</h1>
        <p className="mt-1 text-sm text-gray-500">
          Validate product claims against FDA structure/function rules (21 CFR § 101.93) and FTC
          substantiation requirements. Detect disease claims before they reach market.
        </p>
      </div>

      {/* Input */}
      <div className="rounded-lg border bg-white p-5 space-y-3">
        <label className="block text-sm font-medium text-gray-700">
          Enter a product claim
        </label>
        <textarea
          rows={3}
          value={claim}
          onChange={(e) => setClaim(e.target.value)}
          placeholder="e.g. Supports healthy immune function and promotes energy levels"
          className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <div className="flex items-center justify-between">
          <div className="flex flex-wrap gap-1.5">
            {EXAMPLE_CLAIMS.map((ex) => (
              <button
                key={ex}
                onClick={() => { setClaim(ex); validate(ex); }}
                className="rounded-full border bg-gray-50 px-2.5 py-0.5 text-xs text-gray-600 hover:border-brand-400 hover:text-brand-600 text-left"
              >
                {ex.length > 40 ? ex.slice(0, 38) + '…' : ex}
              </button>
            ))}
          </div>
          <button
            onClick={() => validate(claim)}
            disabled={loading || claim.trim().length < 3}
            className="ml-4 flex-shrink-0 rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {loading ? 'Checking…' : 'Analyze'}
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-4 rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Results */}
      {result && meta && (
        <div className="mt-6 space-y-4">
          {/* Classification header */}
          <div className={`rounded-lg border px-5 py-4 ${meta.color}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-semibold">
                {meta.icon}
                {meta.label}
              </div>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${RISK_BADGE[result.riskLevel]}`}>
                {result.riskLevel} RISK
              </span>
            </div>
            <p className="mt-1.5 text-sm opacity-80">{meta.description}</p>
          </div>

          {/* Claim being analyzed */}
          <div className="rounded-lg border bg-white p-4">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Analyzed claim</p>
            <p className="text-sm text-gray-800 italic">&ldquo;{result.claim}&rdquo;</p>
          </div>

          {/* Suggested rewrite */}
          {result.suggestedRewrite && (
            <div className="rounded-lg border border-green-200 bg-green-50 p-4">
              <div className="flex items-center justify-between mb-1">
                <p className="text-xs font-semibold text-green-800 uppercase tracking-wide">Suggested compliant rewrite</p>
                <CopyButton text={result.suggestedRewrite} />
              </div>
              <p className="text-sm text-green-900 italic">&ldquo;{result.suggestedRewrite}&rdquo;</p>
            </div>
          )}

          {/* Required disclaimer */}
          {result.requiredDisclaimer && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
              <div className="flex items-center justify-between mb-1">
                <p className="text-xs font-semibold text-blue-800 uppercase tracking-wide">
                  Required FDA disclaimer (21 CFR § 101.93(b))
                </p>
                <CopyButton text={result.requiredDisclaimer} />
              </div>
              <p className="text-sm text-blue-900">{result.requiredDisclaimer}</p>
            </div>
          )}

          {/* Check results */}
          <div>
            <h2 className="mb-3 text-base font-semibold text-gray-900">Compliance Checks</h2>
            <CheckResultList checks={result.checks as Parameters<typeof CheckResultList>[0]['checks']} />
          </div>
        </div>
      )}
    </div>
  );
}
