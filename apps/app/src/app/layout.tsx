// Force dynamic so ClerkProvider is never evaluated during `next build`
// static prerendering (NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY may be absent at build time).
export const dynamic = "force-dynamic";

import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { Toaster } from "sonner";
import { Suspense } from "react";
import { PostHogProvider } from "@/components/posthog-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "RegBite US — Dietary Supplement Compliance",
  description:
    "Pre-formulation FDA compliance intelligence for US dietary supplements",
};

// When AUTH_BYPASS=true the Clerk middleware is also bypassed, which means
// ClerkProvider would try to fetch JWKS from the (fake) publishable-key domain
// and throw on the first server render.  Skip it entirely in bypass mode.
const AUTH_BYPASS = process.env.AUTH_BYPASS === "true";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const body = (
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

  if (AUTH_BYPASS) return body;

  return <ClerkProvider>{body}</ClerkProvider>;
}
