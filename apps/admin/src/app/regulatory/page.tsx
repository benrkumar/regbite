import { prisma } from '@regbite/database';

export const dynamic = 'force-dynamic';

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: 'text-red-400 bg-red-900/20 border-red-800',
  HIGH: 'text-orange-400 bg-orange-900/20 border-orange-800',
  MEDIUM: 'text-yellow-400 bg-yellow-900/20 border-yellow-800',
  LOW: 'text-gray-400 bg-gray-800 border-gray-700',
};

export default async function RegulatoryPage() {
  const changes = await prisma.regulatoryChange.findMany({
    orderBy: [{ severity: 'asc' }, { detectedAt: 'desc' }],
    take: 100,
    select: {
      id: true,
      source: true,
      documentTitle: true,
      summary: true,
      changeType: true,
      severity: true,
      detectedAt: true,
      documentHash: true,
    },
  });

  const total = await prisma.regulatoryChange.count();

  return (
    <div className="max-w-5xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Regulatory Changes</h1>
        <p className="text-sm text-gray-500 mt-1">{total.toLocaleString()} documents indexed</p>
      </div>

      <div className="space-y-2">
        {changes.length === 0 && (
          <div className="rounded-lg bg-gray-900 border border-gray-800 px-5 py-8 text-center text-gray-500">
            No regulatory changes indexed yet. Run the scrapers to populate this feed.
          </div>
        )}
        {changes.map((change) => (
          <div key={change.id} className={`rounded-lg border px-5 py-4 ${SEVERITY_COLOR[change.severity] ?? 'bg-gray-900 border-gray-800 text-gray-400'}`}>
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold uppercase tracking-wide">{change.severity}</span>
                  <span className="text-xs text-gray-500">{change.source}</span>
                  <span className="text-xs text-gray-600">{change.changeType}</span>
                </div>
                <p className="text-sm font-medium text-white">{change.documentTitle}</p>
                {change.summary && (
                  <p className="text-xs text-gray-400 mt-1 line-clamp-2">{change.summary}</p>
                )}
              </div>
              <p className="text-xs text-gray-500 flex-shrink-0">
                {new Date(change.detectedAt).toLocaleDateString()}
              </p>
            </div>
          </div>
        ))}
      </div>

      {total > 100 && (
        <p className="mt-4 text-xs text-gray-500 text-center">Showing 100 of {total.toLocaleString()} changes</p>
      )}
    </div>
  );
}
