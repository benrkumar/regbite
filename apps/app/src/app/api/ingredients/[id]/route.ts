import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@regbite/database';
import { checkIngredient } from '@regbite/compliance-engine';

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  const ingredient = await prisma.uSIngredient.findUnique({
    where: { id },
    include: {
      ndiNotifications: {
        select: {
          fdaNotificationNumber: true,
          fdaResponse: true,
          submissionDate: true,
        },
        take: 5,
        orderBy: { submissionDate: 'desc' },
      },
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

  if (!ingredient) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  }

  // Run compliance check
  const complianceResult = await checkIngredient({ name: ingredient.name, casNumber: ingredient.casNumber });

  return NextResponse.json({ ingredient, complianceResult });
}
