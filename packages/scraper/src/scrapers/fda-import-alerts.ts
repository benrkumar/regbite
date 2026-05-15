/**
 * FDA Import Alerts scraper — dietary supplement-related detentions
 *
 * Source: https://www.accessdata.fda.gov/cms_ia/importalert_31.html  (IA 54-06)
 *         https://www.accessdata.fda.gov/cms_ia/importalert_32.html  (IA 66-71)
 *
 * Import Alerts enable FDA to detain shipments at the border without physical
 * examination. This scraper extracts the Red List (detained firms/products)
 * for supplement-related alerts and stores them as RegulatoryChange entries.
 */

import { prisma } from '@regbite/database';
import { fetchHtml, cleanText } from '../lib/parser.js';
import { hashDocument } from '../lib/hasher.js';
import type { FDAScraperResult } from '../types.js';

// Key dietary supplement Import Alerts:
// IA 54-06: Unapproved / misbranded dietary supplements
// IA 66-71: Articles promoted for weight loss / body building with undisclosed drugs
const IMPORT_ALERT_URLS = [
  'https://www.accessdata.fda.gov/cms_ia/importalert_31.html',
  'https://www.accessdata.fda.gov/cms_ia/importalert_32.html',
];

interface ImportAlertEntry {
  alertId: string;
  companyName: string;
  productName: string | null;
  country: string | null;
  reason: string | null;
  sourceUrl: string;
}

async function parseImportAlertPage(url: string): Promise<ImportAlertEntry[]> {
  const { $ } = await fetchHtml(url);
  const entries: ImportAlertEntry[] = [];

  // Import alert pages use tables with company/product/country/reason columns
  $('table tbody tr, table tr').each((rowIdx, row) => {
    if (rowIdx === 0) return; // skip header
    const cells = $(row).find('td');
    if (cells.length < 2) return;

    const companyName = cleanText($(cells[0]).text());
    if (!companyName || companyName.toLowerCase() === 'firm name') return;

    entries.push({
      alertId: hashDocument(`ia:${url}:${rowIdx}`).slice(0, 12),
      companyName,
      productName: cells.length > 1 ? cleanText($(cells[1]).text()) || null : null,
      country: cells.length > 2 ? cleanText($(cells[2]).text()) || null : null,
      reason: cells.length > 3 ? cleanText($(cells[3]).text()) || null : null,
      sourceUrl: url,
    });
  });

  return entries;
}

export async function scrapeImportAlerts(): Promise<FDAScraperResult> {
  const result: FDAScraperResult = {
    source: 'FDA_IMPORT_ALERTS',
    url: IMPORT_ALERT_URLS[0],
    scrapedAt: new Date(),
    records: [],
    errors: [],
  };

  for (const alertUrl of IMPORT_ALERT_URLS) {
    try {
      const entries = await parseImportAlertPage(alertUrl);
      console.log(`[IA] ${alertUrl.split('/').pop()}: ${entries.length} entries`);

      for (const entry of entries) {
        try {
          const docHash = hashDocument(`import-alert:${entry.alertId}:${entry.companyName}`);
          const exists = await prisma.regulatoryChange.findUnique({ where: { documentHash: docHash } });
          if (exists) continue;

          await prisma.regulatoryChange.create({
            data: {
              source: 'FDA_IMPORT_ALERTS',
              sourceUrl: entry.sourceUrl,
              documentTitle: `Import Alert — ${entry.companyName}${entry.productName ? `: ${entry.productName}` : ''}`,
              summary: entry.reason,
              changeType: 'INGREDIENT_RESTRICTION',
              severity: 'HIGH',
              affectedModules: ['INGREDIENT', 'FORMULA'],
              documentHash: docHash,
            },
          });

          result.records.push({
            company: entry.companyName,
            product: entry.productName,
            country: entry.country,
          });
        } catch (err) {
          result.errors.push(`Entry "${entry.companyName}": ${(err as Error).message}`);
        }
      }
    } catch (err) {
      result.errors.push(`Alert page ${alertUrl}: ${(err as Error).message}`);
    }
  }

  return result;
}

if (process.argv[1]?.includes('fda-import-alerts')) {
  scrapeImportAlerts()
    .then((r) =>
      console.log(`[IA] Done — ${r.records.length} records, ${r.errors.length} errors`),
    )
    .catch(console.error)
    .finally(() => prisma.$disconnect());
}
