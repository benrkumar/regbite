/**
 * Weekly regulatory digest job — BullMQ worker
 *
 * Every Monday 9 AM EST (14:00 UTC): fetches last 7 days of regulatory changes,
 * groups by severity, and emails all GROWTH+ org admins.
 *
 * Start with: pnpm --filter @regbite/scraper worker:digest
 * Manual run:  DIGEST=true tsx src/jobs/weekly-digest.ts
 */

import { Queue, Worker } from 'bullmq';
import IORedis from 'ioredis';
import cron from 'node-cron';
import { prisma, PlanType } from '@regbite/database';
import { sendEmail, regulatoryDigestEmail } from '@regbite/config';

const REDIS_URL = process.env.REDIS_URL ?? 'redis://localhost:6379';
const QUEUE_NAME = 'email-digest';

const connection = new IORedis(REDIS_URL, { maxRetriesPerRequest: null });
const digestQueue = new Queue(QUEUE_NAME, { connection });

const GROWTH_PLUS_PLANS: PlanType[] = ['GROWTH', 'PROFESSIONAL', 'ENTERPRISE', 'CONSULTANT'];

const worker = new Worker(
  QUEUE_NAME,
  async (job) => {
    const weekOf = job.data?.weekOf ?? new Date().toISOString().split('T')[0];
    console.log(`[digest-worker] Job ${job.id} started — weekOf: ${weekOf}`);

    // Fetch last 7 days of regulatory changes
    const since = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
    const changes = await prisma.regulatoryChange.findMany({
      where: { createdAt: { gte: since } },
      orderBy: [{ severity: 'asc' }, { createdAt: 'desc' }],
      select: {
        id: true,
        source: true,
        documentTitle: true,
        summary: true,
        changeType: true,
        severity: true,
        createdAt: true,
      },
    });

    if (changes.length === 0) {
      console.log('[digest-worker] No changes this week — skipping email sends');
      return { sent: 0, skipped: 'no changes' };
    }

    console.log(`[digest-worker] Found ${changes.length} changes — fetching admin recipients`);

    // Fetch all active GROWTH+ org admin members
    const admins = await prisma.member.findMany({
      where: {
        deletedAt: null,
        role: { in: ['ACCOUNT_ADMIN', 'SUPER_ADMIN'] },
        organization: {
          deletedAt: null,
          plan: { in: GROWTH_PLUS_PLANS },
        },
      },
      select: {
        email: true,
        name: true,
        organization: { select: { name: true } },
      },
    });

    console.log(`[digest-worker] Sending to ${admins.length} recipients`);

    let sent = 0;
    let errors = 0;

    for (const admin of admins) {
      try {
        const digestChanges = changes.map((c) => ({
          title: c.documentTitle,
          severity: c.severity,
          source: c.source,
        }));
        const template = regulatoryDigestEmail(digestChanges, weekOf);
        await sendEmail({ ...template, to: admin.email });
        sent++;
      } catch (err) {
        errors++;
        console.error(`[digest-worker] Failed to send to ${admin.email}:`, err);
      }
    }

    console.log(`[digest-worker] Done — sent: ${sent}, errors: ${errors}`);
    return { sent, errors, changes: changes.length };
  },
  { connection, concurrency: 1 }
);

worker.on('completed', (job) => {
  console.log(`[digest-worker] Job ${job.id} completed`);
});

worker.on('failed', (job, err) => {
  console.error(`[digest-worker] Job ${job?.id} failed:`, err.message);
});

// Monday 9 AM EST (14:00 UTC)
cron.schedule('0 14 * * 1', async () => {
  const weekOf = new Date().toISOString().split('T')[0];
  console.log(`[digest-cron] Triggering weekly digest — weekOf: ${weekOf}`);
  await digestQueue.add('weekly-digest', { weekOf }, {
    attempts: 3,
    backoff: { type: 'exponential', delay: 60000 },
  });
});

console.log('[digest-worker] Started — Monday 9 AM EST cron active');

// Manual trigger
if (process.env.DIGEST === 'true') {
  const weekOf = new Date().toISOString().split('T')[0];
  digestQueue
    .add('manual-digest', { weekOf })
    .then(() => console.log(`[digest-worker] Manual digest queued — weekOf: ${weekOf}`))
    .catch(console.error);
}

process.on('SIGINT', async () => {
  console.log('[digest-worker] Shutting down...');
  await worker.close();
  await digestQueue.close();
  await connection.quit();
  await prisma.$disconnect();
  process.exit(0);
});
