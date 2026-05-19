"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { DemoBanner } from "@/components/demo-banner";
import {
  LayoutDashboard,
  Search,
  FlaskConical,
  FileCheck,
  MessageSquareWarning,
  Newspaper,
  ClipboardCheck,
  FileText,
  Settings,
  CreditCard,
  ShieldAlert,
  Plane,
} from "lucide-react";

function buildNavigation(username: string) {
  return [
    { name: "Dashboard", href: `/${username}`, icon: LayoutDashboard },
    { name: "Ingredients", href: `/${username}/ingredients`, icon: Search },
    { name: "Formulations", href: `/${username}/formulations`, icon: FlaskConical },
    { name: "Label Validator", href: `/${username}/label-validator`, icon: FileCheck },
    { name: "Claims Checker", href: `/${username}/claims`, icon: MessageSquareWarning },
    { name: "NDI Navigator", href: `/${username}/ndi`, icon: FileText },
    { name: "cGMP Readiness", href: `/${username}/cgmp`, icon: ClipboardCheck },
    { name: "State Compliance", href: `/${username}/state-compliance`, icon: ShieldAlert },
    { name: "Import Intel", href: `/${username}/import-intel`, icon: Plane },
    { name: "Regulatory Feed", href: `/${username}/regulatory`, icon: Newspaper },
    { name: "Settings", href: `/${username}/settings`, icon: Settings },
    { name: "Billing", href: `/${username}/billing`, icon: CreditCard },
  ];
}

export function DashboardClientLayout({
  children,
  username,
}: {
  children: React.ReactNode;
  username: string;
}) {
  const pathname = usePathname();
  const navigation = buildNavigation(username);

  return (
    <div className="flex h-screen">
      <aside className="w-64 bg-[#0D4F3C] text-white flex flex-col border-r border-[#0A3D2E]">
        <div className="p-6 border-b border-[#0A3D2E]">
          <h1 className="text-xl font-bold text-white">RegBite US</h1>
          <p className="text-xs text-green-100/60 mt-1">@{username}</p>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          {navigation.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== `/${username}` && pathname?.startsWith(item.href + "/"));
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-brand-600 text-white"
                    : "text-green-100/70 hover:bg-[#0A3D2E] hover:text-white"
                }`}
              >
                <item.icon className="h-4 w-4 flex-shrink-0" />
                {item.name}
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="flex-1 overflow-y-auto bg-[#F8FAFB] flex flex-col">
        <DemoBanner />
        <div className="p-8 flex-1">{children}</div>
      </main>
    </div>
  );
}
