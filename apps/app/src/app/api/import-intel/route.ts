import { NextRequest, NextResponse } from 'next/server';
import { checkImportRequirements } from '@regbite/compliance-engine';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const {
      supplierCountry,
      supplierName,
      ingredientName,
      hasThirdPartyCertification,
      hasCoA,
      hasFSVPPlan,
      hasSupplierAudit,
      hasHazardAnalysis,
    } = body;

    if (!supplierCountry) {
      return NextResponse.json({ error: 'supplierCountry is required' }, { status: 400 });
    }

    const result = checkImportRequirements({
      supplierCountry,
      supplierName,
      ingredientName,
      hasThirdPartyCertification,
      hasCoA,
      hasFSVPPlan,
      hasSupplierAudit,
      hasHazardAnalysis,
    });

    return NextResponse.json({ result });
  } catch (err) {
    console.error('[/api/import-intel] POST error:', err);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
