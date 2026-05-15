import { NextResponse } from 'next/server';
import { getOrganizationId } from '@/lib/auth';
import { prisma } from '@regbite/database';

export async function GET() {
  const orgId = await getOrganizationId();
  if (!orgId) {
    return NextResponse.json({ currentPlan: 'STARTER', status: 'ACTIVE', currentPeriodEnd: null, hasSubscription: false });
  }

  const [org, subscription] = await Promise.all([
    prisma.organization.findUnique({ where: { id: orgId }, select: { plan: true } }),
    prisma.subscription.findUnique({
      where: { organizationId: orgId },
      select: { status: true, currentPeriodEnd: true },
    }),
  ]);

  return NextResponse.json({
    currentPlan: org?.plan ?? 'STARTER',
    status: subscription?.status ?? 'ACTIVE',
    currentPeriodEnd: subscription?.currentPeriodEnd?.toISOString() ?? null,
    hasSubscription: !!subscription,
  });
}
