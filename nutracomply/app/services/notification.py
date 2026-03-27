"""
Notification Service — sends all transactional emails via Brevo SMTP.

Design system: monochrome Japanese minimal (matches RegBite UI).
All emails share a consistent wrapper with brand header and footer.

Email Workflows:
  1.  Compliance Alert       — CRITICAL/HIGH violations detected on a label
  2.  Regulation Change      — new FSSAI/AYUSH/LM regulation detected by scraper
  3.  Welcome                — sent on registration
  4.  Team Invite            — sent when admin invites a team member
  5.  Invite Accepted        — sent to inviter when member joins
  6.  Payment Confirmation   — sent after successful Razorpay payment
  7.  Subscription Cancelled — sent when subscription is cancelled
  8.  Password Changed       — security confirmation
  9.  License Expiry Reminder— sent when licenses are expiring soon
 10.  Report Shared          — sent when a compliance report link is created
"""

import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import get_settings

settings = get_settings()

# ── Design tokens ─────────────────────────────────────────────────────────────

_INK    = "#111111"
_MUTED  = "#737373"
_LIGHT  = "#A3A3A3"
_BG     = "#F8F8F8"
_BORDER = "#EBEBEB"
_WHITE  = "#FFFFFF"
_RED    = "#B91C1C"
_ORANGE = "#C2410C"
_AMBER  = "#B45309"
_GREEN  = "#15803D"
_BLUE   = "#1D4ED8"

_BASE_URL = "https://steadfast-courage-production-0f66.up.railway.app"

# ── Shared wrapper ────────────────────────────────────────────────────────────

def _wrap(body: str) -> str:
    """Wrap email body in brand container — monochrome, clean, minimal."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width"/></head>
<body style="margin:0;padding:0;background:{_BG};font-family:-apple-system,BlinkMacSystemFont,'Noto Sans JP',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};padding:32px 16px;">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" style="background:{_WHITE};border:1px solid {_BORDER};border-radius:6px;overflow:hidden;">

  <!-- Brand header -->
  <tr><td style="padding:24px 32px 16px;border-bottom:1px solid {_BORDER};">
    <table cellpadding="0" cellspacing="0"><tr>
      <td style="font-size:8px;color:{_INK};vertical-align:middle;padding-right:8px;">&#9679;</td>
      <td>
        <div style="font-size:15px;font-weight:700;color:{_INK};letter-spacing:-0.02em;">RegBite</div>
        <div style="font-size:11px;color:{_LIGHT};margin-top:-1px;">FSSAI Compliance Monitor</div>
      </td>
    </tr></table>
  </td></tr>

  <!-- Body -->
  <tr><td style="padding:28px 32px 32px;color:{_INK};font-size:14px;line-height:1.65;">
    {body}
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:20px 32px;background:{_BG};border-top:1px solid {_BORDER};">
    <p style="margin:0;font-size:11px;color:{_LIGHT};line-height:1.5;">
      RegBite &middot; AI-Powered FSSAI Compliance for India's Nutraceutical Industry<br/>
      Not legal advice. For regulatory compliance assistance only.<br/>
      <a href="{_BASE_URL}/settings" style="color:{_MUTED};text-decoration:underline;">Notification preferences</a>
    </p>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""


def _badge(text: str, color: str) -> str:
    """Inline severity/status badge."""
    return (
        f"<span style='display:inline-block;padding:2px 8px;border-radius:3px;"
        f"font-size:11px;font-weight:600;letter-spacing:0.03em;"
        f"color:{_WHITE};background:{color};'>{text}</span>"
    )


def _btn(label: str, href: str) -> str:
    """Primary CTA button — solid black, monochrome."""
    return (
        f"<a href='{href}' style='display:inline-block;padding:11px 24px;"
        f"background:{_INK};color:{_WHITE};text-decoration:none;border-radius:4px;"
        f"font-weight:500;font-size:13px;letter-spacing:-0.01em;'>{label}</a>"
    )


def _card(content: str, accent: str = _BORDER) -> str:
    """Accent-bordered info card."""
    return (
        f"<div style='background:{_BG};border-left:3px solid {accent};"
        f"border-radius:4px;padding:14px 18px;margin:16px 0;'>{content}</div>"
    )


def _severity_color(sev: str) -> str:
    s = (sev or "").upper()
    if s == "CRITICAL": return _RED
    if s == "HIGH": return _ORANGE
    if s == "MEDIUM": return _AMBER
    return _MUTED


# ── Recipient helpers ─────────────────────────────────────────────────────────

def _get_recipients(user=None) -> list[str]:
    """Build recipient list from user's emails + fallback setting."""
    recipients = set()
    if user and user.notification_emails:
        for email in user.notification_emails:
            if email:
                recipients.add(email.lower())
    if user and hasattr(user, "email") and user.email:
        recipients.add(user.email.lower())
    if settings.alert_to_email:
        recipients.add(settings.alert_to_email.lower())
    return list(recipients)[:5]


def _to(addresses: list[str]) -> list[str]:
    """Send to specific addresses (no user lookup)."""
    return [a.lower() for a in addresses if a][:5]


# ── Send ──────────────────────────────────────────────────────────────────────

def _send_email(subject: str, html_body: str, recipients: list[str]):
    """Send an HTML email to all recipients via Brevo SMTP."""
    if not settings.brevo_smtp_user:
        print(f"[notify] SMTP not configured, skipping: {subject}")
        return
    if not recipients:
        print(f"[notify] No recipients, skipping: {subject}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"RegBite <{settings.alert_from_email}>"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(_wrap(html_body), "html"))

    try:
        with smtplib.SMTP(settings.brevo_smtp_host, settings.brevo_smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.brevo_smtp_user, settings.brevo_smtp_password)
            server.sendmail(settings.alert_from_email, recipients, msg.as_string())
        print(f"[notify] Sent to {len(recipients)}: {subject}")
    except Exception as e:
        print(f"[notify] Failed: {e} — {subject}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. COMPLIANCE ALERT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_alert_email(alert, product=None, user=None):
    """Sent when CRITICAL/HIGH violations are detected on a product label."""
    recipients = _get_recipients(user)
    if not recipients:
        return

    product_name = product.name if product else "Unknown Product"
    sev = alert.severity.value
    sc = _severity_color(sev)

    # Build violation rows
    rows = ""
    for v in (alert.rule_violations or []):
        vs = v.get("severity", "")
        rows += (
            f"<tr>"
            f"<td style='padding:8px 10px;border-bottom:1px solid {_BORDER};vertical-align:top;'>"
            f"{_badge(vs, _severity_color(vs))} "
            f"<strong style='font-size:12px;'>{v.get('rule_code', '')}</strong></td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid {_BORDER};font-size:13px;'>"
            f"{v.get('message', '')}</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid {_BORDER};font-size:12px;color:{_MUTED};'>"
            f"{v.get('remediation', '')}</td>"
            f"</tr>"
        )

    body = f"""
    <p style="margin:0 0 4px;font-size:11px;color:{_LIGHT};">
        {datetime.utcnow().strftime('%d %b %Y, %H:%M')} UTC</p>
    <h2 style="margin:0 0 16px;font-size:18px;font-weight:600;color:{_INK};">
        Compliance Alert</h2>

    {_card(f'''
        <table cellpadding="0" cellspacing="0" style="width:100%;">
          <tr><td style="padding:3px 0;color:{_MUTED};font-size:12px;">Product</td>
              <td style="padding:3px 0;font-weight:600;">{product_name}</td></tr>
          <tr><td style="padding:3px 0;color:{_MUTED};font-size:12px;">Severity</td>
              <td style="padding:3px 0;">{_badge(sev, sc)}</td></tr>
        </table>
        <p style="margin:10px 0 0;font-size:13px;">{alert.message}</p>
    ''', sc)}

    <h3 style="margin:20px 0 8px;font-size:13px;font-weight:600;color:{_INK};
               text-transform:uppercase;letter-spacing:0.05em;">Violations</h3>
    <table style="width:100%;border-collapse:collapse;">
      <tr style="background:{_BG};">
        <th style="padding:8px 10px;text-align:left;font-size:11px;color:{_MUTED};
                   text-transform:uppercase;letter-spacing:0.05em;">Rule</th>
        <th style="padding:8px 10px;text-align:left;font-size:11px;color:{_MUTED};
                   text-transform:uppercase;letter-spacing:0.05em;">Issue</th>
        <th style="padding:8px 10px;text-align:left;font-size:11px;color:{_MUTED};
                   text-transform:uppercase;letter-spacing:0.05em;">Fix</th>
      </tr>
      {rows}
    </table>

    <p style="margin:24px 0 0;">{_btn('View Alerts', f'{_BASE_URL}/alerts')}</p>
    """
    _send_email(f"[RegBite] {sev}: {alert.title}", body, recipients)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. REGULATION CHANGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_regulation_change_email(change, users=None):
    """Sent when the scraper detects a new or amended regulation."""
    if users:
        all_r = set()
        for u in users:
            for a in _get_recipients(u):
                all_r.add(a)
        recipients = list(all_r)[:20]
    else:
        recipients = _get_recipients()
    if not recipients:
        return

    url = change.source_url or ""
    if "ayush.gov.in" in url:
        source = "Ministry of AYUSH"
    elif "consumeraffairs.nic.in" in url or "legalmetrology" in url.lower():
        source = "Legal Metrology"
    elif "egazette" in url.lower():
        source = "eGazette"
    else:
        source = "FSSAI"

    sev = change.severity.value
    sc = _severity_color(sev)
    ct = change.change_type.value.replace("_", " ").title()

    body = f"""
    <p style="margin:0 0 4px;font-size:11px;color:{_LIGHT};">
        {change.detected_at.strftime('%d %b %Y')}</p>
    <h2 style="margin:0 0 16px;font-size:18px;font-weight:600;color:{_INK};">
        Regulation Change Detected</h2>

    {_card(f'''
        <table cellpadding="0" cellspacing="0" style="width:100%;">
          <tr><td style="padding:3px 0;color:{_MUTED};font-size:12px;width:80px;">Source</td>
              <td style="padding:3px 0;font-weight:500;">{source}</td></tr>
          <tr><td style="padding:3px 0;color:{_MUTED};font-size:12px;">Type</td>
              <td style="padding:3px 0;">{ct}</td></tr>
          <tr><td style="padding:3px 0;color:{_MUTED};font-size:12px;">Severity</td>
              <td style="padding:3px 0;">{_badge(sev, sc)}</td></tr>
          <tr><td style="padding:3px 0;color:{_MUTED};font-size:12px;">Document</td>
              <td style="padding:3px 0;font-size:13px;">{change.document_name}</td></tr>
        </table>
    ''', _BLUE)}

    <h3 style="margin:20px 0 6px;font-size:13px;font-weight:600;color:{_INK};
               text-transform:uppercase;letter-spacing:0.05em;">Summary</h3>
    <p style="font-size:13px;color:{_INK};">
        {change.summary_text or 'See full details in RegBite.'}</p>

    <p style="margin:24px 0 0;">{_btn('View Regulation Feed', f'{_BASE_URL}/regulations')}</p>
    """
    _send_email(f"[RegBite] {source}: {change.document_name[:55]}", body, recipients)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. WELCOME
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_welcome_email(user):
    """Sent after registration."""
    if not user or not user.email:
        return

    steps = ""
    for n, txt in enumerate([
        "Add your nutraceutical products",
        "Upload label images or PDFs",
        "Get instant compliance reports against 83 rules across 5 frameworks",
    ], 1):
        steps += (
            f"<div style='padding:12px 16px;background:{_BG};border-radius:4px;"
            f"margin:0 0 6px;font-size:13px;'>"
            f"<strong style='color:{_MUTED};'>{n}.</strong> {txt}</div>"
        )

    body = f"""
    <h2 style="margin:0 0 16px;font-size:18px;font-weight:600;color:{_INK};">
        Welcome to RegBite, {user.name}</h2>
    <p>Your account is ready. Here's how to get started:</p>

    <div style="margin:20px 0;">{steps}</div>

    <p style="font-size:13px;color:{_MUTED};">
        We've added 5 demo products to your account so you can explore immediately.</p>

    <p style="margin:24px 0 0;">{_btn('Go to Dashboard', f'{_BASE_URL}/dashboard')}</p>

    <p style="color:{_MUTED};margin:20px 0 0;font-size:12px;">
        <strong>Tip:</strong> Go to Settings &rarr; Notifications to add team
        email addresses that should receive compliance alerts.</p>
    """
    _send_email("Welcome to RegBite — FSSAI Compliance Made Simple", body, _to([user.email]))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. TEAM INVITE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_team_invite_email(invite_email: str, inviter_name: str, role: str, invite_url: str):
    """Sent when an admin invites a team member."""
    role_display = role.replace("_", " ").title()
    body = f"""
    <h2 style="margin:0 0 16px;font-size:18px;font-weight:600;color:{_INK};">
        You're Invited to RegBite</h2>
    <p><strong>{inviter_name}</strong> has invited you to join their team as a
       <strong>{role_display}</strong>.</p>

    {_card(f'''
        <p style="margin:0;font-size:13px;">RegBite is an AI-powered FSSAI compliance
           platform for India's nutraceutical industry. As a team member, you'll have
           access to compliance reports, product management, and regulation monitoring.</p>
    ''', _GREEN)}

    <p style="margin:24px 0 0;">
        <a href="{invite_url}" style="display:inline-block;padding:13px 32px;
           background:{_INK};color:{_WHITE};text-decoration:none;border-radius:4px;
           font-weight:600;font-size:14px;">Accept Invitation</a>
    </p>

    <p style="color:{_LIGHT};font-size:12px;margin:16px 0 0;">
        This invitation expires in 7 days. Ignore this email if unexpected.</p>
    """
    _send_email(f"{inviter_name} invited you to RegBite", body, _to([invite_email]))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. INVITE ACCEPTED
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_invite_accepted_email(inviter, new_member_name: str, new_member_email: str, role: str):
    """Notify the inviter that their team member accepted."""
    if not inviter or not inviter.email:
        return

    role_display = role.replace("_", " ").title()
    body = f"""
    <h2 style="margin:0 0 16px;font-size:18px;font-weight:600;color:{_INK};">
        New Team Member</h2>

    {_card(f'''
        <table cellpadding="0" cellspacing="0" style="width:100%;">
          <tr><td style="padding:3px 0;color:{_MUTED};font-size:12px;width:60px;">Name</td>
              <td style="padding:3px 0;font-weight:500;">{new_member_name}</td></tr>
          <tr><td style="padding:3px 0;color:{_MUTED};font-size:12px;">Email</td>
              <td style="padding:3px 0;">{new_member_email}</td></tr>
          <tr><td style="padding:3px 0;color:{_MUTED};font-size:12px;">Role</td>
              <td style="padding:3px 0;">{_badge(role_display, _INK)}</td></tr>
        </table>
    ''', _GREEN)}

    <p style="margin:24px 0 0;">{_btn('View Team', f'{_BASE_URL}/team')}</p>
    """
    _send_email(f"[RegBite] {new_member_name} joined your team", body, _to([inviter.email]))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. PAYMENT CONFIRMATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_payment_confirmation_email(user, plan: str, amount_display: str, period_end: str):
    """Sent after successful Razorpay payment."""
    if not user or not user.email:
        return

    body = f"""
    <h2 style="margin:0 0 16px;font-size:18px;font-weight:600;color:{_INK};">
        Payment Confirmed</h2>
    <p>Thank you, {user.name}. Your payment has been processed.</p>

    {_card(f'''
        <table cellpadding="0" cellspacing="0" style="width:100%;">
          <tr><td style="padding:4px 0;color:{_MUTED};font-size:12px;width:80px;">Plan</td>
              <td style="padding:4px 0;font-weight:600;">{plan.title()}</td></tr>
          <tr><td style="padding:4px 0;color:{_MUTED};font-size:12px;">Amount</td>
              <td style="padding:4px 0;font-weight:600;">{amount_display}</td></tr>
          <tr><td style="padding:4px 0;color:{_MUTED};font-size:12px;">Valid until</td>
              <td style="padding:4px 0;font-weight:600;">{period_end}</td></tr>
        </table>
    ''', _GREEN)}

    <p style="margin:24px 0 0;">{_btn('View Billing', f'{_BASE_URL}/billing')}</p>
    """
    _send_email(f"[RegBite] Payment Confirmed — {plan.title()} Plan", body, _to([user.email]))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. SUBSCRIPTION CANCELLED
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_subscription_cancelled_email(user, access_until: str):
    """Sent when the user cancels their subscription."""
    if not user or not user.email:
        return

    body = f"""
    <h2 style="margin:0 0 16px;font-size:18px;font-weight:600;color:{_INK};">
        Subscription Cancelled</h2>
    <p>Hi {user.name}, your subscription has been cancelled as requested.</p>

    {_card(f'''
        <p style="margin:0;font-size:13px;">Your current access continues until
           <strong>{access_until}</strong>. After that, your account will
           revert to the Free plan.</p>
    ''', _AMBER)}

    <p style="color:{_MUTED};font-size:13px;">
        You can resubscribe at any time from the Billing page. Your data will be preserved.</p>

    <p style="margin:24px 0 0;">{_btn('View Billing', f'{_BASE_URL}/billing')}</p>
    """
    _send_email("[RegBite] Subscription Cancelled", body, _to([user.email]))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. PASSWORD CHANGED
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_password_changed_email(user):
    """Security notification after password change."""
    if not user or not user.email:
        return

    body = f"""
    <h2 style="margin:0 0 16px;font-size:18px;font-weight:600;color:{_INK};">
        Password Changed</h2>
    <p>Hi {user.name}, your password was changed on
       {datetime.utcnow().strftime('%d %b %Y at %H:%M')} UTC.</p>

    {_card(f'''
        <p style="margin:0;font-size:13px;color:{_RED};">
            If you did not make this change, please
            <a href="{_BASE_URL}/login" style="color:{_RED};font-weight:600;">
            sign in immediately</a> and reset your password.</p>
    ''', _RED)}
    """
    _send_email("[RegBite] Password Changed", body, _to([user.email]))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. LICENSE EXPIRY REMINDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_license_expiry_email(user, licenses):
    """
    Sent daily for licenses expiring within 30 days.
    `licenses` can be a list of ORM LicenseRenewal objects or dicts.
    """
    if not user or not user.email or not licenses:
        return

    rows = ""
    expired_count = 0
    urgent_count = 0

    for lic in licenses:
        # Support both ORM objects and dicts
        if isinstance(lic, dict):
            name = lic.get("name", "")
            ltype = lic.get("type", "")
            expiry = lic.get("expiry_date", "")
            days = lic.get("days", 0)
        else:
            name = lic.license_name
            ltype = lic.license_type.value if hasattr(lic.license_type, "value") else str(lic.license_type)
            expiry = lic.expiry_date.strftime("%d %b %Y") if lic.expiry_date else ""
            days = lic.days_until_expiry

        if days < 0:
            expired_count += 1
            status = _badge(f"Expired {abs(days)}d ago", _RED)
        elif days == 0:
            expired_count += 1
            status = _badge("Expires today", _RED)
        elif days <= 7:
            urgent_count += 1
            status = _badge(f"{days}d left", _RED)
        elif days <= 14:
            urgent_count += 1
            status = _badge(f"{days}d left", _ORANGE)
        else:
            urgent_count += 1
            status = _badge(f"{days}d left", _AMBER)

        rows += (
            f"<tr>"
            f"<td style='padding:8px 10px;border-bottom:1px solid {_BORDER};font-weight:500;'>{name}</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid {_BORDER};color:{_MUTED};font-size:12px;'>{ltype}</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid {_BORDER};font-size:13px;'>{expiry}</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid {_BORDER};'>{status}</td>"
            f"</tr>"
        )

    parts = []
    if expired_count:
        parts.append(f"{expired_count} expired")
    if urgent_count:
        parts.append(f"{urgent_count} expiring soon")
    subject_detail = ", ".join(parts) or f"{len(licenses)} license(s) need attention"

    body = f"""
    <h2 style="margin:0 0 16px;font-size:18px;font-weight:600;color:{_INK};">
        License Renewal Reminder</h2>
    <p>Hi {user.name}, the following licenses need your attention:</p>

    <table style="width:100%;border-collapse:collapse;margin:16px 0;">
      <tr style="background:{_BG};">
        <th style="padding:8px 10px;text-align:left;font-size:11px;color:{_MUTED};
                   text-transform:uppercase;letter-spacing:0.05em;">License</th>
        <th style="padding:8px 10px;text-align:left;font-size:11px;color:{_MUTED};
                   text-transform:uppercase;letter-spacing:0.05em;">Type</th>
        <th style="padding:8px 10px;text-align:left;font-size:11px;color:{_MUTED};
                   text-transform:uppercase;letter-spacing:0.05em;">Expiry</th>
        <th style="padding:8px 10px;text-align:left;font-size:11px;color:{_MUTED};
                   text-transform:uppercase;letter-spacing:0.05em;">Status</th>
      </tr>
      {rows}
    </table>

    {_card(f'''
        <p style="margin:0;font-size:12px;"><strong>Note:</strong> Under the FSSAI
           Licensing &amp; Registration Amendment 2026, licenses issued after March 2026
           have perpetual validity &mdash; no renewal required.</p>
    ''')}

    <p style="margin:24px 0 0;">{_btn('Manage Licenses', f'{_BASE_URL}/renewals')}</p>
    """
    _send_email(f"[RegBite] License Reminder: {subject_detail}", body, _to([user.email]))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. REPORT SHARED
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send_report_shared_email(user, product_name: str, share_url: str, expires_at: str):
    """Sent when a compliance report share link is created."""
    if not user or not user.email:
        return

    body = f"""
    <h2 style="margin:0 0 16px;font-size:18px;font-weight:600;color:{_INK};">
        Report Shared</h2>
    <p>A shareable link has been created for the compliance report of
       <strong>{product_name}</strong>.</p>

    {_card(f'''
        <p style="margin:0 0 4px;color:{_MUTED};font-size:11px;
                  text-transform:uppercase;letter-spacing:0.05em;">Share URL</p>
        <p style="margin:0;word-break:break-all;font-size:13px;">
            <a href="{share_url}" style="color:{_BLUE};">{share_url}</a></p>
        <p style="margin:8px 0 0;font-size:11px;color:{_LIGHT};">
            Valid until {expires_at}</p>
    ''')}

    <p style="color:{_MUTED};font-size:12px;">
        Anyone with this link can view the report without signing in.
        The link expires automatically after 30 days.</p>

    <p style="margin:24px 0 0;">{_btn('View Reports', f'{_BASE_URL}/reports')}</p>
    """
    _send_email(f"[RegBite] Report Shared — {product_name}", body, _to([user.email]))
