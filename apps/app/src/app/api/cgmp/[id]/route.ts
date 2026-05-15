import { NextRequest, NextResponse } from 'next/server';
import { getOrganizationId } from '@/lib/auth';
import { prisma } from '@regbite/database';

async function resolveOrgId(): Promise<string> {
  const orgId = await getOrganizationId();
  if (orgId) return orgId;
  return process.env.DEV_ORG_ID ?? 'dev-org';
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const orgId = await resolveOrgId();

  const audit = await prisma.cGMPAudit.findFirst({
    where: { id, organizationId: orgId },
  });

  if (!audit) return NextResponse.json({ error: 'Audit not found' }, { status: 404 });
  return NextResponse.json({ audit });
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const orgId = await resolveOrgId();

  const existing = await prisma.cGMPAudit.findFirst({ where: { id, organizationId: orgId } });
  if (!existing) return NextResponse.json({ error: 'Audit not found' }, { status: 404 });

  await prisma.cGMPAudit.delete({ where: { id } });
  return NextResponse.json({ deleted: true });
}
