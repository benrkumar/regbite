"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function OrgSuspendButton({
  orgId,
  suspended,
}: {
  orgId: string;
  suspended: boolean;
}) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function toggle() {
    const confirm = window.confirm(
      suspended
        ? "Restore this organization? They will regain access."
        : "Suspend this organization? They will lose access."
    );
    if (!confirm) return;
    setLoading(true);
    await fetch(`/api/admin/orgs/${orgId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suspended: !suspended }),
    });
    setLoading(false);
    router.refresh();
  }

  return (
    <button
      onClick={toggle}
      disabled={loading}
      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 ${
        suspended
          ? "bg-green-600 text-white hover:bg-green-700"
          : "bg-red-600 text-white hover:bg-red-700"
      }`}
    >
      {loading ? "…" : suspended ? "Restore Organization" : "Suspend Organization"}
    </button>
  );
}
