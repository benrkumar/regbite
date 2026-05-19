'use client';

import { useEffect, useState } from 'react';

interface ScraperStatus {
  recentChanges: {
    id: string;
    source: string;
    documentTitle: string;
    changeType: string;
    severity: string;
    detectedAt: string;
  }[];
  bySource: { source: string; _count: { id: number } }[];
}

const SCRAPERS = [
  { id: 'fda-dsial', name: 'FDA DSIAL', description: 'Dietary Supplement Advisory List' },
  { id: 'fda-ndi', name: 'FDA NDI Database', description: 'New Dietary Ingredient notifications' },
  { id: 'fda-warning-letters', name: 'FDA Warning Letters', description: '5-year supplement warning letters' },
  { id: 'nih-ods', name: 'NIH ODS', description: 'Ingredient fact sheets + DRIs' },
  { id: 'fda-gras', name: 'FDA GRAS', description: 'GRAS Notices (GRN) database' },
  { id: 'federal-register', name: 'Federal Register', description: 'Supplement-related Federal Register notices' },
  { id: 'fda-import-alerts', name: 'FDA Import Alerts', description: 'Import Alert database' },
  { id: 'prop65', name: 'CA Prop 65', description: 'OEHHA Prop 65 chemical list (Excel)' },
  { id: 'ftc-enforcement', name: 'FTC Enforcement', description: 'FTC dietary supplement enforcement actions' },
];

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: 'text-red-400',
  HIGH: 'text-orange-400',
  MEDIUM: 'text-yellow-400',
  LOW: 'text-gray-400',
};

export default function ScraperPage() {
  const [status, setStatus] = useState<ScraperStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/scraper').then((r) => r.json()).then(setStatus).finally(() => setLoading(false));
  }, []);

  const triggerScraper = async (id: string) => {
    setTriggering(id);
    setMessage(null);
    try {
      const res = await fetch('/api/scraper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scraper: id }),
      });
      const data = await res.json();
      setMessage(data.message ?? data.note ?? 'Triggered');
    } finally {
      setTriggering(null);
    }
  };

  return (
    <div className="max-w-5xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Scraper Status</h1>
        <p className="text-sm text-gray-500 mt-1">Monitor and trigger FDA/regulatory data scrapers.</p>
      </div>

      {message && (
        <div className="mb-4 rounded-lg bg-blue-900/30 border border-blue-700 px-4 py-3 text-sm text-blue-300">
          {message}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-6 mb-8">
        {/* Source counts */}
        <div className="rounded-lg bg-gray-900 border border-gray-800 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-800">
            <p className="text-sm font-semibold text-white">Records by Source</p>
          </div>
          <div className="divide-y divide-gray-800">
            {loading && <p className="px-5 py-4 text-sm text-gray-500">Loading…</p>}
            {status?.bySource.length === 0 && <p className="px-5 py-4 text-sm text-gray-500">No regulatory changes indexed yet</p>}
            {status?.bySource.map((s) => (
              <div key={s.source} className="px-5 py-3 flex items-center justify-between">
                <p className="text-sm text-gray-300">{s.source}</p>
                <p className="text-sm font-semibold text-white">{s._count.id.toLocaleString()}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Recent regulatory changes */}
        <div className="rounded-lg bg-gray-900 border border-gray-800 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-800">
            <p className="text-sm font-semibold text-white">Recent Scraped Changes</p>
          </div>
          <div className="divide-y divide-gray-800">
            {loading && <p className="px-5 py-4 text-sm text-gray-500">Loading…</p>}
            {status?.recentChanges.length === 0 && <p className="px-5 py-4 text-sm text-gray-500">No changes yet</p>}
            {status?.recentChanges.slice(0, 8).map((c) => (
              <div key={c.id} className="px-5 py-3">
                <div className="flex items-center gap-2">
                  <p className={`text-xs font-semibold ${SEVERITY_COLOR[c.severity] ?? 'text-gray-500'}`}>{c.severity}</p>
                  <p className="text-xs text-gray-500">{c.source}</p>
                </div>
                <p className="text-xs text-gray-300 mt-0.5 truncate">{c.documentTitle}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Scraper controls */}
      <div className="rounded-lg bg-gray-900 border border-gray-800 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-800">
          <p className="text-sm font-semibold text-white">Manual Scraper Triggers</p>
          <p className="text-xs text-gray-500 mt-0.5">In production, enqueues a BullMQ job to the Railway scraper worker.</p>
        </div>
        <div className="divide-y divide-gray-800">
          {SCRAPERS.map((scraper) => (
            <div key={scraper.id} className="px-5 py-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-white">{scraper.name}</p>
                <p className="text-xs text-gray-500">{scraper.description}</p>
              </div>
              <button
                onClick={() => triggerScraper(scraper.id)}
                disabled={triggering !== null}
                className="text-xs rounded-md bg-gray-800 border border-gray-700 px-3 py-1.5 text-gray-300 hover:bg-gray-700 hover:text-white disabled:opacity-50 transition-colors"
              >
                {triggering === scraper.id ? 'Triggering…' : 'Run Now'}
              </button>
            </div>
          ))}
          <div className="px-5 py-4 flex items-center justify-between bg-gray-800/30">
            <div>
              <p className="text-sm font-medium text-white">Run All Scrapers</p>
              <p className="text-xs text-gray-500">Trigger the full daily scrape job</p>
            </div>
            <button
              onClick={() => triggerScraper('all')}
              disabled={triggering !== null}
              className="text-xs rounded-md bg-brand-700 border border-brand-600 px-3 py-1.5 text-white hover:bg-brand-600 disabled:opacity-50 transition-colors"
            >
              {triggering === 'all' ? 'Triggering…' : 'Run All'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
