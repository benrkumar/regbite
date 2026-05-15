'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, Trash2, ArrowLeft } from 'lucide-react';
import Link from 'next/link';

interface IngredientRow {
  name: string;
  amount: string;
  unit: string;
  casNumber: string;
}

const UNITS = ['mg', 'mcg', 'g', 'IU', 'CFU', 'billion CFU', '%'];

export default function NewFormulationPage() {
  const router = useRouter();
  const [productName, setProductName] = useState('');
  const [productType, setProductType] = useState('DIETARY_SUPPLEMENT');
  const [servingSize, setServingSize] = useState('');
  const [servingsPerContainer, setServingsPerContainer] = useState('');
  const [ingredients, setIngredients] = useState<IngredientRow[]>([
    { name: '', amount: '', unit: 'mg', casNumber: '' },
  ]);
  const [claims, setClaims] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const addRow = () =>
    setIngredients((prev) => [...prev, { name: '', amount: '', unit: 'mg', casNumber: '' }]);

  const removeRow = (i: number) =>
    setIngredients((prev) => prev.filter((_, idx) => idx !== i));

  const updateRow = (i: number, field: keyof IngredientRow, value: string) =>
    setIngredients((prev) => prev.map((row, idx) => idx === i ? { ...row, [field]: value } : row));

  const handleSubmit = async () => {
    if (!productName.trim()) { setError('Product name is required'); return; }
    const validIngredients = ingredients.filter((r) => r.name.trim() && r.amount);
    if (validIngredients.length === 0) { setError('At least one ingredient is required'); return; }

    setSaving(true);
    setError('');

    try {
      const res = await fetch('/api/formulations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          productName: productName.trim(),
          productType,
          servingSize: servingSize || undefined,
          servingsPerContainer: servingsPerContainer || undefined,
          ingredients: validIngredients.map((r) => ({
            name: r.name.trim(),
            amount: parseFloat(r.amount),
            unit: r.unit,
            casNumber: r.casNumber.trim() || null,
          })),
          claims: claims.split('\n').map((c) => c.trim()).filter(Boolean),
        }),
      });

      const data = await res.json();
      if (!res.ok) { setError(data.error?.message ?? 'Failed to create formulation'); return; }
      router.push(`/formulations/${data.formulation.id}`);
    } catch {
      setError('Network error — please try again');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-3xl">
      <Link href="/formulations" className="mb-6 inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900">
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to formulations
      </Link>

      <h1 className="mb-6 text-2xl font-bold text-gray-900">New Formulation</h1>

      <div className="space-y-6">
        {/* Product details */}
        <div className="rounded-lg border bg-white p-5 space-y-4">
          <h2 className="font-semibold text-gray-800">Product Details</h2>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Product Name *</label>
              <input
                type="text"
                value={productName}
                onChange={(e) => setProductName(e.target.value)}
                placeholder="e.g. Daily Multivitamin Complex"
                className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Product Type</label>
              <select
                value={productType}
                onChange={(e) => setProductType(e.target.value)}
                className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              >
                <option value="DIETARY_SUPPLEMENT">Dietary Supplement</option>
                <option value="VITAMIN_MINERAL">Vitamin / Mineral</option>
                <option value="HERBAL_BOTANICAL">Herbal / Botanical</option>
                <option value="AMINO_ACID">Amino Acid</option>
                <option value="SPORTS_NUTRITION">Sports Nutrition</option>
                <option value="PROBIOTICS">Probiotics</option>
                <option value="SPECIALTY">Specialty</option>
              </select>
            </div>
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

        {/* Ingredients table */}
        <div className="rounded-lg border bg-white p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-800">Ingredients *</h2>
            <button
              onClick={addRow}
              className="inline-flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-700 font-medium"
            >
              <Plus className="h-3.5 w-3.5" />
              Add row
            </button>
          </div>

          <div className="space-y-2">
            <div className="grid grid-cols-12 gap-2 text-xs font-medium text-gray-500 uppercase px-1">
              <div className="col-span-5">Ingredient Name</div>
              <div className="col-span-2">Amount</div>
              <div className="col-span-2">Unit</div>
              <div className="col-span-2">CAS # (optional)</div>
              <div className="col-span-1" />
            </div>
            {ingredients.map((row, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 items-center">
                <input
                  type="text"
                  value={row.name}
                  onChange={(e) => updateRow(i, 'name', e.target.value)}
                  placeholder="e.g. Vitamin C"
                  className="col-span-5 rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
                />
                <input
                  type="number"
                  value={row.amount}
                  onChange={(e) => updateRow(i, 'amount', e.target.value)}
                  placeholder="500"
                  className="col-span-2 rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
                />
                <select
                  value={row.unit}
                  onChange={(e) => updateRow(i, 'unit', e.target.value)}
                  className="col-span-2 rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
                >
                  {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
                </select>
                <input
                  type="text"
                  value={row.casNumber}
                  onChange={(e) => updateRow(i, 'casNumber', e.target.value)}
                  placeholder="50-81-7"
                  className="col-span-2 rounded-md border px-3 py-2 text-sm font-mono focus:border-brand-500 focus:outline-none"
                />
                <button
                  onClick={() => removeRow(i)}
                  disabled={ingredients.length === 1}
                  className="col-span-1 flex justify-center text-gray-400 hover:text-red-500 disabled:opacity-30"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Claims */}
        <div className="rounded-lg border bg-white p-5">
          <h2 className="font-semibold text-gray-800 mb-1">Marketing Claims (optional)</h2>
          <p className="text-xs text-gray-500 mb-3">Enter one claim per line. Claims will be analyzed for FDA/FTC compliance.</p>
          <textarea
            value={claims}
            onChange={(e) => setClaims(e.target.value)}
            rows={3}
            placeholder={'Supports immune function\nPromotes healthy energy levels'}
            className="w-full rounded-md border px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-3">
          <Link href="/formulations" className="rounded-lg border px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
            Cancel
          </Link>
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="rounded-lg bg-brand-600 px-6 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Create Formulation'}
          </button>
        </div>
      </div>
    </div>
  );
}
