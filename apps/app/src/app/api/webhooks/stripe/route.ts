import { NextRequest, NextResponse } from 'next/server';
import Stripe from 'stripe';
import { stripe } from '@/lib/stripe';
import { prisma } from '@regbite/database';

function mapPriceIdToPlan(priceId: string): string {
  const map: Record<string, string> = {
    [process.env.STRIPE_PRICE_STARTER_ID ?? '##']: 'STARTER',
    [process.env.STRIPE_PRICE_GROWTH_ID ?? '##']: 'GROWTH',
    [process.env.STRIPE_PRICE_PROFESSIONAL_ID ?? '##']: 'PROFESSIONAL',
    [process.env.STRIPE_PRICE_ENTERPRISE_ID ?? '##']: 'ENTERPRISE',
    [process.env.STRIPE_PRICE_CONSULTANT_ID ?? '##']: 'CONSULTANT',
  };
  return map[priceId] ?? 'STARTER';
}

export async function POST(req: NextRequest) {
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!webhookSecret) {
    return NextResponse.json({ error: 'STRIPE_WEBHOOK_SECRET not configured' }, { status: 500 });
  }

  const body = await req.text();
  const sig = req.headers.get('stripe-signature');
  if (!sig) return NextResponse.json({ error: 'Missing stripe-signature' }, { status: 400 });

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, sig, webhookSecret);
  } catch {
    return NextResponse.json({ error: 'Invalid webhook signature' }, { status: 400 });
  }

  try {
    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object as Stripe.Checkout.Session;
        const orgId = session.metadata?.organizationId;
        if (!orgId || !session.subscription) break;

        const subscription = await stripe.subscriptions.retrieve(session.subscription as string);
        const priceId = subscription.items.data[0]?.price.id ?? '';
        const plan = mapPriceIdToPlan(priceId);
        const customerId = typeof session.customer === 'string' ? session.customer : session.customer?.id ?? '';

        await prisma.$transaction([
          prisma.organization.update({
            where: { id: orgId },
            data: { plan: plan as never, ...(customerId ? { stripeCustomerId: customerId } : {}) },
          }),
          prisma.subscription.upsert({
            where: { organizationId: orgId },
            create: {
              organizationId: orgId,
              stripeSubscriptionId: subscription.id,
              stripeCustomerId: customerId || null,
              stripePriceId: priceId,
              plan: plan as never,
              status: 'ACTIVE',
            },
            update: {
              stripeSubscriptionId: subscription.id,
              stripeCustomerId: customerId || null,
              stripePriceId: priceId,
              plan: plan as never,
              status: 'ACTIVE',
            },
          }),
        ]);
        break;
      }

      case 'customer.subscription.updated': {
        const subscription = event.data.object as Stripe.Subscription;
        const priceId = subscription.items.data[0]?.price.id ?? '';
        const plan = mapPriceIdToPlan(priceId);
        const stripeStatus = subscription.status;
        const status =
          stripeStatus === 'active' ? 'ACTIVE'
          : stripeStatus === 'past_due' ? 'PAST_DUE'
          : stripeStatus === 'canceled' ? 'CANCELLED'
          : stripeStatus === 'trialing' ? 'TRIALING'
          : stripeStatus === 'unpaid' ? 'UNPAID'
          : 'ACTIVE';

        const sub = await prisma.subscription.findFirst({
          where: { stripeSubscriptionId: subscription.id },
        });
        if (!sub) break;

        await prisma.$transaction([
          prisma.subscription.update({
            where: { stripeSubscriptionId: subscription.id },
            data: { plan: plan as never, status: status as never, stripePriceId: priceId },
          }),
          prisma.organization.update({
            where: { id: sub.organizationId },
            data: { plan: plan as never },
          }),
        ]);
        break;
      }

      case 'customer.subscription.deleted': {
        const subscription = event.data.object as Stripe.Subscription;
        const sub = await prisma.subscription.findFirst({
          where: { stripeSubscriptionId: subscription.id },
        });
        if (!sub) break;

        await prisma.$transaction([
          prisma.subscription.update({
            where: { stripeSubscriptionId: subscription.id },
            data: { status: 'CANCELLED', cancelledAt: new Date() },
          }),
          prisma.organization.update({
            where: { id: sub.organizationId },
            data: { plan: 'STARTER' },
          }),
        ]);
        break;
      }

      case 'invoice.payment_failed': {
        const invoice = event.data.object as Stripe.Invoice;
        const subscriptionId = (invoice as { subscription?: string }).subscription;
        if (!subscriptionId) break;
        await prisma.subscription.updateMany({
          where: { stripeSubscriptionId: subscriptionId },
          data: { status: 'PAST_DUE' },
        });
        break;
      }
    }

    return NextResponse.json({ received: true });
  } catch (err) {
    console.error('Stripe webhook error:', err);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}
