"""
Password reset tokens.

Security posture — a reset link is a bearer credential for someone's account,
so the rules here are deliberately strict:

  * The token is `secrets.token_urlsafe(32)` and only its SHA-256 is persisted.
  * Consuming a token is an atomic compare-and-set, so a double-submitted form
    or two open tabs cannot reset twice.
  * Issuing a new token invalidates every outstanding one for that user, so a
    forwarded or shoulder-surfed older link stops working.
  * Every failure mode — unknown token, expired, already used, inactive user —
    returns the same `None`. Callers cannot distinguish them, and neither can
    an attacker.
  * The raw token appears only in the emailed URL. It is never logged and never
    stored.

User enumeration is handled in the route, not here: the request endpoint always
responds identically whether or not the address belongs to an account.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PasswordResetToken, User

settings = get_settings()

TOKEN_TTL_MINUTES = 60
COOLDOWN_SECONDS = 60          # min gap between emails to one address
MAX_ACTIVE_PER_USER = 5        # ceiling on outstanding tokens


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def hash_ip(ip: str) -> str:
    """Salted — enough to spot abuse, holds no raw PII."""
    return hashlib.sha256(f"{ip}|{settings.secret_key}".encode("utf-8")).hexdigest()


def recently_requested(db: Session, user: User) -> bool:
    """True if this user was issued a token within the cooldown window."""
    cutoff = datetime.utcnow() - timedelta(seconds=COOLDOWN_SECONDS)
    return (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at > cutoff,
        )
        .first()
        is not None
    )


def issue_token(db: Session, user: User, ip: str = "unknown") -> str:
    """
    Create a reset token and return the RAW value for the email.

    Invalidates any outstanding tokens for this user first — only the most
    recent link should ever work.
    """
    now = datetime.utcnow()
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({"used_at": now}, synchronize_session=False)

    raw = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(
        user_id=user.id,
        token_hash=_hash(raw),
        created_at=now,
        expires_at=now + timedelta(minutes=TOKEN_TTL_MINUTES),
        ip_hash=hash_ip(ip),
    ))
    db.commit()
    return raw


def peek_token(db: Session, raw: str | None) -> User | None:
    """
    Validate without consuming — used by GET so the form can be rendered.

    Returns None for every failure mode, indistinguishably.
    """
    if not raw:
        return None
    row = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == _hash(raw),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not row:
        return None
    user = db.query(User).filter(User.id == row.user_id).first()
    if not user or not user.is_active:
        return None
    return user


def consume_token(db: Session, raw: str | None) -> User | None:
    """
    Atomically spend the token and return its user.

    The `used_at IS NULL` predicate inside the WHERE is the guarantee: a second
    concurrent submit updates 0 rows and gets None back.
    """
    if not raw:
        return None
    token_h = _hash(raw)
    now = datetime.utcnow()

    updated = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == token_h,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .update({"used_at": now}, synchronize_session=False)
    )
    if not updated:
        return None
    db.commit()

    row = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_h
    ).first()
    if not row:
        return None
    user = db.query(User).filter(User.id == row.user_id).first()
    if not user or not user.is_active:
        return None
    return user


def purge_expired(db: Session, limit: int = 500) -> int:
    """Housekeeping. Cheap and indexed; called opportunistically."""
    try:
        ids = [
            r[0]
            for r in db.query(PasswordResetToken.id)
            .filter(PasswordResetToken.expires_at <= datetime.utcnow())
            .limit(limit)
            .all()
        ]
        if not ids:
            return 0
        db.query(PasswordResetToken).filter(
            PasswordResetToken.id.in_(ids)
        ).delete(synchronize_session=False)
        db.commit()
        return len(ids)
    except Exception:
        db.rollback()
        return 0
