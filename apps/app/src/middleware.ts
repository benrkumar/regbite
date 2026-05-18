import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Clerk auth is intentionally disabled until real credentials are configured.
//
// With placeholder pk_test_* keys, clerkMiddleware redirects every request to
// test.clerk.accounts.dev (Clerk's dev-browser setup), which returns 404
// because no real Clerk application exists there.
//
// TO RE-ENABLE AUTH:
//   1. Create a Clerk application at https://dashboard.clerk.com
//   2. Set NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY in Railway
//   3. Replace this file's contents with the Clerk middleware:
//
//      import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';
//      const isPublicRoute = createRouteMatcher(['/sign-in(.*)', '/sign-up(.*)', '/api/webhooks(.*)']);
//      export default clerkMiddleware(async (auth, req) => {
//        if (!isPublicRoute(req)) await auth.protect();
//      });
//      export const config = { matcher: [...] };

export default function middleware(_req: NextRequest) {
  return NextResponse.next();
}

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
};
