/**
 * FDA GRAS Notices scraper
 *
 * Source: https://www.cfsanappsexternal.fda.gov/scripts/fdcc/index.cfm?set=GRASNotices
 *
 * FDA's GRAS Notice Inventory lists all submitted GRAS notices with FDA's
 * response (No questions / Letter / Cease to evaluate). Populates GRASNotice.
 */

import { prisma } from '@regbite/database';
import { fetchHtml, cleanText } from '../lib/parser.js';
import { hashDocument } from '../lib/hasher.js';
import type { FDAScraperResult } from '../types.js';

const GRAS_URL =
  'https://www.cfsanappsexternal.fda.gov/scripts/fdcc/index.cfm?set=GRASNotices&sortField=GRN_No&lastSortField=GRN_No&sortDirection=DESC';

interface GRASRecord {
  grn: string;
  substance: string;
  intendedUse: string | null;
  notifier: string | null;
  fdaResponse: string | null;
  notificationDate: string | null;
  responseDate: string | null;
  sourceUrl: string;
}

async function parseGRASTable(): Promise<GRASRecord[]> {
  const { $ } = await fetchHtml(GRAS_URL);
  const records: GRASRecord[] = [];

  $('table tbody tr').each((_, row) => {
    const cells = $(row).find('td');
    if (cells.length < 4) return;

    const grnText = cleanText($(cells[0]).text());
    const substance = cleanText($(cells[1]).text());
    if (!grnText || !substance) return;

    const grn = grnText.startsWith('GRN') ? grnText : `GRN ${grnText}`;
    const href = $(cells[0]).find('a').attr('href') ?? '';
    const sourceUrl = href.startsWith('http')
      ? href
      : href
        ? `https://www.cfsanappsexternal.fda.gov${href}`
        : GRAS_URL;

    records.push({
      grn,
      substance,
      intendedUse: cells.length > 2 ? cleanText($(cells[2]).text()) || null : null,
      notifier: cells.length > 3 ? cleanText($(cells[3]).text()) || null : null,
      fdaResponse: cells.length > 4 ? cleanText($(cells[4]).text()) || null : null,
      notificationDate: cells.length > 5 ? cleanText($(cells[5]).text()) || null : null,
      responseDate: cells.length > 6 ? cleanText($(cells[6]).text()) || null : null,
      sourceUrl,
    });
  });

  return records;
}

export async function scrapeGRAS(): Promise<FDAScraperResult> {
  const result: FDAScraperResult = {
    source: 'FDA_GRAS',
    url: GRAS_URL,
    scrapedAt: new Date(),
    records: [],
    errors: [],
  };

  try {
    const notices = await parseGRASTable();
    console.log(`[GRAS] Parsed ${notices.length} GRAS notices`);

    for (const notice of notices) {
      try {
        await prisma.gRASNotice.upsert({
          where: { grn: notice.grn },
          update: {
            substance: notice.substance,
            intendedUse: notice.intendedUse,
            notifier: notice.notifier,
            fdaResponse: notice.fdaResponse,
            notificationDate: notice.notificationDate ? new Date(notice.notificationDate) : null,
            responseDate: notice.responseDate ? new Date(notice.responseDate) : null,
            sourceUrl: notice.sourceUrl,
            scrapedAt: new Date(),
          },
          create: {
            grn: notice.grn,
            substance: notice.substance,
            intendedUse: notice.intendedUse,
            notifier: notice.notifier,
            fdaResponse: notice.fdaResponse,
            notificationDate: notice.notificationDate ? new Date(notice.notificationDate) : null,
            responseDate: notice.responseDate ? new Date(notice.responseDate) : null,
            sourceUrl: notice.sourceUrl,
          },
        });

        // Update ingredient GRAS status if response is "No questions"
        if (notice.fdaResponse?.toLowerCase().includes('no question')) {
          const ingredient = await prisma.uSIngredient.findFirst({
            where: { name: { contains: notice.substance, mode: 'insensitive' } },
          });
          if (ingredient && ingredient.grasStatus !== 'FDA_AFFIRMED') {
            await prisma.uSIngredient.update({
              where: { id: ingredient.id },
              data: { grasStatus: 'SELF_AFFIRMED' },
            });
          }
        }

        const docHash = hashDocument(`gras:${notice.grn}`);
        const exists = await prisma.regulatoryChange.findUnique({ where: { documentHash: docHash } });
        if (!exists) {
          await prisma.regulatoryChange.create({
            data: {
              source: 'FDA_CONSTITUENT_UPDATES',
              sourceUrl: notice.sourceUrl,
              documentTitle: `GRAS Notice ${notice.grn}: ${notice.substance}`,
              summary: notice.fdaResponse,
              changeType: 'INGREDIENT_RESTRICTION',
              severity: 'LOW',
              affectedModules: ['INGREDIENT'],
              documentHash: docHash,
              publishedAt: notice.notificationDate ? new Date(notice.notificationDate) : null,
            },
          });
        }

        result.records.push({ grn: notice.grn, substance: notice.substance });
      } catch (err) {
        result.errors.push(`GRAS ${notice.grn}: ${(err as Error).message}`);
      }
    }
  } catch (err) {
    result.errors.push(`GRAS scrape failed: ${(err as Error).message}`);
  }

  return result;
}

if (process.argv[1]?.includes('fda-gras')) {
  scrapeGRAS()
    .then((r) =>
      console.log(`[GRAS] Done — ${r.records.length} records, ${r.errors.length} errors`),
    )
    .catch(console.error)
    .finally(() => prisma.$disconnect());
}
