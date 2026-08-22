"""
Regression tests for the business-email signup gate.

Regbite sells to registered food businesses, so /register refuses consumer and
disposable mailboxes. The rules that must hold:

  1. Known free providers are refused, including their country variants.
  2. Disposable/throwaway providers are refused, with a distinct message.
  3. Subdomain evasion (foo@mail.gmail.com) is refused — a one-character change
     must not walk past the denylist.
  4. Real company domains are ALLOWED. The gate fails open by design; a false
     positive costs a paying customer.
  5. The allowlist and the killswitch both work, so sales can admit a genuine
     Gmail-run business without a deploy.

Run with:  pytest tests/test_email_domain.py -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.utils.email_domain import (
    DISPOSABLE_PROVIDERS,
    FREE_PROVIDERS,
    domain_of,
    is_free_email,
    validate_business_email,
)


# ── refused: consumer webmail ───────────────────────────────────────────────

@pytest.mark.parametrize("email", [
    "someone@gmail.com",
    "Someone@GMAIL.COM",            # case must not matter
    "  someone@gmail.com  ",        # nor surrounding whitespace
    "someone+label@gmail.com",      # nor plus-addressing
    "someone@googlemail.com",
    "someone@yahoo.co.in",
    "someone@ymail.com",
    "someone@hotmail.com",
    "someone@outlook.com",
    "someone@live.in",
    "someone@icloud.com",
    "someone@rediffmail.com",       # very common on older Indian FBO records
    "someone@indiatimes.com",
    "someone@protonmail.com",
    "someone@zoho.com",             # Zoho's own domain = free tier
    "someone@aol.com",
    "someone@yandex.ru",
])
def test_free_providers_are_refused(email):
    assert is_free_email(email) is True
    assert validate_business_email(email) is not None


def test_free_provider_message_names_the_domain_and_offers_a_route():
    msg = validate_business_email("someone@gmail.com")
    assert "gmail.com" in msg
    # A refused prospect must be given somewhere to go, not just a wall.
    assert "sales@regbite.com" in msg


# ── refused: disposable mail ────────────────────────────────────────────────

@pytest.mark.parametrize("email", [
    "x@mailinator.com",
    "x@guerrillamail.com",
    "x@10minutemail.com",
    "x@yopmail.com",
    "x@temp-mail.org",
    "x@trashmail.com",
    "x@sharklasers.com",
    "x@maildrop.cc",
])
def test_disposable_providers_are_refused(email):
    assert is_free_email(email) is True
    msg = validate_business_email(email)
    assert msg is not None
    assert "disposable" in msg.lower() or "temporary" in msg.lower()


# ── refused: subdomain evasion ──────────────────────────────────────────────

@pytest.mark.parametrize("email", [
    "someone@mail.gmail.com",
    "someone@smtp.yahoo.com",
    "someone@a.b.mailinator.com",
])
def test_subdomains_of_blocked_domains_are_refused(email):
    assert is_free_email(email) is True
    assert validate_business_email(email) is not None


def test_lookalike_domains_are_not_refused():
    """
    The suffix check must match on a dot boundary. `notgmail.com` ends with the
    string "gmail.com" but is a different domain and must pass.
    """
    assert is_free_email("someone@notgmail.com") is False
    assert validate_business_email("someone@notgmail.com") is None


# ── allowed: real businesses ────────────────────────────────────────────────

@pytest.mark.parametrize("email", [
    "priya@herbalifeindia.com",
    "ops@amway.in",
    "regulatory@drreddys.com",
    "qa@patanjaliayurved.net",
    "founder@mystartup.co.in",
    "person@iitb.ac.in",           # academic
    "officer@fssai.gov.in",        # government
    "someone@company.io",
])
def test_business_domains_are_allowed(email):
    assert is_free_email(email) is False
    assert validate_business_email(email) is None


# ── malformed input ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("email", ["", "   ", "notanemail", "@gmail.com", "a@b", "a@@b.com"])
def test_malformed_addresses_get_a_format_error_not_a_domain_error(email):
    msg = validate_business_email(email)
    assert msg is not None
    # Complaining about the domain of an unparseable address is confusing.
    assert "valid email" in msg.lower()


def test_domain_of_uses_the_last_at_sign():
    assert domain_of("weird@name@company.com") == "company.com"


# ── escape hatches ──────────────────────────────────────────────────────────

def test_allowlisted_address_is_admitted(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "free_email_allowlist",
                        "vip@gmail.com, other@yahoo.in", raising=False)
    assert validate_business_email("vip@gmail.com") is None
    assert validate_business_email("VIP@Gmail.com") is None      # normalised
    assert validate_business_email("notvip@gmail.com") is not None  # still refused


def test_killswitch_disables_the_whole_gate(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "block_free_email_signups", False, raising=False)
    assert validate_business_email("someone@gmail.com") is None
    # Structural validation must still run even with the gate off.
    assert validate_business_email("notanemail") is not None


# ── denylist hygiene ────────────────────────────────────────────────────────

def test_denylist_entries_are_normalised():
    """A stray capital or leading dot would silently never match."""
    for domain in FREE_PROVIDERS | DISPOSABLE_PROVIDERS:
        assert domain == domain.strip().lower(), domain
        assert not domain.startswith("."), domain
        assert "@" not in domain, domain
        assert "." in domain, domain
