interface ComplianceScoreBadgeProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
}

export function ComplianceScoreBadge({ score, size = 'md' }: ComplianceScoreBadgeProps) {
  const color =
    score >= 90 ? 'text-green-700 bg-green-50 border-green-200' :
    score >= 70 ? 'text-yellow-700 bg-yellow-50 border-yellow-200' :
    score >= 50 ? 'text-orange-700 bg-orange-50 border-orange-200' :
                  'text-red-700 bg-red-50 border-red-200';

  const label =
    score >= 90 ? 'Compliant' :
    score >= 70 ? 'Review Needed' :
    score >= 50 ? 'Issues Found' :
                  'Non-Compliant';

  const sizeClass =
    size === 'sm' ? 'text-xs px-2 py-0.5' :
    size === 'lg' ? 'text-lg px-4 py-2 font-bold' :
                    'text-sm px-3 py-1';

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${color} ${sizeClass}`}>
      <span className="tabular-nums">{score}</span>
      <span className="opacity-70">/100</span>
      <span className="ml-1 opacity-90">{label}</span>
    </span>
  );
}
