"""
Compliance Report Service — generates unique report IDs and PDF reports.
"""
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session, joinedload

from app.models import ComplianceReport, Product, LabelVersion, ComplianceCheck, CheckResult, Severity


def _generate_report_ref(db: Session) -> str:
    """Generate unique report reference: RB-YYYYMMDD-NNNN"""
    today = datetime.utcnow().strftime("%Y%m%d")
    prefix = f"RB-{today}-"

    # Find highest sequence for today
    existing = (
        db.query(ComplianceReport)
        .filter(ComplianceReport.report_ref.like(f"{prefix}%"))
        .order_by(ComplianceReport.report_ref.desc())
        .first()
    )

    if existing:
        try:
            seq = int(existing.report_ref.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1

    return f"{prefix}{seq:04d}"


def get_or_create_report(
    db: Session,
    user_id: int,
    product_id: int,
    label_version_id: int,
) -> "ComplianceReport":
    """Get existing report for this label version, or create a new one."""
    existing = (
        db.query(ComplianceReport)
        .filter(ComplianceReport.label_version_id == label_version_id)
        .first()
    )
    if existing:
        return existing

    # Get check results for this label version — load rules eagerly
    checks = (
        db.query(ComplianceCheck)
        .options(joinedload(ComplianceCheck.rule))
        .filter(ComplianceCheck.label_version_id == label_version_id)
        .all()
    )

    total = len(checks)
    passed = sum(1 for c in checks if c.result == CheckResult.PASS)
    score = round((passed / total) * 100) if total else 0

    if score >= 90:
        verdict = "COMPLIANT"
    elif score >= 60:
        verdict = "PARTIAL"
    else:
        verdict = "NON_COMPLIANT"

    check_results = []
    for c in checks:
        check_results.append({
            "rule_code": c.rule.rule_code if c.rule else "",
            "category": c.rule.category.value if c.rule else "",
            "severity": c.rule.severity.value if c.rule else "",
            "description": c.rule.description if c.rule else "",
            "regulation_source": c.rule.regulation_source if c.rule else "",
            "result": c.result.value,
            "message": c.message or "",
            "remediation": c.remediation or "",
            "actual_value": c.actual_value or "",
        })

    report = ComplianceReport(
        report_ref=_generate_report_ref(db),
        user_id=user_id,
        product_id=product_id,
        label_version_id=label_version_id,
        score=score,
        verdict=verdict,
        check_results=check_results,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def generate_share_token(db: Session, report: "ComplianceReport") -> str:
    """Generate a 30-day shareable link token."""
    token = secrets.token_urlsafe(32)
    report.share_token = token
    report.share_expires_at = datetime.utcnow() + timedelta(days=30)
    db.commit()
    return token


def generate_pdf_html(report: "ComplianceReport", product: "Product") -> str:
    """Generate the HTML content for a PDF report."""
    from datetime import datetime

    score = report.score or 0
    verdict = report.verdict or "PENDING"

    # Color based on score
    if score >= 90:
        score_color = "#16a34a"
        score_bg = "#dcfce7"
    elif score >= 60:
        score_color = "#d97706"
        score_bg = "#fef3c7"
    else:
        score_color = "#dc2626"
        score_bg = "#fee2e2"

    check_rows = ""
    for cr in (report.check_results or []):
        result = cr.get("result", "")
        sev = cr.get("severity", "")

        if result == "PASS":
            result_icon = "&#10003;"
            result_color = "#16a34a"
            result_bg = "#dcfce7"
        elif result == "FAIL":
            result_icon = "&#10007;"
            result_color = "#dc2626"
            result_bg = "#fee2e2"
        else:
            result_icon = "&#9888;"
            result_color = "#d97706"
            result_bg = "#fef3c7"

        remediation_html = ""
        if cr.get("remediation") and result != "PASS":
            remediation_html = f'<div style="font-size:10px;color:#6b7280;margin-top:3px;font-style:italic;">Fix: {cr["remediation"][:200]}</div>'

        check_rows += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;font-size:11px;color:#374151;">{cr.get('description','')[:80]}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;font-size:10px;color:#6b7280;">{cr.get('regulation_source','')[:60]}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;text-align:center;">
            <span style="background:{result_bg};color:{result_color};padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700;">{result_icon} {result}</span>
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;">
            <div style="font-size:10px;color:#374151;">{cr.get('message','')[:120]}</div>
            {remediation_html}
          </td>
        </tr>"""

    is_certificate = score >= 90
    cert_section = ""
    if is_certificate:
        cert_section = f"""
        <div style="margin:24px 0;padding:20px 24px;background:linear-gradient(135deg,#f0fdf4,#dcfce7);border:2px solid #16a34a;border-radius:12px;text-align:center;">
          <div style="font-size:28px;margin-bottom:8px;">&#127942;</div>
          <div style="font-size:18px;font-weight:800;color:#15803d;margin-bottom:4px;">COMPLIANCE CERTIFICATE</div>
          <div style="font-size:12px;color:#166534;">This product has achieved a compliance score of {score}% and meets all critical FSSAI requirements.</div>
          <div style="margin-top:12px;font-size:11px;color:#4b5563;">Certificate valid for 90 days from generation date · Subject to regulatory amendments</div>
        </div>"""

    num_checks = len(report.check_results or [])
    generated_str = report.created_at.strftime('%d %b %Y, %H:%M UTC') if report.created_at else "N/A"

    if score >= 90:
        verdict_desc = "All critical FSSAI compliance requirements met."
    elif score >= 60:
        verdict_desc = "Some requirements need attention before market release."
    else:
        verdict_desc = "Multiple critical violations require immediate correction."

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; margin:0; padding:0; color:#111827; background:#fff; }}
  @page {{ margin: 20mm; }}
  .page {{ max-width:900px; margin:0 auto; padding:20px; }}
  table {{ width:100%; border-collapse:collapse; }}
</style>
</head>
<body>
<div class="page">
  <!-- Header -->
  <div style="display:flex;justify-content:space-between;align-items:center;padding:16px 20px;background:#0f172a;border-radius:10px;margin-bottom:20px;">
    <div>
      <div style="font-size:20px;font-weight:900;color:#4ade80;letter-spacing:-0.03em;">RegBite</div>
      <div style="font-size:10px;color:#94a3b8;margin-top:2px;">India Nutraceutical Compliance Platform</div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:13px;font-weight:700;color:#f8fafc;">{report.report_ref}</div>
      <div style="font-size:10px;color:#94a3b8;">Generated: {generated_str}</div>
    </div>
  </div>

  <!-- Product info -->
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px 20px;margin-bottom:16px;">
    <div style="font-size:16px;font-weight:800;color:#0f172a;margin-bottom:8px;">{product.name}</div>
    <div style="display:flex;gap:16px;flex-wrap:wrap;">
      <span style="font-size:11px;color:#6b7280;"><b>Category:</b> {product.category or 'N/A'}</span>
      <span style="font-size:11px;color:#6b7280;"><b>SKU:</b> {product.sku or 'N/A'}</span>
    </div>
  </div>

  <!-- Score -->
  <div style="display:flex;gap:16px;margin-bottom:16px;">
    <div style="flex:1;background:{score_bg};border:2px solid {score_color};border-radius:10px;padding:16px 20px;text-align:center;">
      <div style="font-size:42px;font-weight:900;color:{score_color};line-height:1;">{score}%</div>
      <div style="font-size:11px;color:{score_color};font-weight:700;margin-top:4px;">COMPLIANCE SCORE</div>
    </div>
    <div style="flex:2;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px 20px;">
      <div style="font-size:13px;font-weight:800;color:#0f172a;margin-bottom:8px;">Verdict: <span style="color:{score_color};">{verdict.replace('_',' ')}</span></div>
      <div style="font-size:11px;color:#6b7280;line-height:1.6;">{verdict_desc}</div>
      <div style="font-size:10px;color:#9ca3af;margin-top:8px;">Checked against FSSAI (FSS 2022), Legal Metrology, AYUSH guidelines</div>
    </div>
  </div>

  {cert_section}

  <!-- Check results table -->
  <div style="margin-bottom:20px;">
    <div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:10px;padding-bottom:6px;border-bottom:2px solid #e2e8f0;">
      Detailed Compliance Check Results ({num_checks} checks)
    </div>
    <table>
      <thead>
        <tr style="background:#f1f5f9;">
          <th style="padding:8px 12px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;color:#6b7280;font-weight:700;">Check</th>
          <th style="padding:8px 12px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;color:#6b7280;font-weight:700;">Regulation</th>
          <th style="padding:8px 12px;text-align:center;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;color:#6b7280;font-weight:700;">Result</th>
          <th style="padding:8px 12px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;color:#6b7280;font-weight:700;">Details / Fix</th>
        </tr>
      </thead>
      <tbody>
        {check_rows}
      </tbody>
    </table>
  </div>

  <!-- Footer disclaimer -->
  <div style="border-top:1px solid #e2e8f0;padding-top:12px;font-size:9px;color:#9ca3af;text-align:center;line-height:1.6;">
    <strong>DISCLAIMER:</strong> This compliance report is generated for informational purposes only and does not constitute legal, regulatory, or professional advice.
    RegBite outputs should be verified against primary regulatory sources before making any business decisions.
    RegBite is not liable for any regulatory actions taken or not taken on the basis of this report.
    <br/>Report ID: {report.report_ref} · Platform: RegBite v3.0 · <b>Not a substitute for professional regulatory advice</b>
  </div>
</div>
</body>
</html>"""
    return html
