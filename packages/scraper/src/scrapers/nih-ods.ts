/**
 * NIH Office of Dietary Supplements (ODS) fact sheet scraper
 *
 * Source: https://ods.od.nih.gov/factsheets/list-all/
 *
 * ODS publishes health professional fact sheets for each dietary supplement
 * ingredient — including upper intake levels, safety notes, and drug interactions.
 * This scraper indexes the fact sheet list and enriches USIngredient records.
 */

import { prisma } from '@regbite/database';
import { fetchHtml, cleanText } from '../lib/parser.js';
import type { FDAScraperResult } from '../types.js';

const ODS_INDEX_URL = 'https://ods.od.nih.gov/factsheets/list-all/';
const ODS_BASE = 'https://ods.od.nih.gov';

interface ODSFactSheet {
  ingredientName: string;
  url: string;
  upperIntakeLevel: string | null;
  safetyNotes: string | null;
  regulatoryCitations: string[];
}

async function fetchFactSheetIndex(): Promise<{ name: string; url: string }[]> {
  const { $ } = await fetchHtml(ODS_INDEX_URL);
  const sheets: { name: string; url: string }[] = [];

  // ODS index: links to individual fact sheets
  $('a[href*="/factsheets/"]').each((_, el) => {
    const href = $(el).attr('href') ?? '';
    const name = cleanText($(el).text());
    if (!name || href.includes('list-') || href.includes('mailto')) return;
    sheets.push({
      name,
      url: href.startsWith('http') ? href : `${ODS_BASE}${href}`,
    });
  });

  // Deduplicate by URL
  const seen = new Set<string>();
  return sheets.filter(({ url }) => {
    if (seen.has(url)) return false;
    seen.add(url);
    return true;
  });
}

async function parseFactSheet(url: string): Promise<Partial<ODSFactSheet>> {
  const { $ } = await fetchHtml(url);

  // Extract Upper Tolerable Intake Level (UL) — typically in a table or under
  // "Safety" or "Tolerable Upper Intake Levels" section heading
  let upperIntakeLevel: string | null = null;
  let safetyNotes: string | null = null;
  const citations: string[] = [];

  // Strategy: find text near "tolerable upper intake" or "upper limit"
  $('h2, h3, h4').each((_, heading) => {
    const headText = $(heading).text().toLowerCase();
    if (headText.includes('upper intake') || headText.includes('tolerable') || headText.includes('upper limit')) {
      const next = $(heading).nextAll('p, table, ul').first();
      upperIntakeLevel = cleanText(next.text()).slice(0, 300);
    }
    if (headText.includes('health risks') || headText.includes('safety')) {
      const next = $(heading).nextAll('p').first();
      safetyNotes = cleanText(next.text()).slice(0, 500);
    }
  });

  // Extract CFR citations
  $('a[href], p').each((_, el) => {
    const text = $(el).text();
    const match = text.match(/\d+\s+C\.?F\.?R\.?\s+\S+/g);
    if (match) citations.push(...match);
  });

  return { upperIntakeLevel, safetyNotes, regulatoryCitations: [...new Set(citations)] };
}

export async function scrapeNIHODS(): Promise<FDAScraperResult> {
  const result: FDAScraperResult = {
    source: 'NIH_ODS',
    url: ODS_INDEX_URL,
    scrapedAt: new Date(),
    records: [],
    errors: [],
  };

  try {
    const factSheets = await fetchFactSheetIndex();
    console.log(`[ODS] Found ${factSheets.length} fact sheets`);

    // Only fetch fact sheets for ingredients that exist in our DB
    const dbIngredients = await prisma.uSIngredient.findMany({
      select: { id: true, name: true, aliases: true },
    });

    const ingredientMap = new Map<string, string>();
    for (const ing of dbIngredients) {
      ingredientMap.set(ing.name.toLowerCase(), ing.id);
      for (const alias of ing.aliases) {
        ingredientMap.set(alias.toLowerCase(), ing.id);
      }
    }

    for (const sheet of factSheets) {
      // Find matching ingredient by name
      const normalizedName = sheet.name.toLowerCase().replace(/[^a-z0-9 ]/g, '').trim();
      let ingredientId: string | undefined;

      for (const [key, id] of ingredientMap) {
        if (key.includes(normalizedName) || normalizedName.includes(key)) {
          ingredientId = id;
          break;
        }
      }

      if (!ingredientId) continue; // Skip fact sheets without a matching ingredient

      try {
        const data = await parseFactSheet(sheet.url);

        const updates: Record<string, unknown> = { lastReviewedAt: new Date() };
        if (data.upperIntakeLevel) updates.upperIntakeLevel = data.upperIntakeLevel;
        if (data.safetyNotes) {
          updates.advisoryNotes = data.safetyNotes;
        }
        if (data.regulatoryCitations?.length) {
          const existing = await prisma.uSIngredient.findUnique({
            where: { id: ingredientId },
            select: { regulatoryCitations: true },
          });
          const existingCitations = (existing?.regulatoryCitations as string[]) ?? [];
          const merged = [...new Set([...existingCitations, ...data.regulatoryCitations])];
          updates.regulatoryCitations = merged;
        }

        await prisma.uSIngredient.update({
          where: { id: ingredientId },
          data: updates,
        });

        result.records.push({ ingredient: sheet.name, url: sheet.url });
      } catch (err) {
        result.errors.push(`Fact sheet "${sheet.name}": ${(err as Error).message}`);
      }
    }
  } catch (err) {
    result.errors.push(`ODS scrape failed: ${(err as Error).message}`);
  }

  return result;
}

if (process.argv[1]?.includes('nih-ods')) {
  scrapeNIHODS()
    .then((r) =>
      console.log(`[ODS] Done — ${r.records.length} records, ${r.errors.length} errors`),
    )
    .catch(console.error)
    .finally(() => prisma.$disconnect());
}
