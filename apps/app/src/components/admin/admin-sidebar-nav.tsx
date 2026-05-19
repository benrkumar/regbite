"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { name: "Overview", href: "/admin" },
  { name: "Orgs", href: "/admin/orgs" },
  { name: "Revenue", href: "/admin/revenue" },
  { name: "Activity", href: "/admin/activity" },
  { name: "Users", href: "/admin/users" },
  { name: "Ingredients", href: "/admin/ingredients" },
  { name: "Scraper", href: "/admin/scraper" },
  { name: "Regulatory", href: "/admin/regulatory" },
  { name: "Compliance Rules", href: "/admin/compliance-rules" },
];

export function AdminSidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="flex-1 p-3 space-y-0.5">
      {NAV.map((item) => {
        const isActive =
          item.href === "/admin"
            ? pathname === "/admin"
            : pathname === item.href || pathname?.startsWith(item.href + "/");
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center px-3 py-2 rounded-md text-sm transition-colors ${
              isActive
                ? "bg-[#0A3D2E] text-white font-medium"
                : "text-green-100/70 hover:bg-[#0A3D2E] hover:text-white"
            }`}
          >
            {item.name}
          </Link>
        );
      })}
    </nav>
  );
}
