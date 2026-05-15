import { NextResponse } from 'next/server';
import { getCGMPSections } from '@regbite/compliance-engine';

export async function GET() {
  return NextResponse.json({ sections: getCGMPSections() });
}
