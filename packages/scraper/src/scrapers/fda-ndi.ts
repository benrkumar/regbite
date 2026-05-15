/**
 * FDA New Dietary Ingredient (NDI) Notification Inventory scraper
 *
 * Source: https://www.fda.gov/food/new-dietary-ingredients-ndi-notification-process/
 *         inventory-effective-premarket-notifications-submitted-under-section-413-1-fdc-act
 *
 * The FDA publishes an Excel spreadsheet of all NDI notifications with
 * notification number, ingredient name, submitter, and FDA response.
 * This scraper downloads and parses that spreadsheet.
 */

import { prisma } from '@regbite/database';
import { fetchHtml, fetchBuffer, cleanText } from '../lib/parser.js';
import { hashBuffer } from '../lib/hasher.js';
import type { FDAScraperResult } from '../types.js';

const NDI_PAGE_URL =
  'https://www.fda.gov/food/new-dietary-ingredients-ndi-notification-process/inventory-effective-premarket-notifications-submitted-under-section-413-1-fdc-act';

interface NDIRecord {
  fdaNotificationNumber: string;
  ingredientName: string;
  submitter: string;
  submissionDate: string | null;
  fdaResponse: string | null;
  responseDate: string | null;
}

async function findSpreadsheetUrl(): Promise<string | null> {
  const { $ } = await fetchHtml(NDI_PAGE_URL);

  // Look for Excel/CSV download link
  let xlsxUrl: string | null = null;
  $('a[href]').each((_, el) => {
    const href = $(el).attr('href') ?? '';
    if (/\.(xlsx|xls|csv)/i.test(href) && !xlsxUrl) {
      xlsxUrl = href.startsWith('http') ? href : `https://www.fda.gov${href}`;
    }
  });

  return xlsxUrl;
}

async function parseNDISpreadsheet(buf: Buffer): Promise<NDIRecord[]> {
  const xlsxMod = await import('xlsx');
  // Handle both CJS and ESM module shapes
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const XLSX = (xlsxMod as any).default ?? xlsxMod;
  const wb = XLSX.read(buf, { type: 'buffer', cellDates: true });
  const sheetName = wb.SheetNames[0];
  const ws = wb.Sheets[sheetName];
  const rows = XLSX.utils.sheet_to_json(ws, { header: 1 }) as unknown[][];

  if (rows.length < 2) return [];

  // Find header row
  const header = (rows[0] as string[]).map((h: unknown) =>
    String(h ?? '').toLowerCase().replace(/\s+/g, '_'),
  );

  const notifCol = header.findIndex((h) => h.includes('notif') || h.includes('number'));
  const ingCol = header.findIndex((h) => h.includes('ingredient') || h.includes('substance'));
  const submitterCol = header.findIndex((h) => h.includes('submitter') || h.includes('filer'));
  const subDateCol = header.findIndex((h) => h.includes('submit') && h.includes('date'));
  const responseCol = header.findIndex((h) => h.includes('response') || h.includes('status'));
  const respDateCol = header.findIndex(
    (h) => h.includes('response') && h.includes('date'),
  );

  const records: NDIRecord[] = [];
  for (const rawRow of rows.slice(1)) {
    const row = rawRow as unknown[];
    const notifNum = cleanText(String(row[notifCol] ?? ''));
    const ingName = cleanText(String(row[ingCol] ?? ''));
    if (!notifNum && !ingName) continue;

    records.push({
      fdaNotificationNumber: notifNum || `NDI-${records.length + 1}`,
      ingredientName: ingName,
      submitter: cleanText(String(row[submitterCol] ?? '')),
      submissionDate: subDateCol >= 0 ? formatDate(row[subDateCol]) : null,
      fdaResponse: responseCol >= 0 ? cleanText(String(row[responseCol] ?? '')) : null,
      responseDate: respDateCol >= 0 ? formatDate(row[respDateCol]) : null,
    });
  }

  return records;
}

function formatDate(val: unknown): string | null {
  if (!val) return null;
  if (val instanceof Date) return val.toISOString().split('T')[0];
  const s = String(val).trim();
  if (!s || s === 'undefined') return null;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d.toISOString().split('T')[0];
}

export async function scrapeNDI(): Promise<FDAScraperResult> {
  const result: FDAScraperResult = {
    source: 'FDA_NDI',
    url: NDI_PAGE_URL,
    scrapedAt: new Date(),
    records: [],
    errors: [],
  };

  try {
    const xlsxUrl = await findSpreadsheetUrl();
    if (!xlsxUrl) {
      // Fall back to parsing the HTML table directly
      const { $ } = await fetchHtml(NDI_PAGE_URL);
      const htmlRecords: NDIRecord[] = [];

      $('table tbody tr').each((_, row) => {
        const cells = $(row).find('td');
        if (cells.length < 2) return;
        const notifNum = cleanText($(cells[0]).text());
        const ingName = cleanText($(cells[1]).text());
        if (!notifNum) return;
        htmlRecords.push({
          fdaNotificationNumber: notifNum,
          ingredientName: ingName,
          submitter: cleanText($(cells[2]).text()),
          submissionDate: cleanText($(cells[3]).text()) || null,
          fdaResponse: cleanText($(cells[4]).text()) || null,
          responseDate: cleanText($(cells[5]).text()) || null,
        });
      });

      if (htmlRecords.length === 0) {
        result.errors.push('Could not locate NDI spreadsheet or HTML table');
        return result;
      }

      await upsertNDIRecords(htmlRecords, result);
      return result;
    }

    console.log(`[NDI] Downloading spreadsheet from ${xlsxUrl}`);
    const buf = await fetchBuffer(xlsxUrl);
    const fileHash = hashBuffer(buf);

    // Skip if unchanged
    const existing = await prisma.regulatoryChange.findUnique({
      where: { documentHash: `ndi-spreadsheet:${fileHash}` },
    });
    if (existing) {
      console.log('[NDI] Spreadsheet unchanged — skipping');
      return result;
    }

    const ndis = await parseNDISpreadsheet(buf);
    console.log(`[NDI] Parsed ${ndis.length} NDI records`);

    await upsertNDIRecords(ndis, result);

    // Mark spreadsheet as processed
    await prisma.regulatoryChange.upsert({
      where: { documentHash: `ndi-spreadsheet:${fileHash}` },
      update: {},
      create: {
        source: 'FDA_CONSTITUENT_UPDATES',
        sourceUrl: xlsxUrl,
        documentTitle: 'FDA NDI Notification Inventory',
        summary: `${ndis.length} NDI notifications`,
        changeType: 'NDI_DECISION',
        severity: 'MEDIUM',
        affectedModules: ['INGREDIENT'],
        documentHash: `ndi-spreadsheet:${fileHash}`,
      },
    });
  } catch (err) {
    result.errors.push(`NDI scrape failed: ${(err as Error).message}`);
  }

  return result;
}

async function upsertNDIRecords(records: NDIRecord[], result: FDAScraperResult) {
  for (const ndi of records) {
    try {
      // Try to link to existing ingredient
      const ingredient = await prisma.uSIngredient.findFirst({
        where: {
          OR: [
            { name: { contains: ndi.ingredientName, mode: 'insensitive' } },
            { aliases: { has: ndi.ingredientName } },
          ],
        },
        select: { id: true, ndiNotificationsCount: true },
      });

      await prisma.nDINotification.upsert({
        where: { fdaNotificationNumber: ndi.fdaNotificationNumber },
        update: {
          ingredientName: ndi.ingredientName,
          submitter: ndi.submitter || null,
          submissionDate: ndi.submissionDate ? new Date(ndi.submissionDate) : null,
          fdaResponse: ndi.fdaResponse,
          responseDate: ndi.responseDate ? new Date(ndi.responseDate) : null,
          ingredientId: ingredient?.id ?? null,
          scrapedAt: new Date(),
        },
        create: {
          fdaNotificationNumber: ndi.fdaNotificationNumber,
          ingredientName: ndi.ingredientName,
          submitter: ndi.submitter || null,
          submissionDate: ndi.submissionDate ? new Date(ndi.submissionDate) : null,
          fdaResponse: ndi.fdaResponse,
          responseDate: ndi.responseDate ? new Date(ndi.responseDate) : null,
          ingredientId: ingredient?.id ?? null,
        },
      });

      // Update ndiNotificationsCount on the ingredient
      if (ingredient) {
        await prisma.uSIngredient.update({
          where: { id: ingredient.id },
          data: { ndiNotificationsCount: { increment: 1 } },
        });
      }

      result.records.push({
        fdaNotificationNumber: ndi.fdaNotificationNumber,
        ingredientName: ndi.ingredientName,
      });
    } catch (err) {
      result.errors.push(`NDI ${ndi.fdaNotificationNumber}: ${(err as Error).message}`);
    }
  }
}

if (process.argv[1]?.includes('fda-ndi')) {
  scrapeNDI()
    .then((r) =>
      console.log(`[NDI] Done — ${r.records.length} records, ${r.errors.length} errors`),
    )
    .catch(console.error)
    .finally(() => prisma.$disconnect());
}
