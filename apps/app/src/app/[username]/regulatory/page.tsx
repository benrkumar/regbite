'use client';

import { useEffect, useState, useCallback } from 'react';
import { ExternalLink, RefreshCw, Rss } from 'lucide-react';

type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
type ChangeType = 'NEW_RULE' | 'AMENDMENT' | 'GUIDANCE' | 'ENFORCEMENT' | 'WARNING_LETTER' | 'IMPORT_ALERT' | 'UNKNOWN';
type RegulatorySource = 'FDA_DSIAL' | 'FDA_WARNING_LETTERS' | 'FDA_NDI' | 'NIH_ODS' | 'FDA_GRAS' | 'FEDERAL_REGISTER' | 'FDA_IMPORT_ALERTS' | 'FTC' | 'USP' | 'CONGRESS';

interface RegulatoryChangeRecord {
  id: string;
  source: RegulatorySource;
  sourceUrl: string | null;
  documentTitle: string;
  summary: string | null;
  changeType: ChangeType;
  severity: Severity;
  affectedModules: string[];
  publishedAt: string | null;
  detectedAt: string;
}

const SEVERITY_ORDER: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];

const SEVERITY_BADGE: Record<Severity, string> = {
  CRITICAL: 'bg-red-100 text-red-800',
  HIGH: 'bg-orange-100 text-orange-800',
  MEDIUM: 'bg-yellow-100 text-yellow-700',
  LOW: 'bg-gray-100 text-gray-600',
};

const CHANGE_TYPE_LABEL: Record<ChangeType, string> = {
  NEW_RULE: 'New Rule',
  AMENDMENT: 'Amendment',
  GUIDANCE: 'Guidance',
  ENFORCEMENT: 'Enforcement',
  WARNING_LETTER: 'Warning Letter',
  IMPORT_ALERT: 'Import Alert',
  UNKNOWN: 'Update',
};

const SOURCE_LABEL: Record<string, string> = {
  FDA_DSIAL: 'FDA DSIAL',
  FDA_WARNING_LETTERS: 'FDA Warning Letters',
  FDA_NDI: 'FDA NDI',
  NIH_ODS: 'NIH ODS',
  FDA_GRAS: 'FDA GRAS',
  FEDERAL_REGISTER: 'Federal Register',
  FDA_IMPORT_ALERTS: 'FDA Import Alerts',
  FTC: 'FTC',
  USP: 'USP',
  CONGRESS: 'Congress',
};

export default function RegulatoryFeedPage() {
  const [changes, setChanges] = useState<RegulatoryChangeRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeSeverity, setActiveSeverity] = useState<Severity | 'ALL'>('ALL');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (sev?: Severity | 'ALL') => {
    const filter = sev ?? activeSeverity;
    const params = new URLSearchParams({ limit: '50' });
    if (filter !== 'ALL') params.set('severity', filter);
    const res = await fetch(`/api/regulatory?${params}`);
    const data = await res.json();
    setChanges(data.changes ?? []);
  }, [activeSeverity]);

  useEffect(() => {
    setLoading(true);
    load().finally(() => setLoading(false));
  }, []);

  const handleFilter = async (sev: Severity | 'ALL') => {
    setActiveSeverity(sev);
    setRefreshing(true);
    const params = new URLSearchParams({ limit: '50' });
    if (sev !== 'ALL') params.set('severity', sev);
    const res = await fetch(`/api/regulatory?${params}`);
    const data = await res.json();
    setChanges(data.changes ?? []);
    setRefreshing(false);
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await load(activeSeverity);
    setRefreshing(false);
  };

  return (
    <div>
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Regulatory Feed</h1>
          <p className="mt-1 text-sm text-gray-500">
            FDA, FTC, and Federal Register changes affecting dietary supplements. Updated daily.
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing || loading}
          className="inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Severity filter */}
      <div className="mb-5 flex gap-2">
        {(['ALL', ...SEVERITY_ORDER] as const).map((sev) => (
          <button
            key={sev}
            onClick={() => handleFilter(sev)}
            className={`rounded-full px-3 py-1 text-xs font-semibold border transition-colors ${
              activeSeverity === sev
                ? sev === 'ALL'
                  ? 'bg-gray-900 text-white border-gray-900'
                  : `${SEVERITY_BADGE[sev as Severity]} border-current`
                : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
            }`}
          >
            {sev}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-sm text-gray-500">Loading…</div>
      ) : changes.length === 0 ? (
        <div className="rounded-lg border bg-gray-50 px-6 py-16 text-center">
          <Rss className="mx-auto mb-3 h-10 w-10 text-gray-300" />
          <p className="font-medium text-gray-700">No regulatory changes yet</p>
          <p className="mt-1 text-sm text-gray-500">
            The daily scraper will populate this feed with FDA and Federal Register updates.
            {activeSeverity !== 'ALL' && ` No ${activeSeverity} severity items found.`}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {changes.map((change) => (
            <div key={change.id} className="rounded-lg border bg-white p-4">
              <div className="flex items-start gap-3">
                {/* Left accent by severity */}
                <div className={`mt-0.5 h-2 w-2 flex-shrink-0 rounded-full mt-2 ${
                  change.severity === 'CRITICAL' ? 'bg-red-500' :
                  change.severity === 'HIGH' ? 'bg-orange-500' :
                  change.severity === 'MEDIUM' ? 'bg-yellow-400' :
                  'bg-gray-300'
                }`} />

                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium text-gray-900 text-sm leading-snug">
                        {change.documentTitle}
                      </p>
                      {change.summary && (
                        <p className="mt-1 text-xs text-gray-500 line-clamp-2">{change.summary}</p>
                      )}
                    </div>
                    {change.sourceUrl && (
                      <a
                        href={change.sourceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-shrink-0 text-gray-400 hover:text-brand-600 mt-0.5"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    )}
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${SEVERITY_BADGE[change.severity]}`}>
                      {change.severity}
                    </span>
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
                      {CHANGE_TYPE_LABEL[change.changeType] ?? 'Update'}
                    </span>
                    <span className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-700">
                      {SOURCE_LABEL[change.source] ?? change.source}
                    </span>
                    {change.affectedModules.map((mod) => (
                      <span key={mod} className="rounded bg-purple-50 px-1.5 py-0.5 text-xs text-purple-700">
                        {mod}
                      </span>
                    ))}
                    <span className="ml-auto text-xs text-gray-400">
                      {change.publishedAt
                        ? new Date(change.publishedAt).toLocaleDateString()
                        : `Detected ${new Date(change.detectedAt).toLocaleDateString()}`}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
