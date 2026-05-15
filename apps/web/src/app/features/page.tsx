import { CheckCircle } from "lucide-react";

const MODULES = [
  {
    id: "ingredients",
    title: "Ingredient Intelligence",
    subtitle: "Know before you formulate",
    description:
      "Search any supplement ingredient by name or CAS number. Get instant FDA status, GRAS standing, NDI notification history, NIH upper intake levels, and Prop 65 listing — all from a single lookup.",
    features: [
      "FDA status: PERMITTED, GRAS, ADVISORY, RESTRICTED, BANNED",
      "GRAS status with SCOGS/GRN citation",
      "NDI notification requirement determination",
      "NIH Dietary Reference Intakes (UL comparison)",
      "Prop 65 carcinogen / reproductive toxicant screening",
      "FDA warning letter history for the ingredient",
      "Fuzzy name search + CAS number lookup",
    ],
    citation: "21 CFR Parts 101, 170–189; DSHEA § 8; GRAS 21 CFR § 182–186",
  },
  {
    id: "formulations",
    title: "Formulation Compliance",
    subtitle: "Score your full formula",
    description:
      "Enter your complete formula with ingredient names, amounts, and units. Run a full compliance check across all ingredients simultaneously, with dosage validation against NIH upper intake levels and interaction screening.",
    features: [
      "Per-ingredient compliance with pass/fail status",
      "NIH UL dosage comparison for vitamins and minerals",
      "Known ingredient interaction flags",
      "Aggregate compliance score (0–100)",
      "CRITICAL/HIGH/MEDIUM/LOW severity breakdown",
      "Exportable compliance report",
    ],
    citation: "21 CFR Part 111; DSHEA; NIH Dietary Reference Intakes",
  },
  {
    id: "labels",
    title: "Label Validator",
    subtitle: "21 CFR 101.36 compliance",
    description:
      "Validate your Supplement Facts panel against all FDA labeling requirements. Check serving size formatting, %Daily Value accuracy, required nutrients, allergen declarations, proprietary blend disclosure, and more.",
    features: [
      "Serving size format and declaration (21 CFR § 101.9)",
      "%Daily Value accuracy for 13 mandatory nutrients",
      "Proprietary blend total and individual listing",
      "Big 9 allergen declaration (FALCPA + FASTER Act)",
      "Other ingredients list — order and format",
      'Identity statement and "dietary supplement" declaration',
      "Manufacturer/distributor name and address",
      "Lot code and expiration date requirements",
    ],
    citation: "21 CFR § 101.36; 21 CFR § 101.4; FALCPA (FASTER Act)",
  },
  {
    id: "claims",
    title: "Claims Checker",
    subtitle: "Structure/function vs. disease",
    description:
      'Classify any marketing claim as structure/function, disease claim, or nutrient content claim. Verify the required FDA disclaimer is present and get FTC substantiation guidance. Get a compliant rewrite suggestion powered by Claude.',
    features: [
      "Disease claim pattern detection (50+ patterns)",
      "Structure/function claim classification",
      'Required FDA disclaimer: "This statement has not been evaluated..."',
      "FTC competent evidence standard flagging",
      "Safe rewrite generation with compliant language",
      "FDA warning letter precedent lookup",
      "FDA 75-day notification requirement reminder",
    ],
    citation: "21 CFR § 101.93; FTC Policy Statement on Health Claims; DSHEA § 6",
  },
  {
    id: "ndi",
    title: "NDI Navigator",
    subtitle: "New Dietary Ingredient eligibility",
    description:
      "Determine if your ingredient requires an NDI notification before marketing. Check against the pre-DSHEA grandfather date, existing FDA notifications, and GRAS status — with a complete 15-step submission checklist.",
    features: [
      "Pre-DSHEA (October 1994) grandfather status check",
      "GRAS exemption determination",
      "Existing NDI notification database search",
      "NDI requirement with regulatory basis",
      "15-step DSHEA § 8 submission checklist",
      "75-day FDA review period guidance",
      "Safety evidence requirements (21 CFR § 190.6)",
    ],
    citation: "DSHEA § 8; 21 CFR § 190.6; FDA NDI Guidance (2016, revised 2022)",
  },
  {
    id: "cgmp",
    title: "cGMP Readiness",
    subtitle: "21 CFR Part 111 audit",
    description:
      "Walk through a scored readiness assessment covering all 7 sections of 21 CFR Part 111 cGMP for dietary supplements. Identify gaps, track remediation, and export a summary report.",
    features: [
      "Personnel — training, qualifications (§ 111.8–111.16)",
      "Physical plant and grounds (§ 111.15–111.27)",
      "Equipment and utensils (§ 111.27–111.35)",
      "Production and process controls (§ 111.65–111.95)",
      "Quality control operations (§ 111.105–111.140)",
      "Laboratory operations (§ 111.315–111.370)",
      "Complaint handling and records (§ 111.560–111.605)",
      "Section scores + overall compliance score",
    ],
    citation: "21 CFR Part 111 (Dietary Supplement cGMP Final Rule 2007)",
  },
  {
    id: "state",
    title: "State Compliance",
    subtitle: "California, New York, Florida",
    description:
      "Screen ingredients against the California Proposition 65 chemical list (900+ chemicals). Check New York and Florida state-level registration and labeling requirements beyond FDA standards.",
    features: [
      "Prop 65 chemical screening by name or CAS number",
      "Carcinogen vs. reproductive toxicant classification",
      "California short-form warning language generation",
      "NY Department of Ag & Markets requirements",
      "FL FDACS dietary supplement registration checklist",
      "FL Deceptive Trade Practices Act guidance",
      "OEHHA list updated twice per year",
    ],
    citation: "Cal. Health & Safety Code § 25249.5; OEHHA Title 27, CCR § 25600; FL Stat. § 500.10",
  },
  {
    id: "import",
    title: "Import Intelligence",
    subtitle: "FSMA FSVP + FDA Import Alerts",
    description:
      "Assess FDA Import Alert risk by supplier country. Generate a complete Foreign Supplier Verification Program (FSVP) checklist for FSMA compliance, with enhanced guidance for high-risk countries.",
    features: [
      "High-risk country detection (FDA Import Alert history)",
      "11-item FSVP checklist (21 CFR Part 1 Subpart L)",
      "FSVP plan requirement determination",
      "Hazard analysis documentation checklist",
      "Certificate of Analysis (CoA) requirements",
      "Onsite audit guidance for high-risk suppliers",
      "Third-party certification credit (ISO 22000, NSF)",
    ],
    citation: "21 CFR Part 1 Subpart L (§ 1.500–1.514); FDA Import Alert IA 54-06",
  },
];

export default function FeaturesPage() {
  return (
    <main className="max-w-5xl mx-auto px-6 py-16">
      <div className="text-center mb-16">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">Every compliance module you need</h1>
        <p className="text-lg text-gray-500 max-w-2xl mx-auto">
          Eight interconnected compliance tools covering the full pre-formulation workflow for US dietary supplements.
        </p>
      </div>

      <div className="space-y-16">
        {MODULES.map((mod) => (
          <div key={mod.id} id={mod.id} className="grid md:grid-cols-2 gap-10 items-start">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-brand-600 mb-1">{mod.subtitle}</p>
              <h2 className="text-2xl font-bold text-gray-900 mb-3">{mod.title}</h2>
              <p className="text-gray-600 mb-4 leading-relaxed">{mod.description}</p>
              <p className="text-xs font-mono text-gray-400">{mod.citation}</p>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-6">
              <ul className="space-y-2.5">
                {mod.features.map((f) => (
                  <li key={f} className="flex items-start gap-2.5">
                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-gray-700">{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-20 text-center rounded-xl bg-gray-950 text-white p-12">
        <h2 className="text-2xl font-bold mb-3">Ready to start?</h2>
        <p className="text-gray-400 mb-8">Free trial — no credit card required.</p>
        <a
          href="https://app.regbiteusa.com/sign-up"
          className="inline-block rounded-lg bg-white text-gray-900 px-8 py-3.5 font-semibold hover:bg-gray-100 transition-colors"
        >
          Start free trial
        </a>
      </div>
    </main>
  );
}
