import type { Metadata } from "next";
import "./globals.css";
import { AdminSidebarNav } from "@/components/admin-sidebar-nav";

export const metadata: Metadata = {
  title: "RegBite US — Admin",
  description: "Internal admin panel for RegBite US",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-[#F8FAFB] text-gray-900 antialiased min-h-screen">
        <div className="flex h-screen">
          <aside className="w-56 bg-[#0D4F3C] border-r border-[#0A3D2E] flex flex-col">
            <div className="p-5 border-b border-[#0A3D2E]">
              <p className="text-sm font-bold text-white">RegBite US</p>
              <p className="text-xs text-green-100/60 mt-0.5">Admin Panel</p>
            </div>
            <AdminSidebarNav />
            <div className="p-4 border-t border-[#0A3D2E]">
              <p className="text-xs text-green-100/40">Internal use only</p>
            </div>
          </aside>
          <main className="flex-1 overflow-y-auto bg-[#F8FAFB]">
            <div className="p-8">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
