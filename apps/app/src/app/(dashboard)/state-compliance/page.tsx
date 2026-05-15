'use client';

import { useState } from 'react';
import { Plus, X, AlertTriangle, CheckCircle, ShieldAlert } from 'lucide-react';

interface Ingredient {
  name: string;
  casNumber: string;
}

interface ChemicalMatch {
  ingredientName: string;
  chemicalName: string;
  casNumber: string | null;
  listingMechanism: string | null;
  type: 'CARCINOGEN' | 'REPRODUCTIVE_TOXICANT' | 'BOTH' | 'UNKNOWN';
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

interface Prop65Result {
  targetsCalifornia: boolean;
  chemicalsFound: ChemicalMatch[];
  warningRequired: boolean;
  checks: CheckResult[];
  warningLanguage?: string;
}

const STATUS_STYLES: Record<string, string> = {
  PASS: 'bg-green-50 border-green-200 text-green-800',
  FAIL: 'bg-red-50 border-red-200 text-red-800',
  WARNING: 'bg-amber-50 border-amber-200 text-amber-800',
  INFO: 'bg-blue-50 border-blue-200 text-blue-800',
};

const TYPE_LABEL: Record<string, string> = {
  CARCINOGEN: 'Carcinogen',
  REPRODUCTIVE_TOXICANT: 'Reproductive Toxicant',
  BOTH: 'Carcinogen + Reproductive Toxicant',
  UNKNOWN: 'Listed Chemical',
};

const TYPE_COLOR: Record<string, string> = {
  CARCINOGEN: 'bg-red-100 text-red-800',
  REPRODUCTIVE_TOXICANT: 'bg-purple-100 text-purple-800',
  BOTH: 'bg-red-100 text-red-900',
  UNKNOWN: 'bg-gray-100 text-gray-700',
};

const NY_REQUIREMENTS = [
  {
    id: 'NY-001',
    title: 'NY Article 28 Registration',
    description: 'Dietary supplements sold in New York may require registration under NY Health Law Article 28 for certain product categories.',
    citation: 'NY Health Law § 206',
    required: false,
    note: 'Check with NYSDOH for your specific product type.',
  },
  {
    id: 'NY-002',
    title: 'Mercury-free labeling (NY)',
    description: 'Products with fish or fish-derived omega-3 ingredients may need to comply with NY mercury disclosure requirements.',
    citation: 'NY Environmental Conservation Law § 71-2727',
    required: false,
    note: 'Applies to fish oil and marine products.',
  },
  {
    id: 'NY-003',
    title: 'NY Ag & Markets — ingredient restrictions',
    description: 'NY Department of Agriculture & Markets regulates certain food additives and ingredients beyond federal standards.',
    citation: 'NY Ag & Markets Law § 200 et seq.',
    required: true,
    note: 'Ensure all ingredients comply with both federal and NY state standards.',
  },
];

const FL_REQUIREMENTS = [
  {
    id: 'FL-001',
    title: 'FDACS Dietary Supplement Registration',
    description: 'Florida requires manufacturers and distributors of dietary supplements to register with the Florida Department of Agriculture and Consumer Services (FDACS) if selling in FL.',
    citation: 'FL Stat. § 500.10; Rule 5K-4.002',
    required: true,
    note: 'Annual registration required. Fee varies by establishment type.',
  },
  {
    id: 'FL-002',
    title: 'FL FDACS Labeling Compliance',
    description: 'Labels must comply with FDACS requirements in addition to FDA requirements. FDACS may conduct label reviews.',
    citation: 'FL Stat. § 500.04; Rule 5K-4.010',
    required: true,
    note: 'FDACS enforces state labeling standards; violations can result in stop-sale orders.',
  },
  {
    id: 'FL-003',
    title: 'Florida Deceptive Trade Practices',
    description: 'FL Deceptive and Unfair Trade Practices Act applies to supplement marketing claims. Claims must be truthful and substantiated.',
    citation: 'FL Stat. § 501.201 et seq.',
    required: true,
    note: 'FL AG actively enforces against misleading supplement claims.',
  },
];

export default function StateCompliancePage() {
  const [activeTab, setActiveTab] = useState<'ca' | 'ny' | 'fl'>('ca');
  const [ingredients, setIngredients] = useState<Ingredient[]>([{ name: '', casNumber: '' }]);
  const [targetsCalifornia, setTargetsCalifornia] = useState(true);
  const [hasWarning, setHasWarning] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Prop65Result | null>(null);

  const addIngredient = () => setIngredients((prev) => [...prev, { name: '', casNumber: '' }]);
  const removeIngredient = (i: number) => setIngredients((prev) => prev.filter((_, idx) => idx !== i));
  const updateIngredient = (i: number, field: keyof Ingredient, value: string) => {
    setIngredients((prev) => prev.map((ing, idx) => (idx === i ? { ...ing, [field]: value } : ing)));
  };

  const handleCheck = async () => {
    const valid = ingredients.filter((i) => i.name.trim());
    if (valid.length === 0) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch('/api/state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ingredients: valid.map((i) => ({ name: i.name.trim(), casNumber: i.casNumber.trim() || undefined })),
          targetMarkets: targetsCalifornia ? ['california'] : ['other'],
          hasCaliforniaWarning: hasWarning,
        }),
      });
      const data = await res.json();
      if (data.result) setResult(data.result);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">State Compliance</h1>
        <p className="mt-1 text-sm text-gray-500">California Prop 65, New York, and Florida state-level requirements for dietary supplements.</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-gray-200">
        {(['ca', 'ny', 'fl'] as const).map((tab) => {
          const labels = { ca: 'California (Prop 65)', ny: 'New York', fl: 'Florida' };
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                activeTab === tab
                  ? 'border-brand-600 text-brand-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {labels[tab]}
            </button>
          );
        })}
      </div>

      {/* CA Prop 65 */}
      {activeTab === 'ca' && (
        <div className="space-y-6">
          <div className="rounded-lg border bg-amber-50 border-amber-200 p-4">
            <div className="flex gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-amber-900">California Proposition 65</p>
                <p className="text-sm text-amber-800 mt-1">
                  Prop 65 requires businesses to provide clear warnings before knowingly exposing Californians to chemicals listed by OEHHA as known carcinogens or reproductive toxicants.
                  The list contains 900+ chemicals and is updated twice per year.
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-lg border bg-white p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-4">Screen Ingredients Against Prop 65 List</h2>

            <div className="mb-4">
              <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={targetsCalifornia}
                  onChange={(e) => setTargetsCalifornia(e.target.checked)}
                  className="rounded"
                />
                Product is sold in California
              </label>
            </div>

            <div className="mb-4">
              <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={hasWarning}
                  onChange={(e) => setHasWarning(e.target.checked)}
                  className="rounded"
                />
                Product already has a California Prop 65 warning
              </label>
            </div>

            <div className="space-y-2 mb-4">
              {ingredients.map((ing, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <input
                    type="text"
                    placeholder="Ingredient name (e.g., Lead acetate)"
                    value={ing.name}
                    onChange={(e) => updateIngredient(i, 'name', e.target.value)}
                    className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                  <input
                    type="text"
                    placeholder="CAS # (optional)"
                    value={ing.casNumber}
                    onChange={(e) => updateIngredient(i, 'casNumber', e.target.value)}
                    className="w-36 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                  {ingredients.length > 1 && (
                    <button onClick={() => removeIngredient(i)} className="text-gray-400 hover:text-red-500">
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>

            <div className="flex gap-3">
              <button
                onClick={addIngredient}
                className="inline-flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-700 font-medium"
              >
                <Plus className="h-4 w-4" />
                Add ingredient
              </button>
              <button
                onClick={handleCheck}
                disabled={loading || !ingredients.some((i) => i.name.trim())}
                className="ml-auto inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {loading ? 'Checking…' : 'Run Prop 65 Screen'}
              </button>
            </div>
          </div>

          {result && (
            <div className="space-y-4">
              {/* Summary */}
              <div className={`rounded-lg border p-4 flex items-start gap-3 ${
                result.warningRequired ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'
              }`}>
                {result.warningRequired ? (
                  <ShieldAlert className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
                ) : (
                  <CheckCircle className="h-5 w-5 text-green-600 flex-shrink-0 mt-0.5" />
                )}
                <div>
                  <p className={`text-sm font-semibold ${result.warningRequired ? 'text-red-900' : 'text-green-900'}`}>
                    {result.warningRequired
                      ? `Prop 65 warning required — ${result.chemicalsFound.length} listed chemical${result.chemicalsFound.length !== 1 ? 's' : ''} found`
                      : result.chemicalsFound.length > 0
                      ? 'Prop 65 warning already present'
                      : 'No Prop 65 chemicals detected'}
                  </p>
                  {!result.targetsCalifornia && (
                    <p className="text-sm text-gray-600 mt-0.5">Product not targeted at California — Prop 65 does not apply.</p>
                  )}
                </div>
              </div>

              {/* Chemicals found */}
              {result.chemicalsFound.length > 0 && (
                <div className="rounded-lg border bg-white overflow-hidden">
                  <div className="px-5 py-3 bg-gray-50 border-b">
                    <p className="text-sm font-semibold text-gray-700">Listed Chemicals Found</p>
                  </div>
                  <div className="divide-y">
                    {result.chemicalsFound.map((chem, i) => (
                      <div key={i} className="px-5 py-4">
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <p className="text-sm font-medium text-gray-900">{chem.chemicalName}</p>
                            <p className="text-xs text-gray-500 mt-0.5">from: {chem.ingredientName} {chem.casNumber && `· CAS ${chem.casNumber}`}</p>
                            {chem.listingMechanism && (
                              <p className="text-xs text-gray-500 mt-0.5">{chem.listingMechanism}</p>
                            )}
                          </div>
                          <span className={`flex-shrink-0 inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${TYPE_COLOR[chem.type]}`}>
                            {TYPE_LABEL[chem.type]}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Warning language */}
              {result.warningLanguage && (
                <div className="rounded-lg border bg-amber-50 border-amber-200 p-4">
                  <p className="text-xs font-semibold text-amber-900 uppercase tracking-wide mb-2">Required Warning Language</p>
                  <p className="text-sm text-amber-900 font-medium">{result.warningLanguage}</p>
                  <p className="text-xs text-amber-700 mt-2">
                    Place this warning on the product label before selling in California. See OEHHA Title 27, CCR § 25603 for full requirements.
                  </p>
                </div>
              )}

              {/* Check results */}
              <div className="space-y-2">
                {result.checks.map((check) => (
                  <div key={check.ruleId} className={`rounded-lg border px-4 py-3 ${STATUS_STYLES[check.status] ?? ''}`}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-bold uppercase tracking-wide">{check.status}</span>
                      <span className="text-sm font-medium">{check.ruleName}</span>
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
            </div>
          )}
        </div>
      )}

      {/* NY Tab */}
      {activeTab === 'ny' && (
        <div className="space-y-4">
          <div className="rounded-lg border bg-blue-50 border-blue-200 p-4">
            <p className="text-sm text-blue-900 font-semibold">New York State Requirements</p>
            <p className="text-sm text-blue-800 mt-1">
              New York enforces additional labeling, registration, and ingredient requirements beyond federal FDA standards.
              The NYSDOH and NY Department of Agriculture & Markets both have jurisdiction over dietary supplements.
            </p>
          </div>
          <div className="space-y-3">
            {NY_REQUIREMENTS.map((req) => (
              <div key={req.id} className="rounded-lg border bg-white p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-gray-900">{req.title}</p>
                      <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${req.required ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'}`}>
                        {req.required ? 'Required' : 'Conditional'}
                      </span>
                    </div>
                    <p className="text-sm text-gray-600 mt-1">{req.description}</p>
                    <p className="text-xs text-gray-500 mt-1.5">{req.note}</p>
                  </div>
                </div>
                <p className="mt-2 text-xs font-mono text-gray-400">{req.citation}</p>
              </div>
            ))}
          </div>
          <div className="rounded-lg border bg-gray-50 p-4">
            <p className="text-sm text-gray-700">
              <strong>Note:</strong> NY requirements are evolving. Consult a regulatory attorney or the NY Department of Agriculture &amp; Markets for the latest requirements specific to your product category.
            </p>
          </div>
        </div>
      )}

      {/* FL Tab */}
      {activeTab === 'fl' && (
        <div className="space-y-4">
          <div className="rounded-lg border bg-orange-50 border-orange-200 p-4">
            <p className="text-sm text-orange-900 font-semibold">Florida FDACS Requirements</p>
            <p className="text-sm text-orange-800 mt-1">
              Florida requires dietary supplement manufacturers and distributors to register with FDACS before selling in the state.
              Non-compliance can result in stop-sale orders and civil penalties.
            </p>
          </div>
          <div className="space-y-3">
            {FL_REQUIREMENTS.map((req) => (
              <div key={req.id} className="rounded-lg border bg-white p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-gray-900">{req.title}</p>
                      <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${req.required ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'}`}>
                        {req.required ? 'Required' : 'Conditional'}
                      </span>
                    </div>
                    <p className="text-sm text-gray-600 mt-1">{req.description}</p>
                    <p className="text-xs text-gray-500 mt-1.5">{req.note}</p>
                  </div>
                </div>
                <p className="mt-2 text-xs font-mono text-gray-400">{req.citation}</p>
              </div>
            ))}
          </div>
          <div className="rounded-lg border bg-gray-50 p-4">
            <p className="text-sm text-gray-700">
              <strong>FDACS Registration:</strong> Visit{' '}
              <span className="font-mono text-brand-700">freshfromflorida.com</span>{' '}
              for current registration forms and fee schedules. Annual renewal required.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
