export default function PrivacyPage() {
  const EFFECTIVE = "May 15, 2026";

  return (
    <main className="max-w-3xl mx-auto px-6 py-16">
      <h1 className="text-4xl font-bold text-gray-900 mb-2">Privacy Policy</h1>
      <p className="text-sm text-gray-400 mb-10">Effective: {EFFECTIVE}</p>

      <div className="space-y-8 text-gray-600 leading-relaxed text-sm">
        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">1. Information We Collect</h2>
          <p>We collect information you provide directly:</p>
          <ul className="list-disc pl-5 mt-2 space-y-1">
            <li>Account information (email, name) via Clerk authentication</li>
            <li>Organization details (company name)</li>
            <li>Formula and ingredient data you enter for compliance checks</li>
            <li>Billing information via Stripe (we do not store card numbers)</li>
          </ul>
          <p className="mt-3">We collect information automatically:</p>
          <ul className="list-disc pl-5 mt-2 space-y-1">
            <li>Usage data (features used, compliance checks run)</li>
            <li>Browser and device information</li>
            <li>IP addresses and approximate location</li>
          </ul>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">2. How We Use Your Information</h2>
          <ul className="list-disc pl-5 space-y-1">
            <li>To provide and improve the Service</li>
            <li>To process payments and manage subscriptions</li>
            <li>To send transactional emails (compliance alerts, receipts)</li>
            <li>To send regulatory digest emails (you may unsubscribe)</li>
            <li>To analyze usage and improve compliance rules</li>
            <li>To comply with legal obligations</li>
          </ul>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">3. Formula and Ingredient Data</h2>
          <p>
            Formula and ingredient data you submit for compliance checks is stored to provide the Service and may be used in
            aggregate (non-identifiable) form to improve our compliance rules. We do not share your specific formula data
            with third parties. You may request deletion of your data at any time.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">4. Third-Party Services</h2>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong>Clerk</strong> — authentication and identity management</li>
            <li><strong>Stripe</strong> — payment processing (subject to Stripe&apos;s Privacy Policy)</li>
            <li><strong>Resend</strong> — transactional email delivery</li>
            <li><strong>Anthropic Claude</strong> — AI-powered compliance analysis (data processed by Anthropic&apos;s API)</li>
            <li><strong>PostHog</strong> — usage analytics (may be disabled by browser privacy controls)</li>
          </ul>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">5. Data Retention</h2>
          <p>
            We retain your account and formula data for as long as your account is active. After account deletion, we retain
            data for up to 90 days for backup purposes, then permanently delete it. Billing records are retained for 7 years
            as required by law.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">6. Your Rights</h2>
          <p>You have the right to:</p>
          <ul className="list-disc pl-5 mt-2 space-y-1">
            <li>Access the personal data we hold about you</li>
            <li>Request correction of inaccurate data</li>
            <li>Request deletion of your account and data</li>
            <li>Export your formula and compliance data</li>
            <li>Opt out of marketing emails</li>
          </ul>
          <p className="mt-2">
            To exercise these rights, contact us at <a href="mailto:privacy@regbiteusa.com" className="text-brand-700 underline">privacy@regbiteusa.com</a>.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">7. Security</h2>
          <p>
            We use industry-standard security practices including TLS encryption in transit, encrypted databases at rest,
            and access controls limiting who can view customer data. No method of transmission over the internet is 100% secure.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">8. California Residents</h2>
          <p>
            California residents have additional rights under the CCPA/CPRA, including the right to know, delete, and opt-out
            of sale of personal information. We do not sell personal information. To exercise CCPA rights, contact us at
            <a href="mailto:privacy@regbiteusa.com" className="text-brand-700 underline ml-1">privacy@regbiteusa.com</a>.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">9. Changes to This Policy</h2>
          <p>
            We may update this Privacy Policy from time to time. We will notify you of material changes via email.
            Continued use of the Service after changes constitutes acceptance of the updated policy.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">10. Contact</h2>
          <p>
            Privacy questions: <a href="mailto:privacy@regbiteusa.com" className="text-brand-700 underline">privacy@regbiteusa.com</a>
          </p>
        </section>
      </div>
    </main>
  );
}
