import Link from "next/link";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen bg-[#F8FAFB]">
      {/* Left branding panel */}
      <div className="hidden lg:flex w-[420px] shrink-0 bg-[#0D4F3C] flex-col justify-between p-12 text-white">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">RegBite US</h1>
          <p className="text-green-100/60 text-sm mt-1">
            FDA Dietary Supplement Compliance
          </p>
        </div>
        <div className="space-y-6">
          <p className="text-green-100/80 text-base leading-relaxed">
            Pre-formulation compliance intelligence for US dietary supplements.
            Check ingredients, validate labels, and stay ahead of FDA
            requirements — before you manufacture.
          </p>
          <div className="space-y-3 text-sm text-green-100/60">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
              Ingredient safety screening
            </div>
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
              Label compliance checker
            </div>
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
              NDI &amp; cGMP readiness
            </div>
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
              State-by-state regulations
            </div>
          </div>
        </div>
        <p className="text-xs text-green-100/30">© 2025 RegBite US</p>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-gray-900">Welcome</h2>
            <p className="text-gray-500 mt-1 text-sm">
              Sign in to your compliance workspace
            </p>
          </div>

          {/* Demo CTA — prominent during testing */}
          <div className="rounded-xl border border-[#0D4F3C]/20 bg-[#0D4F3C]/5 p-5 mb-6">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-8 h-8 rounded-full bg-[#0D4F3C] flex items-center justify-center shrink-0 mt-0.5">
                <svg
                  className="w-4 h-4 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                  />
                </svg>
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-900">
                  Demo Account
                </p>
                <p className="text-xs text-gray-500 mt-0.5">
                  Explore the full platform — no account needed
                </p>
              </div>
            </div>
            <Link
              href="/demo"
              className="flex items-center justify-center gap-2 w-full bg-[#0D4F3C] text-white text-sm font-medium py-2.5 px-4 rounded-lg hover:bg-[#0A3D2E] transition-colors"
            >
              Continue as Demo
              <svg
                className="w-4 h-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M13 7l5 5m0 0l-5 5m5-5H6"
                />
              </svg>
            </Link>
          </div>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-200" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-[#F8FAFB] px-3 text-gray-400">
                or sign in with your account
              </span>
            </div>
          </div>

          {/* Auth form — disabled until Clerk keys are configured */}
          <div className="space-y-4 opacity-40 pointer-events-none select-none">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Email
              </label>
              <input
                type="email"
                disabled
                placeholder="you@company.com"
                className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm bg-white text-gray-400"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Password
              </label>
              <input
                type="password"
                disabled
                placeholder="••••••••"
                className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm bg-white"
              />
            </div>
            <button
              disabled
              className="w-full bg-gray-300 text-gray-500 text-sm font-medium py-2.5 px-4 rounded-lg cursor-not-allowed"
            >
              Sign in
            </button>
          </div>

          <p className="text-xs text-gray-400 text-center mt-5">
            Full authentication coming soon
          </p>
        </div>
      </div>
    </div>
  );
}
