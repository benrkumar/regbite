import { SeverityBadge, StatusBadge } from './severity-badge';

interface CheckResult {
  ruleId: string;
  ruleName: string;
  status: 'PASS' | 'FAIL' | 'WARNING' | 'SKIPPED';
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  message: string;
  remediation?: string;
  regulatoryCitation?: string;
}

interface CheckResultCardProps {
  check: CheckResult;
  defaultOpen?: boolean;
}

export function CheckResultCard({ check, defaultOpen = false }: CheckResultCardProps) {
  const borderColor =
    check.status === 'FAIL' && check.severity === 'CRITICAL' ? 'border-l-red-600' :
    check.status === 'FAIL' ? 'border-l-orange-500' :
    check.status === 'WARNING' ? 'border-l-yellow-500' :
    check.status === 'PASS' ? 'border-l-green-500' :
    'border-l-gray-300';

  return (
    <details className={`rounded-lg border border-l-4 bg-white ${borderColor}`} open={defaultOpen}>
      <summary className="flex cursor-pointer items-center justify-between gap-3 p-4 select-none">
        <div className="flex items-center gap-3 min-w-0">
          <StatusBadge status={check.status} />
          <span className="font-medium text-gray-900 truncate">{check.ruleName}</span>
          <span className="text-xs text-gray-400 font-mono">{check.ruleId}</span>
        </div>
        <SeverityBadge severity={check.severity} />
      </summary>
      <div className="border-t px-4 pb-4 pt-3 space-y-2">
        <p className="text-sm text-gray-700">{check.message}</p>
        {check.remediation && (
          <div className="rounded-md bg-blue-50 border border-blue-200 px-3 py-2">
            <p className="text-xs font-semibold text-blue-800 mb-0.5">Remediation</p>
            <p className="text-xs text-blue-700">{check.remediation}</p>
          </div>
        )}
        {check.regulatoryCitation && (
          <p className="text-xs text-gray-400 font-mono">
            Citation: {check.regulatoryCitation}
          </p>
        )}
      </div>
    </details>
  );
}

interface CheckResultListProps {
  checks: CheckResult[];
  showAll?: boolean;
}

export function CheckResultList({ checks, showAll = false }: CheckResultListProps) {
  const ordered = [...checks].sort((a, b) => {
    const statusOrder = { FAIL: 0, WARNING: 1, PASS: 2, SKIPPED: 3 };
    const severityOrder = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
    if (a.status !== b.status) return statusOrder[a.status] - statusOrder[b.status];
    return severityOrder[a.severity] - severityOrder[b.severity];
  });

  return (
    <div className="space-y-2">
      {ordered.map((check) => (
        <CheckResultCard
          key={check.ruleId}
          check={check}
          defaultOpen={showAll || check.status === 'FAIL'}
        />
      ))}
    </div>
  );
}
