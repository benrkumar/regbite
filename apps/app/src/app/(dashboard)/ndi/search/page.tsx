'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Search } from 'lucide-react';

interface NDIRecord {
  id: string;
  fdaNotificationNumber: string;
  ingredientName: string;
  submitter: string | null;
  submissionDate: string | null;
  fdaResponse: string | null;
}

export default function NDISearchPage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<NDIRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const search = async (q: string) => {
    if (q.trim().length < 2) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/ndi/search?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      setResults(data.results ?? []);
      setSearched(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl">
      <Link href="/ndi" className="mb-6 inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900">
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to NDI Navigator
      </Link>

      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">NDI Notification Database</h1>
        <p className="mt-1 text-sm text-gray-500">
          Search FDA&apos;s New Dietary Ingredient notification history. An existing notification may mean
          you do not need to file your own if your conditions of use are the same.
        </p>
      </div>

      {/* Search */}
      <div className="relative mb-6">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search by ingredient name, notification number, or submitter"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && search(query)}
          className="w-full rounded-lg border border-gray-300 bg-white pl-10 pr-4 py-3 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <button
          onClick={() => search(query)}
          disabled={loading || query.trim().length < 2}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {loading ? 'Searching…' : 'Search'}
        </button>
      </div>

      {results.length > 0 ? (
        <div className="rounded-lg border bg-white divide-y">
          {results.map((ndi) => (
            <div key={ndi.id} className="px-5 py-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="font-medium text-gray-900">{ndi.ingredientName}</p>
                  <p className="mt-0.5 text-xs text-gray-500">
                    {ndi.submitter ?? 'Unknown submitter'}
                    {ndi.submissionDate && ` · ${new Date(ndi.submissionDate).toLocaleDateString()}`}
                  </p>
                  {ndi.fdaResponse && (
                    <p className="mt-1.5 text-sm text-gray-700">{ndi.fdaResponse}</p>
                  )}
                </div>
                <span className="flex-shrink-0 rounded bg-blue-50 px-2 py-0.5 text-xs font-mono text-blue-700">
                  {ndi.fdaNotificationNumber}
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : searched && !loading ? (
        <div className="rounded-lg border bg-white px-6 py-12 text-center">
          <p className="text-gray-500">No NDI notifications found for &quot;{query}&quot;</p>
          <p className="mt-1 text-sm text-gray-400">
            No match doesn&apos;t automatically mean no notification was filed — FDA&apos;s database may be incomplete.
          </p>
        </div>
      ) : !searched ? (
        <div className="rounded-lg border bg-gray-50 px-6 py-12 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-white border">
            <Search className="h-5 w-5 text-gray-400" />
          </div>
          <p className="font-medium text-gray-700">Search the NDI notification database</p>
          <p className="mt-1 text-sm text-gray-500">
            Find prior notifications by ingredient name, FDA number, or submitter company.
          </p>
        </div>
      ) : null}
    </div>
  );
}
