import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@regbite/database';

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get('q')?.trim();
  if (!q || q.length < 2) {
    return NextResponse.json({ results: [] });
  }

  const results = await prisma.uSIngredient.findMany({
    where: {
      OR: [
        { name: { contains: q, mode: 'insensitive' } },
        { aliases: { has: q } },
        { casNumber: q },
      ],
    },
    select: {
      id: true,
      name: true,
      fdaStatus: true,
      grasStatus: true,
      prop65Listed: true,
      advisoryNotes: true,
    },
    take: 20,
    orderBy: { name: 'asc' },
  });

  return NextResponse.json({ results });
}
