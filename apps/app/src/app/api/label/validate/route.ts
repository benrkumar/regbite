import { NextRequest, NextResponse } from 'next/server';
import { validateLabel } from '@regbite/compliance-engine';
import { z } from 'zod';

const nutrientSchema = z.object({
  name: z.string(),
  amount: z.number(),
  unit: z.string(),
  dvPercent: z.number().nullable().optional(),
});

const schema = z.object({
  servingSize: z.string().optional(),
  servingsPerContainer: z.union([z.string(), z.number()]).optional(),
  nutrients: z.array(nutrientSchema).optional(),
  proprietaryBlend: z.object({
    name: z.string(),
    totalAmount: z.number(),
    unit: z.string(),
    ingredients: z.array(z.string()),
  }).optional(),
  otherIngredients: z.array(z.string()).optional(),
  allergens: z.array(z.string()).optional(),
  netQuantity: z.string().optional(),
  identityStatement: z.string().optional(),
  manufacturerInfo: z.string().optional(),
  lotCode: z.string().nullable().optional(),
  hasExpirationDate: z.boolean().optional(),
});

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null);
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  const result = await validateLabel(parsed.data);
  return NextResponse.json({ result });
}
