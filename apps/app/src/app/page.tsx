import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="max-w-2xl text-center">
        <h1 className="text-4xl font-bold tracking-tight mb-4">
          RegBite US
        </h1>
        <p className="text-lg text-gray-600 mb-8">
          Pre-formulation FDA compliance intelligence for US dietary supplements.
          Check ingredients, validate labels, and ensure claims compliance before
          you manufacture.
        </p>
        <div className="flex gap-4 justify-center">
          <Link
            href="/dashboard"
            className="rounded-lg bg-brand-600 px-6 py-3 text-white font-medium hover:bg-brand-700 transition-colors"
          >
            Go to Dashboard
          </Link>
        </div>
      </div>
    </main>
  );
}
