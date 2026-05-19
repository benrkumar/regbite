import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@regbite/database';

export async function GET() {
  try {
    const recentChanges = await prisma.regulatoryChange.findMany({
      orderBy: { detectedAt: 'desc' },
      take: 20,
      select: {
        id: true,
        source: true,
        documentTitle: true,
        changeType: true,
        severity: true,
        detectedAt: true,
      },
    });

    const bySource = await prisma.regulatoryChange.groupBy({
      by: ['source'],
      _count: { id: true },
      orderBy: { _count: { id: 'desc' } },
    });

    return NextResponse.json({ recentChanges, bySource });
  } catch (err) {
    console.error('[admin/api/scraper]', err);
    return NextResponse.json({ error: 'DB error' }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const { scraper } = body as { scraper?: string };

  return NextResponse.json({
    message: `Scraper trigger not yet implemented in this environment. Would run: ${scraper ?? 'all'}`,
    note: 'In production, this enqueues a BullMQ job to the scraper worker on Railway.',
  });
}
