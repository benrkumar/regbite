import { CheckCircle } from "lucide-react";
import { APP_URL } from "@/lib/config";

const PLANS = [
  {
    name: "Starter",
    price: 199,
    description: "For early-stage brands validating their first formula.",
    features: [
      "50 compliance checks/month",
      "Ingredient lookups",
      "Label Validator",
      "Claims Checker",
      "1 user",
      "Email support",
    ],
    highlight: false,
    cta: "Start free trial",
  },
  {
    name: "Growth",
    price: 399,
    description: "For growing brands with multiple formulas in development.",
    features: [
      "200 compliance checks/month",
      "All Starter features",
      "NDI Navigator",
      "cGMP Readiness",
      "State Compliance (Prop 65)",
      "Up to 3 users",
      "Priority email support",
    ],
    highlight: true,
    cta: "Start free trial",
  },
  {
    name: "Professional",
    price: 699,
    description: "For established brands with a full compliance workflow.",
    features: [
      "Unlimited compliance checks",
      "All Growth features",
      "Import Intelligence (FSVP)",
      "Regulatory Feed",
      "PDF report exports",
      "Up to 10 users",
      "Phone + email support",
    ],
    highlight: false,
    cta: "Start free trial",
  },
  {
    name: "Enterprise",
    price: 999,
    description: "For large brands and contract manufacturers.",
    features: [
      "Unlimited everything",
      "All Professional features",
      "Custom compliance rules",
      "API access",
      "Dedicated account manager",
      "Unlimited users",
      "SLA + priority support",
    ],
    highlight: false,
    cta: "Contact us",
  },
  {
    name: "Consultant",
    price: 499,
    description: "For regulatory consultants managing multiple client brands.",
    features: [
      "Unlimited client organizations",
      "All Professional features",
      "White-label report exports",
      "Client management dashboard",
      "Up to 5 consultant users",
      "Priority support",
    ],
    highlight: false,
    cta: "Start free trial",
  },
];

export default function PricingPage() {
  return (
    <main className="max-w-6xl mx-auto px-6 py-16">
      <div className="text-center mb-14">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">Pricing</h1>
        <p className="text-lg text-gray-500">
          All plans include a 14-day free trial. No credit card required to start.
        </p>
      </div>

      <div className="grid md:grid-cols-3 lg:grid-cols-5 gap-4">
        {PLANS.map((plan) => (
          <div
            key={plan.name}
            className={`rounded-xl border p-6 flex flex-col ${
              plan.highlight
                ? "border-gray-900 bg-gray-950 text-white shadow-xl scale-105'}"
                : "border-gray-200 bg-white"
            }`}
          >
            <div className="mb-4">
              <p className={`text-sm font-semibold mb-1 ${plan.highlight ? "text-gray-300" : "text-gray-500"}`}>
                {plan.name}
              </p>
              <p className={`text-3xl font-bold ${plan.highlight ? "text-white" : "text-gray-900"}`}>
                ${plan.price}
                <span className={`text-sm font-normal ml-1 ${plan.highlight ? "text-gray-400" : "text-gray-500"}`}>/mo</span>
              </p>
              <p className={`text-xs mt-2 leading-relaxed ${plan.highlight ? "text-gray-400" : "text-gray-500"}`}>
                {plan.description}
              </p>
            </div>

            <ul className="space-y-2 flex-1 mb-6">
              {plan.features.map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <CheckCircle className={`h-3.5 w-3.5 flex-shrink-0 mt-0.5 ${plan.highlight ? "text-green-400" : "text-green-600"}`} />
                  <span className={`text-xs ${plan.highlight ? "text-gray-300" : "text-gray-600"}`}>{f}</span>
                </li>
              ))}
            </ul>

            <a
              href={plan.cta === "Contact us" ? "/contact" : `${APP_URL}/sign-up`}
              className={`block text-center rounded-lg px-4 py-2.5 text-sm font-medium transition-colors ${
                plan.highlight
                  ? "bg-white text-gray-900 hover:bg-gray-100"
                  : "bg-gray-900 text-white hover:bg-gray-700"
              }`}
            >
              {plan.cta}
            </a>
          </div>
        ))}
      </div>

      <div className="mt-12 rounded-xl bg-gray-50 border border-gray-200 p-8 text-center">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">Need a custom plan?</h2>
        <p className="text-gray-500 text-sm mb-4">
          Large brands, contract manufacturers, and multi-brand portfolios — contact us for custom pricing.
        </p>
        <a
          href="/contact"
          className="inline-block rounded-lg border border-gray-300 px-6 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-100 transition-colors"
        >
          Get in touch
        </a>
      </div>

      <div className="mt-10 text-center">
        <p className="text-xs text-gray-400">
          Prices in USD. Billed monthly or annually (20% discount). All plans include 14-day free trial.
          RegBite US is a compliance intelligence tool — not a substitute for qualified legal or regulatory advice.
        </p>
      </div>
    </main>
  );
}
