import { Resend } from 'resend';

// Lazy placeholder — prevents "Missing API key" throw at module-eval time during `next build`
export const resend = new Resend(process.env.RESEND_API_KEY ?? 'resend-not-configured');

const FROM = 'RegBite US <noreply@regbite.com>';

export interface SendEmailOptions {
  to: string | string[];
  subject: string;
  html: string;
}

export async function sendEmail(opts: SendEmailOptions) {
  return resend.emails.send({ from: FROM, ...opts });
}

// ── Email templates ────────────────────────────────────────────────────────────

export function welcomeEmail(name: string, orgName: string): SendEmailOptions {
  return {
    to: '',
    subject: 'Welcome to RegBite US',
    html: `
      <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
        <h1 style="color: #1a1a2e; font-size: 24px;">Welcome to RegBite US, ${name}!</h1>
        <p>Your workspace <strong>${orgName}</strong> is ready.</p>
        <p>RegBite US helps you navigate FDA/DSHEA supplement compliance before you go to market. Here's what you can do:</p>
        <ul>
          <li><strong>Ingredient Checker</strong> — Look up FDA status, GRAS classification, and warning letter history for any ingredient</li>
          <li><strong>Formulation Analyzer</strong> — Run a pre-market compliance check on your full formulation</li>
          <li><strong>Label Validator</strong> — Verify your Supplement Facts panel against 21 CFR § 101.36</li>
          <li><strong>Claims Checker</strong> — Detect disease claims and generate compliant rewrites</li>
        </ul>
        <a href="${process.env.NEXT_PUBLIC_APP_URL ?? 'https://app.regbite.com'}/dashboard"
           style="display: inline-block; background: #4f46e5; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; margin-top: 16px;">
          Open Dashboard →
        </a>
        <p style="margin-top: 32px; color: #6b7280; font-size: 12px;">
          RegBite US · FDA Supplement Compliance Platform
        </p>
      </div>
    `,
  };
}

export function complianceAlertEmail(
  productName: string,
  issues: { severity: string; message: string }[],
  appUrl: string,
): SendEmailOptions {
  const criticalCount = issues.filter((i) => i.severity === 'CRITICAL').length;
  const issueRows = issues
    .slice(0, 5)
    .map((i) => `<li style="margin-bottom: 8px;"><strong>[${i.severity}]</strong> ${i.message}</li>`)
    .join('');

  return {
    to: '',
    subject: `Compliance Alert: ${productName} — ${criticalCount} critical issue${criticalCount !== 1 ? 's' : ''}`,
    html: `
      <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #dc2626;">Compliance Issues Detected</h2>
        <p>Your compliance check for <strong>${productName}</strong> found ${issues.length} issue(s).</p>
        <ul>${issueRows}</ul>
        ${issues.length > 5 ? `<p style="color: #6b7280;">… and ${issues.length - 5} more</p>` : ''}
        <a href="${appUrl}" style="display: inline-block; background: #4f46e5; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; margin-top: 16px;">
          View Full Report →
        </a>
      </div>
    `,
  };
}

export function regulatoryDigestEmail(
  changes: { title: string; severity: string; source: string }[],
  weekOf: string,
): SendEmailOptions {
  const rows = changes
    .slice(0, 10)
    .map(
      (c) =>
        `<tr>
          <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${c.title}</td>
          <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; white-space: nowrap;">${c.severity}</td>
          <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; color: #6b7280;">${c.source}</td>
        </tr>`,
    )
    .join('');

  return {
    to: '',
    subject: `Weekly Regulatory Digest — ${weekOf}`,
    html: `
      <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #1a1a2e;">Regulatory Update Digest</h2>
        <p>Week of ${weekOf} — ${changes.length} regulatory change(s) detected.</p>
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
          <thead>
            <tr style="background: #f9fafb;">
              <th style="padding: 8px; text-align: left;">Change</th>
              <th style="padding: 8px; text-align: left;">Severity</th>
              <th style="padding: 8px; text-align: left;">Source</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
        <a href="${process.env.NEXT_PUBLIC_APP_URL ?? 'https://app.regbite.com'}/regulatory"
           style="display: inline-block; background: #4f46e5; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; margin-top: 16px;">
          View Full Feed →
        </a>
      </div>
    `,
  };
}

export function teamInviteEmail(
  inviterName: string,
  orgName: string,
  inviteUrl: string,
): SendEmailOptions {
  return {
    to: '',
    subject: `${inviterName} invited you to join ${orgName} on RegBite US`,
    html: `
      <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #1a1a2e;">You've been invited to ${orgName}</h2>
        <p><strong>${inviterName}</strong> invited you to collaborate on FDA supplement compliance in RegBite US.</p>
        <a href="${inviteUrl}" style="display: inline-block; background: #4f46e5; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; margin-top: 16px;">
          Accept Invitation →
        </a>
        <p style="margin-top: 32px; color: #6b7280; font-size: 12px;">
          If you didn't expect this invitation, you can safely ignore this email.
        </p>
      </div>
    `,
  };
}
