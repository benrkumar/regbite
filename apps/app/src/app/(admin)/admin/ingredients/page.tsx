import { prisma } from '@regbite/database';

export const dynamic = 'force-dynamic';

const STATUS_COLOR: Record<string, string> = {
  PERMITTED: 'text-green-400',
  GRAS: 'text-green-400',
  RESTRICTED: 'text-yellow-400',
  ADVISORY: 'text-orange-400',
  BANNED: 'text-red-400',
  UNKNOWN: 'text-gray-500',
};

export default async function IngredientsPage() {
  const ingredients = await prisma.uSIngredient.findMany({
    orderBy: { name: 'asc' },
    take: 200,
    select: {
      id: true,
      name: true,
      casNumber: true,
      fdaStatus: true,
      grasStatus: true,
      ndiNotificationsCount: true,
      prop65Listed: true,
      dsheaGrandfathered: true,
    },
  });

  const total = await prisma.uSIngredient.count();

  const byStatus = ingredients.reduce<Record<string, number>>((acc, i) => {
    acc[i.fdaStatus] = (acc[i.fdaStatus] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="max-w-5xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">US Ingredients Database</h1>
          <p className="text-sm text-gray-500 mt-1">{total.toLocaleString()} total ingredients</p>
        </div>
      </div>

      {/* Status summary */}
      <div className="flex gap-4 mb-6 flex-wrap">
        {Object.entries(byStatus).map(([status, count]) => (
          <div key={status} className="rounded-lg bg-gray-900 border border-gray-800 px-4 py-2">
            <p className={`text-lg font-bold ${STATUS_COLOR[status] ?? 'text-gray-400'}`}>{count}</p>
            <p className="text-xs text-gray-500">{status}</p>
          </div>
        ))}
      </div>

      <div className="rounded-lg bg-gray-900 border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-left">
              <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">Name</th>
              <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">CAS</th>
              <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">FDA Status</th>
              <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">GRAS</th>
              <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">NDI Notifications</th>
              <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">Prop 65</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {ingredients.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-6 text-center text-gray-500">No ingredients in database — run seed to populate</td>
              </tr>
            )}
            {ingredients.map((ing) => (
              <tr key={ing.id} className="hover:bg-gray-800/50">
                <td className="px-5 py-3 text-gray-200 font-medium">{ing.name}</td>
                <td className="px-5 py-3 text-xs text-gray-500 font-mono">{ing.casNumber ?? '—'}</td>
                <td className={`px-5 py-3 text-xs font-semibold ${STATUS_COLOR[ing.fdaStatus] ?? 'text-gray-400'}`}>{ing.fdaStatus}</td>
                <td className="px-5 py-3 text-xs text-gray-400">{ing.grasStatus ?? '—'}</td>
                <td className="px-5 py-3 text-xs text-gray-400">{ing.ndiNotificationsCount ?? 0}</td>
                <td className="px-5 py-3 text-xs">
                  {ing.prop65Listed ? <span className="text-orange-400">Listed</span> : <span className="text-gray-600">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {total > 200 && (
          <div className="px-5 py-3 border-t border-gray-800 text-xs text-gray-500">
            Showing 200 of {total.toLocaleString()} ingredients
          </div>
        )}
      </div>
    </div>
  );
}
