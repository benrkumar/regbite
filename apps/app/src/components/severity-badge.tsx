type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
type Status = 'PASS' | 'FAIL' | 'WARNING' | 'SKIPPED';

export function SeverityBadge({ severity }: { severity: Severity }) {
  const styles: Record<Severity, string> = {
    CRITICAL: 'bg-red-100 text-red-800 border-red-200',
    HIGH: 'bg-orange-100 text-orange-800 border-orange-200',
    MEDIUM: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    LOW: 'bg-gray-100 text-gray-700 border-gray-200',
  };
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium ${styles[severity]}`}>
      {severity}
    </span>
  );
}

export function StatusBadge({ status }: { status: Status }) {
  const styles: Record<Status, string> = {
    PASS: 'bg-green-100 text-green-800',
    FAIL: 'bg-red-100 text-red-800',
    WARNING: 'bg-yellow-100 text-yellow-800',
    SKIPPED: 'bg-gray-100 text-gray-500',
  };
  const icons: Record<Status, string> = {
    PASS: '✓',
    FAIL: '✗',
    WARNING: '⚠',
    SKIPPED: '—',
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold ${styles[status]}`}>
      {icons[status]} {status}
    </span>
  );
}
