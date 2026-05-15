import { NextRequest, NextResponse } from 'next/server';
import { Webhook } from 'svix';
import { headers } from 'next/headers';
import { prisma } from '@regbite/database';

interface UserData {
  id: string;
  email_addresses: { email_address: string }[];
  first_name?: string | null;
  last_name?: string | null;
}

interface OrgData {
  id: string;
  name: string;
  slug?: string | null;
}

interface MembershipData {
  organization: { id: string };
  public_user_data: { user_id: string; identifier: string };
  role: string;
}

function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60);
}

export async function POST(req: NextRequest) {
  const webhookSecret = process.env.CLERK_WEBHOOK_SECRET;
  if (!webhookSecret) {
    return NextResponse.json({ error: 'CLERK_WEBHOOK_SECRET not configured' }, { status: 500 });
  }

  const headerPayload = await headers();
  const svixId = headerPayload.get('svix-id');
  const svixTimestamp = headerPayload.get('svix-timestamp');
  const svixSignature = headerPayload.get('svix-signature');

  if (!svixId || !svixTimestamp || !svixSignature) {
    return NextResponse.json({ error: 'Missing svix headers' }, { status: 400 });
  }

  const payload = await req.text();
  const wh = new Webhook(webhookSecret);

  let event: { type: string; data: Record<string, unknown> };
  try {
    event = wh.verify(payload, {
      'svix-id': svixId,
      'svix-timestamp': svixTimestamp,
      'svix-signature': svixSignature,
    }) as { type: string; data: Record<string, unknown> };
  } catch {
    return NextResponse.json({ error: 'Invalid webhook signature' }, { status: 400 });
  }

  try {
    switch (event.type) {
      case 'user.created': {
        const d = event.data as unknown as UserData;
        const email = d.email_addresses[0]?.email_address ?? '';
        const name = [d.first_name, d.last_name].filter(Boolean).join(' ') || email;
        const orgSlug = slugify(`${name}-workspace`);
        const org = await prisma.organization.upsert({
          where: { slug: orgSlug },
          create: { name: `${name}'s Workspace`, slug: orgSlug, plan: 'STARTER' },
          update: {},
        });
        await prisma.member.upsert({
          where: { clerkUserId: d.id },
          create: { clerkUserId: d.id, email, name, role: 'ACCOUNT_ADMIN', organizationId: org.id },
          update: { email, name },
        });
        break;
      }

      case 'user.updated': {
        const d = event.data as unknown as UserData;
        const email = d.email_addresses[0]?.email_address ?? '';
        const name = [d.first_name, d.last_name].filter(Boolean).join(' ') || email;
        await prisma.member.updateMany({ where: { clerkUserId: d.id }, data: { email, name } });
        break;
      }

      case 'user.deleted': {
        const { id } = event.data as { id: string };
        await prisma.member.updateMany({ where: { clerkUserId: id }, data: { deletedAt: new Date() } });
        break;
      }

      case 'organization.created': {
        const d = event.data as unknown as OrgData;
        await prisma.organization.upsert({
          where: { clerkOrgId: d.id },
          create: { clerkOrgId: d.id, name: d.name, slug: d.slug ?? slugify(d.name), plan: 'STARTER' },
          update: { name: d.name, ...(d.slug ? { slug: d.slug } : {}) },
        });
        break;
      }

      case 'organization.updated': {
        const d = event.data as unknown as OrgData;
        await prisma.organization.updateMany({
          where: { clerkOrgId: d.id },
          data: { name: d.name, ...(d.slug ? { slug: d.slug } : {}) },
        });
        break;
      }

      case 'organization.deleted': {
        const { id } = event.data as { id: string };
        await prisma.organization.updateMany({ where: { clerkOrgId: id }, data: { deletedAt: new Date() } });
        break;
      }

      case 'organizationMembership.created': {
        const d = event.data as unknown as MembershipData;
        const org = await prisma.organization.findFirst({ where: { clerkOrgId: d.organization.id } });
        if (!org) break;
        const role = d.role === 'org:admin' ? 'ACCOUNT_ADMIN' : 'EDITOR';
        await prisma.member.upsert({
          where: { clerkUserId: d.public_user_data.user_id },
          create: {
            clerkUserId: d.public_user_data.user_id,
            email: d.public_user_data.identifier,
            role,
            organizationId: org.id,
          },
          update: { organizationId: org.id, role },
        });
        break;
      }

      case 'organizationMembership.deleted': {
        const d = event.data as unknown as MembershipData;
        const org = await prisma.organization.findFirst({ where: { clerkOrgId: d.organization.id } });
        if (!org) break;
        await prisma.member.updateMany({
          where: { clerkUserId: d.public_user_data.user_id, organizationId: org.id },
          data: { deletedAt: new Date() },
        });
        break;
      }
    }

    return NextResponse.json({ received: true });
  } catch (err) {
    console.error('Clerk webhook error:', err);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}
