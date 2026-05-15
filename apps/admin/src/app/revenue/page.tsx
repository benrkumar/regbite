"use client";

import { useEffect, useState } from "react";

export const dynamic = "force-dynamic";

interface RevenueData {
  mrr: number;
  byStatus: Record<string, number>;
  byPlan: Record<string, number>;
  recentEvents: Array<{
    id: string;
    status: string;
    plan: string;
    createdAt: string;
    organization: { name: string; slug: string } | null;
  }>;
}

const PLAN_ORDER = ["STARTER", "GROWTH", "PROFESSIONAL", "ENTERPRISE", "CONSULTANT"];

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: "bg-[#22C55E]/15 text-green-700",
  TRIALING: "bg-blue-100 text-blue-700",
  PAST_DUE: "bg-red-100 text-red-700",
  CANCELLED: "bg-gray-100 text-gray-600",
  UNPAID: "bg-orange-100 text-orange-700",
};

const PLAN_BAR_COLORS: Record<string, string> = {
  STARTER: "bg-gray-400",
  GROWTH: "bg-[#0D4F3C]",
  PROFESSIONAL: "bg-blue-500",
  ENTERPRISE: "bg-purple-500",
  CONSULTANT: "bg-amber-500",
};

export default function RevenuePage() {
  const [data, setData] = useState<RevenueData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/revenue")
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); });
  }, []);

  if (loading || !data) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-gray-200 rounded animate-pulse" />
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 bg-white rounded-xl border border-gray-200 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const totalActive = data.byStatus.ACTIVE ?? 0;
  const totalTrialing = data.byStatus.TRIALING ?? 0;
  const totalPastDue = data.byStatus.PAST_DUE ?? 0;

  const maxPlanCount = Math.max(...PLAN_ORDER.map((p) => data.byPlan[p] ?? 0), 1);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Revenue</h1>

      {/* Top stat cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Monthly MRR", value: `$${data.mrr.toLocaleString()}`, sub: "active + trialing", color: "text-gray-900" },
          { label: "Active", value: totalActive.toString(), sub: "subscriptions", color: "text-green-700" },
          { label: "Trialing", value: totalTrialing.toString(), sub: "subscriptions", color: "text-blue-700" },
          { label: "Past Due", value: totalPastDue.toString(), sub: "subscriptions", color: "text-red-700" },
        ].map(({ label, value, sub, color }) => (
          <div key={label} className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-4">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
            <p className={`text-3xl font-bold mt-1 ${color}`}>{value}</p>
            <p className="text-xs text-gray-400 mt-0.5">{sub}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Plan breakdown bar chart */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-5">Active by Plan</h3>
          <div className="space-y-3">
            {PLAN_ORDER.map((plan) => {
              const count = data.byPlan[plan] ?? 0;
              const pct = Math.round((count / maxPlanCount) * 100);
              return (
                <div key={plan}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-600">{plan}</span>
                    <span className="font-medium text-gray-900">{count}</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${PLAN_BAR_COLORS[plan] ?? "bg-gray-400"}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Status breakdown */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <h3 className="text-sm font-semibold text-gray-900 mb-5">All Subscription Statuses</h3>
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(data.byStatus).map(([status, count]) => (
              <div key={status} className="border border-gray-100 rounded-lg p-3">
                <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[status] ?? "bg-gray-100 text-gray-600"}`}>
                  {status}
                </span>
                <p className="text-2xl font-bold text-gray-900 mt-2">{count}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recent events */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-900">Recent Subscription Events</h3>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/50">
              <th className="text-left px-6 py-3 font-medium text-gray-500">Organization</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Plan</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Status</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {data.recentEvents.map((e) => (
              <tr key={e.id} className="hover:bg-gray-50/50">
                <td className="px-6 py-3 font-medium text-gray-900">
                  {e.organization?.name ?? "—"}
                </td>
                <td className="px-6 py-3 text-gray-600">{e.plan}</td>
                <td className="px-6 py-3">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[e.status] ?? "bg-gray-100 text-gray-600"}`}>
                    {e.status}
                  </span>
                </td>
                <td className="px-6 py-3 text-gray-500 text-xs">
                  {new Date(e.createdAt).toLocaleDateString()}
                </td>
              </tr>
            ))}
            {data.recentEvents.length === 0 && (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-gray-400 text-sm">No subscription events yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
