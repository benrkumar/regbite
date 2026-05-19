import { NextRequest, NextResponse } from "next/server";

/**
 * Basic Auth middleware for the admin service.
 * Set ADMIN_BASIC_AUTH_USER and ADMIN_BASIC_AUTH_PASS in Railway env vars.
 * Bypass is disabled when both env vars are set.
 */
export function middleware(req: NextRequest) {
  const user = process.env.ADMIN_BASIC_AUTH_USER;
  const pass = process.env.ADMIN_BASIC_AUTH_PASS;

  // If env vars are not configured, block all access in production
  if (!user || !pass) {
    if (process.env.NODE_ENV === "production") {
      return new NextResponse("Admin access requires ADMIN_BASIC_AUTH_USER and ADMIN_BASIC_AUTH_PASS to be set.", {
        status: 503,
        headers: { "Content-Type": "text/plain" },
      });
    }
    // In development, allow access without auth
    return NextResponse.next();
  }

  const authHeader = req.headers.get("authorization");

  if (authHeader && authHeader.startsWith("Basic ")) {
    const base64 = authHeader.slice("Basic ".length);
    const decoded = Buffer.from(base64, "base64").toString("utf-8");
    const colonIndex = decoded.indexOf(":");
    const reqUser = decoded.slice(0, colonIndex);
    const reqPass = decoded.slice(colonIndex + 1);

    if (reqUser === user && reqPass === pass) {
      return NextResponse.next();
    }
  }

  return new NextResponse("Unauthorized", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="RegBite Admin"' },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
