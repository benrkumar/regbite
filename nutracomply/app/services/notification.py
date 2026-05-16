"""
Notification Service — sends all transactional emails via Brevo SMTP.

Email Workflows:
  1. Compliance Alert      — CRITICAL/HIGH violations detected on a label
  2. Regulation Change     — new FSSAI/AYUSH/LM regulation detected by scraper
  3. Welcome               — sent on registration
  4. Team Invite           — sent when admin invites a team member
  5. Invite Accepted       — sent to inviter when member joins
  6. Payment Confirmation  — sent after successful Razorpay payment
  7. Subscription Cancelled — sent when subscription is cancelled
  8. Password Changed      — security confirmation
  9. License Expiry Reminder — sent when licenses are expiring soon
 10. Report Shared         — sent when a compliance report link is created
"""

import html
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import get_settings

settings = get_settings()

# Public base URL for links in emails — configurable via APP_BASE_URL env var
_BASE = settings.app_base_url.rstrip("/")

# ── Shared email wrapper ─────────────────────────────────────────────────────

_FOOTER = (
    "<hr style='border:none;border-top:1px solid #e5e7eb;margin:24px 0 16px;'/>"
    "<p style='color:#9ca3af;font-size:0.8em;line-height:1.5;'>"
    "RegBite — AI-Powered FSSAI Compliance<br/>"
    "Not legal advice. For regulatory compliance assistance only.<br/>"
    f"<a href='{_BASE}/settings' "
    "style='color:#6b7280;'>Manage notification preferences</a>"
    "</p>"
)


def _wrap_html(body_html: str) -> str:
    """Wrap email body in a consistent container with footer."""
    return (
        "<div style='font-family:-apple-system,BlinkMacSystemFont,sans-serif;"
        "max-width:600px;margin:0 auto;color:#1f2937;line-height:1.6;'>"
        f"{body_html}"
        f"{_FOOTER}"
        "</div>"
    )


def _get_recipients(user=None) -> list[str]:
    """
    Build recipient list from user's notification_emails + fallback setting.
    Deduplicates and returns up to 5 addresses.
    """
    recipients = set()

    # Per-user notification emails (up to 5)
    if user and user.notification_emails:
        for email in user.notification_emails:
            if email:
                recipients.add(email.lower())

    # Also add the user's own email if they have one
    if user and hasattr(user, "email") and user.email:
        recipients.add(user.email.lower())

    # Fallback global setting
    if settings.alert_to_email:
        recipients.add(settings.alert_to_email.lower())

    return list(recipients)[:5]


def _send_to(recipients: list[str]) -> list[str]:
    """Send to specific addresses (no user lookup)."""
    return [r.lower() for r in recipients if r][:5]


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
    msg.attach(MIMEText(_wrap_html(html_body), "html"))

    try:
        with smtplib.SMTP(settings.brevo_smtp_host, settings.brevo_smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.brevo_smtp_user, settings.brevo_smtp_password)
            server.sendmail(settings.alert_from_email, recipients, msg.as_string())
        print(f"[notify] Sent to {len(recipients)} recipient(s): {subject}")
    except Exception as e:
        print(f"[notify] Failed: {e} — {subject}")


# ── 1. Compliance Alert ──────────────────────────────────────────────────────

def send_alert_email(alert, product=None, user=None):
    """Send compliance alert email when CRITICAL/HIGH violations detected."""
    recipients = _get_recipients(user)
    if not recipients:
        return

    product_name = html.escape(product.name if product else "Unknown Product")
    severity_color = "#DC2626" if alert.severity.value == "CRITICAL" else "#EA580C"
    subject = f"[RegBite] {alert.severity.value}: {alert.title}"

    violations_html = ""
    for v in (alert.rule_violations or []):
        sev = v.get("severity", "")
        sev_color = "#DC2626" if sev == "CRITICAL" else "#EA580C" if sev == "HIGH" else "#D97706"
        violations_html += (
            f"<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #f3f4f6;'>"
            f"<span style='color:{sev_color};font-weight:600;font-size:0.75em;'>{html.escape(sev)}</span> "
            f"<strong>{html.escape(v.get('rule_code', ''))}</strong></td>"
            f"<td style='padding:8px;border-bottom:1px solid #f3f4f6;'>{html.escape(v.get('message', ''))}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #f3f4f6;font-size:0.85em;color:#6b7280;'>"
            f"{html.escape(v.get('remediation', ''))}</td>"
            f"</tr>"
        )

    body = f"""
    <h2 style='color:{severity_color};margin:0 0 8px;'>Compliance Alert: {alert.severity.value}</h2>
    <p style='margin:0 0 16px;color:#6b7280;'>{datetime.utcnow().strftime('%d %b %Y, %H:%M')} UTC</p>

    <div style='background:#fef2f2;border-left:4px solid {severity_color};padding:12px 16px;margin:0 0 20px;border-radius:4px;'>
        <p style='margin:0;'><strong>Product:</strong> {product_name}</p>
        <p style='margin:4px 0 0;'>{html.escape(alert.message or '')}</p>
    </div>

    <h3 style='margin:0 0 8px;font-size:1em;'>Violations Found</h3>
    <table style='width:100%;border-collapse:collapse;font-size:0.9em;'>
        <tr style='background:#f9fafb;'>
            <th style='padding:8px;text-align:left;'>Rule</th>
            <th style='padding:8px;text-align:left;'>Issue</th>
            <th style='padding:8px;text-align:left;'>Remediation</th>
        </tr>
        {violations_html}
    </table>

    <p style='margin:20px 0 0;'>
        <a href='{_BASE}/alerts'
           style='display:inline-block;padding:10px 20px;background:#111;color:#fff;
                  text-decoration:none;border-radius:4px;font-weight:500;'>
            View in RegBite
        </a>
    </p>
    """
    _send_email(subject, body, recipients)


# ── 2. Regulation Change ─────────────────────────────────────────────────────

def send_regulation_change_email(change, users=None):
    """Send email about a new FSSAI/AYUSH/Legal Metrology regulation change."""
    if users:
        all_recipients = set()
        for u in users:
            for addr in _get_recipients(u):
                all_recipients.add(addr)
        recipients = list(all_recipients)[:20]
    else:
        recipients = _get_recipients()

    if not recipients:
        return

    source_url = change.source_url or ""
    if "ayush.gov.in" in source_url:
        source_org = "Ministry of AYUSH"
    elif "consumeraffairs.nic.in" in source_url or "legalmetrology" in source_url.lower():
        source_org = "Legal Metrology"
    else:
        source_org = "FSSAI"

    severity_color = "#DC2626" if change.severity.value in ("CRITICAL", "HIGH") else "#D97706"
    subject = f"[RegBite] {source_org} Update: {change.document_name[:60]}"

    body = f"""
    <h2 style='color:#111;margin:0 0 8px;'>Regulation Change Detected</h2>
    <p style='margin:0 0 16px;color:#6b7280;'>{change.detected_at.strftime('%d %b %Y')}</p>

    <div style='background:#f0f9ff;border-left:4px solid #3b82f6;padding:12px 16px;margin:0 0 20px;border-radius:4px;'>
        <p style='margin:0;'><strong>Source:</strong> {source_org}</p>
        <p style='margin:4px 0 0;'><strong>Type:</strong> {change.change_type.value.replace('_', ' ').title()}</p>
        <p style='margin:4px 0 0;'><strong>Severity:</strong>
            <span style='color:{severity_color};font-weight:600;'>{change.severity.value}</span></p>
        <p style='margin:4px 0 0;'><strong>Document:</strong> {change.document_name}</p>
    </div>

    <h3 style='margin:0 0 8px;font-size:1em;'>Summary</h3>
    <p>{change.summary_text or 'See full details in RegBite.'}</p>

    <p style='margin:20px 0 0;'>
        <a href='{_BASE}/regulations'
           style='display:inline-block;padding:10px 20px;background:#111;color:#fff;
                  text-decoration:none;border-radius:4px;font-weight:500;'>
            View Regulation Feed
        </a>
    </p>
    """
    _send_email(subject, body, recipients)


# ── 3. Welcome Email ─────────────────────────────────────────────────────────

def send_welcome_email(user):
    """Send welcome email after registration."""
    if not user or not user.email:
        return

    subject = "Welcome to RegBite — FSSAI Compliance Made Simple"
    body = f"""
    <h2 style='color:#111;margin:0 0 8px;'>Welcome to RegBite, {user.name}!</h2>
    <p>Your account is ready. Here's how to get started:</p>

    <div style='margin:20px 0;'>
        <div style='padding:12px 16px;background:#f9fafb;border-radius:4px;margin:0 0 8px;'>
            <strong>1.</strong> Add your nutraceutical products
        </div>
        <div style='padding:12px 16px;background:#f9fafb;border-radius:4px;margin:0 0 8px;'>
            <strong>2.</strong> Upload label images or PDFs
        </div>
        <div style='padding:12px 16px;background:#f9fafb;border-radius:4px;margin:0 0 8px;'>
            <strong>3.</strong> Get instant compliance reports against 64 FSSAI rules
        </div>
    </div>

    <p>We've added 5 demo products to your account so you can explore the platform right away.</p>

    <p style='margin:20px 0 0;'>
        <a href='{_BASE}/dashboard'
           style='display:inline-block;padding:10px 20px;background:#111;color:#fff;
                  text-decoration:none;border-radius:4px;font-weight:500;'>
            Go to Dashboard
        </a>
    </p>

    <p style='color:#6b7280;margin:20px 0 0;font-size:0.9em;'>
        <strong>Tip:</strong> Go to Settings → Notifications to add team email addresses
        that should receive compliance alerts.
    </p>
    """
    _send_email(subject, body, _send_to([user.email]))


# ── 4. Team Invite Email ─────────────────────────────────────────────────────

def send_team_invite_email(invite_email: str, inviter_name: str, role: str, invite_url: str):
    """Send team invitation email to new member."""
    subject = f"{inviter_name} invited you to RegBite"
    body = f"""
    <h2 style='color:#111;margin:0 0 8px;'>You're Invited to RegBite</h2>
    <p><strong>{inviter_name}</strong> has invited you to join their team as a
       <strong>{role.replace('_', ' ').title()}</strong>.</p>

    <div style='background:#f0fdf4;border-left:4px solid #22c55e;padding:12px 16px;margin:20px 0;border-radius:4px;'>
        <p style='margin:0;'>RegBite is an AI-powered FSSAI compliance platform for
           India's nutraceutical industry. As a team member, you'll have access to
           compliance reports, product management, and regulation monitoring.</p>
    </div>

    <p style='margin:20px 0;'>
        <a href='{invite_url}'
           style='display:inline-block;padding:12px 28px;background:#111;color:#fff;
                  text-decoration:none;border-radius:4px;font-weight:500;font-size:1.05em;'>
            Accept Invitation
        </a>
    </p>

    <p style='color:#6b7280;font-size:0.85em;'>
        This invitation expires in 7 days. If you didn't expect this, you can ignore this email.
    </p>
    """
    _send_email(subject, body, _send_to([invite_email]))


# ── 5. Invite Accepted ───────────────────────────────────────────────────────

def send_invite_accepted_email(inviter, new_member_name: str, new_member_email: str, role: str):
    """Notify inviter that their team member accepted."""
    if not inviter or not inviter.email:
        return

    subject = f"[RegBite] {new_member_name} joined your team"
    body = f"""
    <h2 style='color:#111;margin:0 0 8px;'>New Team Member</h2>
    <p><strong>{new_member_name}</strong> ({new_member_email}) has accepted your invitation
       and joined your team as a <strong>{role.replace('_', ' ').title()}</strong>.</p>

    <p style='margin:20px 0 0;'>
        <a href='{_BASE}/team'
           style='display:inline-block;padding:10px 20px;background:#111;color:#fff;
                  text-decoration:none;border-radius:4px;font-weight:500;'>
            View Team
        </a>
    </p>
    """
    _send_email(subject, body, _send_to([inviter.email]))


# ── 6. Payment Confirmation ──────────────────────────────────────────────────

def send_payment_confirmation_email(user, plan: str, amount_display: str, period_end: str):
    """Send payment confirmation after successful Razorpay payment."""
    if not user or not user.email:
        return

    subject = f"[RegBite] Payment Confirmed — {plan.title()} Plan"
    body = f"""
    <h2 style='color:#111;margin:0 0 8px;'>Payment Confirmed</h2>
    <p>Thank you, {user.name}! Your payment has been processed successfully.</p>

    <div style='background:#f0fdf4;border-left:4px solid #22c55e;padding:12px 16px;margin:20px 0;border-radius:4px;'>
        <table style='width:100%;'>
            <tr><td style='padding:4px 0;color:#6b7280;'>Plan</td>
                <td style='padding:4px 0;font-weight:600;'>{plan.title()}</td></tr>
            <tr><td style='padding:4px 0;color:#6b7280;'>Amount</td>
                <td style='padding:4px 0;font-weight:600;'>{amount_display}</td></tr>
            <tr><td style='padding:4px 0;color:#6b7280;'>Valid Until</td>
                <td style='padding:4px 0;font-weight:600;'>{period_end}</td></tr>
        </table>
    </div>

    <p style='margin:20px 0 0;'>
        <a href='{_BASE}/billing'
           style='display:inline-block;padding:10px 20px;background:#111;color:#fff;
                  text-decoration:none;border-radius:4px;font-weight:500;'>
            View Billing
        </a>
    </p>
    """
    _send_email(subject, body, _send_to([user.email]))


# ── 7. Subscription Cancelled ────────────────────────────────────────────────

def send_subscription_cancelled_email(user, access_until: str):
    """Send confirmation when subscription is cancelled."""
    if not user or not user.email:
        return

    subject = "[RegBite] Subscription Cancelled"
    body = f"""
    <h2 style='color:#111;margin:0 0 8px;'>Subscription Cancelled</h2>
    <p>Hi {user.name}, your subscription has been cancelled as requested.</p>

    <div style='background:#fffbeb;border-left:4px solid #f59e0b;padding:12px 16px;margin:20px 0;border-radius:4px;'>
        <p style='margin:0;'>Your current access continues until <strong>{access_until}</strong>.
           After that, your account will revert to the Free plan.</p>
    </div>

    <p style='color:#6b7280;'>You can resubscribe at any time from the Billing page.
       Your data will be preserved.</p>

    <p style='margin:20px 0 0;'>
        <a href='{_BASE}/billing'
           style='display:inline-block;padding:10px 20px;background:#111;color:#fff;
                  text-decoration:none;border-radius:4px;font-weight:500;'>
            View Billing
        </a>
    </p>
    """
    _send_email(subject, body, _send_to([user.email]))


# ── 8. Password Changed ─────────────────────────────────────────────────────

def send_password_changed_email(user):
    """Security notification when password is changed."""
    if not user or not user.email:
        return

    subject = "[RegBite] Password Changed"
    body = f"""
    <h2 style='color:#111;margin:0 0 8px;'>Password Changed</h2>
    <p>Hi {user.name}, your RegBite password was changed on
       {datetime.utcnow().strftime('%d %b %Y at %H:%M')} UTC.</p>

    <div style='background:#fef2f2;border-left:4px solid #DC2626;padding:12px 16px;margin:20px 0;border-radius:4px;'>
        <p style='margin:0;'>If you did not make this change, please
           <a href='{_BASE}/login'
              style='color:#DC2626;font-weight:600;'>sign in immediately</a>
           and reset your password, or contact support.</p>
    </div>
    """
    _send_email(subject, body, _send_to([user.email]))


# ── 9. License Expiry Reminder ───────────────────────────────────────────────

def send_license_expiry_email(user, licenses: list):
    """
    Send reminder about expiring/expired licenses.
    `licenses` is a list of dicts: [{"name": ..., "type": ..., "expiry_date": ..., "days": ...}]
    """
    if not user or not user.email or not licenses:
        return

    rows = ""
    for lic in licenses:
        days = lic["days"]
        if days < 0:
            status = f'<span style="color:#DC2626;font-weight:600;">Expired {abs(days)}d ago</span>'
        elif days == 0:
            status = '<span style="color:#DC2626;font-weight:600;">Expires today</span>'
        elif days <= 30:
            status = f'<span style="color:#EA580C;font-weight:600;">{days} days left</span>'
        else:
            status = f'<span style="color:#D97706;">{days} days left</span>'

        rows += (
            f"<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #f3f4f6;'>{lic['name']}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #f3f4f6;'>{lic['type']}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #f3f4f6;'>{lic['expiry_date']}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #f3f4f6;'>{status}</td>"
            f"</tr>"
        )

    expired_count = sum(1 for l in licenses if l["days"] < 0)
    urgent_count = sum(1 for l in licenses if 0 <= l["days"] <= 30)
    subject_parts = []
    if expired_count:
        subject_parts.append(f"{expired_count} expired")
    if urgent_count:
        subject_parts.append(f"{urgent_count} expiring soon")
    subject = f"[RegBite] License Reminder: {', '.join(subject_parts) or f'{len(licenses)} license(s) need attention'}"

    body = f"""
    <h2 style='color:#111;margin:0 0 8px;'>License Renewal Reminder</h2>
    <p>Hi {user.name}, the following licenses need your attention:</p>

    <table style='width:100%;border-collapse:collapse;font-size:0.9em;margin:16px 0;'>
        <tr style='background:#f9fafb;'>
            <th style='padding:8px;text-align:left;'>License</th>
            <th style='padding:8px;text-align:left;'>Type</th>
            <th style='padding:8px;text-align:left;'>Expiry</th>
            <th style='padding:8px;text-align:left;'>Status</th>
        </tr>
        {rows}
    </table>

    <p style='margin:20px 0 0;'>
        <a href='{_BASE}/renewals'
           style='display:inline-block;padding:10px 20px;background:#111;color:#fff;
                  text-decoration:none;border-radius:4px;font-weight:500;'>
            Manage Licenses
        </a>
    </p>
    """
    _send_email(subject, body, _send_to([user.email]))


# ── 10. Report Shared ────────────────────────────────────────────────────────

def send_report_shared_email(user, product_name: str, share_url: str, expires_at: str):
    """Notify user that their compliance report share link was created."""
    if not user or not user.email:
        return

    subject = f"[RegBite] Compliance Report Shared — {product_name}"
    body = f"""
    <h2 style='color:#111;margin:0 0 8px;'>Report Shared</h2>
    <p>A shareable link has been created for the compliance report of
       <strong>{product_name}</strong>.</p>

    <div style='background:#f9fafb;border:1px solid #e5e7eb;padding:12px 16px;margin:20px 0;border-radius:4px;'>
        <p style='margin:0 0 4px;color:#6b7280;font-size:0.85em;'>Share URL (valid until {expires_at}):</p>
        <p style='margin:0;word-break:break-all;'>
            <a href='{share_url}' style='color:#4f46e5;'>{share_url}</a>
        </p>
    </div>

    <p style='color:#6b7280;font-size:0.85em;'>
        Anyone with this link can view the report without signing in.
        The link expires automatically after 30 days.
    </p>
    """
    _send_email(subject, body, _send_to([user.email]))


# ── 11. Bulk Upload Complete ─────────────────────────────────────────────────

def send_bulk_complete_email(user, results: list):
    """Send a summary email when all labels in a bulk upload batch are analyzed."""
    recipients = _get_recipients(user)
    if not recipients:
        return

    total = len(results)
    label_word = "labels" if total != 1 else "label"
    have_word = "have" if total != 1 else "has"
    subject = f"[RegBite] Bulk analysis complete — {total} {label_word} ready"

    rows_html = ""
    for r in results:
        score = r.get("score", 0)
        name  = r.get("product_name", "Unknown")
        lid   = r.get("label_id")
        color = "#16a34a" if score >= 80 else "#dc2626" if score < 50 else "#ea580c"
        url   = f"{_BASE}/labels/{lid}"
        rows_html += (
            "<tr>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #f3f4f6;'>{name}</td>"
            "<td style='padding:8px 12px;border-bottom:1px solid #f3f4f6;text-align:center;'>"
            f"<span style='color:{color};font-weight:600;'>{score}%</span></td>"
            "<td style='padding:8px 12px;border-bottom:1px solid #f3f4f6;text-align:center;'>"
            f"<a href='{url}' style='color:#2B4874;text-decoration:none;'>View Report →</a></td>"
            "</tr>"
        )

    body = (
        "<h2 style='color:#111827;margin:0 0 8px;'>Bulk Analysis Complete</h2>"
        f"<p style='color:#6b7280;margin:0 0 20px;'>Your {total} {label_word} {have_word} been analyzed "
        "and compliance reports are ready.</p>"
        "<table style='width:100%;border-collapse:collapse;font-size:0.9em;'>"
        "<thead><tr style='background:#f9fafb;'>"
        "<th style='padding:8px 12px;text-align:left;border-bottom:2px solid #e5e7eb;"
        "font-weight:600;color:#374151;'>Product</th>"
        "<th style='padding:8px 12px;text-align:center;border-bottom:2px solid #e5e7eb;"
        "font-weight:600;color:#374151;'>Score</th>"
        "<th style='padding:8px 12px;text-align:center;border-bottom:2px solid #e5e7eb;"
        "font-weight:600;color:#374151;'>Report</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table>"
        "<p style='margin-top:24px;'>"
        f"<a href='{_BASE}/products' style='background:#2B4874;color:white;"
        "padding:10px 20px;border-radius:6px;text-decoration:none;"
        "display:inline-block;font-size:0.9em;font-weight:500;'>View All Products →</a></p>"
    )
    _send_email(subject, body, recipients)
