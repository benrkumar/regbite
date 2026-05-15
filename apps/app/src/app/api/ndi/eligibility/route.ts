import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { assessNDIEligibility } from '@regbite/compliance-engine';
import { prisma } from '@regbite/database';

const schema = z.object({
  ingredientName: z.string().min(1).max(200),
  casNumber: z.string().optional(),
  preMarketDSHEA: z.boolean().optional(),
  hasSafetyStudies: z.boolean().optional(),
  intendedUse: z.string().optional(),
});

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null);
  const parsed = schema.safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const { ingredientName, casNumber, preMarketDSHEA, hasSafetyStudies, intendedUse } = parsed.data;

  // Enrich from DB if available
  const dbIngredient = await prisma.uSIngredient.findFirst({
    where: casNumber
      ? { casNumber }
      : { name: { contains: ingredientName, mode: 'insensitive' } },
    select: {
      fdaStatus: true,
      grasStatus: true,
      dsheaGrandfathered: true,
      ndiNotificationsCount: true,
    },
  });

  const result = assessNDIEligibility({
    ingredientName,
    casNumber,
    preMarketDSHEA: preMarketDSHEA ?? dbIngredient?.dsheaGrandfathered ?? undefined,
    existingNDICount: dbIngredient?.ndiNotificationsCount ?? 0,
    grasStatus: dbIngredient?.grasStatus,
    fdaStatus: dbIngredient?.fdaStatus,
    hasSafetyStudies,
    intendedUse,
  });

  return NextResponse.json({ result });
}
