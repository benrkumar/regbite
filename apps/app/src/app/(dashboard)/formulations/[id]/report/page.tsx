import { notFound } from "next/navigation";
import { prisma } from "@regbite/database";
import { requireOrganizationId } from "@/lib/auth";
import { PrintButton } from "./print-button";

export const dynamic = "force-dynamic";

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "text-red-700 bg-red-50 border-red-200",
  HIGH: "text-orange-700 bg-orange-50 border-orange-200",
  MEDIUM: "text-yellow-700 bg-yellow-50 border-yellow-200",
  LOW: "text-blue-700 bg-blue-50 border-blue-200",
};

export default async function ReportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const orgId = await requireOrganizationId();

  const check = await prisma.complianceCheck.findFirst({
    where: { id, organizationId: orgId },
    include: {
      formulation: {
        select: {
          productName: true,
          productType: true,
          servingSize: true,
          ingredients: true,
          claims: true,
        },
      },
      organization: { select: { name: true } },
    },
  });

  if (!check) notFound();

  const formulation = check.formulation!;
  const results = (check.results as { items?: Array<{ field: string; status: string; severity?: string; message: string; citation?: string }> }) ?? {};
  const items = results.items ?? [];
  const score = check.overallScore ?? 0;

  const scoreColor =
    score >= 80 ? "text-green-700" : score >= 60 ? "text-yellow-700" : "text-red-700";

  const generatedAt = new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <>
      <style>{`
        @media print {
          .no-print { display: none !important; }
          body { background: white; }
          .print-page { box-shadow: none; border: none; }
        }
      `}</style>

      <div className="max-w-3xl mx-auto py-8 px-6">
        {/* Actions — hidden when printing */}
        <div className="no-print flex items-center justify-between mb-6">
          <a href={`/formulations/${check.formulationId}`} className="text-sm text-brand-600 hover:underline">
            ← Back to Formulation
          </a>
          <div className="flex gap-3">
            <PrintButton checkId={check.id} />
          </div>
        </div>

        {/* Report */}
        <div className="print-page bg-white border border-gray-200 rounded-xl shadow-sm p-10 space-y-8">
          {/* Cover */}
          <div className="border-b border-gray-100 pb-8">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-brand-600 mb-1">
                  RegBite US — Compliance Report
                </p>
                <h1 className="text-2xl font-bold text-gray-900">{formulation.productName}</h1>
                <p className="text-sm text-gray-500 mt-1">
                  {formulation.productType.replace(/_/g, " ")}
                  {formulation.servingSize ? ` · ${formulation.servingSize}` : ""}
                </p>
              </div>
              <div className="text-right">
                <p className={`text-5xl font-black ${scoreColor}`}>{score}</p>
                <p className="text-xs text-gray-400 mt-0.5">Compliance Score</p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4 mt-6 text-xs text-gray-500">
              <div>
                <span className="font-medium text-gray-700">Organization</span>
                <br />{check.organization.name}
              </div>
              <div>
                <span className="font-medium text-gray-700">Check Type</span>
                <br />{check.checkType}
              </div>
              <div>
                <span className="font-medium text-gray-700">Generated</span>
                <br />{generatedAt}
              </div>
            </div>
          </div>

          {/* Ingredients */}
          {Array.isArray(formulation.ingredients) && (formulation.ingredients as unknown[]).length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-gray-900 mb-3">Ingredients</h2>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    <th className="text-left px-3 py-2 font-medium text-gray-500">Ingredient</th>
                    <th className="text-left px-3 py-2 font-medium text-gray-500">Amount</th>
                    <th className="text-left px-3 py-2 font-medium text-gray-500">Unit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {(formulation.ingredients as Array<{ name: string; amount: number; unit: string }>).map((ing, i) => (
                    <tr key={i}>
                      <td className="px-3 py-1.5 text-gray-700">{ing.name}</td>
                      <td className="px-3 py-1.5 text-gray-600">{ing.amount}</td>
                      <td className="px-3 py-1.5 text-gray-600">{ing.unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Claims */}
          {formulation.claims.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-gray-900 mb-3">Claims</h2>
              <ul className="space-y-1">
                {formulation.claims.map((c, i) => (
                  <li key={i} className="text-xs text-gray-600 flex items-start gap-2">
                    <span className="text-gray-300 mt-0.5">•</span>{c}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Check results */}
          {items.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-gray-900 mb-3">
                Compliance Findings ({items.length})
              </h2>
              <div className="space-y-2">
                {items.map((item, i) => (
                  <div
                    key={i}
                    className={`border rounded-lg p-3 text-xs ${SEVERITY_COLORS[item.severity ?? ""] ?? "border-gray-200 bg-gray-50"}`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <span className="font-semibold">{item.field}</span>
                        {item.severity && (
                          <span className="ml-2 uppercase text-xs opacity-70">[{item.severity}]</span>
                        )}
                        <p className="mt-0.5 text-gray-700">{item.message}</p>
                        {item.citation && (
                          <p className="mt-1 font-mono opacity-60">{item.citation}</p>
                        )}
                      </div>
                      <span className={`shrink-0 font-semibold uppercase ${item.status === "PASS" ? "text-green-600" : item.status === "WARN" ? "text-yellow-600" : "text-red-600"}`}>
                        {item.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="border-t border-gray-100 pt-6 text-xs text-gray-400 text-center">
            <p>Generated by RegBite US · FDA Dietary Supplement Compliance Platform</p>
            <p className="mt-0.5">Report ID: {check.id} · This report is for informational purposes only and does not constitute legal advice.</p>
          </div>
        </div>
      </div>
    </>
  );
}
