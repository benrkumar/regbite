import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@regbite/database";
import { clerkClient } from "@clerk/nextjs/server";

const DEMO_EMAILS: Record<string, string> = {
  admin: "demo@regbite.com",
  viewer: "viewer@regbite.com",
};

/**
 * GET /api/demo?role=admin|viewer
 *
 * Creates a Clerk short-lived sign-in token for the demo user and redirects
 * to the Clerk sign-in page so the user is auto-signed in without typing credentials.
 *
 * Falls back to /sign-in with pre-filled email if the Clerk user is a placeholder
 * (seed was run without CLERK_SECRET_KEY).
 */
export async function GET(req: NextRequest) {
  const role = req.nextUrl.searchParams.get("role") ?? "admin";
  const email = DEMO_EMAILS[role] ?? DEMO_EMAILS.admin;
  const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";

  // Look up the demo member in DB
  const member = await prisma.member.findFirst({
    where: { email, deletedAt: null },
    select: { clerkUserId: true },
  });

  if (!member) {
    return NextResponse.redirect(
      `${appUrl}/sign-in?hint=${encodeURIComponent("Demo account not found — run pnpm db:demo first")}`
    );
  }

  // If clerkUserId is a placeholder, fall back to showing the sign-in page
  if (member.clerkUserId.startsWith("demo_") && member.clerkUserId.endsWith("_placeholder")) {
    return NextResponse.redirect(
      `${appUrl}/sign-in?hint=${encodeURIComponent("Enter demo credentials below")}&email=${encodeURIComponent(email)}`
    );
  }

  try {
    const client = await clerkClient();
    const { token } = await client.signInTokens.createSignInToken({
      userId: member.clerkUserId,
      expiresInSeconds: 300,
    });

    // Clerk frontends accept ?__clerk_ticket= to auto-sign in
    return NextResponse.redirect(`${appUrl}/sign-in?__clerk_ticket=${token}`);
  } catch (err) {
    console.error("[demo route] Failed to create sign-in token:", err);
    // Fall back to regular sign-in page
    return NextResponse.redirect(
      `${appUrl}/sign-in?email=${encodeURIComponent(email)}`
    );
  }
}
