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

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Ingredients", href: "/ingredients", icon: Search },
  { name: "Formulations", href: "/formulations", icon: FlaskConical },
  { name: "Label Validator", href: "/label-validator", icon: FileCheck },
  { name: "Claims Checker", href: "/claims", icon: MessageSquareWarning },
  { name: "NDI Navigator", href: "/ndi", icon: FileText },
  { name: "cGMP Readiness", href: "/cgmp", icon: ClipboardCheck },
  { name: "State Compliance", href: "/state-compliance", icon: ShieldAlert },
  { name: "Import Intel", href: "/import-intel", icon: Plane },
  { name: "Regulatory Feed", href: "/regulatory", icon: Newspaper },
  { name: "Settings", href: "/settings", icon: Settings },
  { name: "Billing", href: "/billing", icon: CreditCard },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="flex h-screen">
      <aside className="w-64 bg-[#0D4F3C] text-white flex flex-col border-r border-[#0A3D2E]">
        <div className="p-6 border-b border-[#0A3D2E]">
          <h1 className="text-xl font-bold text-white">RegBite US</h1>
          <p className="text-xs text-green-100/60 mt-1">FDA Compliance Platform</p>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          {navigation.map((item) => {
            const isActive = pathname === item.href || pathname?.startsWith(item.href + "/");
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
