'use client';

import { useEffect, useState } from 'react';
import { Check, ExternalLink, Zap } from 'lucide-react';

type PlanKey = 'STARTER' | 'GROWTH' | 'PROFESSIONAL' | 'ENTERPRISE' | 'CONSULTANT';

const PLANS: {
  key: PlanKey;
  name: string;
  price: number;
  formulations: number | null;
  users: number | null;
  features: string[];
  popular?: boolean;
}[] = [
  {
    key: 'STARTER',
    name: 'Starter',
    price: 199,
    formulations: 10,
    users: 2,
    features: ['Ingredient checker', 'Formulation analysis', 'Label validator', 'Claims checker'],
  },
  {
    key: 'GROWTH',
    name: 'Growth',
    price: 399,
    formulations: 50,
    users: 5,
    features: ['Everything in Starter', 'NDI Navigator', 'cGMP Readiness', 'Regulatory feed', 'Email alerts'],
    popular: true,
  },
  {
    key: 'PROFESSIONAL',
    name: 'Professional',
    price: 699,
    formulations: 200,
    users: 15,
    features: ['Everything in Growth', 'State compliance (Prop 65, NY, FL)', 'Import Intelligence', 'PDF reports', 'API access'],
  },
  {
    key: 'ENTERPRISE',
    name: 'Enterprise',
    price: 999,
    formulations: null,
    users: null,
    features: ['Unlimited formulations', 'Unlimited users', 'Custom integrations', 'SLA guarantee', 'Dedicated support'],
  },
  {
    key: 'CONSULTANT',
    name: 'Consultant',
    price: 499,
    formulations: 100,
    users: 3,
    features: ['Multi-org management', '100 formulations/org', 'White-label reports', 'Client sharing'],
  },
];

interface BillingData {
  currentPlan: PlanKey;
  status: string;
  currentPeriodEnd: string | null;
  hasSubscription: boolean;
}

export default function BillingPage() {
  const [billing, setBilling] = useState<BillingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState<PlanKey | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);

  useEffect(() => {
    fetch('/api/billing/status')
      .then((r) => r.json())
      .then((d) => setBilling(d))
      .catch(() => setBilling({ currentPlan: 'STARTER', status: 'ACTIVE', currentPeriodEnd: null, hasSubscription: false }))
      .finally(() => setLoading(false));
  }, []);

  const handleCheckout = async (plan: PlanKey) => {
    setCheckoutLoading(plan);
    try {
      const res = await fetch('/api/billing/create-checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan }),
      });
      const data = await res.json();
      if (data.url) window.location.href = data.url;
    } finally {
      setCheckoutLoading(null);
    }
  };

  const handlePortal = async () => {
    setPortalLoading(true);
    try {
      const res = await fetch('/api/billing/create-portal', { method: 'POST' });
      const data = await res.json();
      if (data.url) window.location.href = data.url;
    } finally {
      setPortalLoading(false);
    }
  };

  const currentPlan = billing?.currentPlan ?? 'STARTER';

  return (
    <div>
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Billing</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage your subscription and usage.
          </p>
        </div>
        {billing?.hasSubscription && (
          <button
            onClick={handlePortal}
            disabled={portalLoading}
            className="inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            {portalLoading ? 'Opening…' : 'Manage Subscription'}
          </button>
        )}
      </div>

      {/* Current plan banner */}
      {!loading && (
        <div className="mb-8 rounded-lg border bg-white p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Current Plan</p>
              <p className="mt-1 text-xl font-bold text-gray-900">{currentPlan}</p>
              {billing?.currentPeriodEnd && (
                <p className="mt-1 text-sm text-gray-500">
                  {billing.status === 'PAST_DUE' ? (
                    <span className="text-red-600 font-medium">Payment past due</span>
                  ) : (
                    `Renews ${new Date(billing.currentPeriodEnd).toLocaleDateString()}`
                  )}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Zap className="h-8 w-8 text-brand-500" />
            </div>
          </div>
        </div>
      )}

      {/* Pricing grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {PLANS.map((plan) => {
          const isCurrent = currentPlan === plan.key;
          return (
            <div
              key={plan.key}
              className={`relative flex flex-col rounded-xl border bg-white p-5 ${
                plan.popular ? 'border-brand-400 ring-1 ring-brand-400' : ''
              } ${isCurrent ? 'bg-brand-50 border-brand-300' : ''}`}
            >
              {plan.popular && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand-600 px-3 py-0.5 text-xs font-semibold text-white">
                  Popular
                </span>
              )}
              <div className="mb-4">
                <p className="font-bold text-gray-900">{plan.name}</p>
                <p className="mt-1">
                  <span className="text-2xl font-bold text-gray-900">${plan.price}</span>
                  <span className="text-sm text-gray-500">/mo</span>
                </p>
                <p className="mt-1 text-xs text-gray-500">
                  {plan.formulations ? `${plan.formulations} formulations` : 'Unlimited'} ·{' '}
                  {plan.users ? `${plan.users} users` : 'Unlimited users'}
                </p>
              </div>

              <ul className="mb-5 flex-1 space-y-1.5">
                {plan.features.map((feat) => (
                  <li key={feat} className="flex items-start gap-2 text-xs text-gray-700">
                    <Check className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-green-500" />
                    {feat}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => !isCurrent && handleCheckout(plan.key)}
                disabled={isCurrent || checkoutLoading !== null}
                className={`w-full rounded-lg py-2 text-sm font-medium transition-colors ${
                  isCurrent
                    ? 'bg-brand-100 text-brand-700 cursor-default'
                    : plan.popular
                    ? 'bg-brand-600 text-white hover:bg-brand-700'
                    : 'border border-gray-300 text-gray-700 hover:bg-gray-50'
                } disabled:opacity-50`}
              >
                {isCurrent
                  ? 'Current plan'
                  : checkoutLoading === plan.key
                  ? 'Redirecting…'
                  : 'Upgrade'}
              </button>
            </div>
          );
        })}
      </div>

      <p className="mt-6 text-center text-xs text-gray-400">
        All prices in USD. Billed monthly. Cancel anytime via the Stripe customer portal.
        US companies only — US FDA supplement regulations.
      </p>
    </div>
  );
}
