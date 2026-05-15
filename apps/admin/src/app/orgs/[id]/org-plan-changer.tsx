"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const PLANS = ["STARTER", "GROWTH", "PROFESSIONAL", "ENTERPRISE", "CONSULTANT"] as const;

export function OrgPlanChanger({
  orgId,
  currentPlan,
}: {
  orgId: string;
  currentPlan: string;
}) {
  const router = useRouter();
  const [plan, setPlan] = useState(currentPlan);
  const [saving, setSaving] = useState(false);

  async function apply() {
    setSaving(true);
    await fetch(`/api/orgs/${orgId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan }),
    });
    setSaving(false);
    router.refresh();
  }

  return (
    <div className="flex items-center gap-3">
      <label className="text-xs font-medium text-gray-700">Change Plan</label>
      <select
        value={plan}
        onChange={(e) => setPlan(e.target.value)}
        className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#0D4F3C]/30"
      >
        {PLANS.map((p) => (
          <option key={p} value={p}>{p}</option>
        ))}
      </select>
      <button
        onClick={apply}
        disabled={saving || plan === currentPlan}
        className="bg-[#0D4F3C] text-white px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-[#0A3D2E] disabled:opacity-50 transition-colors"
      >
        {saving ? "Saving…" : "Apply"}
      </button>
    </div>
  );
}
