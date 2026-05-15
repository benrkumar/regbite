import { prisma } from '@regbite/database';

export const dynamic = 'force-dynamic';

export default async function UsersPage() {
  const members = await prisma.member.findMany({
    where: { deletedAt: null },
    orderBy: { createdAt: 'desc' },
    take: 100,
    include: { organization: { select: { name: true, plan: true } } },
  });

  return (
    <div className="max-w-5xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Users</h1>
          <p className="text-sm text-gray-500 mt-1">{members.length} active members</p>
        </div>
      </div>

      <div className="rounded-lg bg-gray-900 border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-left">
              <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">Email</th>
              <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">Organization</th>
              <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">Plan</th>
              <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">Role</th>
              <th className="px-5 py-3 text-xs font-medium text-gray-400 uppercase tracking-wide">Joined</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {members.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-6 text-center text-gray-500">No users yet</td>
              </tr>
            )}
            {members.map((member) => (
              <tr key={member.id} className="hover:bg-gray-800/50">
                <td className="px-5 py-3 text-gray-200">{member.email}</td>
                <td className="px-5 py-3 text-gray-400">{member.organization.name}</td>
                <td className="px-5 py-3">
                  <span className="text-xs rounded-full bg-gray-800 px-2.5 py-0.5 text-gray-400">
                    {member.organization.plan}
                  </span>
                </td>
                <td className="px-5 py-3 text-xs text-gray-400">{member.role}</td>
                <td className="px-5 py-3 text-xs text-gray-500">{new Date(member.createdAt).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
