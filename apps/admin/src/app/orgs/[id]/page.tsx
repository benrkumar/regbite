import { notFound } from "next/navigation";
import { prisma } from "@regbite/database";
import { OrgPlanChanger } from "./org-plan-changer";
import { OrgSuspendButton } from "./org-suspend-button";

export const dynamic = "force-dynamic";

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

const ROLE_BADGE: Record<string, string> = {
  SUPER_ADMIN: "bg-red-100 text-red-700",
  ACCOUNT_ADMIN: "bg-teal-100 text-teal-700",
  EDITOR: "bg-blue-100 text-blue-700",
  VIEWER: "bg-gray-100 text-gray-600",
  CONSULTANT: "bg-purple-100 text-purple-700",
};

export default async function OrgDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const org = await prisma.organization.findUnique({
    where: { id },
    select: {
      id: true,
      name: true,
      slug: true,
      plan: true,
      deletedAt: true,
      createdAt: true,
      members: {
        where: { deletedAt: null },
        select: { id: true, email: true, name: true, role: true, createdAt: true },
        orderBy: { createdAt: "asc" },
      },
      formulations: {
        take: 10,
        orderBy: { createdAt: "desc" },
        select: { id: true, productName: true, status: true, complianceScore: true, createdAt: true },
      },
      complianceChecks: {
        take: 10,
        orderBy: { createdAt: "desc" },
        select: {
          id: true,
          checkType: true,
          status: true,
          overallScore: true,
          createdAt: true,
          formulation: { select: { productName: true } },
        },
      },
      subscriptions: {
        orderBy: { createdAt: "desc" },
        take: 1,
        select: { id: true, status: true, plan: true, currentPeriodEnd: true },
      },
    },
  });

  if (!org) notFound();

  const suspended = org.deletedAt !== null;
  const subscription = org.subscriptions[0] ?? null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">{org.name}</h1>
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-medium ${PLAN_BADGE[org.plan] ?? "bg-gray-100 text-gray-600"}`}>
              {org.plan}
            </span>
            {suspended && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">
                SUSPENDED
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500 mt-1">
            /{org.slug} · Created {new Date(org.createdAt).toLocaleDateString()}
            {subscription && (
              <> · Subscription: <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${STATUS_BADGE[subscription.status] ?? "bg-gray-100 text-gray-600"}`}>
                {subscription.status}
              </span></>
            )}
          </p>
        </div>
        <a href="/orgs" className="text-sm text-[#0D4F3C] hover:underline">← Back to Orgs</a>
      </div>

      {/* 2-col grid */}
      <div className="grid grid-cols-2 gap-6">
        {/* Members */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
          <div className="px-6 py-4 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900">Members ({org.members.length})</h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/50">
                <th className="text-left px-5 py-2.5 font-medium text-gray-500">Member</th>
                <th className="text-left px-5 py-2.5 font-medium text-gray-500">Role</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {org.members.map((m) => (
                <tr key={m.id}>
                  <td className="px-5 py-2.5">
                    <div className="font-medium text-gray-800 text-xs">{m.name ?? m.email}</div>
                    {m.name && <div className="text-gray-400 text-xs">{m.email}</div>}
                  </td>
                  <td className="px-5 py-2.5">
                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${ROLE_BADGE[m.role] ?? "bg-gray-100 text-gray-600"}`}>
                      {m.role}
                    </span>
                  </td>
                </tr>
              ))}
              {org.members.length === 0 && (
                <tr><td colSpan={2} className="px-5 py-6 text-center text-gray-400 text-xs">No members</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Recent formulations */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
          <div className="px-6 py-4 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900">Recent Formulations</h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/50">
                <th className="text-left px-5 py-2.5 font-medium text-gray-500">Product</th>
                <th className="text-left px-5 py-2.5 font-medium text-gray-500">Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {org.formulations.map((f) => (
                <tr key={f.id}>
                  <td className="px-5 py-2.5">
                    <div className="text-xs font-medium text-gray-800">{f.productName}</div>
                    <div className="text-xs text-gray-400">{f.status}</div>
                  </td>
                  <td className="px-5 py-2.5">
                    {f.complianceScore != null ? (
                      <span className={`text-xs font-bold ${f.complianceScore >= 80 ? "text-green-600" : f.complianceScore >= 60 ? "text-yellow-600" : "text-red-600"}`}>
                        {f.complianceScore}
                      </span>
                    ) : <span className="text-gray-400 text-xs">—</span>}
                  </td>
                </tr>
              ))}
              {org.formulations.length === 0 && (
                <tr><td colSpan={2} className="px-5 py-6 text-center text-gray-400 text-xs">No formulations</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Check history */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-900">Recent Compliance Checks</h3>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/50">
              <th className="text-left px-5 py-2.5 font-medium text-gray-500">Product</th>
              <th className="text-left px-5 py-2.5 font-medium text-gray-500">Type</th>
              <th className="text-left px-5 py-2.5 font-medium text-gray-500">Status</th>
              <th className="text-left px-5 py-2.5 font-medium text-gray-500">Score</th>
              <th className="text-left px-5 py-2.5 font-medium text-gray-500">Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {org.complianceChecks.map((c) => (
              <tr key={c.id}>
                <td className="px-5 py-2.5 text-xs text-gray-700">{c.formulation?.productName ?? "—"}</td>
                <td className="px-5 py-2.5 text-xs text-gray-600">{c.checkType}</td>
                <td className="px-5 py-2.5 text-xs">{c.status}</td>
                <td className="px-5 py-2.5">
                  {c.overallScore != null ? (
                    <span className={`text-xs font-bold ${c.overallScore >= 80 ? "text-green-600" : c.overallScore >= 60 ? "text-yellow-600" : "text-red-600"}`}>
                      {c.overallScore}
                    </span>
                  ) : <span className="text-gray-400 text-xs">—</span>}
                </td>
                <td className="px-5 py-2.5 text-xs text-gray-400">{new Date(c.createdAt).toLocaleDateString()}</td>
              </tr>
            ))}
            {org.complianceChecks.length === 0 && (
              <tr><td colSpan={5} className="px-5 py-6 text-center text-gray-400 text-xs">No checks</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Danger zone */}
      <div className="bg-white rounded-xl border border-red-200 shadow-sm p-6">
        <h3 className="text-sm font-semibold text-red-700 mb-4">Danger Zone</h3>
        <div className="flex flex-wrap gap-6 items-start">
          <OrgPlanChanger orgId={org.id} currentPlan={org.plan} />
          <OrgSuspendButton orgId={org.id} suspended={suspended} />
        </div>
      </div>
    </div>
  );
}
