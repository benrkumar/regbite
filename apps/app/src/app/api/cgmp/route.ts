import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { scoreCGMPAudit, buildEmptyAuditInput } from '@regbite/compliance-engine';
import { getOrganizationId } from '@/lib/auth';
import { prisma } from '@regbite/database';

const createSchema = z.object({
  title: z.string().min(1).max(200),
});

const updateSchema = z.object({
  id: z.string(),
  sections: z.record(z.record(z.boolean().nullable())),
});

async function resolveOrgId(): Promise<string> {
  const orgId = await getOrganizationId();
  if (orgId) return orgId;
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
  const audits = await prisma.cGMPAudit.findMany({
    where: { organizationId: orgId },
    orderBy: { updatedAt: 'desc' },
    select: { id: true, title: true, overallScore: true, completedAt: true, createdAt: true, updatedAt: true },
  });
  return NextResponse.json({ audits });
}

export async function POST(req: NextRequest) {
  const orgId = await resolveOrgId();
  const body = await req.json().catch(() => null);
  const parsed = createSchema.safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const audit = await prisma.cGMPAudit.create({
    data: {
      organizationId: orgId,
      title: parsed.data.title,
      sections: buildEmptyAuditInput(),
    },
  });

  return NextResponse.json({ audit }, { status: 201 });
}

export async function PATCH(req: NextRequest) {
  const orgId = await resolveOrgId();
  const body = await req.json().catch(() => null);
  const parsed = updateSchema.safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });

  const existing = await prisma.cGMPAudit.findFirst({
    where: { id: parsed.data.id, organizationId: orgId },
  });
  if (!existing) return NextResponse.json({ error: 'Audit not found' }, { status: 404 });

  const auditResult = scoreCGMPAudit(parsed.data.sections);

  const audit = await prisma.cGMPAudit.update({
    where: { id: parsed.data.id },
    data: {
      sections: parsed.data.sections,
      overallScore: auditResult.overallScore,
    },
  });

  return NextResponse.json({ audit, result: auditResult });
}
