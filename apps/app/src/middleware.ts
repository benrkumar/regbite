// ─── Clerk Auth Middleware ────────────────────────────────────────────────────
//
// STATUS: Disabled — waiting for real Clerk credentials to be set in Railway.
//
// With placeholder pk_test_* keys, clerkMiddleware redirects every request to
// test.clerk.accounts.dev (which returns 404 — no real Clerk app exists there).
//
// TO ENABLE:
//   1. Create a Clerk application at https://dashboard.clerk.com
//   2. Set NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY in Railway env
//      for the 'regbite' service.
//   3. In Clerk Dashboard → User settings, enable the "Username" field.
//   4. Uncomment the clerkMiddleware block below and delete the bypass block.
//
// ─────────────────────────────────────────────────────────────────────────────

// --- UNCOMMENT WHEN REAL CLERK KEYS ARE SET ---
//
// import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';
//
// // Public routes that don't require sign-in
// const isPublicRoute = createRouteMatcher([
//   '/',
//   '/sign-in(.*)',
//   '/sign-up(.*)',
//   '/api/webhooks(.*)',
// ]);
//
// export default clerkMiddleware(async (auth, req) => {
//   if (!isPublicRoute(req)) await auth.protect();
// });
//
// export const config = {
//   matcher: [
//     '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
//     '/(api|trpc)(.*)',
//   ],
// };

// --- BYPASS (remove once Clerk keys are configured) ---
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export default function middleware(_req: NextRequest) {
  return NextResponse.next();
}

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
};
