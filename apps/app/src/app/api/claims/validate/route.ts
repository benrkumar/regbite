import { NextRequest, NextResponse } from 'next/server';
import { classifyClaim } from '@regbite/compliance-engine';
import { z } from 'zod';

const schema = z.object({
  claim: z.string().min(3).max(2000),
  useAI: z.boolean().default(false),
});

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null);
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  const result = classifyClaim({ claim: parsed.data.claim });
  return NextResponse.json({ result });
}
