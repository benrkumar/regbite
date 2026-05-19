'use client';

import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { CheckResultList } from '@/components/check-result-card';
import { ComplianceScoreBadge } from '@/components/compliance-score-badge';

interface NutrientRow {
  name: string;
  amount: string;
  unit: string;
  dvPercent: string;
}

interface LabelResult {
  overallScore: number;
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

const NUTRIENT_UNITS = ['mg', 'mcg', 'g', 'IU', '%'];

export default function LabelValidatorPage() {
  const [servingSize, setServingSize] = useState('');
  const [servingsPerContainer, setServingsPerContainer] = useState('');
  const [nutrients, setNutrients] = useState<NutrientRow[]>([
    { name: '', amount: '', unit: 'mg', dvPercent: '' },
  ]);
  const [hasProprietaryBlend, setHasProprietaryBlend] = useState(false);
  const [blendName, setBlendName] = useState('');
  const [blendTotal, setBlendTotal] = useState('');
  const [blendIngredients, setBlendIngredients] = useState('');
  const [otherIngredients, setOtherIngredients] = useState('');
  const [allergens, setAllergens] = useState('');
  const [netQuantity, setNetQuantity] = useState('');
  const [identityStatement, setIdentityStatement] = useState('');
  const [manufacturerInfo, setManufacturerInfo] = useState('');
  const [lotCode, setLotCode] = useState('');
  const [hasExpiration, setHasExpiration] = useState(false);
  const [validating, setValidating] = useState(false);
  const [result, setResult] = useState<LabelResult | null>(null);
  const [error, setError] = useState('');

  const addNutrient = () =>
    setNutrients((p) => [...p, { name: '', amount: '', unit: 'mg', dvPercent: '' }]);

  const removeNutrient = (i: number) =>
    setNutrients((p) => p.filter((_, idx) => idx !== i));

  const updateNutrient = (i: number, field: keyof NutrientRow, value: string) =>
    setNutrients((p) => p.map((row, idx) => idx === i ? { ...row, [field]: value } : row));

  const handleValidate = async () => {
    setValidating(true);
    setError('');
    setResult(null);

    const validNutrients = nutrients
      .filter((n) => n.name.trim() && n.amount)
      .map((n) => ({
        name: n.name.trim(),
        amount: parseFloat(n.amount),
        unit: n.unit,
        dvPercent: n.dvPercent ? parseFloat(n.dvPercent) : null,
      }));

    const body: Record<string, unknown> = {};
    if (servingSize) body.servingSize = servingSize;
    if (servingsPerContainer) body.servingsPerContainer = servingsPerContainer;
    if (validNutrients.length) body.nutrients = validNutrients;
    if (otherIngredients) body.otherIngredients = otherIngredients.split(',').map((s) => s.trim()).filter(Boolean);
    if (allergens) body.allergens = allergens.split(',').map((s) => s.trim()).filter(Boolean);
    if (netQuantity) body.netQuantity = netQuantity;
    if (identityStatement) body.identityStatement = identityStatement;
    if (manufacturerInfo) body.manufacturerInfo = manufacturerInfo;
    if (lotCode) body.lotCode = lotCode;
    body.hasExpirationDate = hasExpiration;

    if (hasProprietaryBlend && blendName) {
      body.proprietaryBlend = {
        name: blendName,
        totalAmount: parseFloat(blendTotal) || 0,
        unit: 'mg',
        ingredients: blendIngredients.split(',').map((s) => s.trim()).filter(Boolean),
      };
    }

    try {
      const res = await fetch('/api/label/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) { setError('Validation failed — please try again.'); return; }
      setResult(data.result);
    } catch {
      setError('Network error — please try again.');
    } finally {
      setValidating(false);
    }
  };

  return (
    <div className="max-w-4xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Label Validator</h1>
        <p className="mt-1 text-sm text-gray-500">
          Validate your Supplement Facts panel against FDA 21 CFR § 101.36 requirements.
          Enter your label details below to run a 10-point compliance check.
        </p>
      </div>

      <div className="space-y-5">
        {/* Serving info */}
        <div className="rounded-lg border bg-white p-5 space-y-4">
          <h2 className="font-semibold text-gray-800">Serving Information</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Serving Size</label>
              <input
                type="text"
                value={servingSize}
                onChange={(e) => setServingSize(e.target.value)}
                placeholder="e.g. 2 capsules"
                className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Servings Per Container</label>
              <input
                type="text"
                value={servingsPerContainer}
                onChange={(e) => setServingsPerContainer(e.target.value)}
                placeholder="e.g. 30"
                className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
          </div>
        </div>

        {/* Nutrients */}
        <div className="rounded-lg border bg-white p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-800">Nutrients</h2>
            <button
              onClick={addNutrient}
              className="inline-flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-700 font-medium"
            >
              <Plus className="h-3.5 w-3.5" />
              Add nutrient
            </button>
          </div>
          <div className="space-y-2">
            <div className="grid grid-cols-12 gap-2 text-xs font-medium text-gray-500 uppercase px-1">
              <div className="col-span-5">Nutrient Name</div>
              <div className="col-span-2">Amount</div>
              <div className="col-span-2">Unit</div>
              <div className="col-span-2">% DV</div>
              <div className="col-span-1" />
            </div>
            {nutrients.map((row, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 items-center">
                <input
                  type="text"
                  value={row.name}
                  onChange={(e) => updateNutrient(i, 'name', e.target.value)}
                  placeholder="e.g. Vitamin C"
                  className="col-span-5 rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
                />
                <input
                  type="number"
                  value={row.amount}
                  onChange={(e) => updateNutrient(i, 'amount', e.target.value)}
                  placeholder="500"
                  className="col-span-2 rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
                />
                <select
                  value={row.unit}
                  onChange={(e) => updateNutrient(i, 'unit', e.target.value)}
                  className="col-span-2 rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
                >
                  {NUTRIENT_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
                </select>
                <input
                  type="number"
                  value={row.dvPercent}
                  onChange={(e) => updateNutrient(i, 'dvPercent', e.target.value)}
                  placeholder="56"
                  className="col-span-2 rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
                />
                <button
                  onClick={() => removeNutrient(i)}
                  disabled={nutrients.length === 1}
                  className="col-span-1 flex justify-center text-gray-400 hover:text-red-500 disabled:opacity-30"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Proprietary blend toggle */}
        <div className="rounded-lg border bg-white p-5 space-y-4">
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="prop-blend"
              checked={hasProprietaryBlend}
              onChange={(e) => setHasProprietaryBlend(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-brand-600"
            />
            <label htmlFor="prop-blend" className="font-semibold text-gray-800 cursor-pointer">
              Contains a proprietary blend
            </label>
          </div>
          {hasProprietaryBlend && (
            <div className="grid grid-cols-2 gap-4 pt-1">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Blend Name</label>
                <input
                  type="text"
                  value={blendName}
                  onChange={(e) => setBlendName(e.target.value)}
                  placeholder="e.g. Energy Matrix"
                  className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Total Weight (mg)</label>
                <input
                  type="number"
                  value={blendTotal}
                  onChange={(e) => setBlendTotal(e.target.value)}
                  placeholder="500"
                  className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-1">Ingredients in blend (comma-separated)</label>
                <input
                  type="text"
                  value={blendIngredients}
                  onChange={(e) => setBlendIngredients(e.target.value)}
                  placeholder="e.g. Caffeine, L-Theanine, Rhodiola"
                  className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
                />
              </div>
            </div>
          )}
        </div>

        {/* Label details */}
        <div className="rounded-lg border bg-white p-5 space-y-4">
          <h2 className="font-semibold text-gray-800">Label Details</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Other Ingredients
                <span className="ml-1 text-xs text-gray-400">(comma-separated)</span>
              </label>
              <input
                type="text"
                value={otherIngredients}
                onChange={(e) => setOtherIngredients(e.target.value)}
                placeholder="e.g. Gelatin, Magnesium stearate"
                className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Allergens Declared
                <span className="ml-1 text-xs text-gray-400">(comma-separated)</span>
              </label>
              <input
                type="text"
                value={allergens}
                onChange={(e) => setAllergens(e.target.value)}
                placeholder="e.g. Milk, Soy"
                className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Net Quantity</label>
              <input
                type="text"
                value={netQuantity}
                onChange={(e) => setNetQuantity(e.target.value)}
                placeholder="e.g. 60 Capsules (54 g)"
                className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Statement of Identity</label>
              <input
                type="text"
                value={identityStatement}
                onChange={(e) => setIdentityStatement(e.target.value)}
                placeholder="e.g. Vitamin C Dietary Supplement"
                className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Manufacturer / Distributor Info</label>
              <input
                type="text"
                value={manufacturerInfo}
                onChange={(e) => setManufacturerInfo(e.target.value)}
                placeholder="e.g. Distributed by NutriCo Inc., 123 Main St, Austin, TX 78701"
                className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Lot Code</label>
              <input
                type="text"
                value={lotCode}
                onChange={(e) => setLotCode(e.target.value)}
                placeholder="e.g. LOT24A001"
                className="w-full rounded-md border px-3 py-2 text-sm font-mono focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div className="flex items-center gap-3 pt-6">
              <input
                type="checkbox"
                id="has-exp"
                checked={hasExpiration}
                onChange={(e) => setHasExpiration(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-brand-600"
              />
              <label htmlFor="has-exp" className="text-sm font-medium text-gray-700 cursor-pointer">
                Expiration / best-by date is present
              </label>
            </div>
          </div>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="flex justify-end">
          <button
            onClick={handleValidate}
            disabled={validating}
            className="rounded-lg bg-brand-600 px-6 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {validating ? 'Validating…' : 'Run Label Validation'}
          </button>
        </div>

        {/* Results */}
        {result && (
          <div className="space-y-4 pt-2">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-900">Validation Results</h2>
              <ComplianceScoreBadge score={result.overallScore} />
            </div>
            <CheckResultList checks={result.checks as Parameters<typeof CheckResultList>[0]['checks']} />
          </div>
        )}
      </div>
    </div>
  );
}
