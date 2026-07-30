"""
Anonymous upload stash.

A visitor drops a label on the landing page before they have an account. We hold
the file server-side, send them to sign up, then attach it to their new account
and run the analysis — so they never have to pick the file twice.

Security posture (this is the app's only unauthenticated byte-storing path):
  * The claim token is random (secrets.token_urlsafe) and stored only as a
    SHA-256 hash, so a DB read never yields a replayable credential.
  * The token travels in an httponly cookie and never in a URL, query string or
    form field — no referrer leak, no browser history, no access-log entry.
  * There is deliberately no endpoint that reads stashed bytes back out. The
    only way they leave the DB is by being attached to a real LabelVersion.
  * Claiming is a single-use atomic compare-and-set.
  * Rows expire after 2h and are swept opportunistically.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LabelVersion, PendingUpload, Product

settings = get_settings()

STASH_TTL_SECONDS = 7200            # 2h
STASH_MAX_BYTES = 10 * 1024 * 1024  # 10 MB — deliberately below the 50 MB
                                    # authenticated cap; an unauthenticated
                                    # endpoint writing 50 MB rows is a
                                    # storage-exhaustion primitive.
STASH_FORM_MAX_BYTES = 16 * 1024
STASH_COOKIE = "rb_stash"
PER_IP_UNCLAIMED_MAX = 2            # parked rows one visitor may hold
UNCLAIMED_BYTE_CEIL = 500 * 1024 * 1024


# ── tokens & hashing ────────────────────────────────────────────────────────

def mint_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def hash_ip(ip: str) -> str:
    """Salted hash — enough for abuse accounting, holds no PII."""
    return hashlib.sha256(f"{ip}|{settings.secret_key}".encode("utf-8")).hexdigest()


# ── cookie helpers ──────────────────────────────────────────────────────────

def set_stash_cookie(response, raw_token: str, secure: bool) -> None:
    response.set_cookie(
        STASH_COOKIE,
        raw_token,
        httponly=True,      # no JS needs this; it is a bearer token for a file
        samesite="lax",     # blocks cross-site POST; the visitor may still
                            # return via an external link
        secure=secure,
        max_age=STASH_TTL_SECONDS,
        path="/",
    )


def clear_stash_cookie(response) -> None:
    response.delete_cookie(STASH_COOKIE, path="/")


# ── abuse accounting ────────────────────────────────────────────────────────

def count_unclaimed_for_ip(db: Session, ip_hash_value: str) -> int:
    return (
        db.query(func.count(PendingUpload.id))
        .filter(
            PendingUpload.ip_hash == ip_hash_value,
            PendingUpload.claimed_at.is_(None),
            PendingUpload.expires_at > datetime.utcnow(),
        )
        .scalar()
        or 0
    )


def unclaimed_bytes(db: Session) -> int:
    return (
        db.query(func.coalesce(func.sum(PendingUpload.byte_size), 0))
        .filter(
            PendingUpload.claimed_at.is_(None),
            PendingUpload.expires_at > datetime.utcnow(),
        )
        .scalar()
        or 0
    )


# ── create / read / claim ───────────────────────────────────────────────────

def create_stash(
    db: Session,
    *,
    kind: str = "file",
    file_bytes: bytes | None = None,
    file_name: str | None = None,
    suffix: str | None = None,
    file_type: str | None = None,
    category: str | None = None,
    form_json: dict | None = None,
    ip: str = "unknown",
) -> str:
    """Persist a pending upload and return the RAW claim token (caller sets the cookie)."""
    row = PendingUpload(
        token_hash="",  # set below, after we mint
        kind=kind,
        file_name=(file_name or "")[:255] or None,
        file_type=file_type,
        suffix=suffix,
        category=(category or "")[:100] or None,
        byte_size=len(file_bytes) if file_bytes else 0,
        file_data=file_bytes,
        form_json=form_json,
        ip_hash=hash_ip(ip),
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(seconds=STASH_TTL_SECONDS),
    )
    raw = mint_token()
    row.token_hash = hash_token(raw)
    db.add(row)
    db.commit()
    return raw


def read_stash(db: Session, raw_token: str | None) -> PendingUpload | None:
    """Unclaimed + unexpired only. Read-only — does not consume the token."""
    if not raw_token:
        return None
    return (
        db.query(PendingUpload)
        .filter(
            PendingUpload.token_hash == hash_token(raw_token),
            PendingUpload.claimed_at.is_(None),
            PendingUpload.expires_at > datetime.utcnow(),
        )
        .first()
    )


def claim_stash(db: Session, raw_token: str | None, user) -> LabelVersion | None:
    """
    Atomically consume the stash and materialise it as a Product + LabelVersion
    owned by `user`. Returns the LabelVersion, or None if there was nothing
    claimable (missing / expired / already claimed all collapse to one
    indistinguishable no-op).

    Only handles kind="file"; kind="form" is resumed by the caller from form_json.
    """
    if not raw_token:
        return None

    token_h = hash_token(raw_token)

    # The claimed_at IS NULL predicate inside the WHERE is the atomicity
    # guarantee: a double-submitted signup or a second tab updates 0 rows.
    updated = (
        db.query(PendingUpload)
        .filter(
            PendingUpload.token_hash == token_h,
            PendingUpload.claimed_at.is_(None),
            PendingUpload.expires_at > datetime.utcnow(),
        )
        .update(
            {"claimed_at": datetime.utcnow(), "claimed_by_user_id": user.id},
            synchronize_session=False,
        )
    )
    if not updated:
        return None
    db.commit()

    row = db.query(PendingUpload).filter(PendingUpload.token_hash == token_h).first()
    if row is None or row.kind != "file" or not row.file_data:
        return None

    product = Product(
        user_id=user.id,
        name=_product_name_from(row.file_name),
        category=row.category or "Health Supplement",
        is_quick_check=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    # Mirror _save_label_file: write to disk AND keep the bytes in the row, so
    # previews survive a container reset.
    suffix = row.suffix or ".jpg"
    upload_dir = Path(settings.upload_dir) / "checker"
    upload_dir.mkdir(parents=True, exist_ok=True)
    disk_name = f"{uuid.uuid4().hex}{suffix}"   # never derived from user input
    disk_path = upload_dir / disk_name
    try:
        with open(disk_path, "wb") as fh:
            fh.write(row.file_data)
    except OSError:
        disk_path = upload_dir / disk_name  # keep the path; bytes are in file_data

    label = LabelVersion(
        product_id=product.id,
        file_path=str(disk_path),
        file_name=row.file_name or disk_name,
        file_type=row.file_type or ("pdf" if suffix == ".pdf" else "image"),
        is_current=True,
        file_data=row.file_data,
    )
    db.add(label)
    db.commit()
    db.refresh(label)

    # Bytes now live on the LabelVersion; drop the duplicate copy.
    db.query(PendingUpload).filter(PendingUpload.id == row.id).update({"file_data": None})
    db.commit()

    return label


def _product_name_from(file_name: str | None) -> str:
    if not file_name:
        return "Quick check"
    stem = Path(file_name).stem.replace("_", " ").replace("-", " ").strip()
    return (stem[:80] or "Quick check")


def purge_expired(db: Session, limit: int = 500) -> int:
    """Delete expired rows. Cheap and indexed; called opportunistically."""
    try:
        ids = [
            r[0]
            for r in db.query(PendingUpload.id)
            .filter(PendingUpload.expires_at <= datetime.utcnow())
            .limit(limit)
            .all()
        ]
        if not ids:
            return 0
        db.query(PendingUpload).filter(PendingUpload.id.in_(ids)).delete(
            synchronize_session=False
        )
        db.commit()
        return len(ids)
    except Exception:
        db.rollback()
        return 0
