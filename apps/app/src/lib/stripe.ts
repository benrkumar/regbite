import Stripe from 'stripe';

// Lazy placeholder — prevents "Neither apiKey nor config.authenticator provided"
// throw at module-eval time during `next build` when env var is absent.
export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY ?? 'sk_test_stripe-not-configured', {
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
