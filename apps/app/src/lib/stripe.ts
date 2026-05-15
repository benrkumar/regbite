import Stripe from 'stripe';

export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY ?? '', {
  apiVersion: '2026-04-22.dahlia',
  typescript: true,
});

export const STRIPE_PRICE_IDS: Record<string, string | undefined> = {
  STARTER: process.env.STRIPE_PRICE_STARTER_ID,
  GROWTH: process.env.STRIPE_PRICE_GROWTH_ID,
  PROFESSIONAL: process.env.STRIPE_PRICE_PROFESSIONAL_ID,
  ENTERPRISE: process.env.STRIPE_PRICE_ENTERPRISE_ID,
  CONSULTANT: process.env.STRIPE_PRICE_CONSULTANT_ID,
};
