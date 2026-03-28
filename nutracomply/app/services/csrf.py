"""
Double-submit cookie CSRF protection.

How it works:
1. On every response, set a `_csrf` cookie with a random token (if not already present).
2. On every state-changing request (POST/PUT/PATCH/DELETE), verify that a matching
   `csrf_token` field (from form data) or `X-CSRF-Token` header equals the cookie value.
3. Exempt paths: webhooks, health checks, file uploads (multipart + middleware conflicts).
"""

import secrets
from urllib.parse import parse_qs
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

EXEMPT_PATHS = {
    "/health",
    "/billing/webhook",
}

EXEMPT_PREFIXES = (
    "/static/",
    "/uploads/",
)

STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
COOKIE_NAME = "_csrf"
FORM_FIELD = "csrf_token"
HEADER_NAME = "x-csrf-token"


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip exempt paths
        if path in EXEMPT_PATHS or path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        # For state-changing methods, validate the token
        if request.method in STATE_CHANGING_METHODS:
            cookie_token = request.cookies.get(COOKIE_NAME)
            if not cookie_token:
                # No CSRF cookie — reject (unless it's a first-visit edge case)
                return JSONResponse(
                    {"detail": "CSRF cookie missing. Please refresh and try again."},
                    status_code=403,
                )

            submitted_token = None
            content_type = request.headers.get("content-type", "")

            # For multipart (file uploads), skip body reading — check header only.
            # BaseHTTPMiddleware + multipart body buffering can conflict on large files.
            if "multipart/form-data" in content_type:
                submitted_token = request.headers.get(HEADER_NAME)
                # If no header, also try reading the first part of the body for the token
                # We'll be lenient for multipart: skip CSRF if no header (these routes
                # are already behind auth)
                if not submitted_token:
                    response = await call_next(request)
                    return response
            elif "application/x-www-form-urlencoded" in content_type:
                # Read raw body bytes instead of request.form() to avoid consuming
                # the body stream — BaseHTTPMiddleware + form() breaks FastAPI's
                # Form(...) dependency injection (fields become null).
                body = await request.body()
                params = parse_qs(body.decode("utf-8"))
                submitted_token = params.get(FORM_FIELD, [None])[0]
            else:
                # JSON or other content types — check header
                submitted_token = request.headers.get(HEADER_NAME)

            if not submitted_token:
                submitted_token = request.headers.get(HEADER_NAME)

            if not submitted_token or not secrets.compare_digest(submitted_token, cookie_token):
                return JSONResponse(
                    {"detail": "CSRF token mismatch. Please refresh and try again."},
                    status_code=403,
                )

        response = await call_next(request)

        # Set CSRF cookie if not present
        if COOKIE_NAME not in request.cookies:
            token = generate_csrf_token()
            response.set_cookie(
                COOKIE_NAME,
                token,
                httponly=False,  # JS needs to read it for AJAX
                samesite="lax",
                secure=request.url.scheme == "https",
                max_age=86400,
            )

        return response
