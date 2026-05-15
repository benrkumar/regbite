"use client";

import { useState } from "react";
import Link from "next/link";
import {
  FlaskConical,
  ShieldCheck,
  Users,
  Copy,
  Check,
  ExternalLink,
  LayoutDashboard,
  Search,
  FileCheck,
  MessageSquareWarning,
} from "lucide-react";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "https://app.regbite.com";

const DEMO_ACCOUNTS = [
  {
    role: "admin",
    label: "Account Admin",
    email: "demo@regbite.com",
    password: "Demo1234!",
    description: "Full access — view, create, and manage formulations, run compliance checks, manage team members, and access billing.",
    badge: "bg-teal-100 text-teal-700",
    icon: ShieldCheck,
  },
  {
    role: "viewer",
    label: "Viewer (Read-Only)",
    email: "viewer@regbite.com",
    password: "Demo1234!",
    description: "Read-only access — view formulations and compliance results without the ability to create or modify anything.",
    badge: "bg-gray-100 text-gray-600",
    icon: Users,
  },
];

const DEMO_DATA = [
  { icon: FlaskConical, label: "3 formulations", sub: "MultiVit PRO · Pre-Workout X · Sleep Formula" },
  { icon: ShieldCheck, label: "3 completed compliance checks", sub: "Scores: 87 · 62 · 91" },
  { icon: Search, label: "Full ingredient database", sub: "200+ ingredients with FDA status & NIH ULs" },
  { icon: FileCheck, label: "Label validator", sub: "21 CFR 101.36 rules" },
  { icon: MessageSquareWarning, label: "Claims checker", sub: "Structure/function vs. disease claims" },
  { icon: LayoutDashboard, label: "GROWTH plan features", sub: "All 9 compliance modules enabled" },
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="p-1 rounded hover:bg-gray-100 transition-colors text-gray-400 hover:text-gray-600"
      title="Copy to clipboard"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

function DemoCard({
  account,
}: {
  account: (typeof DEMO_ACCOUNTS)[number];
}) {
  const Icon = account.icon;
  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8 flex flex-col gap-6">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-[#0D4F3C]/10 flex items-center justify-center">
            <Icon className="h-5 w-5 text-[#0D4F3C]" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">{account.label}</h3>
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium mt-1 ${account.badge}`}>
              {account.role === "admin" ? "GROWTH plan" : "Read-only"}
            </span>
          </div>
        </div>
      </div>

      <p className="text-sm text-gray-600 leading-relaxed">{account.description}</p>

      {/* Credentials */}
      <div className="bg-gray-50 rounded-xl border border-gray-200 divide-y divide-gray-200">
        <div className="flex items-center justify-between px-4 py-3">
          <div>
            <p className="text-xs text-gray-400 mb-0.5">Email</p>
            <p className="text-sm font-mono font-medium text-gray-800">{account.email}</p>
          </div>
          <CopyButton text={account.email} />
        </div>
        <div className="flex items-center justify-between px-4 py-3">
          <div>
            <p className="text-xs text-gray-400 mb-0.5">Password</p>
            <p className="text-sm font-mono font-medium text-gray-800">{account.password}</p>
          </div>
          <CopyButton text={account.password} />
        </div>
      </div>

      {/* CTA buttons */}
      <div className="flex flex-col gap-2">
        <a
          href={`${APP_URL}/api/demo?role=${account.role}`}
          className="flex items-center justify-center gap-2 bg-[#0D4F3C] text-white rounded-lg px-4 py-2.5 text-sm font-medium hover:bg-[#0A3D2E] transition-colors"
        >
          <ExternalLink className="h-4 w-4" />
          Launch Demo (one-click)
        </a>
        <a
          href={`${APP_URL}/sign-in`}
          className="flex items-center justify-center gap-2 border border-gray-200 text-gray-700 rounded-lg px-4 py-2.5 text-sm font-medium hover:bg-gray-50 transition-colors"
          target="_blank"
          rel="noopener noreferrer"
        >
          Sign in manually with credentials above
        </a>
      </div>
    </div>
  );
}

export default function DemoPage() {
  return (
    <div className="min-h-screen bg-[#F8FAFB]">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur border-b border-gray-100">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" className="font-bold text-gray-900">RegBite US</Link>
          <Link href="/pricing" className="text-sm text-gray-600 hover:text-gray-900">See Pricing →</Link>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-16">
        {/* Hero */}
        <div className="text-center mb-14">
          <div className="inline-flex items-center gap-2 bg-[#0D4F3C]/10 text-[#0D4F3C] px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wide mb-4">
            Interactive Demo
          </div>
          <h1 className="text-4xl font-black text-gray-900 mb-4">
            Try RegBite US — no signup required
          </h1>
          <p className="text-lg text-gray-500 max-w-xl mx-auto">
            A pre-populated account for Apex Nutrition. Explore formulations, compliance checks, the label validator, and all 9 modules.
          </p>
        </div>

        {/* Demo data summary */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8 mb-10">
          <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide mb-5">
            What's pre-loaded in the demo
          </h2>
          <div className="grid grid-cols-2 gap-3">
            {DEMO_DATA.map(({ icon: Icon, label, sub }) => (
              <div key={label} className="flex items-start gap-3">
                <div className="h-8 w-8 rounded-lg bg-[#0D4F3C]/10 flex items-center justify-center shrink-0 mt-0.5">
                  <Icon className="h-4 w-4 text-[#0D4F3C]" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-800">{label}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{sub}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Account cards */}
        <div className="grid grid-cols-2 gap-6 mb-10">
          {DEMO_ACCOUNTS.map((account) => (
            <DemoCard key={account.role} account={account} />
          ))}
        </div>

        {/* Footnote */}
        <p className="text-center text-xs text-gray-400">
          Demo data resets periodically. All compliance checks are based on real FDA regulations.{" "}
          <Link href="/pricing" className="underline hover:text-gray-600">Start your own account →</Link>
        </p>
      </main>
    </div>
  );
}
