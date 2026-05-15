import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@regbite/database';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const severity = searchParams.get('severity'); // CRITICAL | HIGH | MEDIUM | LOW
  const source = searchParams.get('source');
  const limit = Math.min(parseInt(searchParams.get('limit') ?? '50', 10), 100);

  const where: Record<string, unknown> = {};
  if (severity) where.severity = severity;
  if (source) where.source = source;

  const changes = await prisma.regulatoryChange.findMany({
    where,
    orderBy: [{ severity: 'asc' }, { detectedAt: 'desc' }],
    take: limit,
    select: {
      id: true,
      source: true,
      sourceUrl: true,
      documentTitle: true,
      summary: true,
      changeType: true,
      severity: true,
      affectedModules: true,
      publishedAt: true,
      detectedAt: true,
    },
  });

  return NextResponse.json({ changes });
}
