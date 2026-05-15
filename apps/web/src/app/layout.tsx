import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "RegBite US — FDA Supplement Compliance",
  description:
    "Pre-formulation compliance intelligence for US dietary supplement brands. Check ingredient status, validate labels, screen claims — before you manufacture.",
};

function Header() {
  return (
    <header className="sticky top-0 z-50 bg-white border-b border-gray-200">
      <div className="max-w-6xl mx-auto px-6 flex items-center justify-between h-16">
        <Link href="/" className="flex items-center gap-2">
          <span className="text-lg font-bold text-gray-900">RegBite US</span>
          <span className="text-xs text-gray-400 font-medium">FDA Compliance</span>
        </Link>
        <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-gray-600">
          <Link href="/features" className="hover:text-gray-900 transition-colors">Features</Link>
          <Link href="/pricing" className="hover:text-gray-900 transition-colors">Pricing</Link>
          <Link href="/about" className="hover:text-gray-900 transition-colors">About</Link>
        </nav>
        <div className="flex items-center gap-3">
          <a href="https://app.regbiteusa.com/sign-in" className="text-sm font-medium text-gray-600 hover:text-gray-900">Sign in</a>
          <a
            href="https://app.regbiteusa.com/sign-up"
            className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 transition-colors"
          >
            Start free trial
          </a>
        </div>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="border-t border-gray-200 bg-gray-50">
      <div className="max-w-6xl mx-auto px-6 py-12">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-10">
          <div>
            <p className="text-sm font-semibold text-gray-900 mb-3">Product</p>
            <ul className="space-y-2">
              <li><Link href="/features" className="text-sm text-gray-500 hover:text-gray-900">Features</Link></li>
              <li><Link href="/pricing" className="text-sm text-gray-500 hover:text-gray-900">Pricing</Link></li>
              <li><a href="https://app.regbiteusa.com" className="text-sm text-gray-500 hover:text-gray-900">Dashboard</a></li>
            </ul>
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900 mb-3">Compliance</p>
            <ul className="space-y-2">
              <li><Link href="/features#ingredients" className="text-sm text-gray-500 hover:text-gray-900">Ingredient Checker</Link></li>
              <li><Link href="/features#labels" className="text-sm text-gray-500 hover:text-gray-900">Label Validator</Link></li>
              <li><Link href="/features#claims" className="text-sm text-gray-500 hover:text-gray-900">Claims Checker</Link></li>
              <li><Link href="/features#cgmp" className="text-sm text-gray-500 hover:text-gray-900">cGMP Readiness</Link></li>
            </ul>
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900 mb-3">Company</p>
            <ul className="space-y-2">
              <li><Link href="/about" className="text-sm text-gray-500 hover:text-gray-900">About</Link></li>
              <li><Link href="/contact" className="text-sm text-gray-500 hover:text-gray-900">Contact</Link></li>
            </ul>
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900 mb-3">Legal</p>
            <ul className="space-y-2">
              <li><Link href="/terms" className="text-sm text-gray-500 hover:text-gray-900">Terms of Service</Link></li>
              <li><Link href="/privacy" className="text-sm text-gray-500 hover:text-gray-900">Privacy Policy</Link></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-gray-200 pt-6 flex items-center justify-between">
          <p className="text-sm text-gray-400">© {new Date().getFullYear()} RegBite US. All rights reserved.</p>
          <p className="text-xs text-gray-400">Not a substitute for legal advice. Always consult a qualified regulatory attorney.</p>
        </div>
      </div>
    </footer>
  );
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-white text-gray-900 antialiased">
        <Header />
        {children}
        <Footer />
      </body>
    </html>
  );
}
