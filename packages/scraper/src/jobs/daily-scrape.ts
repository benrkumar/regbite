/**
 * Daily scrape job — BullMQ worker
 *
 * Runs all FDA/NIH scrapers on a schedule:
 *   - 6 AM EST daily: DSIAL, Warning Letters, Federal Register
 *   - Weekly Sunday 2 AM EST: NDI, GRAS, NIH ODS, Import Alerts
 *
 * Start with: pnpm --filter @regbite/scraper worker
 */

import { Queue, Worker, Job } from 'bullmq';
import IORedis from 'ioredis';
import cron from 'node-cron';
import { prisma } from '@regbite/database';
import { scrapeDSIAL } from '../scrapers/fda-dsial.js';
import { scrapeWarningLetters } from '../scrapers/fda-warning-letters.js';
import { scrapeFederalRegister } from '../scrapers/federal-register.js';
import { scrapeNDI } from '../scrapers/fda-ndi.js';
import { scrapeGRAS } from '../scrapers/fda-gras.js';
import { scrapeNIHODS } from '../scrapers/nih-ods.js';
import { scrapeImportAlerts } from '../scrapers/fda-import-alerts.js';
import type { FDAScraperResult } from '../types.js';

const REDIS_URL = process.env.REDIS_URL ?? 'redis://localhost:6379';
const QUEUE_NAME = 'fda-scraper';

const connection = new IORedis(REDIS_URL, { maxRetriesPerRequest: null });

const scraperQueue = new Queue(QUEUE_NAME, { connection });

type ScraperJobData = {
  scrapers: string[];
  triggeredBy: 'cron' | 'manual';
};

const scraperMap: Record<string, () => Promise<FDAScraperResult>> = {
  dsial: scrapeDSIAL,
  'warning-letters': scrapeWarningLetters,
  'federal-register': scrapeFederalRegister,
  ndi: scrapeNDI,
  gras: scrapeGRAS,
  'nih-ods': scrapeNIHODS,
  'import-alerts': scrapeImportAlerts,
};

const worker = new Worker<ScraperJobData>(
  QUEUE_NAME,
  async (job: Job<ScraperJobData>) => {
    const { scrapers, triggeredBy } = job.data;
    console.log(`[worker] Job ${job.id} started — scrapers: ${scrapers.join(', ')} (${triggeredBy})`);

    const results: Record<string, { records: number; errors: number }> = {};

    for (const scraperName of scrapers) {
      const fn = scraperMap[scraperName];
      if (!fn) {
        console.warn(`[worker] Unknown scraper: ${scraperName}`);
        continue;
      }

      try {
        await job.updateProgress({ current: scraperName, status: 'running' });
        const result = await fn();

        results[scraperName] = {
          records: result.records.length,
          errors: result.errors.length,
        };

        if (result.errors.length) {
          console.warn(`[worker] ${scraperName} completed with ${result.errors.length} errors:`, result.errors.slice(0, 3));
        } else {
          console.log(`[worker] ${scraperName} — ${result.records.length} records`);
        }

        await job.updateProgress({ current: scraperName, status: 'done', ...results[scraperName] });
      } catch (err) {
        results[scraperName] = { records: 0, errors: 1 };
        console.error(`[worker] ${scraperName} threw:`, err);
      }
    }

    return results;
  },
  {
    connection,
    concurrency: 1,
    limiter: { max: 1, duration: 5000 },
  },
);

worker.on('completed', (job) => {
  console.log(`[worker] Job ${job.id} completed`);
});

worker.on('failed', (job, err) => {
  console.error(`[worker] Job ${job?.id} failed:`, err.message);
});

// ── Cron schedules ────────────────────────────────────────────────────────────

// Daily at 6 AM EST (11:00 UTC): fast scrapers
cron.schedule('0 11 * * *', async () => {
  console.log('[cron] Daily scrape triggered');
  await scraperQueue.add(
    'daily',
    {
      scrapers: ['dsial', 'warning-letters', 'federal-register'],
      triggeredBy: 'cron',
    },
    { attempts: 2, backoff: { type: 'exponential', delay: 60000 } },
  );
});

// Weekly Sunday at 2 AM EST (07:00 UTC): heavier scrapers
cron.schedule('0 7 * * 0', async () => {
  console.log('[cron] Weekly scrape triggered');
  await scraperQueue.add(
    'weekly',
    {
      scrapers: ['ndi', 'gras', 'nih-ods', 'import-alerts'],
      triggeredBy: 'cron',
    },
    { attempts: 2, backoff: { type: 'exponential', delay: 120000 } },
  );
});

console.log('[scraper-worker] Started — listening for jobs');
console.log('[scraper-worker] Daily schedule: 6 AM EST (dsial, warning-letters, federal-register)');
console.log('[scraper-worker] Weekly schedule: Sunday 2 AM EST (ndi, gras, nih-ods, import-alerts)');

// Manual trigger support: SCRAPER=dsial,warning-letters node daily-scrape.ts
const manualScrapers = process.env.SCRAPER?.split(',').filter(Boolean);
if (manualScrapers?.length) {
  scraperQueue
    .add('manual', { scrapers: manualScrapers, triggeredBy: 'manual' })
    .then(() => console.log(`[scraper-worker] Queued manual run: ${manualScrapers.join(', ')}`))
    .catch(console.error);
}

// Graceful shutdown
process.on('SIGINT', async () => {
  console.log('[scraper-worker] Shutting down...');
  await worker.close();
  await scraperQueue.close();
  await connection.quit();
  await prisma.$disconnect();
  process.exit(0);
});
