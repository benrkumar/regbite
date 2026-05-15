import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@regbite/database';
import { z } from 'zod';
import { getOrganizationId } from '@/lib/auth';

const createSchema = z.object({
  productName: z.string().min(1).max(200),
  productType: z.enum([
    'DIETARY_SUPPLEMENT', 'VITAMIN_MINERAL', 'HERBAL_BOTANICAL',
    'AMINO_ACID', 'SPORTS_NUTRITION', 'PROBIOTICS', 'SPECIALTY',
  ]).default('DIETARY_SUPPLEMENT'),
  servingSize: z.string().optional(),
  servingsPerContainer: z.string().optional(),
  ingredients: z.array(z.object({
    name: z.string().min(1),
    amount: z.number().positive(),
    unit: z.string().min(1),
    casNumber: z.string().optional().nullable(),
  })).min(1),
  claims: z.array(z.string()).default([]),
});

async function resolveOrgId(): Promise<string> {
  const orgId = await getOrganizationId();
  if (orgId) return orgId;

  // Dev fallback: create org on demand
  const devId = process.env.DEV_ORG_ID ?? 'dev-org';
  await prisma.organization.upsert({
    where: { id: devId },
    update: {},
    create: { id: devId, name: 'Dev Organization', slug: 'dev-org', plan: 'STARTER' },
  });
  return devId;
}

export async function GET() {
  const orgId = await resolveOrgId();

  const formulations = await prisma.formulation.findMany({
    where: { organizationId: orgId },
    orderBy: { updatedAt: 'desc' },
    select: {
      id: true, productName: true, productType: true, status: true,
      complianceScore: true, createdAt: true, updatedAt: true,
    },
  });

  return NextResponse.json({ formulations });
}

export async function POST(req: NextRequest) {
  const orgId = await resolveOrgId();

  const body = await req.json().catch(() => null);
  const parsed = createSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  const formulation = await prisma.formulation.create({
    data: {
      organizationId: orgId,
      productName: parsed.data.productName,
      productType: parsed.data.productType,
      servingSize: parsed.data.servingSize,
      servingsPerContainer: parsed.data.servingsPerContainer,
      ingredients: parsed.data.ingredients,
      claims: parsed.data.claims,
      status: 'DRAFT',
    },
  });

  return NextResponse.json({ formulation }, { status: 201 });
}
