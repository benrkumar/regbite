export default function AboutPage() {
  return (
    <main className="max-w-3xl mx-auto px-6 py-16">
      <h1 className="text-4xl font-bold text-gray-900 mb-6">About RegBite US</h1>

      <div className="prose prose-gray max-w-none space-y-6 text-gray-600 leading-relaxed">
        <p className="text-lg text-gray-700">
          RegBite US is a pre-formulation compliance intelligence platform built for US dietary supplement brands,
          formulators, and regulatory consultants.
        </p>

        <p>
          The US dietary supplement industry operates under a complex patchwork of federal regulations — DSHEA, 21 CFR Part 111
          cGMP, 21 CFR 101.36 labeling, FSMA, FTC advertising standards, and state laws like California&apos;s Proposition 65.
          Navigating all of these simultaneously, before a single unit is manufactured, is exactly the problem we built RegBite US to solve.
        </p>

        <p>
          Our compliance engine is built code-first from primary sources: the Code of Federal Regulations (21 CFR), DSHEA statutory text,
          FDA guidance documents, NIH Dietary Reference Intakes, and OEHHA Prop 65 chemical data. Rules are version-controlled and
          updated when regulations change.
        </p>

        <h2 className="text-xl font-semibold text-gray-900 mt-10 mb-3">What we are</h2>
        <p>
          A compliance intelligence tool. We help you understand what the regulations say, check your formulas and labels against those
          requirements, and identify gaps before they become FDA warning letters or FTC enforcement actions.
        </p>

        <h2 className="text-xl font-semibold text-gray-900 mt-10 mb-3">What we are not</h2>
        <p>
          A law firm. A regulatory consultant. A guarantee of FDA approval. Compliance checks on RegBite US reflect our interpretation
          of applicable regulations and do not constitute legal advice. We strongly recommend that brands verify findings with a
          qualified regulatory attorney before product launch.
        </p>

        <h2 className="text-xl font-semibold text-gray-900 mt-10 mb-3">Data sources</h2>
        <ul className="list-disc pl-6 space-y-1 text-gray-600">
          <li>FDA Dietary Supplement Advisory List (DSIAL)</li>
          <li>FDA NDI Notification Database</li>
          <li>FDA GRAS Notices (GRN) database</li>
          <li>FDA Warning Letters (5-year history)</li>
          <li>NIH Office of Dietary Supplements — Dietary Reference Intakes</li>
          <li>OEHHA California Prop 65 Chemical List</li>
          <li>Federal Register (supplement-related notices)</li>
          <li>FDA Import Alert database</li>
          <li>FTC enforcement actions (dietary supplements)</li>
        </ul>

        <div className="mt-10 rounded-xl bg-gray-50 border border-gray-200 p-6">
          <p className="text-sm text-gray-700 font-semibold mb-1">Questions or feedback?</p>
          <p className="text-sm text-gray-500">
            Reach us at{" "}
            <a href="mailto:hello@regbiteusa.com" className="text-brand-700 underline">hello@regbiteusa.com</a>.
          </p>
        </div>
      </div>
    </main>
  );
}
