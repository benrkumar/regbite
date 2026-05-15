import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@regbite/database";
import { requireOrganizationId } from "@/lib/auth";
import { auth, clerkClient } from "@clerk/nextjs/server";
import { sendEmail, teamInviteEmail } from "@regbite/config";

const inviteSchema = z.object({
  email: z.string().email(),
  role: z.enum(["ACCOUNT_ADMIN", "EDITOR", "VIEWER", "CONSULTANT"]),
});

export async function POST(req: NextRequest) {
  try {
    const orgId = await requireOrganizationId();
    const body = await req.json();
    const { email, role } = inviteSchema.parse(body);

    const org = await prisma.organization.findUnique({
      where: { id: orgId },
      select: { id: true, name: true, clerkOrgId: true },
    });
    if (!org) return NextResponse.json({ error: "Not found" }, { status: 404 });

    // Send Clerk invitation if we have a Clerk org
    if (org.clerkOrgId) {
      const client = await clerkClient();
      await client.organizations.createOrganizationInvitation({
        organizationId: org.clerkOrgId,
        emailAddress: email,
        role: "org:member",
        inviterUserId: (await auth()).userId ?? "",
      });
    }

    // Send Resend email
    try {
      const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "https://app.regbite.com";
      await sendEmail({
        ...teamInviteEmail(email, org.name, appUrl),
        to: email,
      });
    } catch {
      // Email failure is non-fatal
    }

    // Log activity
    const { userId } = await auth();
    const member = userId
      ? await prisma.member.findFirst({
          where: { clerkUserId: userId, organizationId: orgId, deletedAt: null },
          select: { id: true },
        })
      : null;

    if (member) {
      await prisma.activityLog.create({
        data: {
          memberId: member.id,
          organizationId: orgId,
          action: "MEMBER_INVITED",
          resourceType: "Member",
          detail: `Invited ${email} as ${role}`,
          ipAddress: req.headers.get("x-forwarded-for") ?? undefined,
        },
      });
    }

    return NextResponse.json({ success: true });
  } catch (err) {
    if (err instanceof z.ZodError) {
      return NextResponse.json({ error: err.issues }, { status: 422 });
    }
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
}
