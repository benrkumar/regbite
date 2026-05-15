import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@regbite/database";
import { requireOrganizationId } from "@/lib/auth";
import { auth } from "@clerk/nextjs/server";

export async function GET() {
  try {
    const orgId = await requireOrganizationId();
    const org = await prisma.organization.findUnique({
      where: { id: orgId },
      select: {
        id: true,
        name: true,
        slug: true,
        plan: true,
        createdAt: true,
        _count: { select: { members: { where: { deletedAt: null } } } },
      },
    });
    if (!org) return NextResponse.json({ error: "Not found" }, { status: 404 });
    return NextResponse.json(org);
  } catch {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
}

const patchSchema = z.object({ name: z.string().min(1).max(100) });

export async function PATCH(req: NextRequest) {
  try {
    const orgId = await requireOrganizationId();
    const body = await req.json();
    const { name } = patchSchema.parse(body);

    const { userId } = await auth();
    const member = userId
      ? await prisma.member.findFirst({
          where: { clerkUserId: userId, organizationId: orgId, deletedAt: null },
          select: { id: true },
        })
      : null;

    const org = await prisma.organization.update({
      where: { id: orgId },
      data: { name },
      select: { id: true, name: true, slug: true, plan: true, createdAt: true },
    });

    if (member) {
      await prisma.activityLog.create({
        data: {
          memberId: member.id,
          organizationId: orgId,
          action: "ORG_UPDATED",
          resourceType: "Organization",
          resourceId: orgId,
          detail: `Name changed to "${name}"`,
          ipAddress: req.headers.get("x-forwarded-for") ?? undefined,
        },
      });
    }

    return NextResponse.json(org);
  } catch (err) {
    if (err instanceof z.ZodError) {
      return NextResponse.json({ error: err.issues }, { status: 422 });
    }
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
}
