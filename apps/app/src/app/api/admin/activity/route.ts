import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@regbite/database";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const orgId = searchParams.get("orgId") ?? undefined;
    const action = searchParams.get("action") ?? undefined;
    const limit = Math.min(parseInt(searchParams.get("limit") ?? "50"), 200);

    const logs = await prisma.activityLog.findMany({
      where: {
        ...(orgId ? { organizationId: orgId } : {}),
        ...(action ? { action: { contains: action, mode: "insensitive" } } : {}),
      },
      orderBy: { createdAt: "desc" },
      take: limit,
      select: {
        id: true,
        action: true,
        resourceType: true,
        resourceId: true,
        detail: true,
        ipAddress: true,
        createdAt: true,
        member: { select: { email: true, name: true } },
        organization: { select: { name: true, slug: true } },
      },
    });

    return NextResponse.json(logs);
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
