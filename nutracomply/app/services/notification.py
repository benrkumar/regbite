"""
Notification Service — sends email alerts via Brevo SMTP (free tier).
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import get_settings

settings = get_settings()


def send_alert_email(alert, product=None):
    """Send a compliance alert email."""
    if not settings.brevo_smtp_user or not settings.alert_to_email:
        print("[notify] SMTP not configured, skipping email")
        return

    product_name = product.name if product else "Unknown Product"
    subject = f"[RegBite] {alert.severity.value}: {alert.title} — {product_name}"

    body_lines = [
        f"<h2>RegBite Compliance Alert</h2>",
        f"<p><strong>Product:</strong> {product_name}</p>",
        f"<p><strong>Severity:</strong> <span style='color:red'>{alert.severity.value}</span></p>",
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
        f"<p><a href='http://localhost:8000/labels/{alert.label_version_id}'>View Full Report →</a></p>",
        f"<p style='color:gray;font-size:0.8em'>RegBite — FSSAI Compliance Monitor</p>",
    ]

    html_body = "\n".join(body_lines)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.alert_from_email
    msg["To"] = settings.alert_to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.brevo_smtp_host, settings.brevo_smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.brevo_smtp_user, settings.brevo_smtp_password)
            server.sendmail(settings.alert_from_email, settings.alert_to_email, msg.as_string())
        print(f"[notify] Alert email sent: {subject}")
    except Exception as e:
        print(f"[notify] Failed to send email: {e}")
        raise


def send_regulation_change_email(change):
    """Send email about a new FSSAI regulation change."""
    if not settings.brevo_smtp_user or not settings.alert_to_email:
        return

    subject = f"[RegBite] FSSAI Regulation Change: {change.change_type.value} — {change.document_name}"

    html_body = f"""
    <h2>FSSAI Regulation Change Detected</h2>
    <p><strong>Change Type:</strong> {change.change_type.value}</p>
    <p><strong>Document:</strong> {change.document_name}</p>
    <p><strong>Severity:</strong> {change.severity.value}</p>
    <p><strong>Detected At:</strong> {change.detected_at}</p>
    <hr/>
    <h3>Summary:</h3>
    <p>{change.summary_text or 'See full details in RegBite.'}</p>
    <hr/>
    <p><a href='http://localhost:8000/regulations'>View Regulation Feed →</a></p>
    <p style='color:gray;font-size:0.8em'>RegBite — FSSAI Compliance Monitor</p>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.alert_from_email
    msg["To"] = settings.alert_to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.brevo_smtp_host, settings.brevo_smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.brevo_smtp_user, settings.brevo_smtp_password)
            server.sendmail(settings.alert_from_email, settings.alert_to_email, msg.as_string())
        print(f"[notify] Regulation change email sent")
    except Exception as e:
        print(f"[notify] Regulation email failed: {e}")
