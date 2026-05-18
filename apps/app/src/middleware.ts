import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';
import { NextResponse } from 'next/server';
import type { NextRequest, NextFetchEvent } from 'next/server';

const isPublicRoute = createRouteMatcher([
  '/sign-in(.*)',
  '/sign-up(.*)',
  '/api/webhooks(.*)',
]);

// Bypass all Clerk auth when AUTH_BYPASS=true.
// This avoids the "dev-browser-missing" redirect loop caused by placeholder
// pk_test_* keys that don't back a real Clerk application.
// Set AUTH_BYPASS=false (or remove it) once real Clerk credentials are set.
//
// IMPORTANT: ClerkProvider is ALSO conditionally skipped in layout.tsx when
// AUTH_BYPASS=true so the server doesn't attempt a JWKS fetch against the
// fake publishable-key domain on first render.
const clerkHandler = clerkMiddleware(async (auth, req) => {
  if (!isPublicRoute(req)) {
    await auth.protect();
  }
});

export default async function middleware(
  req: NextRequest,
  event: NextFetchEvent,
): Promise<Response> {
  if (process.env.AUTH_BYPASS === 'true') {
    return NextResponse.next();
  }
  return clerkHandler(req, event) as Promise<Response>;
}

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
};
