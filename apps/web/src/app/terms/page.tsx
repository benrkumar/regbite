export default function TermsPage() {
  const EFFECTIVE = "May 15, 2026";

  return (
    <main className="max-w-3xl mx-auto px-6 py-16">
      <h1 className="text-4xl font-bold text-gray-900 mb-2">Terms of Service</h1>
      <p className="text-sm text-gray-400 mb-10">Effective: {EFFECTIVE}</p>

      <div className="space-y-8 text-gray-600 leading-relaxed text-sm">
        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">1. Acceptance of Terms</h2>
          <p>
            By accessing or using RegBite US (&quot;Service&quot;), you agree to these Terms of Service. If you do not agree,
            do not use the Service. These terms constitute a legally binding agreement between you and RegBite US, Inc.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">2. Description of Service</h2>
          <p>
            RegBite US provides a compliance intelligence platform for US dietary supplement regulations. The Service includes
            ingredient checking, label validation, claims classification, NDI eligibility assessment, cGMP readiness audits,
            state compliance screening, and import intelligence tools.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">3. Not Legal Advice</h2>
          <p className="font-medium text-gray-800">
            THE SERVICE IS NOT A SUBSTITUTE FOR LEGAL ADVICE.
          </p>
          <p className="mt-2">
            Compliance checks and outputs from RegBite US reflect our interpretation of applicable US regulations at the time of
            your query. They do not constitute legal advice, regulatory guidance, or a guarantee of FDA compliance. You should
            verify all findings with a qualified regulatory attorney or consultant before making product or labeling decisions.
            Regulations change frequently; we do not guarantee that all regulatory data is current.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">4. Account and Organization</h2>
          <p>
            You must create an account to use the Service. You are responsible for maintaining the confidentiality of your
            credentials and for all activity under your account. Organizations on RegBite US are responsible for ensuring that
            all members comply with these Terms.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">5. Subscription and Billing</h2>
          <p>
            Paid plans are billed monthly or annually in advance. You authorize us to charge the payment method on file for
            all fees. Refunds are not issued for partial billing periods. You may cancel at any time; cancellation takes effect
            at the end of your current billing period.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">6. Acceptable Use</h2>
          <p>You agree not to use the Service to:</p>
          <ul className="list-disc pl-5 mt-2 space-y-1">
            <li>Violate any applicable law or regulation</li>
            <li>Reverse engineer, scrape, or systematically download Service data</li>
            <li>Resell or sublicense access to the Service without written permission</li>
            <li>Submit false, misleading, or fraudulent information</li>
          </ul>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">7. Intellectual Property</h2>
          <p>
            All content, software, and databases in the Service are the property of RegBite US, Inc. or its licensors.
            You may not copy, reproduce, or distribute Service content without prior written permission. Regulatory citations
            and statutory text are in the public domain; our compilations and analysis are proprietary.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">8. Disclaimer of Warranties</h2>
          <p>
            THE SERVICE IS PROVIDED &quot;AS IS&quot; WITHOUT WARRANTY OF ANY KIND. WE DISCLAIM ALL WARRANTIES, EXPRESS OR IMPLIED,
            INCLUDING WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT. WE DO NOT WARRANT
            THAT THE SERVICE IS ACCURATE, COMPLETE, OR CURRENT.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">9. Limitation of Liability</h2>
          <p>
            TO THE MAXIMUM EXTENT PERMITTED BY LAW, REGBITE US, INC. SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL,
            CONSEQUENTIAL, OR PUNITIVE DAMAGES ARISING FROM YOUR USE OF THE SERVICE. OUR TOTAL LIABILITY SHALL NOT EXCEED THE
            AMOUNT YOU PAID US IN THE TWELVE MONTHS PRECEDING THE CLAIM.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">10. Changes to Terms</h2>
          <p>
            We may update these Terms at any time. We will notify you of material changes via email or in-app notice.
            Continued use of the Service after changes constitutes acceptance of the new Terms.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-gray-900 mb-2">11. Contact</h2>
          <p>
            Questions about these Terms: <a href="mailto:legal@regbiteusa.com" className="text-brand-700 underline">legal@regbiteusa.com</a>
          </p>
        </section>
      </div>
    </main>
  );
}
