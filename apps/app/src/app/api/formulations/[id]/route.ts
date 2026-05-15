import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@regbite/database';

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  const formulation = await prisma.formulation.findUnique({
    where: { id },
    include: {
      complianceChecks: {
        orderBy: { createdAt: 'desc' },
        take: 5,
        select: {
          id: true, checkType: true, status: true, overallScore: true,
          results: true, createdAt: true,
        },
      },
    },
  });

  if (!formulation) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  }

  return NextResponse.json({ formulation });
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const body = await req.json().catch(() => ({}));

  const formulation = await prisma.formulation.update({
    where: { id },
    data: {
      ...(body.productName && { productName: body.productName }),
      ...(body.servingSize && { servingSize: body.servingSize }),
      ...(body.servingsPerContainer && { servingsPerContainer: body.servingsPerContainer }),
      ...(body.ingredients && { ingredients: body.ingredients }),
      ...(body.claims && { claims: body.claims }),
      ...(body.status && { status: body.status }),
    },
  });

  return NextResponse.json({ formulation });
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  await prisma.formulation.update({
    where: { id },
    data: { status: 'ARCHIVED' },
  });
  return NextResponse.json({ success: true });
}
