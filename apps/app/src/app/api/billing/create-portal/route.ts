import { NextRequest, NextResponse } from 'next/server';
import { stripe } from '@/lib/stripe';
import { requireOrganizationId } from '@/lib/auth';
import { prisma } from '@regbite/database';

export async function POST(req: NextRequest) {
  const orgId = await requireOrganizationId().catch(() => null);
  if (!orgId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const org = await prisma.organization.findUnique({ where: { id: orgId } });
  if (!org?.stripeCustomerId) {
    return NextResponse.json({ error: 'No active subscription found' }, { status: 404 });
  }

  const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000';

  const session = await stripe.billingPortal.sessions.create({
    customer: org.stripeCustomerId,
    return_url: `${appUrl}/billing`,
  });

  return NextResponse.json({ url: session.url });
}
