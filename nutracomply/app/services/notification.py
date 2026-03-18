"""
Notification Service — sends email alerts via Brevo SMTP (free tier).
Supports multi-recipient: sends to user.notification_emails (up to 5)
plus the fallback alert_to_email from settings.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import get_settings

settings = get_settings()


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

    # Fallback global setting
    if settings.alert_to_email:
        recipients.add(settings.alert_to_email.lower())

    return list(recipients)[:5]


def _send_email(subject: str, html_body: str, recipients: list[str]):
    """Send an HTML email to all recipients via Brevo SMTP."""
    if not settings.brevo_smtp_user:
        print("[notify] SMTP not configured, skipping email")
        return
    if not recipients:
        print("[notify] No recipients configured, skipping email")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.alert_from_email
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.brevo_smtp_host, settings.brevo_smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.brevo_smtp_user, settings.brevo_smtp_password)
            server.sendmail(settings.alert_from_email, recipients, msg.as_string())
        print(f"[notify] Email sent to {len(recipients)} recipient(s): {subject}")
    except Exception as e:
        print(f"[notify] Failed to send email: {e}")
        raise


def send_alert_email(alert, product=None, user=None):
    """Send a compliance alert email to all of the user's notification addresses."""
    recipients = _get_recipients(user)
    if not recipients:
        return

    product_name = product.name if product else "Unknown Product"
    subject = f"[RegBite] {alert.severity.value}: {alert.title} — {product_name}"

    body_lines = [
        f"<h2 style='color:#4f46e5;'>RegBite Compliance Alert</h2>",
        f"<p><strong>Product:</strong> {product_name}</p>",
        f"<p><strong>Severity:</strong> <span style='color:red;font-weight:700;'>{alert.severity.value}</span></p>",
        f"<p><strong>Alert:</strong> {alert.message}</p>",
        f"<hr/>",
        f"<h3>Violations Found:</h3>",
        f"<ul>",
    ]

    for v in (alert.rule_violations or []):
        body_lines.append(
            f"<li><strong>[{v.get('severity', '')}] {v.get('rule_code', '')}:</strong> "
            f"{v.get('message', '')} "
            f"<br/><em>Fix: {v.get('remediation', '')}</em></li>"
        )

    body_lines += [
        f"</ul>",
        f"<hr/>",
        f"<p style='color:#6b7280;font-size:0.85em;'>RegBite — FSSAI Compliance Monitor<br/>This alert was sent because your product does not meet FSSAI regulations.</p>",
    ]

    _send_email(subject, "\n".join(body_lines), recipients)


def send_regulation_change_email(change, users=None):
    """
    Send email about a new FSSAI/AYUSH/Legal Metrology regulation change.
    `users` is an optional list of User objects to notify; falls back to global setting.
    """
    if users:
        # Collect all unique recipient emails across all users
        all_recipients = set()
        for u in users:
            for addr in _get_recipients(u):
                all_recipients.add(addr)
        recipients = list(all_recipients)[:20]  # cap at 20 total
    else:
        recipients = _get_recipients()

    if not recipients:
        return

    # Derive source org from URL
    source_url = change.source_url or ""
    if "ayush.gov.in" in source_url:
        source_org = "Ministry of AYUSH"
    elif "consumeraffairs.nic.in" in source_url or "legalmetrology" in source_url.lower():
        source_org = "Legal Metrology"
    else:
        source_org = "FSSAI"

    subject = f"[RegBite] {source_org} Regulation Update: {change.change_type.value} — {change.document_name[:60]}"

    html_body = f"""
    <h2 style='color:#4f46e5;'>Regulation Change Detected</h2>
    <p><strong>Source:</strong> {source_org}</p>
    <p><strong>Change Type:</strong> {change.change_type.value.replace('_', ' ')}</p>
    <p><strong>Document:</strong> {change.document_name}</p>
    <p><strong>Severity:</strong> <strong style='color:{"red" if change.severity.value in ("CRITICAL","HIGH") else "orange"}'>{change.severity.value}</strong></p>
    <p><strong>Detected:</strong> {change.detected_at.strftime('%d %B %Y')}</p>
    <hr/>
    <h3>Summary:</h3>
    <p>{change.summary_text or 'See full details in RegBite.'}</p>
    <hr/>
    <p><a href='https://app.regbite.in/regulations' style='color:#4f46e5;'>View Regulation Feed in RegBite &rarr;</a></p>
    <p style='color:#9ca3af;font-size:0.8em;'>RegBite — FSSAI Compliance Monitor &nbsp;&middot;&nbsp; Not legal advice</p>
    """

    _send_email(subject, html_body, recipients)
