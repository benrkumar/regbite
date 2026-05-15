import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@regbite/database';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const q = searchParams.get('q')?.trim() ?? '';

  if (q.length < 2) return NextResponse.json({ results: [] });

  const notifications = await prisma.nDINotification.findMany({
    where: {
      OR: [
        { ingredientName: { contains: q, mode: 'insensitive' } },
        { fdaNotificationNumber: { contains: q, mode: 'insensitive' } },
        { submitter: { contains: q, mode: 'insensitive' } },
      ],
    },
    orderBy: { submissionDate: 'desc' },
    take: 20,
    select: {
      id: true,
      fdaNotificationNumber: true,
      ingredientName: true,
      submitter: true,
      submissionDate: true,
      fdaResponse: true,
    },
  });

  return NextResponse.json({ results: notifications });
}
