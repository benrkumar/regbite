"""
Double-submit cookie CSRF protection.

How it works:
1. On every response, set a `_csrf` cookie with a random token (if not already present).
2. On every state-changing request (POST/PUT/PATCH/DELETE), verify that a matching
   `csrf_token` field (from form data) or `X-CSRF-Token` header equals the cookie value.
3. Exempt paths: webhooks, health checks.
"""

import re
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

            if "multipart/form-data" in content_type:
                submitted_token = request.headers.get(HEADER_NAME)
                if not submitted_token:
                    # Fallback: extract csrf_token from the multipart body without
                    # calling request.form() (which conflicts with FastAPI's
                    # Form(...) dependency injection under BaseHTTPMiddleware).
                    # The hidden csrf_token <input> is appended first by the inline
                    # script in base.html/public_base.html, so it lives in the
                    # first few KB. Tolerate optional extra part-headers (e.g. a
                    # Content-Type line) between the disposition and the value.
                    body = await request.body()
                    m = re.search(
                        rb'name="csrf_token"(?:;[^\r\n]*)?\r\n'
                        rb'(?:[A-Za-z][A-Za-z0-9-]*:[^\r\n]*\r\n)*'
                        rb'\r\n([^\r\n]+)',
                        body[:4096],
                    )
                    if m:
                        submitted_token = m.group(1).decode("utf-8", errors="ignore")
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
