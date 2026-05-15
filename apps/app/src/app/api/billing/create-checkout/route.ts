import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { stripe, STRIPE_PRICE_IDS } from '@/lib/stripe';
import { requireOrganizationId } from '@/lib/auth';
import { prisma } from '@regbite/database';

const schema = z.object({
  plan: z.enum(['STARTER', 'GROWTH', 'PROFESSIONAL', 'ENTERPRISE', 'CONSULTANT']),
});

export async function POST(req: NextRequest) {
  const orgId = await requireOrganizationId().catch(() => null);
  if (!orgId) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const body = await req.json().catch(() => null);
  const parsed = schema.safeParse(body);
  if (!parsed.success) return NextResponse.json({ error: 'Invalid plan' }, { status: 400 });

  const { plan } = parsed.data;
  const priceId = STRIPE_PRICE_IDS[plan];
  if (!priceId) {
    return NextResponse.json({ error: `Stripe price ID for ${plan} not configured` }, { status: 500 });
  }

  const org = await prisma.organization.findUnique({ where: { id: orgId } });
  if (!org) return NextResponse.json({ error: 'Organization not found' }, { status: 404 });

  const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000';

  const session = await stripe.checkout.sessions.create({
    mode: 'subscription',
    payment_method_types: ['card'],
    line_items: [{ price: priceId, quantity: 1 }],
    customer: org.stripeCustomerId ?? undefined,
    customer_email: org.stripeCustomerId ? undefined : undefined,
    metadata: { organizationId: orgId },
    success_url: `${appUrl}/billing?success=true`,
    cancel_url: `${appUrl}/billing`,
    subscription_data: {
      metadata: { organizationId: orgId },
    },
  });

  return NextResponse.json({ url: session.url });
}
