import { NextResponse } from 'next/server';
import { prisma } from '@regbite/database';

export async function GET() {
  try {
    const [
      orgsCount,
      membersCount,
      formulationsCount,
      checksCount,
      ingredientsCount,
      warningLettersCount,
      ndiCount,
      regulatoryChangesCount,
      prop65Count,
      subscriptionsCount,
    ] = await Promise.all([
      prisma.organization.count({ where: { deletedAt: null } }),
      prisma.member.count({ where: { deletedAt: null } }),
      prisma.formulation.count(),
      prisma.complianceCheck.count(),
      prisma.uSIngredient.count(),
      prisma.fDAWarningLetter.count(),
      prisma.nDINotification.count(),
      prisma.regulatoryChange.count(),
      prisma.prop65Chemical.count(),
      prisma.subscription.count({ where: { status: 'ACTIVE' } }),
    ]);

    const recentOrgs = await prisma.organization.findMany({
      where: { deletedAt: null },
      orderBy: { createdAt: 'desc' },
      take: 10,
      select: { id: true, name: true, plan: true, createdAt: true },
    });

    const recentChecks = await prisma.complianceCheck.findMany({
      orderBy: { createdAt: 'desc' },
      take: 5,
      select: {
        id: true,
        checkType: true,
        status: true,
        overallScore: true,
        createdAt: true,
        organization: { select: { name: true } },
      },
    });

    return NextResponse.json({
      counts: {
        orgs: orgsCount,
        members: membersCount,
        formulations: formulationsCount,
        checks: checksCount,
        ingredients: ingredientsCount,
        warningLetters: warningLettersCount,
        ndiNotifications: ndiCount,
        regulatoryChanges: regulatoryChangesCount,
        prop65Chemicals: prop65Count,
        activeSubscriptions: subscriptionsCount,
      },
      recentOrgs,
      recentChecks,
    });
  } catch (err) {
    console.error('[admin/api/stats]', err);
    return NextResponse.json({ error: 'DB error' }, { status: 500 });
  }
}
