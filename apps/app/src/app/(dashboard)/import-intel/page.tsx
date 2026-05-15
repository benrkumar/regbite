'use client';

import { useState } from 'react';
import { AlertTriangle, CheckCircle, ShieldAlert, ChevronDown, ChevronRight } from 'lucide-react';

interface FSVPItem {
  id: string;
  requirement: string;
  description: string;
  citation: string;
  status: 'REQUIRED' | 'CONDITIONAL';
}

interface CheckResult {
  ruleId: string;
  ruleName: string;
  status: 'PASS' | 'FAIL' | 'WARNING' | 'INFO';
  severity: string;
  message: string;
  remediation?: string;
  regulatoryCitation?: string;
}

interface ImportResult {
  supplierCountry: string;
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  checks: CheckResult[];
  fsvpChecklist: FSVPItem[];
  importAlertRisk: boolean;
  keyRequirements: string[];
}

const STATUS_STYLES: Record<string, string> = {
  PASS: 'bg-green-50 border-green-200 text-green-800',
  FAIL: 'bg-red-50 border-red-200 text-red-800',
  WARNING: 'bg-amber-50 border-amber-200 text-amber-800',
  INFO: 'bg-blue-50 border-blue-200 text-blue-800',
};

const RISK_COLORS: Record<string, string> = {
  LOW: 'bg-green-100 text-green-800',
  MEDIUM: 'bg-yellow-100 text-yellow-800',
  HIGH: 'bg-orange-100 text-orange-800',
  CRITICAL: 'bg-red-100 text-red-800',
};

const HIGH_RISK_EXAMPLES = ['China', 'India', 'Brazil', 'Mexico', 'Thailand', 'Vietnam'];

function FSVPChecklist({ items }: { items: FSVPItem[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border bg-white overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-50"
      >
        <div>
          <p className="text-sm font-semibold text-gray-900">FSVP Compliance Checklist</p>
          <p className="text-xs text-gray-500 mt-0.5">{items.length} requirements — 21 CFR Part 1 Subpart L</p>
        </div>
        {open ? <ChevronDown className="h-4 w-4 text-gray-400" /> : <ChevronRight className="h-4 w-4 text-gray-400" />}
      </button>
      {open && (
        <div className="border-t divide-y">
          {items.map((item) => (
            <div key={item.id} className="px-5 py-4">
              <div className="flex items-start gap-3">
                <span className={`flex-shrink-0 mt-0.5 inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                  item.status === 'REQUIRED' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'
                }`}>
                  {item.status}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">{item.requirement}</p>
                  <p className="text-xs text-gray-500 mt-1">{item.description}</p>
                  <p className="text-xs font-mono text-gray-400 mt-1">{item.citation}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ImportIntelPage() {
  const [supplierCountry, setSupplierCountry] = useState('');
  const [supplierName, setSupplierName] = useState('');
  const [ingredientName, setIngredientName] = useState('');
  const [hasFSVPPlan, setHasFSVPPlan] = useState(false);
  const [hasHazardAnalysis, setHasHazardAnalysis] = useState(false);
  const [hasCoA, setHasCoA] = useState(false);
  const [hasSupplierAudit, setHasSupplierAudit] = useState(false);
  const [hasThirdPartyCertification, setHasThirdPartyCertification] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);

  const handleCheck = async () => {
    if (!supplierCountry.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch('/api/import-intel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          supplierCountry: supplierCountry.trim(),
          supplierName: supplierName.trim() || undefined,
          ingredientName: ingredientName.trim() || undefined,
          hasFSVPPlan,
          hasHazardAnalysis,
          hasCoA,
          hasSupplierAudit,
          hasThirdPartyCertification,
        }),
      });
      const data = await res.json();
      if (data.result) setResult(data.result);
    } finally {
      setLoading(false);
    }
  };

  const failCount = result?.checks.filter((c) => c.status === 'FAIL').length ?? 0;
  const warnCount = result?.checks.filter((c) => c.status === 'WARNING').length ?? 0;

  return (
    <div className="max-w-4xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Import Intelligence</h1>
        <p className="mt-1 text-sm text-gray-500">
          FDA Import Alert risk assessment and FSMA Foreign Supplier Verification Program (FSVP) checklist for imported dietary supplement ingredients.
        </p>
      </div>

      <div className="rounded-lg border bg-blue-50 border-blue-200 p-4 mb-6">
        <div className="flex gap-2">
          <AlertTriangle className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-blue-900">FSMA FSVP Required</p>
            <p className="text-sm text-blue-800 mt-0.5">
              All US importers of dietary supplement ingredients must maintain a written Foreign Supplier Verification Program (FSVP) under 21 CFR Part 1 Subpart L.
              High-risk countries ({HIGH_RISK_EXAMPLES.join(', ')}, and others) require enhanced verification including onsite audits.
            </p>
          </div>
        </div>
      </div>

      {/* Input form */}
      <div className="rounded-lg border bg-white p-6 mb-6">
        <h2 className="text-base font-semibold text-gray-900 mb-4">Supplier & Ingredient Details</h2>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Supplier Country <span className="text-red-500">*</span></label>
            <input
              type="text"
              placeholder="e.g., China, India, Germany"
              value={supplierCountry}
              onChange={(e) => setSupplierCountry(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Supplier Name</label>
            <input
              type="text"
              placeholder="e.g., Zhejiang XYZ Biotech Co."
              value={supplierName}
              onChange={(e) => setSupplierName(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div className="col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">Ingredient / Product</label>
            <input
              type="text"
              placeholder="e.g., Vitamin C (ascorbic acid), Astragalus extract"
              value={ingredientName}
              onChange={(e) => setIngredientName(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
        </div>

        <div className="mb-5">
          <p className="text-sm font-medium text-gray-700 mb-2">Current FSVP Status</p>
          <div className="grid grid-cols-2 gap-2">
            {([
              { key: 'hasFSVPPlan', label: 'FSVP plan documented', state: hasFSVPPlan, set: setHasFSVPPlan },
              { key: 'hasHazardAnalysis', label: 'Hazard analysis completed', state: hasHazardAnalysis, set: setHasHazardAnalysis },
              { key: 'hasCoA', label: 'Certificate of Analysis (CoA) on file', state: hasCoA, set: setHasCoA },
              { key: 'hasSupplierAudit', label: 'Supplier audit completed', state: hasSupplierAudit, set: setHasSupplierAudit },
              { key: 'hasThirdPartyCertification', label: 'Third-party certification (ISO 22000 / NSF)', state: hasThirdPartyCertification, set: setHasThirdPartyCertification },
            ] as const).map((item) => (
              <label key={item.key} className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={item.state}
                  onChange={(e) => item.set(e.target.checked)}
                  className="rounded"
                />
                {item.label}
              </label>
            ))}
          </div>
        </div>

        <div className="flex justify-end">
          <button
            onClick={handleCheck}
            disabled={loading || !supplierCountry.trim()}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {loading ? 'Analyzing…' : 'Analyze Import Risk'}
          </button>
        </div>
      </div>

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Risk summary */}
          <div className={`rounded-lg border p-4 flex items-center gap-4 ${
            result.riskLevel === 'CRITICAL' || result.riskLevel === 'HIGH'
              ? 'bg-red-50 border-red-200'
              : result.riskLevel === 'MEDIUM'
              ? 'bg-amber-50 border-amber-200'
              : 'bg-green-50 border-green-200'
          }`}>
            {result.riskLevel === 'LOW' ? (
              <CheckCircle className="h-6 w-6 text-green-600 flex-shrink-0" />
            ) : (
              <ShieldAlert className={`h-6 w-6 flex-shrink-0 ${result.riskLevel === 'MEDIUM' ? 'text-amber-600' : 'text-red-600'}`} />
            )}
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-gray-900">Import Risk: {result.supplierCountry}</p>
                <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${RISK_COLORS[result.riskLevel]}`}>
                  {result.riskLevel}
                </span>
                {result.importAlertRisk && (
                  <span className="inline-block rounded-full px-2.5 py-0.5 text-xs font-medium bg-red-200 text-red-900">
                    Import Alert Risk
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-600 mt-0.5">
                {failCount > 0 && `${failCount} compliance gap${failCount !== 1 ? 's' : ''}`}
                {failCount > 0 && warnCount > 0 && ', '}
                {warnCount > 0 && `${warnCount} warning${warnCount !== 1 ? 's' : ''}`}
                {failCount === 0 && warnCount === 0 && 'All required FSVP elements present'}
              </p>
            </div>
          </div>

          {/* Key requirements */}
          {result.keyRequirements.length > 0 && (
            <div className="rounded-lg border bg-white p-5">
              <p className="text-sm font-semibold text-gray-900 mb-3">Key Requirements</p>
              <ul className="space-y-2">
                {result.keyRequirements.map((req, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                    <span className="text-brand-600 font-bold flex-shrink-0 mt-0.5">·</span>
                    {req}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Check results */}
          <div className="space-y-2">
            {result.checks.map((check) => (
              <div key={check.ruleId} className={`rounded-lg border px-4 py-3 ${STATUS_STYLES[check.status] ?? ''}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold uppercase tracking-wide">{check.status}</span>
                  <span className="text-xs font-medium text-gray-500 uppercase">{check.severity}</span>
                  <span className="text-sm font-semibold">{check.ruleName}</span>
                </div>
                <p className="text-sm">{check.message}</p>
                {check.remediation && (
                  <p className="text-sm mt-1 opacity-80">→ {check.remediation}</p>
                )}
                {check.regulatoryCitation && (
                  <p className="text-xs mt-1 font-mono opacity-70">{check.regulatoryCitation}</p>
                )}
              </div>
            ))}
          </div>

          {/* FSVP Checklist */}
          {result.fsvpChecklist.length > 0 && (
            <FSVPChecklist items={result.fsvpChecklist} />
          )}
        </div>
      )}
    </div>
  );
}
