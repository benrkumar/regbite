import { APP_URL } from "@/lib/config";

export default function ContactPage() {
  return (
    <main className="max-w-xl mx-auto px-6 py-16">
      <h1 className="text-4xl font-bold text-gray-900 mb-4">Contact</h1>
      <p className="text-gray-500 mb-10">
        Questions about RegBite US, pricing, enterprise plans, or regulatory coverage? Get in touch.
      </p>

      <div className="space-y-6">
        <div className="rounded-xl border border-gray-200 bg-gray-50 p-6">
          <p className="text-sm font-semibold text-gray-900 mb-1">General inquiries</p>
          <a href="mailto:hello@regbiteusa.com" className="text-sm text-brand-700 underline">
            hello@regbiteusa.com
          </a>
        </div>

        <div className="rounded-xl border border-gray-200 bg-gray-50 p-6">
          <p className="text-sm font-semibold text-gray-900 mb-1">Enterprise &amp; custom plans</p>
          <p className="text-sm text-gray-500 mb-2">
            Large brands, contract manufacturers, multi-brand portfolios, and regulatory consulting firms.
          </p>
          <a href="mailto:enterprise@regbiteusa.com" className="text-sm text-brand-700 underline">
            enterprise@regbiteusa.com
          </a>
        </div>

        <div className="rounded-xl border border-gray-200 bg-gray-50 p-6">
          <p className="text-sm font-semibold text-gray-900 mb-1">Regulatory data corrections</p>
          <p className="text-sm text-gray-500 mb-2">
            Found an error in our ingredient database or compliance rules? We take data accuracy seriously.
          </p>
          <a href="mailto:data@regbiteusa.com" className="text-sm text-brand-700 underline">
            data@regbiteusa.com
          </a>
        </div>
      </div>

      <div className="mt-10 rounded-xl bg-gray-950 text-white p-6">
        <p className="text-sm font-semibold mb-1">Start your free trial</p>
        <p className="text-xs text-gray-400 mb-4">No credit card required. 14-day trial on all plans.</p>
        <a
          href={`${APP_URL}/sign-up`}
          className="inline-block rounded-lg bg-white text-gray-900 px-5 py-2.5 text-sm font-medium hover:bg-gray-100 transition-colors"
        >
          Create free account
        </a>
      </div>
    </main>
  );
}
