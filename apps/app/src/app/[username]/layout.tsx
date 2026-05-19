// Force all user routes to be server-side rendered (never statically prerendered).
// This prevents build-time failures when NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is absent.
export const dynamic = "force-dynamic";

import { DashboardClientLayout } from "@/components/dashboard-client-layout";

export default async function UserLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ username: string }>;
}) {
  const { username } = await params;
  return <DashboardClientLayout username={username}>{children}</DashboardClientLayout>;
}
