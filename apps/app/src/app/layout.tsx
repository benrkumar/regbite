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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider>
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
    </ClerkProvider>
  );
}
