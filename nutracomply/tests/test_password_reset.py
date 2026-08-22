"""
Regression tests for password reset tokens.

A reset link is a bearer credential for someone's account, so these properties
are the whole security model and must not regress:

  1. Only the SHA-256 of a token is persisted — a DB leak yields nothing
     replayable.
  2. Consuming is atomic and single-use, so a double-submitted form or two open
     tabs cannot reset twice.
  3. Issuing a new token invalidates every outstanding one for that user.
  4. Expired tokens, unknown tokens, used tokens and inactive users are all
     indistinguishable to the caller — every one returns None.

Run with:  pytest tests/test_password_reset.py -v
"""
import hashlib
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, PasswordResetToken, User
from app.services import password_reset as pr


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _user(db, email="qa@realnutraco.in", active=True):
    u = User(email=email, name="QA", hashed_password="x", is_active=active,
             notification_emails=[])
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ── storage ─────────────────────────────────────────────────────────────────

def test_only_the_hash_is_stored(db):
    user = _user(db)
    raw = pr.issue_token(db, user)

    row = db.query(PasswordResetToken).filter_by(user_id=user.id).one()
    assert row.token_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in row.token_hash
    # Nothing anywhere on the row may hold the replayable value.
    assert all(raw != getattr(row, c.name) for c in row.__table__.columns)


def test_ip_is_hashed_not_stored_raw(db):
    user = _user(db)
    pr.issue_token(db, user, ip="203.0.113.9")
    row = db.query(PasswordResetToken).filter_by(user_id=user.id).one()
    assert row.ip_hash and "203.0.113.9" not in row.ip_hash


def test_tokens_are_unique_per_issue(db):
    a, b = _user(db, "a@co.in"), _user(db, "b@co.in")
    assert pr.issue_token(db, a) != pr.issue_token(db, b)


# ── single use ──────────────────────────────────────────────────────────────

def test_token_works_exactly_once(db):
    user = _user(db)
    raw = pr.issue_token(db, user)

    assert pr.consume_token(db, raw).id == user.id
    # The second attempt is the double-submit / two-tabs case.
    assert pr.consume_token(db, raw) is None


def test_peek_does_not_consume(db):
    user = _user(db)
    raw = pr.issue_token(db, user)

    assert pr.peek_token(db, raw).id == user.id
    assert pr.peek_token(db, raw).id == user.id      # still valid
    assert pr.consume_token(db, raw).id == user.id   # and still spendable


def test_issuing_again_invalidates_the_previous_link(db):
    user = _user(db)
    first = pr.issue_token(db, user)
    second = pr.issue_token(db, user)

    # A forwarded or shoulder-surfed older link must stop working.
    assert pr.peek_token(db, first) is None
    assert pr.consume_token(db, first) is None
    assert pr.consume_token(db, second).id == user.id


# ── failure modes all look identical ────────────────────────────────────────

@pytest.mark.parametrize("bad", [None, "", "not-a-real-token", "x" * 43])
def test_unknown_tokens_return_none(db, bad):
    assert pr.peek_token(db, bad) is None
    assert pr.consume_token(db, bad) is None


def test_expired_token_is_refused(db):
    user = _user(db)
    raw = pr.issue_token(db, user)

    row = db.query(PasswordResetToken).filter_by(user_id=user.id).one()
    row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()

    assert pr.peek_token(db, raw) is None
    assert pr.consume_token(db, raw) is None


def test_token_for_deactivated_user_is_refused(db):
    user = _user(db)
    raw = pr.issue_token(db, user)

    user.is_active = False
    db.commit()

    # Deactivation between issue and use must not be a way back in.
    assert pr.peek_token(db, raw) is None
    assert pr.consume_token(db, raw) is None


def test_ttl_is_an_hour(db):
    user = _user(db)
    pr.issue_token(db, user)
    row = db.query(PasswordResetToken).filter_by(user_id=user.id).one()
    assert 55 <= (row.expires_at - row.created_at).total_seconds() / 60 <= 65


# ── cooldown & housekeeping ─────────────────────────────────────────────────

def test_cooldown_reports_a_recent_request(db):
    user = _user(db)
    assert pr.recently_requested(db, user) is False
    pr.issue_token(db, user)
    assert pr.recently_requested(db, user) is True


def test_cooldown_lapses(db):
    user = _user(db)
    pr.issue_token(db, user)
    row = db.query(PasswordResetToken).filter_by(user_id=user.id).one()
    row.created_at = datetime.utcnow() - timedelta(seconds=pr.COOLDOWN_SECONDS + 5)
    db.commit()
    assert pr.recently_requested(db, user) is False


def test_purge_removes_only_expired_rows(db):
    user = _user(db)
    stale = pr.issue_token(db, user)
    db.query(PasswordResetToken).update(
        {"expires_at": datetime.utcnow() - timedelta(hours=2)})
    db.commit()
    live = pr.issue_token(db, user)

    assert pr.purge_expired(db) == 1
    assert pr.peek_token(db, stale) is None
    assert pr.peek_token(db, live).id == user.id
