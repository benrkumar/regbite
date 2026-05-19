export default function DashboardPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard title="Formulations" value="0" subtitle="Total products" />
        <StatCard title="Compliance Score" value="--" subtitle="Average across all" />
        <StatCard title="Critical Issues" value="0" subtitle="Requires attention" />
        <StatCard title="Regulatory Updates" value="0" subtitle="This month" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-4">Recent Compliance Checks</h2>
          <p className="text-gray-500 text-sm">
            No compliance checks yet. Create a formulation to get started.
          </p>
        </div>
        <div className="bg-white rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-4">Regulatory Alerts</h2>
          <p className="text-gray-500 text-sm">
            No regulatory changes detected yet. Scrapers will populate this feed.
          </p>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  subtitle,
}: {
  title: string;
  value: string;
  subtitle: string;
}) {
  return (
    <div className="bg-white rounded-lg border p-4">
      <p className="text-sm text-gray-500">{title}</p>
      <p className="text-3xl font-bold mt-1">{value}</p>
      <p className="text-xs text-gray-400 mt-1">{subtitle}</p>
    </div>
  );
}
