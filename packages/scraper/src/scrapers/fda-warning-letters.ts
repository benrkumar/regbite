/**
 * FDA Warning Letters scraper — dietary supplement companies, last 5 years
 *
 * Source: https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/
 *         compliance-actions-and-activities/warning-letters
 *
 * Uses Playwright to load the dynamic search page, filters by product type
 * "Food, Beverage & Dietary Supplements", extracts letter metadata, and
 * stores results in FDAWarningLetter.
 */

import { prisma } from '@regbite/database';
import { newPage, closeBrowser } from '../lib/browser.js';
import { hashDocument } from '../lib/hasher.js';
import { rateLimit } from '../lib/rate-limiter.js';
import type { FDAScraperResult } from '../types.js';

const BASE_URL =
  'https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters';

// FDA warning letters API endpoint (JSON feed)
const API_URL =
  'https://www.fda.gov/api/warning-letters/v1/warning-letters?issueDate=%5B2020-01-01+TO+2029-12-31%5D&productTypes=Food+Dietary+Supplements&count=100&skip=0';

interface WarningLetterRecord {
  letterId: string;
  companyName: string;
  issueDate: string;
  subject: string;
  letterUrl: string;
  ingredientsCited: string[];
  claimsCited: string[];
  violationTypes: string[];
}

async function fetchWarningLettersFromAPI(skip = 0): Promise<WarningLetterRecord[]> {
  const url = API_URL.replace('skip=0', `skip=${skip}`);
  await rateLimit('www.fda.gov');

  const res = await fetch(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (compatible; RegBite-Scraper/1.0; +https://regbite.com)',
      Accept: 'application/json',
    },
  });
  if (!res.ok) throw new Error(`FDA API HTTP ${res.status}`);

  const json = (await res.json()) as { results?: unknown[]; hits?: { hits: unknown[] } };

  // FDA API returns results in different shapes depending on the endpoint
  const items: Record<string, unknown>[] =
    (json.results as Record<string, unknown>[]) ??
    ((json.hits?.hits as Record<string, unknown>[]) ?? []);

  return items.map((item) => ({
    letterId:
      String(item['letter-id'] ?? item.letterid ?? item.id ?? '').trim() ||
      hashDocument(JSON.stringify(item)).slice(0, 12),
    companyName: String(item['company-name'] ?? item.companyName ?? item.company ?? ''),
    issueDate: String(item['issue-date'] ?? item.issueDate ?? item.date ?? '2020-01-01'),
    subject: String(item.subject ?? item.Subject ?? ''),
    letterUrl: `https://www.fda.gov${String(item.url ?? item.URL ?? '')}`,
    ingredientsCited: [],
    claimsCited: [],
    violationTypes: extractViolationTypes(String(item.subject ?? '')),
  }));
}

async function fetchWarningLettersPlaywright(): Promise<WarningLetterRecord[]> {
  const page = await newPage();
  const records: WarningLetterRecord[] = [];

  try {
    await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });

    // Try to find a "filter by product type" or search form
    const rows = await page
      .locator('table tr, .warning-letter-row, [data-entity-type="warning-letter"]')
      .all();

    for (const row of rows.slice(0, 50)) {
      const cells = await row.locator('td').all();
      if (cells.length < 3) continue;

      const letterUrl = await cells[0].locator('a').getAttribute('href').catch(() => '');
      const companyName = await cells[0].locator('a').textContent().catch(() => '');
      const issueDateText = await cells[1].textContent().catch(() => '');
      const subject = await cells[2].textContent().catch(() => '');

      if (!companyName) continue;

      records.push({
        letterId: hashDocument(`wl:${companyName}:${issueDateText}`).slice(0, 12),
        companyName: companyName.trim(),
        issueDate: issueDateText.trim(),
        subject: subject.trim(),
        letterUrl: letterUrl?.startsWith('http')
          ? letterUrl
          : `https://www.fda.gov${letterUrl ?? ''}`,
        ingredientsCited: [],
        claimsCited: [],
        violationTypes: extractViolationTypes(subject ?? ''),
      });
    }
  } finally {
    await page.context().close();
  }

  return records;
}

function extractViolationTypes(subject: string): string[] {
  const types: string[] = [];
  const s = subject.toLowerCase();
  if (s.includes('adulterat')) types.push('ADULTERATION');
  if (s.includes('misbranded') || s.includes('label')) types.push('MISBRANDING');
  if (s.includes('drug claim') || s.includes('disease claim')) types.push('DISEASE_CLAIM');
  if (s.includes('cgmp') || s.includes('good manufactur')) types.push('CGMP_VIOLATION');
  if (s.includes('ndi') || s.includes('new dietary ingredient')) types.push('NDI_VIOLATION');
  if (s.includes('unapproved') || s.includes('illegal ingredient')) types.push('UNAPPROVED_INGREDIENT');
  return types.length ? types : ['OTHER'];
}

export async function scrapeWarningLetters(): Promise<FDAScraperResult> {
  const result: FDAScraperResult = {
    source: 'FDA_WARNING_LETTERS',
    url: BASE_URL,
    scrapedAt: new Date(),
    records: [],
    errors: [],
  };

  let records: WarningLetterRecord[] = [];

  try {
    records = await fetchWarningLettersFromAPI();
    if (records.length === 0) {
      records = await fetchWarningLettersPlaywright();
    }
    console.log(`[WL] Fetched ${records.length} warning letters`);
  } catch (err) {
    result.errors.push(`Fetch failed: ${(err as Error).message}`);
    return result;
  }

  for (const rec of records) {
    try {
      const docHash = hashDocument(`wl:${rec.letterId}`);

      await prisma.fDAWarningLetter.upsert({
        where: { letterId: rec.letterId },
        update: {
          companyName: rec.companyName,
          subject: rec.subject,
          ingredientsCited: rec.ingredientsCited,
          claimsCited: rec.claimsCited,
          violationTypes: rec.violationTypes,
          letterUrl: rec.letterUrl,
          scrapedAt: new Date(),
        },
        create: {
          letterId: rec.letterId,
          companyName: rec.companyName,
          issueDate: new Date(rec.issueDate),
          subject: rec.subject,
          ingredientsCited: rec.ingredientsCited,
          claimsCited: rec.claimsCited,
          violationTypes: rec.violationTypes,
          letterUrl: rec.letterUrl,
        },
      });

      // Track as regulatory change if new
      const exists = await prisma.regulatoryChange.findUnique({ where: { documentHash: docHash } });
      if (!exists) {
        await prisma.regulatoryChange.create({
          data: {
            source: 'FDA_WARNING_LETTERS',
            sourceUrl: rec.letterUrl,
            documentTitle: `Warning Letter: ${rec.companyName}`,
            summary: rec.subject,
            changeType: 'CLAIMS_ENFORCEMENT',
            severity: 'HIGH',
            affectedModules: ['CLAIMS', 'LABEL'],
            documentHash: docHash,
            publishedAt: new Date(rec.issueDate),
          },
        });
      }

      result.records.push({ letterId: rec.letterId, company: rec.companyName });
    } catch (err) {
      result.errors.push(`Letter ${rec.letterId}: ${(err as Error).message}`);
    }
  }

  await closeBrowser();
  return result;
}

if (process.argv[1]?.includes('fda-warning-letters')) {
  scrapeWarningLetters()
    .then((r) =>
      console.log(`[WL] Done — ${r.records.length} records, ${r.errors.length} errors`),
    )
    .catch(console.error)
    .finally(() => prisma.$disconnect());
}
