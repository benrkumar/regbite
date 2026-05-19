import { NextResponse } from "next/server";
import { prisma } from "@regbite/database";

export const dynamic = "force-dynamic";

const PLAN_PRICES: Record<string, number> = {
  STARTER: 199,
  GROWTH: 399,
  PROFESSIONAL: 699,
  ENTERPRISE: 999,
  CONSULTANT: 499,
};

export async function GET() {
  try {
    const [subscriptions, recentEvents] = await Promise.all([
      prisma.subscription.findMany({
        select: { status: true, plan: true, currentPeriodEnd: true, createdAt: true },
      }),
      prisma.subscription.findMany({
        orderBy: { createdAt: "desc" },
        take: 10,
        select: {
          id: true,
          status: true,
          plan: true,
          createdAt: true,
          organization: { select: { name: true, slug: true } },
        },
      }),
    ]);

    // MRR: sum of active + trialing subscription plan prices
    const mrr = subscriptions
      .filter((s) => s.status === "ACTIVE" || s.status === "TRIALING")
      .reduce((sum, s) => sum + (PLAN_PRICES[s.plan] ?? 0), 0);

    // Counts by status
    const byStatus = subscriptions.reduce<Record<string, number>>((acc, s) => {
      acc[s.status] = (acc[s.status] ?? 0) + 1;
      return acc;
    }, {});

    // Active counts by plan
    const byPlan = subscriptions
      .filter((s) => s.status === "ACTIVE")
      .reduce<Record<string, number>>((acc, s) => {
        acc[s.plan] = (acc[s.plan] ?? 0) + 1;
        return acc;
      }, {});

    return NextResponse.json({ mrr, byStatus, byPlan, recentEvents });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
