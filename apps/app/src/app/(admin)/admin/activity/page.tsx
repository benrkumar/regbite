"use client";

import { useEffect, useState } from "react";

export const dynamic = "force-dynamic";

interface ActivityRow {
  id: string;
  action: string;
  resourceType: string | null;
  resourceId: string | null;
  detail: string | null;
  ipAddress: string | null;
  createdAt: string;
  member: { email: string; name: string | null } | null;
  organization: { name: string; slug: string } | null;
}

const ACTION_COLORS: Record<string, string> = {
  MEMBER_INVITED: "bg-blue-100 text-blue-700",
  MEMBER_ROLE_CHANGED: "bg-blue-100 text-blue-700",
  ORG_UPDATED: "bg-teal-100 text-teal-700",
  MEMBER_REMOVED: "bg-red-100 text-red-700",
};

function actionColor(action: string): string {
  if (ACTION_COLORS[action]) return ACTION_COLORS[action];
  if (action.includes("FORMULATION") || action.includes("CHECK")) return "bg-purple-100 text-purple-700";
  return "bg-gray-100 text-gray-600";
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export default function ActivityPage() {
  const [rows, setRows] = useState<ActivityRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [orgFilter, setOrgFilter] = useState("");
  const [actionFilter, setActionFilter] = useState("");

  function load() {
    const params = new URLSearchParams({ limit: "100" });
    if (actionFilter) params.set("action", actionFilter);
    setLoading(true);
    fetch(`/api/activity?${params}`)
      .then((r) => r.json())
      .then((data) => {
        setRows(Array.isArray(data) ? data : []);
        setLoading(false);
      });
  }

  useEffect(() => { load(); }, [actionFilter]);

  const displayed = orgFilter
    ? rows.filter((r) => r.organization?.name.toLowerCase().includes(orgFilter.toLowerCase()))
    : rows;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Activity Log</h1>

      {/* Filters */}
      <div className="flex gap-3 items-center">
        <input
          type="search"
          value={orgFilter}
          onChange={(e) => setOrgFilter(e.target.value)}
          placeholder="Filter by org…"
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-[#0D4F3C]/30 bg-white"
        />
        <input
          type="search"
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          placeholder="Filter by action…"
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-[#0D4F3C]/30 bg-white"
        />
        <span className="text-xs text-gray-400">{displayed.length} entries</span>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400 text-sm">Loading…</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/50">
                <th className="text-left px-5 py-3 font-medium text-gray-500 w-24">Time</th>
                <th className="text-left px-5 py-3 font-medium text-gray-500">Org</th>
                <th className="text-left px-5 py-3 font-medium text-gray-500">Member</th>
                <th className="text-left px-5 py-3 font-medium text-gray-500">Action</th>
                <th className="text-left px-5 py-3 font-medium text-gray-500">Detail</th>
                <th className="text-left px-5 py-3 font-medium text-gray-500">IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {displayed.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50/50">
                  <td className="px-5 py-2.5 text-gray-400 text-xs whitespace-nowrap">
                    {timeAgo(r.createdAt)}
                  </td>
                  <td className="px-5 py-2.5 text-gray-700">
                    {r.organization?.name ?? <span className="text-gray-400">—</span>}
                  </td>
                  <td className="px-5 py-2.5 text-gray-600 text-xs">
                    {r.member?.email ?? <span className="text-gray-400">—</span>}
                  </td>
                  <td className="px-5 py-2.5">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium ${actionColor(r.action)}`}>
                      {r.action}
                    </span>
                  </td>
                  <td className="px-5 py-2.5 text-gray-500 text-xs max-w-xs truncate">
                    {r.detail ?? "—"}
                  </td>
                  <td className="px-5 py-2.5 text-gray-400 text-xs font-mono">
                    {r.ipAddress ?? "—"}
                  </td>
                </tr>
              ))}
              {displayed.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-10 text-center text-gray-400 text-sm">No activity found</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
