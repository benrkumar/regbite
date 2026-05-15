import Link from "next/link";
import {
  FlaskConical,
  FileCheck,
  MessageSquareWarning,
  ClipboardCheck,
  FileText,
  ShieldAlert,
  Plane,
  Search,
  ArrowRight,
  CheckCircle,
} from "lucide-react";

const FEATURES = [
  {
    icon: Search,
    title: "Ingredient Intelligence",
    description: "Instantly check FDA status, GRAS standing, NDI requirement, and Prop 65 status for any supplement ingredient.",
  },
  {
    icon: FlaskConical,
    title: "Formulation Compliance",
    description: "Upload your complete formula and get a scored compliance report with per-ingredient findings and NIH dosage comparison.",
  },
  {
    icon: FileCheck,
    title: "Label Validator",
    description: "Validate Supplement Facts panels against all 21 CFR 101.36 requirements: DV%, serving sizes, allergens, and more.",
  },
  {
    icon: MessageSquareWarning,
    title: "Claims Checker",
    description: "Classify structure/function vs. disease claims, verify the FDA disclaimer is present, and get FTC substantiation guidance.",
  },
  {
    icon: FileText,
    title: "NDI Navigator",
    description: "Determine NDI notification eligibility, check existing notifications, and generate your 15-step submission checklist.",
  },
  {
    icon: ClipboardCheck,
    title: "cGMP Readiness",
    description: "Walk through all 7 sections of 21 CFR Part 111 with a scored audit checklist. Export a gap analysis report.",
  },
  {
    icon: ShieldAlert,
    title: "State Compliance",
    description: "Screen ingredients against California Prop 65, check NY and Florida state-level registration requirements.",
  },
  {
    icon: Plane,
    title: "Import Intelligence",
    description: "Assess FDA Import Alert risk by supplier country and generate your FSMA FSVP checklist for foreign ingredients.",
  },
];

const TRUST_ITEMS = [
  "21 CFR Part 111 (cGMP) requirements",
  "DSHEA ingredient status + NDI eligibility",
  "21 CFR 101.36 Supplement Facts requirements",
  "FDA structure/function claim vs. disease claim rules",
  "FTC substantiation standards for health claims",
  "FSMA Foreign Supplier Verification Program (FSVP)",
  "California Proposition 65 chemical screening",
  "FDA Import Alert risk by country of origin",
];

export default function HomePage() {
  return (
    <main>
      {/* Hero */}
      <section className="bg-gray-950 text-white py-24 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-block rounded-full bg-gray-800 px-4 py-1.5 text-xs font-medium text-gray-300 mb-6">
            Built for US dietary supplement brands
          </div>
          <h1 className="text-5xl md:text-6xl font-bold tracking-tight mb-6 leading-tight">
            FDA Compliance Intelligence<br />
            <span className="text-gray-400">Before You Manufacture</span>
          </h1>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto mb-10">
            Check ingredient status, validate Supplement Facts panels, screen claims, and assess NDI eligibility —
            all in one platform built for US regulatory requirements.
          </p>
          <div className="flex items-center justify-center gap-4 flex-wrap">
            <a
              href="https://app.regbiteusa.com/sign-up"
              className="rounded-lg bg-white text-gray-900 px-8 py-3.5 font-semibold text-base hover:bg-gray-100 transition-colors"
            >
              Start free trial
            </a>
            <Link
              href="/features"
              className="inline-flex items-center gap-1.5 text-gray-400 hover:text-white text-base font-medium transition-colors"
            >
              See all features <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* Social proof strip */}
      <section className="border-b border-gray-200 bg-gray-50 py-6 px-6">
        <div className="max-w-6xl mx-auto flex items-center justify-center gap-8 flex-wrap text-sm text-gray-500">
          <span>FDA/DSHEA compliance</span>
          <span className="text-gray-300">·</span>
          <span>21 CFR Part 111 cGMP</span>
          <span className="text-gray-300">·</span>
          <span>FTC substantiation</span>
          <span className="text-gray-300">·</span>
          <span>FSMA FSVP</span>
          <span className="text-gray-300">·</span>
          <span>California Prop 65</span>
          <span className="text-gray-300">·</span>
          <span>NDI Navigator</span>
        </div>
      </section>

      {/* Features grid */}
      <section className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-bold text-gray-900 mb-3">Everything you need to launch compliant supplements</h2>
            <p className="text-gray-500 max-w-xl mx-auto">
              Eight compliance modules covering the full pre-formulation workflow — from ingredient sourcing to label approval.
            </p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <div key={f.title} className="rounded-xl border border-gray-200 bg-white p-6 hover:shadow-sm transition-shadow">
                  <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100">
                    <Icon className="h-5 w-5 text-gray-700" />
                  </div>
                  <h3 className="text-sm font-semibold text-gray-900 mb-1.5">{f.title}</h3>
                  <p className="text-sm text-gray-500 leading-relaxed">{f.description}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Regulatory coverage */}
      <section className="bg-gray-50 py-20 px-6 border-t border-gray-200">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-10">
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Comprehensive regulatory coverage</h2>
            <p className="text-gray-500">Code-first rules engine built from primary FDA sources.</p>
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            {TRUST_ITEMS.map((item) => (
              <div key={item} className="flex items-center gap-2.5">
                <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0" />
                <span className="text-sm text-gray-700">{item}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing CTA */}
      <section className="py-20 px-6 border-t border-gray-200">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-2xl font-bold text-gray-900 mb-3">Simple, transparent pricing</h2>
          <p className="text-gray-500 mb-8">
            Plans for solo formulators to large supplement brands. All plans include full access to the compliance engine.
          </p>
          <div className="flex items-center justify-center gap-4">
            <Link
              href="/pricing"
              className="rounded-lg bg-gray-900 px-6 py-3 text-sm font-medium text-white hover:bg-gray-700 transition-colors"
            >
              View pricing
            </Link>
            <a
              href="https://app.regbiteusa.com/sign-up"
              className="rounded-lg border border-gray-300 px-6 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Start free trial
            </a>
          </div>
        </div>
      </section>

      {/* Disclaimer */}
      <section className="bg-gray-50 border-t border-gray-200 py-6 px-6">
        <p className="text-xs text-gray-400 text-center max-w-3xl mx-auto">
          RegBite US is a compliance intelligence tool, not a legal service. Compliance checks reflect our interpretation of applicable regulations and should be verified by a qualified regulatory attorney before product launch.
        </p>
      </section>
    </main>
  );
}
