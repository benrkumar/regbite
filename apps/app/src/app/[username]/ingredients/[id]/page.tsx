import { notFound } from 'next/navigation';
import { prisma } from '@regbite/database';
import { checkIngredient } from '@regbite/compliance-engine';
import { ComplianceScoreBadge } from '@/components/compliance-score-badge';
import { CheckResultList } from '@/components/check-result-card';
import { StatusBadge } from '@/components/severity-badge';
import Link from 'next/link';
import { ArrowLeft, ExternalLink } from 'lucide-react';

interface PageProps {
  params: Promise<{ id: string }>;
}

const FDA_STATUS_BADGE: Record<string, string> = {
  PERMITTED: 'bg-green-100 text-green-800',
  RESTRICTED: 'bg-orange-100 text-orange-800',
  BANNED: 'bg-red-100 text-red-800',
  ADVISORY: 'bg-yellow-100 text-yellow-800',
  UNKNOWN: 'bg-gray-100 text-gray-600',
};

export default async function IngredientDetailPage({ params }: PageProps) {
  const { id } = await params;

  const ingredient = await prisma.uSIngredient.findUnique({
    where: { id },
    include: {
      ndiNotifications: { take: 5, orderBy: { submissionDate: 'desc' } },
      warningLetterLinks: {
        include: {
          warningLetter: {
            select: { letterId: true, subject: true, companyName: true, issueDate: true, letterUrl: true },
          },
        },
        take: 10,
      },
    },
  });

  if (!ingredient) notFound();

  const compliance = await checkIngredient({ name: ingredient.name, casNumber: ingredient.casNumber });
  const score = compliance.checks.filter(c => c.status === 'PASS').length /
                compliance.checks.filter(c => c.status !== 'SKIPPED').length * 100;

  const citations = Array.isArray(ingredient.regulatoryCitations)
    ? ingredient.regulatoryCitations as string[]
    : [];

  return (
    <div className="max-w-4xl">
      <Link href="/ingredients" className="mb-6 inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900">
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to search
      </Link>

      {/* Header */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{ingredient.name}</h1>
          {ingredient.casNumber && (
            <p className="mt-1 text-sm text-gray-500 font-mono">CAS: {ingredient.casNumber}</p>
          )}
          {ingredient.aliases.length > 0 && (
            <p className="mt-1 text-xs text-gray-400">Also known as: {ingredient.aliases.slice(0, 4).join(', ')}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-2">
          <span className={`rounded-md px-3 py-1 text-sm font-semibold ${FDA_STATUS_BADGE[ingredient.fdaStatus] ?? FDA_STATUS_BADGE.UNKNOWN}`}>
            {ingredient.fdaStatus}
          </span>
          <ComplianceScoreBadge score={Math.round(score)} size="sm" />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left column — info panels */}
        <div className="space-y-4 lg:col-span-1">
          {/* Regulatory summary */}
          <div className="rounded-lg border bg-white p-4">
            <h3 className="mb-3 text-sm font-semibold text-gray-700 uppercase tracking-wide">Regulatory Summary</h3>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-500">FDA Status</dt>
                <dd>
                  <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${FDA_STATUS_BADGE[ingredient.fdaStatus] ?? FDA_STATUS_BADGE.UNKNOWN}`}>
                    {ingredient.fdaStatus}
                  </span>
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">GRAS Status</dt>
                <dd className="font-medium text-gray-800">{ingredient.grasStatus.replace('_', ' ')}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Pre-DSHEA</dt>
                <dd>
                  <StatusBadge status={ingredient.dsheaGrandfathered ? 'PASS' : 'WARNING'} />
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">NDI Required</dt>
                <dd>
                  <StatusBadge status={compliance.ndiRequired ? 'FAIL' : 'PASS'} />
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Prop 65</dt>
                <dd>
                  <StatusBadge status={ingredient.prop65Listed ? 'WARNING' : 'PASS'} />
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Warning Letters</dt>
                <dd className={`font-semibold ${ingredient.warningLetterLinks.length > 0 ? 'text-orange-600' : 'text-green-600'}`}>
                  {ingredient.warningLetterLinks.length}
                </dd>
              </div>
            </dl>
          </div>

          {/* Safety levels */}
          {(ingredient.safeUsageLevel || ingredient.upperIntakeLevel) && (
            <div className="rounded-lg border bg-white p-4">
              <h3 className="mb-3 text-sm font-semibold text-gray-700 uppercase tracking-wide">Safety Levels</h3>
              <div className="space-y-2 text-sm">
                {ingredient.safeUsageLevel && (
                  <div>
                    <p className="text-xs text-gray-500">Typical safe usage</p>
                    <p className="text-gray-800">{ingredient.safeUsageLevel}</p>
                  </div>
                )}
                {ingredient.upperIntakeLevel && (
                  <div>
                    <p className="text-xs text-gray-500">NIH Upper Intake Level (UL)</p>
                    <p className="text-gray-800">{ingredient.upperIntakeLevel}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Citations */}
          {citations.length > 0 && (
            <div className="rounded-lg border bg-white p-4">
              <h3 className="mb-3 text-sm font-semibold text-gray-700 uppercase tracking-wide">Citations</h3>
              <ul className="space-y-1">
                {citations.map((c, i) => (
                  <li key={i} className="text-xs text-gray-600 font-mono">{c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Right column — compliance checks + warning letters */}
        <div className="space-y-6 lg:col-span-2">
          {/* Advisory notes */}
          {ingredient.advisoryNotes && (
            <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
              <p className="text-sm font-semibold text-yellow-800 mb-1">FDA Advisory Note</p>
              <p className="text-sm text-yellow-700">{ingredient.advisoryNotes}</p>
            </div>
          )}

          {/* Compliance checks */}
          <div>
            <h2 className="mb-3 text-base font-semibold text-gray-900">Compliance Checks</h2>
            <CheckResultList checks={compliance.checks} />
          </div>

          {/* Warning letters */}
          {ingredient.warningLetterLinks.length > 0 && (
            <div>
              <h2 className="mb-3 text-base font-semibold text-gray-900">
                FDA Warning Letters ({ingredient.warningLetterLinks.length})
              </h2>
              <div className="space-y-2">
                {ingredient.warningLetterLinks.map(({ warningLetter: wl }) => (
                  <div key={wl.letterId} className="rounded-lg border bg-white p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-medium text-sm text-gray-900">{wl.companyName}</p>
                        <p className="text-xs text-gray-500 mt-0.5">{wl.subject}</p>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className="text-xs text-gray-400">
                          {wl.issueDate ? new Date(wl.issueDate).toLocaleDateString() : ''}
                        </span>
                        <a href={wl.letterUrl} target="_blank" rel="noopener noreferrer"
                           className="text-gray-400 hover:text-brand-600">
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* NDI Notifications */}
          {ingredient.ndiNotifications.length > 0 && (
            <div>
              <h2 className="mb-3 text-base font-semibold text-gray-900">
                NDI Notifications ({ingredient.ndiNotificationsCount})
              </h2>
              <div className="space-y-2">
                {ingredient.ndiNotifications.map((ndi) => (
                  <div key={ndi.fdaNotificationNumber} className="rounded-lg border bg-white p-4 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs text-gray-600">{ndi.fdaNotificationNumber}</span>
                      <span className="text-xs text-gray-400">
                        {ndi.submissionDate ? new Date(ndi.submissionDate).toLocaleDateString() : ''}
                      </span>
                    </div>
                    {ndi.fdaResponse && (
                      <p className="mt-1 text-gray-700">{ndi.fdaResponse}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
