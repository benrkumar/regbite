import { auth } from '@clerk/nextjs/server';
import { prisma } from '@regbite/database';

export async function getOrganizationId(): Promise<string | null> {
  // Dev bypass
  if (process.env.NODE_ENV === 'development' && process.env.DEV_ORG_ID) {
    return process.env.DEV_ORG_ID;
  }

  const { userId, orgId: clerkOrgId } = await auth();
  if (!userId) return null;

  if (clerkOrgId) {
    const org = await prisma.organization.findFirst({
      where: { clerkOrgId },
      select: { id: true },
    });
    return org?.id ?? null;
  }

  // Personal workspace (no org selected)
  const member = await prisma.member.findFirst({
    where: { clerkUserId: userId, deletedAt: null },
    select: { organizationId: true },
  });
  return member?.organizationId ?? null;
}

export async function requireOrganizationId(): Promise<string> {
  const orgId = await getOrganizationId();
  if (!orgId) throw new Error('Not authenticated or organization not found');
  return orgId;
}
