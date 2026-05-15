import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@regbite/database';
import { checkFormula } from '@regbite/compliance-engine';

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  const formulation = await prisma.formulation.findUnique({ where: { id } });
  if (!formulation) {
    return NextResponse.json({ error: 'Formulation not found' }, { status: 404 });
  }

  // Create a pending compliance check record
  const check = await prisma.complianceCheck.create({
    data: {
      formulationId: id,
      organizationId: formulation.organizationId,
      checkType: 'FORMULA',
      status: 'RUNNING',
    },
  });

  try {
    const ingredients = formulation.ingredients as {
      name: string; amount: number; unit: string; casNumber?: string;
    }[];

    const result = await checkFormula({ ingredients, servingSize: formulation.servingSize ?? undefined });

    // Store results
    await prisma.complianceCheck.update({
      where: { id: check.id },
      data: {
        status: 'COMPLETED',
        overallScore: result.overallScore,
        results: result as never,
        regulatoryCitations: result.checks.map((c) => c.regulatoryCitation).filter(Boolean) as never,
      },
    });

    // Update formulation score and status
    const status =
      result.overallScore >= 90 ? 'COMPLIANT' :
      result.overallScore >= 50 ? 'UNDER_REVIEW' :
      'NON_COMPLIANT';

    await prisma.formulation.update({
      where: { id },
      data: { complianceScore: result.overallScore, status },
    });

    return NextResponse.json({ checkId: check.id, result });
  } catch (err) {
    await prisma.complianceCheck.update({
      where: { id: check.id },
      data: { status: 'FAILED' },
    });
    console.error('[check] Formula check failed:', err);
    return NextResponse.json({ error: 'Compliance check failed' }, { status: 500 });
  }
}
