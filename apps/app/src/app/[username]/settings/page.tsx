"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Lock, Building2, Users, Bell } from "lucide-react";

// ── Types ────────────────────────────────────────────────────────────────────

interface OrgData {
  id: string;
  name: string;
  slug: string;
  plan: string;
  createdAt: string;
  _count: { members: number };
}

interface MemberRow {
  id: string;
  email: string;
  name: string | null;
  role: string;
  createdAt: string;
}

const ROLE_COLORS: Record<string, string> = {
  SUPER_ADMIN: "bg-red-100 text-red-700",
  ACCOUNT_ADMIN: "bg-teal-100 text-teal-700",
  EDITOR: "bg-blue-100 text-blue-700",
  VIEWER: "bg-gray-100 text-gray-600",
  CONSULTANT: "bg-purple-100 text-purple-700",
};

const EDITABLE_ROLES = ["ACCOUNT_ADMIN", "EDITOR", "VIEWER", "CONSULTANT"];

// ── Org tab ──────────────────────────────────────────────────────────────────

const orgSchema = z.object({ name: z.string().min(1, "Name required").max(100) });
type OrgForm = z.infer<typeof orgSchema>;

function OrganizationTab({ org, onUpdated }: { org: OrgData; onUpdated: (o: OrgData) => void }) {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<OrgForm>({
    resolver: zodResolver(orgSchema),
    defaultValues: { name: org.name },
  });

  async function onSubmit(data: OrgForm) {
    const res = await fetch("/api/settings/organization", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (res.ok) {
      const updated = await res.json();
      onUpdated(updated);
      toast.success("Organization updated");
    } else {
      toast.error("Failed to update organization");
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6 max-w-lg">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Organization Name</label>
        <input
          {...register("name")}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        {errors.name && <p className="text-xs text-red-500 mt-1">{errors.name.message}</p>}
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Slug</label>
        <div className="flex items-center gap-2 border border-gray-200 rounded-lg px-3 py-2 bg-gray-50">
          <Lock className="h-3.5 w-3.5 text-gray-400" />
          <span className="text-sm text-gray-500">{org.slug}</span>
        </div>
        <p className="text-xs text-gray-400 mt-1">Slug cannot be changed after creation.</p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Current Plan</label>
          <div className="border border-gray-200 rounded-lg px-3 py-2 bg-gray-50 flex items-center justify-between">
            <span className="text-sm font-medium">{org.plan}</span>
            <a href="/billing" className="text-xs text-brand-600 hover:underline">Upgrade</a>
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Members</label>
          <div className="border border-gray-200 rounded-lg px-3 py-2 bg-gray-50">
            <span className="text-sm">{org._count.members} members</span>
          </div>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Member Since</label>
        <div className="border border-gray-200 rounded-lg px-3 py-2 bg-gray-50">
          <span className="text-sm text-gray-500">
            {new Date(org.createdAt).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}
          </span>
        </div>
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        className="bg-brand-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors"
      >
        {isSubmitting ? "Saving…" : "Save Changes"}
      </button>
    </form>
  );
}

// ── Team tab ─────────────────────────────────────────────────────────────────

const inviteSchema = z.object({
  email: z.string().email("Valid email required"),
  role: z.enum(["ACCOUNT_ADMIN", "EDITOR", "VIEWER", "CONSULTANT"]),
});
type InviteForm = z.infer<typeof inviteSchema>;

function TeamTab({ members: initial }: { members: MemberRow[] }) {
  const [members, setMembers] = useState(initial);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<InviteForm>({
    resolver: zodResolver(inviteSchema),
    defaultValues: { role: "EDITOR" },
  });

  async function changeRole(id: string, role: string) {
    const res = await fetch(`/api/settings/team/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    if (res.ok) {
      const updated = await res.json();
      setMembers((prev) => prev.map((m) => (m.id === id ? { ...m, role: updated.role } : m)));
      toast.success("Role updated");
    } else {
      toast.error("Failed to update role");
    }
  }

  async function removeMember(id: string) {
    if (!confirm("Remove this team member?")) return;
    setRemovingId(id);
    const res = await fetch(`/api/settings/team/${id}`, { method: "DELETE" });
    if (res.ok) {
      setMembers((prev) => prev.filter((m) => m.id !== id));
      toast.success("Member removed");
    } else {
      const data = await res.json();
      toast.error(data.error ?? "Failed to remove member");
    }
    setRemovingId(null);
  }

  async function sendInvite(data: InviteForm) {
    const res = await fetch("/api/settings/team/invite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (res.ok) {
      toast.success(`Invite sent to ${data.email}`);
      reset();
    } else {
      toast.error("Failed to send invite");
    }
  }

  return (
    <div className="space-y-8">
      {/* Members table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-900">Team Members ({members.length})</h3>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/50">
              <th className="text-left px-6 py-3 font-medium text-gray-500">Member</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Role</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Joined</th>
              <th className="text-right px-6 py-3 font-medium text-gray-500">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {members.map((m) => (
              <tr key={m.id} className="hover:bg-gray-50/50">
                <td className="px-6 py-3">
                  <div className="font-medium text-gray-900">{m.name ?? m.email}</div>
                  {m.name && <div className="text-xs text-gray-400">{m.email}</div>}
                </td>
                <td className="px-6 py-3">
                  {EDITABLE_ROLES.includes(m.role) ? (
                    <select
                      value={m.role}
                      onChange={(e) => changeRole(m.id, e.target.value)}
                      className="text-xs border border-gray-200 rounded px-2 py-1 bg-white focus:outline-none focus:ring-1 focus:ring-brand-500"
                    >
                      {EDITABLE_ROLES.map((r) => (
                        <option key={r} value={r}>{r.replace("_", " ")}</option>
                      ))}
                    </select>
                  ) : (
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${ROLE_COLORS[m.role] ?? "bg-gray-100 text-gray-600"}`}>
                      {m.role.replace("_", " ")}
                    </span>
                  )}
                </td>
                <td className="px-6 py-3 text-gray-500 text-xs">
                  {new Date(m.createdAt).toLocaleDateString()}
                </td>
                <td className="px-6 py-3 text-right">
                  {EDITABLE_ROLES.includes(m.role) && (
                    <button
                      onClick={() => removeMember(m.id)}
                      disabled={removingId === m.id}
                      className="text-xs text-red-500 hover:text-red-700 disabled:opacity-50"
                    >
                      {removingId === m.id ? "Removing…" : "Remove"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Invite form */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Invite Team Member</h3>
        <form onSubmit={handleSubmit(sendInvite)} className="flex gap-3 items-start">
          <div className="flex-1">
            <input
              {...register("email")}
              type="email"
              placeholder="colleague@company.com"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            {errors.email && <p className="text-xs text-red-500 mt-1">{errors.email.message}</p>}
          </div>
          <div>
            <select
              {...register("role")}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              {EDITABLE_ROLES.map((r) => (
                <option key={r} value={r}>{r.replace("_", " ")}</option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={isSubmitting}
            className="bg-brand-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors whitespace-nowrap"
          >
            {isSubmitting ? "Sending…" : "Send Invite"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Notifications tab ────────────────────────────────────────────────────────

function NotificationsTab({ orgId }: { orgId: string }) {
  const [alerts, setAlerts] = useState(true);
  const [digest, setDigest] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(`notif_${orgId}`);
      if (stored) {
        const prefs = JSON.parse(stored);
        setAlerts(prefs.alerts ?? true);
        setDigest(prefs.digest ?? false);
      }
    } catch {}
  }, [orgId]);

  function save(key: string, value: boolean) {
    const prefs = { alerts, digest, [key]: value };
    localStorage.setItem(`notif_${orgId}`, JSON.stringify(prefs));
    toast.success("Preferences saved");
  }

  return (
    <div className="space-y-4 max-w-lg">
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm divide-y divide-gray-100">
        <div className="flex items-center justify-between px-6 py-4">
          <div>
            <p className="text-sm font-medium text-gray-900">Compliance Alert Emails</p>
            <p className="text-xs text-gray-500 mt-0.5">Receive emails when new compliance issues are detected</p>
          </div>
          <button
            role="switch"
            aria-checked={alerts}
            onClick={() => { setAlerts(!alerts); save("alerts", !alerts); }}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${alerts ? "bg-brand-600" : "bg-gray-200"}`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${alerts ? "translate-x-6" : "translate-x-1"}`} />
          </button>
        </div>
        <div className="flex items-center justify-between px-6 py-4">
          <div>
            <p className="text-sm font-medium text-gray-900">Weekly Regulatory Digest</p>
            <p className="text-xs text-gray-500 mt-0.5">Monday morning summary of new FDA/FTC changes</p>
          </div>
          <button
            role="switch"
            aria-checked={digest}
            onClick={() => { setDigest(!digest); save("digest", !digest); }}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${digest ? "bg-brand-600" : "bg-gray-200"}`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${digest ? "translate-x-6" : "translate-x-1"}`} />
          </button>
        </div>
      </div>
      <p className="text-xs text-gray-400">Preferences are stored locally in this browser. Server-side sync coming soon.</p>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const TABS = [
  { id: "organization", label: "Organization", icon: Building2 },
  { id: "team", label: "Team", icon: Users },
  { id: "notifications", label: "Notifications", icon: Bell },
] as const;
type TabId = (typeof TABS)[number]["id"];

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("organization");
  const [org, setOrg] = useState<OrgData | null>(null);
  const [members, setMembers] = useState<MemberRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch("/api/settings/organization").then((r) => r.json()),
      fetch("/api/settings/team").then((r) => r.json()),
    ]).then(([orgData, membersData]) => {
      setOrg(orgData);
      setMembers(Array.isArray(membersData) ? membersData : []);
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
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Settings</h1>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-gray-200 mb-8">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              activeTab === id
                ? "border-brand-600 text-brand-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "organization" && org && (
        <OrganizationTab org={org} onUpdated={setOrg} />
      )}
      {activeTab === "team" && (
        <TeamTab members={members} />
      )}
      {activeTab === "notifications" && org && (
        <NotificationsTab orgId={org.id} />
      )}
    </div>
  );
}
