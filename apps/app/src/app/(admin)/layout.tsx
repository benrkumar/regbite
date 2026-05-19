export const dynamic = "force-dynamic";

import { AdminSidebarNav } from "@/components/admin/admin-sidebar-nav";

// TODO: Once Clerk is configured, replace the bypass below with real role check:
//
//   import { auth } from "@clerk/nextjs/server";
//   const { sessionClaims } = await auth();
//   if (sessionClaims?.metadata?.role !== "SUPER_ADMIN") {
//     redirect("/sign-in");
//   }
//
// For now, /admin/* is not linked publicly — security through obscurity until Clerk lands.

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen bg-gray-950 text-white antialiased">
      <aside className="w-56 bg-[#0D4F3C] border-r border-[#0A3D2E] flex flex-col shrink-0">
        <div className="p-5 border-b border-[#0A3D2E]">
          <p className="text-sm font-bold text-white">RegBite US</p>
          <p className="text-xs text-green-100/60 mt-0.5">Superadmin</p>
        </div>
        <AdminSidebarNav />
        <div className="p-4 border-t border-[#0A3D2E]">
          <p className="text-xs text-green-100/40">Internal use only</p>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto bg-gray-950">
        <div className="p-8">{children}</div>
      </main>
    </div>
  );
}
