import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@regbite/database";

export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const org = await prisma.organization.findUnique({
      where: { id },
      select: {
        id: true,
        name: true,
        slug: true,
        plan: true,
        deletedAt: true,
        createdAt: true,
        members: {
          where: { deletedAt: null },
          select: { id: true, email: true, name: true, role: true, createdAt: true },
          orderBy: { createdAt: "asc" },
        },
        formulations: {
          take: 10,
          orderBy: { createdAt: "desc" },
          select: { id: true, productName: true, status: true, complianceScore: true, createdAt: true },
        },
        complianceChecks: {
          take: 10,
          orderBy: { createdAt: "desc" },
          select: {
            id: true,
            checkType: true,
            status: true,
            overallScore: true,
            createdAt: true,
            formulation: { select: { productName: true } },
          },
        },
        subscriptions: {
          orderBy: { createdAt: "desc" },
          take: 1,
          select: { id: true, status: true, plan: true, currentPeriodEnd: true, createdAt: true },
        },
      },
    });

    if (!org) return NextResponse.json({ error: "Not found" }, { status: 404 });

    return NextResponse.json({
      ...org,
      suspended: org.deletedAt !== null,
      subscription: org.subscriptions[0] ?? null,
    });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

const patchSchema = z.object({
  plan: z.enum(["STARTER", "GROWTH", "PROFESSIONAL", "ENTERPRISE", "CONSULTANT"]).optional(),
  suspended: z.boolean().optional(),
});

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await req.json();
    const { plan, suspended } = patchSchema.parse(body);

    const data: Record<string, unknown> = {};
    if (plan !== undefined) data.plan = plan;
    if (suspended !== undefined) data.deletedAt = suspended ? new Date() : null;

    const org = await prisma.organization.update({
      where: { id },
      data,
      select: { id: true, name: true, plan: true, deletedAt: true },
    });

    return NextResponse.json({ ...org, suspended: org.deletedAt !== null });
  } catch (err) {
    if (err instanceof z.ZodError) {
      return NextResponse.json({ error: err.issues }, { status: 422 });
    }
    console.error(err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
