import { NextResponse } from "next/server";
import { prisma } from "@regbite/database";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const orgs = await prisma.organization.findMany({
      orderBy: { createdAt: "desc" },
      select: {
        id: true,
        name: true,
        slug: true,
        plan: true,
        deletedAt: true,
        createdAt: true,
        _count: {
          select: {
            members: { where: { deletedAt: null } },
            formulations: true,
            complianceChecks: true,
          },
        },
        subscriptions: {
          orderBy: { createdAt: "desc" },
          take: 1,
          select: { status: true, plan: true, currentPeriodEnd: true },
        },
      },
    });

    const mapped = orgs.map((o) => ({
      id: o.id,
      name: o.name,
      slug: o.slug,
      plan: o.plan,
      suspended: o.deletedAt !== null,
      createdAt: o.createdAt,
      memberCount: o._count.members,
      formulationCount: o._count.formulations,
      checkCount: o._count.complianceChecks,
      subscription: o.subscriptions[0] ?? null,
    }));

    // Summary stats
    const total = mapped.length;
    const active = mapped.filter((o) => o.subscription?.status === "ACTIVE").length;
    const trialing = mapped.filter((o) => o.subscription?.status === "TRIALING").length;
    const pastDue = mapped.filter((o) => o.subscription?.status === "PAST_DUE").length;

    return NextResponse.json({ orgs: mapped, stats: { total, active, trialing, pastDue } });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
