"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { name: "Overview", href: "/" },
  { name: "Orgs", href: "/orgs" },
  { name: "Revenue", href: "/revenue" },
  { name: "Activity", href: "/activity" },
  { name: "Users", href: "/users" },
  { name: "Ingredients", href: "/ingredients" },
  { name: "Scraper", href: "/scraper" },
  { name: "Regulatory", href: "/regulatory" },
  { name: "Compliance Rules", href: "/compliance-rules" },
];

export function AdminSidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="flex-1 p-3 space-y-0.5">
      {NAV.map((item) => {
        const isActive =
          item.href === "/"
            ? pathname === "/"
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
