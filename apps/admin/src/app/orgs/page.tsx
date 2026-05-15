"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export const dynamic = "force-dynamic";

interface OrgRow {
  id: string;
  name: string;
  slug: string;
  plan: string;
  suspended: boolean;
  createdAt: string;
  memberCount: number;
  formulationCount: number;
  checkCount: number;
  subscription: { status: string; plan: string } | null;
}

interface Stats {
  total: number;
  active: number;
  trialing: number;
  pastDue: number;
}

const PLAN_BADGE: Record<string, string> = {
  STARTER: "bg-gray-100 text-gray-700",
  GROWTH: "bg-teal-100 text-teal-700",
  PROFESSIONAL: "bg-blue-100 text-blue-700",
  ENTERPRISE: "bg-purple-100 text-purple-700",
  CONSULTANT: "bg-amber-100 text-amber-700",
};

const STATUS_BADGE: Record<string, string> = {
  ACTIVE: "bg-[#22C55E]/15 text-green-700",
  TRIALING: "bg-blue-100 text-blue-700",
  PAST_DUE: "bg-red-100 text-red-700",
  CANCELLED: "bg-gray-100 text-gray-600",
  UNPAID: "bg-orange-100 text-orange-700",
};

function OrgSearchFilter({
  orgs,
  onFilter,
}: {
  orgs: OrgRow[];
  onFilter: (filtered: OrgRow[]) => void;
}) {
  const [query, setQuery] = useState("");

  useEffect(() => {
    const q = query.toLowerCase();
    onFilter(
      q
        ? orgs.filter(
            (o) =>
              o.name.toLowerCase().includes(q) ||
              o.slug.toLowerCase().includes(q) ||
              o.plan.toLowerCase().includes(q)
          )
        : orgs
    );
  }, [query, orgs, onFilter]);

  return (
    <input
      type="search"
      value={query}
      onChange={(e) => setQuery(e.target.value)}
      placeholder="Search organizations…"
      className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-72 focus:outline-none focus:ring-2 focus:ring-[#0D4F3C]/30 bg-white"
    />
  );
}

export default function OrgsPage() {
  const [orgs, setOrgs] = useState<OrgRow[]>([]);
  const [filtered, setFiltered] = useState<OrgRow[]>([]);
  const [stats, setStats] = useState<Stats>({ total: 0, active: 0, trialing: 0, pastDue: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/orgs")
      .then((r) => r.json())
      .then(({ orgs: data, stats: s }) => {
        setOrgs(data);
        setFiltered(data);
        setStats(s);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-gray-200 rounded animate-pulse" />
        <div className="h-64 bg-white rounded-xl border border-gray-200 animate-pulse" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Organizations</h1>

      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Total", value: stats.total, color: "text-gray-900" },
          { label: "Active", value: stats.active, color: "text-green-700" },
          { label: "Trialing", value: stats.trialing, color: "text-blue-700" },
          { label: "Past Due", value: stats.pastDue, color: "text-red-700" },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-4">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
            <p className={`text-3xl font-bold mt-1 ${color}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Search + table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <span className="text-sm font-semibold text-gray-900">All Organizations</span>
          <OrgSearchFilter orgs={orgs} onFilter={setFiltered} />
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/50">
              <th className="text-left px-6 py-3 font-medium text-gray-500">Org Name</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Plan</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Members</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Formulations</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Status</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.map((o) => (
              <tr key={o.id} className="hover:bg-gray-50/50">
                <td className="px-6 py-3">
                  <Link href={`/orgs/${o.id}`} className="font-medium text-[#0D4F3C] hover:underline">
                    {o.name}
                  </Link>
                  <div className="text-xs text-gray-400">{o.slug}</div>
                </td>
                <td className="px-6 py-3">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${PLAN_BADGE[o.plan] ?? "bg-gray-100 text-gray-600"}`}>
                    {o.plan}
                  </span>
                </td>
                <td className="px-6 py-3 text-gray-700">{o.memberCount}</td>
                <td className="px-6 py-3 text-gray-700">{o.formulationCount}</td>
                <td className="px-6 py-3">
                  {o.suspended ? (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">SUSPENDED</span>
                  ) : o.subscription ? (
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${STATUS_BADGE[o.subscription.status] ?? "bg-gray-100 text-gray-600"}`}>
                      {o.subscription.status}
                    </span>
                  ) : (
                    <span className="text-xs text-gray-400">—</span>
                  )}
                </td>
                <td className="px-6 py-3 text-gray-500 text-xs">
                  {new Date(o.createdAt).toLocaleDateString()}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-10 text-center text-gray-400 text-sm">
                  No organizations found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
