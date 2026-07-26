"""
Regression tests for CSRFMiddleware, focused on multipart/form-data uploads.

Background: file-upload forms (enctype="multipart/form-data") repeatedly broke
with a 403 "CSRF token required for file uploads" because the middleware only
accepted the token from an X-CSRF-Token header, which relied on a JS interceptor
that could silently fail. The middleware now also extracts `csrf_token` from the
multipart body as a fallback.

The two things that MUST hold and are locked in here:
  1. A multipart POST carrying the token in the body (hidden <input>, no header)
     is accepted.
  2. Reading the body in the middleware does NOT break FastAPI's File()/Form()
     dependency injection downstream — the handler still receives the uploaded
     file bytes and form fields intact.

Run with:  pytest tests/test_csrf_middleware.py -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.testclient import TestClient

from app.services.csrf import CSRFMiddleware, COOKIE_NAME

TOKEN = "test-csrf-token-value-123"


def _make_client(with_cookie: bool = True) -> TestClient:
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/form")
    async def get_form():
        return {"ok": True}

    @app.post("/products/add")
    async def add_product(
        name: str = Form(...),
        file: UploadFile | None = File(None),
    ):
        # Echo back what the handler actually received so the test can prove the
        # body was not consumed/garbled by the middleware.
        contents = await file.read() if file is not None else b""
        return {
            "name": name,
            "filename": file.filename if file is not None else None,
            "file_len": len(contents),
        }

    # raise_server_exceptions=False so a 500 surfaces as a response, not a raised
    # exception, making assertions clearer.
    client = TestClient(app, raise_server_exceptions=False)
    if with_cookie:
        client.cookies.set(COOKIE_NAME, TOKEN)
    return client


# ─── Multipart uploads ───────────────────────────────────────────────────────

class TestMultipartUpload:
    def test_token_in_body_is_accepted_and_file_reaches_handler(self):
        """The core regression: token in the multipart body (no header) works,
        AND the file + form field still arrive intact at the handler."""
        client = _make_client()
        file_bytes = b"\x89PNG\r\n\x1a\n" + b"fake-image-data" * 100
        resp = client.post(
            "/products/add",
            data={"csrf_token": TOKEN, "name": "OmegaPlus"},
            files={"file": ("label.png", file_bytes, "image/png")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "OmegaPlus"
        assert body["filename"] == "label.png"
        assert body["file_len"] == len(file_bytes)

    def test_token_in_body_part_with_content_type_header(self):
        """Some clients add a Content-Type header to a plain field part; the
        body-token extraction must tolerate extra part-headers before the value."""
        client = _make_client()
        boundary = "BOUNDARY123"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="csrf_token"\r\n'
            "Content-Type: text/plain\r\n"
            f"\r\n{TOKEN}\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="name"\r\n'
            "\r\nOmegaPlus\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="label.png"\r\n'
            "Content-Type: image/png\r\n"
            "\r\nPNGDATA\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        resp = client.post(
            "/products/add",
            content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "OmegaPlus"

    def test_token_in_header_is_accepted(self):
        client = _make_client()
        resp = client.post(
            "/products/add",
            data={"name": "OmegaPlus"},
            files={"file": ("label.png", b"abc", "image/png")},
            headers={"X-CSRF-Token": TOKEN},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "OmegaPlus"

    def test_multipart_without_file_still_validates_from_body(self):
        """Optional-file form: token in body, no file selected."""
        client = _make_client()
        resp = client.post(
            "/products/add",
            data={"csrf_token": TOKEN, "name": "NoFileProduct"},
            files={"_": ("", b"", "application/octet-stream")},
        )
        # python-multipart still produces a multipart request; token must be read
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "NoFileProduct"

    def test_missing_token_is_rejected(self):
        client = _make_client()
        resp = client.post(
            "/products/add",
            data={"name": "OmegaPlus"},
            files={"file": ("label.png", b"abc", "image/png")},
        )
        assert resp.status_code == 403, resp.text

    def test_wrong_token_is_rejected(self):
        client = _make_client()
        resp = client.post(
            "/products/add",
            data={"csrf_token": "not-the-right-token", "name": "OmegaPlus"},
            files={"file": ("label.png", b"abc", "image/png")},
        )
        assert resp.status_code == 403, resp.text

    def test_missing_cookie_is_rejected(self):
        client = _make_client(with_cookie=False)
        resp = client.post(
            "/products/add",
            data={"csrf_token": TOKEN, "name": "OmegaPlus"},
            files={"file": ("label.png", b"abc", "image/png")},
        )
        assert resp.status_code == 403, resp.text


# ─── Cookie issuance ─────────────────────────────────────────────────────────

class TestCookieIssuance:
    def test_get_sets_csrf_cookie_when_absent(self):
        client = _make_client(with_cookie=False)
        resp = client.get("/form")
        assert resp.status_code == 200
        assert COOKIE_NAME in resp.cookies
