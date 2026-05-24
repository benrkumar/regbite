"use client";

import { useUser } from "@clerk/nextjs";
import { Component, type ReactNode } from "react";

const DEMO_EMAILS = ["demo@regbite.com", "viewer@regbite.com"];

// Silently absorbs any Clerk context errors (e.g. when ClerkProvider is absent)
class SafeClerkBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) return null;
    return this.props.children as ReactNode;
  }
}

function DemoBannerContent() {
  const { user } = useUser();
  const email = user?.primaryEmailAddress?.emailAddress ?? "";

  if (!DEMO_EMAILS.includes(email)) return null;

  return (
    <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 text-xs text-amber-800 text-center font-medium">
      Demo account · Data may be reset periodically ·{" "}
      <a
        href={process.env.NEXT_PUBLIC_MARKETING_URL ?? "https://regbiteusa.com"}
        className="underline hover:text-amber-900"
      >
        Sign up for a real account →
      </a>
    </div>
  );
}

export function DemoBanner() {
  return (
    <SafeClerkBoundary>
      <DemoBannerContent />
    </SafeClerkBoundary>
  );
}
