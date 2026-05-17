// Force all dashboard routes to be server-side rendered (never statically prerendered).
// This prevents build-time failures when NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is absent.
export const dynamic = "force-dynamic";

import { DashboardClientLayout } from "@/components/dashboard-client-layout";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardClientLayout>{children}</DashboardClientLayout>;
}
