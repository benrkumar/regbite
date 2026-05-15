import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "RegBite US — Admin",
  description: "Internal admin panel for RegBite US",
};

const NAV = [
  { name: "Overview", href: "/" },
  { name: "Users", href: "/users" },
  { name: "Ingredients", href: "/ingredients" },
  { name: "Scraper", href: "/scraper" },
  { name: "Regulatory", href: "/regulatory" },
  { name: "Compliance Rules", href: "/compliance-rules" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-white antialiased min-h-screen">
        <div className="flex h-screen">
          <aside className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col">
            <div className="p-5 border-b border-gray-800">
              <p className="text-sm font-bold text-white">RegBite US</p>
              <p className="text-xs text-gray-500 mt-0.5">Admin Panel</p>
            </div>
            <nav className="flex-1 p-3 space-y-0.5">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="flex items-center px-3 py-2 rounded-md text-sm text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
                >
                  {item.name}
                </Link>
              ))}
            </nav>
            <div className="p-4 border-t border-gray-800">
              <p className="text-xs text-gray-600">Internal use only</p>
            </div>
          </aside>
          <main className="flex-1 overflow-y-auto bg-gray-950">
            <div className="p-8">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
