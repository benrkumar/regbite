'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Search } from 'lucide-react';
import { SeverityBadge } from '@/components/severity-badge';

interface IngredientResult {
  id: string;
  name: string;
  fdaStatus: string;
  grasStatus: string;
  prop65Listed: boolean;
  advisoryNotes: string | null;
}

const FDA_STATUS_STYLES: Record<string, string> = {
  PERMITTED: 'bg-green-100 text-green-800',
  RESTRICTED: 'bg-orange-100 text-orange-800',
  BANNED: 'bg-red-100 text-red-800',
  ADVISORY: 'bg-yellow-100 text-yellow-800',
  UNKNOWN: 'bg-gray-100 text-gray-600',
};

export default function IngredientsPage() {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<IngredientResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const search = useCallback(async (q: string) => {
    if (q.length < 2) { setResults([]); return; }
    setLoading(true);
    try {
      const res = await fetch(`/api/ingredients/search?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      setResults(data.results ?? []);
      setSearched(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') search(query);
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Ingredient Checker</h1>
        <p className="mt-1 text-sm text-gray-500">
          Search any dietary supplement ingredient for FDA status, GRAS classification,
          NDI requirements, and warning letter history.
        </p>
      </div>

      {/* Search bar */}
      <div className="relative mb-6">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search by ingredient name or CAS number (e.g. Vitamin C, Ephedra, 50-81-7)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          className="w-full rounded-lg border border-gray-300 bg-white pl-10 pr-4 py-3 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <button
          onClick={() => search(query)}
          disabled={loading || query.length < 2}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>

      {/* Results */}
      {results.length > 0 ? (
        <div className="rounded-lg border bg-white divide-y">
          {results.map((ing) => (
            <button
              key={ing.id}
              onClick={() => router.push(`/ingredients/${ing.id}`)}
              className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-50 transition-colors"
            >
              <div className="min-w-0">
                <p className="font-medium text-gray-900">{ing.name}</p>
                {ing.advisoryNotes && (
                  <p className="mt-0.5 text-xs text-gray-500 truncate max-w-xl">{ing.advisoryNotes}</p>
                )}
              </div>
              <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                {ing.prop65Listed && (
                  <span className="rounded bg-purple-100 px-1.5 py-0.5 text-xs font-medium text-purple-800">Prop 65</span>
                )}
                <span className={`rounded px-2 py-0.5 text-xs font-semibold ${FDA_STATUS_STYLES[ing.fdaStatus] ?? FDA_STATUS_STYLES.UNKNOWN}`}>
                  {ing.fdaStatus}
                </span>
              </div>
            </button>
          ))}
        </div>
      ) : searched && !loading ? (
        <div className="rounded-lg border bg-white px-6 py-12 text-center">
          <p className="text-gray-500">No ingredients found for &quot;{query}&quot;</p>
          <p className="mt-1 text-sm text-gray-400">Try a different name or CAS number.</p>
        </div>
      ) : !searched ? (
        <div className="rounded-lg border bg-gray-50 px-6 py-12 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-white border">
            <Search className="h-5 w-5 text-gray-400" />
          </div>
          <p className="font-medium text-gray-700">Search the ingredient database</p>
          <p className="mt-1 text-sm text-gray-500">
            Contains 116 dietary supplement ingredients with FDA regulatory data.
          </p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {['Vitamin C', 'Ashwagandha', 'Ephedra', 'St. John\'s Wort', 'CBD', 'Melatonin'].map((name) => (
              <button
                key={name}
                onClick={() => { setQuery(name); search(name); }}
                className="rounded-full border bg-white px-3 py-1 text-xs text-gray-600 hover:border-brand-400 hover:text-brand-600"
              >
                {name}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
