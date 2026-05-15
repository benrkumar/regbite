import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@regbite/database";
import { requireOrganizationId } from "@/lib/auth";
import { auth } from "@clerk/nextjs/server";

const roleSchema = z.object({
  role: z.enum(["ACCOUNT_ADMIN", "EDITOR", "VIEWER", "CONSULTANT"]),
});

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ memberId: string }> }
) {
  try {
    const orgId = await requireOrganizationId();
    const { memberId } = await params;
    const body = await req.json();
    const { role } = roleSchema.parse(body);

    const target = await prisma.member.findFirst({
      where: { id: memberId, organizationId: orgId, deletedAt: null },
    });
    if (!target) return NextResponse.json({ error: "Not found" }, { status: 404 });
    if (target.role === "SUPER_ADMIN") {
      return NextResponse.json({ error: "Cannot modify SUPER_ADMIN" }, { status: 403 });
    }

    const updated = await prisma.member.update({
      where: { id: memberId },
      data: { role },
      select: { id: true, email: true, name: true, role: true },
    });

    const { userId } = await auth();
    const actor = userId
      ? await prisma.member.findFirst({
          where: { clerkUserId: userId, organizationId: orgId, deletedAt: null },
          select: { id: true },
        })
      : null;

    if (actor) {
      await prisma.activityLog.create({
        data: {
          memberId: actor.id,
          organizationId: orgId,
          action: "MEMBER_ROLE_CHANGED",
          resourceType: "Member",
          resourceId: memberId,
          detail: `Role changed to ${role}`,
          ipAddress: req.headers.get("x-forwarded-for") ?? undefined,
        },
      });
    }

    return NextResponse.json(updated);
  } catch (err) {
    if (err instanceof z.ZodError) {
      return NextResponse.json({ error: err.issues }, { status: 422 });
    }
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ memberId: string }> }
) {
  try {
    const orgId = await requireOrganizationId();
    const { memberId } = await params;

    const target = await prisma.member.findFirst({
      where: { id: memberId, organizationId: orgId, deletedAt: null },
    });
    if (!target) return NextResponse.json({ error: "Not found" }, { status: 404 });
    if (target.role === "SUPER_ADMIN") {
      return NextResponse.json({ error: "Cannot remove SUPER_ADMIN" }, { status: 403 });
    }

    // Guard: cannot remove the last admin
    if (target.role === "ACCOUNT_ADMIN") {
      const adminCount = await prisma.member.count({
        where: { organizationId: orgId, role: "ACCOUNT_ADMIN", deletedAt: null },
      });
      if (adminCount <= 1) {
        return NextResponse.json({ error: "Cannot remove the last admin" }, { status: 409 });
      }
    }

    await prisma.member.update({
      where: { id: memberId },
      data: { deletedAt: new Date() },
    });

    const { userId } = await auth();
    const actor = userId
      ? await prisma.member.findFirst({
          where: { clerkUserId: userId, organizationId: orgId, deletedAt: null },
          select: { id: true },
        })
      : null;

    if (actor) {
      await prisma.activityLog.create({
        data: {
          memberId: actor.id,
          organizationId: orgId,
          action: "MEMBER_REMOVED",
          resourceType: "Member",
          resourceId: memberId,
          detail: `Removed ${target.email}`,
          ipAddress: req.headers.get("x-forwarded-for") ?? undefined,
        },
      });
    }

    return NextResponse.json({ success: true });
  } catch {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
}
