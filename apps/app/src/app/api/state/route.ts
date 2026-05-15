import { NextRequest, NextResponse } from 'next/server';
import { checkProp65 } from '@regbite/compliance-engine';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { ingredients, targetMarkets, hasCaliforniaWarning } = body;

    if (!Array.isArray(ingredients) || ingredients.length === 0) {
      return NextResponse.json({ error: 'ingredients array is required' }, { status: 400 });
    }
    if (!Array.isArray(targetMarkets)) {
      return NextResponse.json({ error: 'targetMarkets array is required' }, { status: 400 });
    }

    const result = await checkProp65({ ingredients, targetMarkets, hasCaliforniaWarning });
    return NextResponse.json({ result });
  } catch (err) {
    console.error('[/api/state] POST error:', err);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
