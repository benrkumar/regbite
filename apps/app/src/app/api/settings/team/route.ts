import { NextResponse } from "next/server";
import { prisma } from "@regbite/database";
import { requireOrganizationId } from "@/lib/auth";

export async function GET() {
  try {
    const orgId = await requireOrganizationId();
    const members = await prisma.member.findMany({
      where: { organizationId: orgId, deletedAt: null },
      select: {
        id: true,
        email: true,
        name: true,
        role: true,
        createdAt: true,
      },
      orderBy: { createdAt: "asc" },
    });
    return NextResponse.json(members);
  } catch {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
}
