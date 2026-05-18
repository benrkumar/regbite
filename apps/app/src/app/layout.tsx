// force-dynamic: ensures this layout is never statically prerendered at build
// time when NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY may be absent.
export const dynamic = "force-dynamic";

import type { Metadata } from "next";
import { Toaster } from "sonner";
import { Suspense } from "react";
import { PostHogProvider } from "@/components/posthog-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "RegBite US — Dietary Supplement Compliance",
  description:
    "Pre-formulation FDA compliance intelligence for US dietary supplements",
};

// ClerkProvider is intentionally omitted until real Clerk credentials are set.
//
// With placeholder pk_test_* keys, ClerkProvider attempts a JWKS network fetch
// against test.clerk.accounts.dev on every server render, which throws an
// unhandled error and crashes the Node.js process.
//
// TO RE-ENABLE AUTH: wrap the returned JSX in <ClerkProvider> once
// NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY are configured.

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Suspense fallback={null}>
          <PostHogProvider>
            {children}
          </PostHogProvider>
        </Suspense>
        <Toaster position="top-right" richColors />
      </body>
    </html>
  );
}
