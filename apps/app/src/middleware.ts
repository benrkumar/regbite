import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';
import { NextResponse, type NextRequest } from 'next/server';

const isPublicRoute = createRouteMatcher([
  '/sign-in(.*)',
  '/sign-up(.*)',
  '/api/webhooks(.*)',
]);

// Clerk handler — created at module load (placeholder keys are format-valid so no throw)
const withClerkAuth = clerkMiddleware(async (auth, req) => {
  if (!isPublicRoute(req)) {
    await auth.protect();
  }
});

export default function middleware(req: NextRequest) {
  // Bypass Clerk when AUTH_BYPASS=true (set this env var when Clerk credentials
  // are not yet configured — avoids the "dev-browser-missing" 404 loop with
  // placeholder pk_test_* keys that don't back a real Clerk application).
  if (process.env.AUTH_BYPASS === 'true') {
    return NextResponse.next();
  }
  return withClerkAuth(req as Parameters<typeof withClerkAuth>[0]);
}

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
};
