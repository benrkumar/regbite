/**
 * FDA Dietary Supplement Ingredient Advisory List (DSIAL) scraper
 *
 * Source: https://www.fda.gov/food/dietary-supplement-ingredient-advisory-list/
 *         fda-dietary-supplement-ingredient-advisory-list
 *
 * The DSIAL page lists ingredients FDA has flagged as unsafe or unapproved for
 * use in dietary supplements. This scraper extracts each listed ingredient and
 * updates the USIngredient table + creates RegulatoryChange entries.
 */

import { prisma } from '@regbite/database';
import { fetchHtml, cleanText } from '../lib/parser.js';
import { hashDocument } from '../lib/hasher.js';
import type { FDAScraperResult } from '../types.js';

const DSIAL_URL =
  'https://www.fda.gov/food/dietary-supplement-ingredient-advisory-list/fda-dietary-supplement-ingredient-advisory-list';

interface DSIALEntry {
  name: string;
  reason: string;
  addedDate: string | null;
  sourceUrl: string;
}

async function parseDSIAL(): Promise<DSIALEntry[]> {
  const { $, raw: pageText } = await fetchHtml(DSIAL_URL);
  const entries: DSIALEntry[] = [];

  // FDA DSIAL page structure: ingredients are listed in accordion sections
  // (<h3> or .accordion__heading) or in a <ul>/<table> within the page body.
  // We extract all heading + paragraph pairs in the main content area.

  // Strategy 1: accordion-style items (FDA's common pattern)
  $('[data-entity-type="ingredient"], .advisory-ingredient').each((_, el) => {
    const name = cleanText($(el).find('.name, h3, h4').first().text());
    const reason = cleanText($(el).find('.description, p').first().text());
    if (name) entries.push({ name, reason, addedDate: null, sourceUrl: DSIAL_URL });
  });

  // Strategy 2: headings followed by paragraphs in main content (fallback)
  if (entries.length === 0) {
    $('#content h2, #content h3, .lcds-external-link').each((_, el) => {
      const heading = $(el);
      const name = cleanText(heading.text());
      if (!name || name.length < 3) return;
      const reason = cleanText(heading.next('p, ul').text());
      entries.push({ name, reason, addedDate: null, sourceUrl: DSIAL_URL });
    });
  }

  // Strategy 3: flat list items (some FDA pages use <li> with ingredient names)
  if (entries.length === 0) {
    $('main ul li, article ul li').each((_, el) => {
      const name = cleanText($(el).find('strong, a').first().text() || $(el).text());
      if (name && name.length > 2 && name.length < 120) {
        entries.push({ name, reason: cleanText($(el).text()), addedDate: null, sourceUrl: DSIAL_URL });
      }
    });
  }

  // If we still got nothing, capture the raw text so it can be reviewed
  if (entries.length === 0 && pageText.length > 1000) {
    console.warn('[DSIAL] Page structure changed — could not parse entries. Raw length:', pageText.length);
  }

  return entries;
}

export async function scrapeDSIAL(): Promise<FDAScraperResult> {
  const result: FDAScraperResult = {
    source: 'FDA_DSIAL',
    url: DSIAL_URL,
    scrapedAt: new Date(),
    records: [],
    errors: [],
  };

  try {
    const entries = await parseDSIAL();
    console.log(`[DSIAL] Parsed ${entries.length} entries`);

    for (const entry of entries) {
      try {
        const docHash = hashDocument(`dsial:${entry.name}`);

        // Update USIngredient if exists
        const existing = await prisma.uSIngredient.findFirst({
          where: {
            OR: [
              { name: { contains: entry.name, mode: 'insensitive' } },
              { aliases: { has: entry.name } },
            ],
          },
        });

        if (existing) {
          await prisma.uSIngredient.update({
            where: { id: existing.id },
            data: {
              fdaStatus: 'ADVISORY',
              advisoryNotes: entry.reason || existing.advisoryNotes,
              lastReviewedAt: new Date(),
            },
          });
        }

        // Create RegulatoryChange if new
        const alreadyTracked = await prisma.regulatoryChange.findUnique({
          where: { documentHash: docHash },
        });

        if (!alreadyTracked) {
          await prisma.regulatoryChange.create({
            data: {
              source: 'FDA_CONSTITUENT_UPDATES',
              sourceUrl: entry.sourceUrl,
              documentTitle: `FDA Advisory: ${entry.name}`,
              summary: entry.reason,
              changeType: 'INGREDIENT_RESTRICTION',
              severity: 'HIGH',
              affectedModules: ['INGREDIENT', 'FORMULA'],
              documentHash: docHash,
              publishedAt: entry.addedDate ? new Date(entry.addedDate) : null,
            },
          });
        }

        result.records.push({ name: entry.name, reason: entry.reason, updated: !!existing });
      } catch (err) {
        result.errors.push(`Entry "${entry.name}": ${(err as Error).message}`);
      }
    }
  } catch (err) {
    result.errors.push(`Fetch failed: ${(err as Error).message}`);
  }

  return result;
}

// Standalone runner
if (process.argv[1]?.includes('fda-dsial')) {
  scrapeDSIAL()
    .then((r) => {
      console.log(`[DSIAL] Done — ${r.records.length} records, ${r.errors.length} errors`);
      if (r.errors.length) console.error('[DSIAL] Errors:', r.errors);
    })
    .catch(console.error)
    .finally(() => prisma.$disconnect());
}
