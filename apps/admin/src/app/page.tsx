'use client';

import { useEffect, useState } from 'react';

interface Stats {
  counts: Record<string, number>;
  recentOrgs: { id: string; name: string; plan: string; createdAt: string }[];
  recentChecks: { id: string; checkType: string; status: string; overallScore: number | null; createdAt: string; organization: { name: string } }[];
}

const STAT_LABELS: Record<string, string> = {
  orgs: 'Organizations',
  members: 'Members',
  formulations: 'Formulations',
  checks: 'Compliance Checks',
  ingredients: 'US Ingredients',
  warningLetters: 'Warning Letters',
  ndiNotifications: 'NDI Notifications',
  regulatoryChanges: 'Regulatory Changes',
  prop65Chemicals: 'Prop 65 Chemicals',
  activeSubscriptions: 'Active Subscriptions',
};

export default function AdminDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/stats').then((r) => r.json()).then(setStats).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-sm text-gray-400">Loading…</div>;
  if (!stats) return <div className="text-sm text-red-400">Failed to load stats</div>;

  return (
    <div className="max-w-5xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">System Overview</h1>
        <p className="text-sm text-gray-500 mt-1">Real-time metrics from the RegBite US database.</p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-10">
        {Object.entries(stats.counts).map(([key, val]) => (
          <div key={key} className="rounded-lg bg-gray-900 border border-gray-800 p-4">
            <p className="text-2xl font-bold text-white">{val.toLocaleString()}</p>
            <p className="text-xs text-gray-500 mt-0.5">{STAT_LABELS[key] ?? key}</p>
          </div>
        ))}
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Recent orgs */}
        <div className="rounded-lg bg-gray-900 border border-gray-800 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-800">
            <p className="text-sm font-semibold text-white">Recent Organizations</p>
          </div>
          <div className="divide-y divide-gray-800">
            {stats.recentOrgs.length === 0 && (
              <p className="px-5 py-4 text-sm text-gray-500">No organizations yet</p>
            )}
            {stats.recentOrgs.map((org) => (
              <div key={org.id} className="px-5 py-3 flex items-center justify-between">
                <div>
                  <p className="text-sm text-white">{org.name}</p>
                  <p className="text-xs text-gray-500">{new Date(org.createdAt).toLocaleDateString()}</p>
                </div>
                <span className="text-xs rounded-full bg-gray-800 px-2.5 py-0.5 text-gray-400">{org.plan}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Recent checks */}
        <div className="rounded-lg bg-gray-900 border border-gray-800 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-800">
            <p className="text-sm font-semibold text-white">Recent Compliance Checks</p>
          </div>
          <div className="divide-y divide-gray-800">
            {stats.recentChecks.length === 0 && (
              <p className="px-5 py-4 text-sm text-gray-500">No checks run yet</p>
            )}
            {stats.recentChecks.map((check) => (
              <div key={check.id} className="px-5 py-3 flex items-center justify-between">
                <div>
                  <p className="text-sm text-white">{check.organization.name}</p>
                  <p className="text-xs text-gray-500">{check.checkType} · {new Date(check.createdAt).toLocaleDateString()}</p>
                </div>
                <div className="text-right">
                  {check.overallScore != null && (
                    <p className="text-sm font-medium text-white">{check.overallScore}%</p>
                  )}
                  <p className={`text-xs ${check.status === 'COMPLETED' ? 'text-green-500' : 'text-yellow-500'}`}>{check.status}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
