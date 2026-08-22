"""
Business-email gate for signups.

Regbite sells to registered food businesses (FBOs), so a signup from a consumer
mailbox is almost always a tyre-kicker, a competitor, or trial abuse. This module
answers one question: does this address belong to a free consumer provider or a
disposable-mail service?

Two deliberate design points:

1.  **The list is a denylist, not an allowlist.** We cannot enumerate every
    legitimate company domain in India, so anything not recognised as free is
    allowed through. That fails *open*, which is the correct direction — losing a
    real customer costs far more than admitting a Gmail user.

2.  **There is an escape hatch.** A meaningful number of genuine small
    nutraceutical manufacturers in India really do run on Gmail. When sales wants
    to let one in, `FREE_EMAIL_ALLOWLIST` admits specific addresses without a
    deploy, and `BLOCK_FREE_EMAIL_SIGNUPS=false` disables the gate entirely.

Not implemented on purpose: MX-record lookups. They add a network round-trip to
the signup path and a new failure mode (DNS timeout = nobody can register), which
is a bad trade for the marginal accuracy.
"""

import re

from app.config import get_settings

# Consumer webmail. Ordered by how often we actually see them on Indian signups.
FREE_PROVIDERS = {
    # Google
    "gmail.com", "googlemail.com",
    # Microsoft
    "hotmail.com", "hotmail.co.uk", "hotmail.co.in", "hotmail.fr",
    "outlook.com", "outlook.in", "live.com", "live.co.uk", "live.in",
    "msn.com", "passport.com", "windowslive.com",
    # Yahoo and its aliases
    "yahoo.com", "yahoo.co.in", "yahoo.in", "yahoo.co.uk", "yahoo.ca",
    "yahoo.com.au", "yahoo.fr", "yahoo.de", "yahoo.es", "yahoo.it",
    "ymail.com", "rocketmail.com",
    # Apple
    "icloud.com", "me.com", "mac.com",
    # India-specific consumer mail — common on older FBO registrations
    "rediffmail.com", "rediff.com", "indiatimes.com", "sify.com",
    "in.com", "vsnl.net", "vsnl.com", "bsnl.in", "airtelmail.in",
    "dataone.in", "hathway.com",
    # Privacy-focused consumer mail
    "protonmail.com", "protonmail.ch", "proton.me", "pm.me",
    "tutanota.com", "tutanota.de", "tuta.io", "tuta.com",
    "hushmail.com", "mailfence.com", "posteo.de", "runbox.com",
    # Other global free providers
    "aol.com", "aim.com", "gmx.com", "gmx.net", "gmx.de", "gmx.at",
    "mail.com", "email.com", "usa.com", "consultant.com",
    "zoho.com", "zohomail.com", "zoho.in",   # Zoho's own domain = free tier;
                                             # business customers use their own
    "yandex.com", "yandex.ru", "ya.ru",
    "fastmail.com", "fastmail.fm",           # personal plans dominate
    "inbox.com", "lycos.com", "excite.com", "rocketmail.com",
    "seznam.cz", "web.de", "t-online.de", "libero.it", "orange.fr",
    "wanadoo.fr", "free.fr", "laposte.net", "bol.com.br", "uol.com.br",
    "qq.com", "163.com", "126.com", "sina.com", "sohu.com", "naver.com",
    "daum.net", "hanmail.net",
}

# Disposable / throwaway mailboxes. These are unambiguous — no legitimate
# business has ever run on one.
DISPOSABLE_PROVIDERS = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net",
    "guerrillamail.org", "sharklasers.com", "grr.la", "spam4.me",
    "10minutemail.com", "10minutemail.net", "tempmail.com", "temp-mail.org",
    "tempmail.net", "tempr.email", "tmpmail.org", "throwawaymail.com",
    "yopmail.com", "yopmail.fr", "yopmail.net", "cool.fr.nf", "jetable.org",
    "trashmail.com", "trashmail.de", "trash-mail.com", "wegwerfmail.de",
    "dispostable.com", "getnada.com", "nada.email", "maildrop.cc",
    "fakeinbox.com", "mintemail.com", "spamgourmet.com", "mailnesia.com",
    "moakt.com", "emailondeck.com", "mohmal.com", "discard.email",
    "luxusmail.org", "mailcatch.com", "inboxbear.com", "harakirimail.com",
    "spambog.com", "mytrashmail.com", "tempinbox.com", "mailexpire.com",
    "burnermail.io", "anonaddy.com", "addy.io", "simplelogin.com",
    "simplelogin.io", "duck.com", "33mail.com", "spamex.com",
    "byom.de", "einrot.com", "fleckens.hu", "gustr.com", "jourrapide.com",
    "rhyta.com", "superrito.com", "teleworm.us", "armyspy.com", "cuvox.de",
    "dayrep.com",
}

BLOCKED_DOMAINS = FREE_PROVIDERS | DISPOSABLE_PROVIDERS

# Same shape as settings.EMAIL_RE — structural validity only.
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def normalize(email: str) -> str:
    return (email or "").strip().lower()


def domain_of(email: str) -> str:
    """Everything after the last '@' — an address may legally contain more than one."""
    return normalize(email).rpartition("@")[2]


def is_free_email(email: str) -> bool:
    """
    True when the address belongs to a known free or disposable provider.

    Subdomains count: `foo@mail.gmail.com` resolves to gmail.com. Without this a
    one-character change walks straight past the denylist.
    """
    domain = domain_of(email)
    if not domain:
        return False
    if domain in BLOCKED_DOMAINS:
        return True
    return any(domain.endswith("." + blocked) for blocked in BLOCKED_DOMAINS)


def _allowlist() -> set:
    """Specific addresses sales has cleared, from the FREE_EMAIL_ALLOWLIST env var."""
    raw = get_settings().free_email_allowlist or ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _gate_enabled() -> bool:
    return bool(get_settings().block_free_email_signups)


def validate_business_email(email: str) -> str | None:
    """
    Return a user-facing error string, or None when the address may sign up.

    Checks structure first so a malformed address gets a message about *that*
    rather than a confusing complaint about its domain.
    """
    clean = normalize(email)

    if not clean or not EMAIL_RE.match(clean):
        return "Please enter a valid email address."

    if not _gate_enabled() or clean in _allowlist():
        return None

    domain = domain_of(clean)

    if is_free_email(clean):
        if domain in DISPOSABLE_PROVIDERS or any(
            domain.endswith("." + d) for d in DISPOSABLE_PROVIDERS
        ):
            return (
                "Temporary and disposable email addresses can't be used to create "
                "an account. Please sign up with your company email address."
            )
        return (
            f"Please sign up with your work email address. Regbite accounts are for "
            f"registered food businesses, so we can't accept {domain} addresses. "
            f"If your business genuinely runs on {domain}, email sales@regbite.com "
            f"and we'll set you up."
        )

    return None
