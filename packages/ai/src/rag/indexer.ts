/**
 * RAG indexer — embeds regulatory documents and stores vectors in pgvector
 *
 * Run after scraping to build/refresh the embedding index.
 * Text is chunked to 512 tokens max before embedding.
 */

import { prisma } from '@regbite/database';
import { embed } from '../embeddings.js';

const CHUNK_SIZE = 2000; // ~512 tokens at ~4 chars/token

function chunk(text: string): string[] {
  if (text.length <= CHUNK_SIZE) return [text];
  const chunks: string[] = [];
  for (let i = 0; i < text.length; i += CHUNK_SIZE) {
    chunks.push(text.slice(i, i + CHUNK_SIZE));
  }
  return chunks;
}

/** Index all warning letters that don't yet have embeddings */
export async function indexWarningLetters(): Promise<{ indexed: number; errors: number }> {
  const unindexed = await prisma.fDAWarningLetter.findMany({
    where: { embedding: null, rawText: { not: null } } as never,
    select: { id: true, rawText: true, subject: true, companyName: true },
    take: 100,
  });

  let indexed = 0;
  let errors = 0;

  for (const wl of unindexed) {
    try {
      const text = wl.rawText ?? `${wl.companyName}: ${wl.subject}`;
      const chunks = chunk(text);
      // Use the first chunk's embedding as the document-level embedding
      const vec = await embed(chunks[0]);
      const vecStr = `[${vec.join(',')}]`;

      await prisma.$executeRaw`
        UPDATE "FDAWarningLetter"
        SET embedding = ${vecStr}::vector
        WHERE id = ${wl.id}
      `;
      indexed++;
    } catch {
      errors++;
    }
  }

  return { indexed, errors };
}

/** Index NDI notifications that don't yet have embeddings */
export async function indexNDINotifications(): Promise<{ indexed: number; errors: number }> {
  const unindexed = await prisma.nDINotification.findMany({
    where: { embedding: null } as never,
    select: { id: true, ingredientName: true, fdaResponse: true, rawText: true },
    take: 200,
  });

  let indexed = 0;
  let errors = 0;

  for (const ndi of unindexed) {
    try {
      const text =
        ndi.rawText ??
        [ndi.ingredientName, ndi.fdaResponse].filter(Boolean).join(' — ');
      const vec = await embed(text);
      const vecStr = `[${vec.join(',')}]`;

      await prisma.$executeRaw`
        UPDATE "NDINotification"
        SET embedding = ${vecStr}::vector
        WHERE id = ${ndi.id}
      `;
      indexed++;
    } catch {
      errors++;
    }
  }

  return { indexed, errors };
}

/** Index regulatory changes that don't yet have embeddings */
export async function indexRegulatoryChanges(): Promise<{ indexed: number; errors: number }> {
  const unindexed = await prisma.regulatoryChange.findMany({
    where: { embedding: null } as never,
    select: { id: true, documentTitle: true, summary: true },
    take: 200,
  });

  let indexed = 0;
  let errors = 0;

  for (const rc of unindexed) {
    try {
      const text = [rc.documentTitle, rc.summary].filter(Boolean).join('. ');
      const vec = await embed(text);
      const vecStr = `[${vec.join(',')}]`;

      await prisma.$executeRaw`
        UPDATE "RegulatoryChange"
        SET embedding = ${vecStr}::vector
        WHERE id = ${rc.id}
      `;
      indexed++;
    } catch {
      errors++;
    }
  }

  return { indexed, errors };
}

/** Run a full index pass over all document types */
export async function indexAll(): Promise<void> {
  console.log('[indexer] Starting full RAG index pass...');

  const wl = await indexWarningLetters();
  console.log(`[indexer] Warning letters: ${wl.indexed} indexed, ${wl.errors} errors`);

  const ndi = await indexNDINotifications();
  console.log(`[indexer] NDI notifications: ${ndi.indexed} indexed, ${ndi.errors} errors`);

  const rc = await indexRegulatoryChanges();
  console.log(`[indexer] Regulatory changes: ${rc.indexed} indexed, ${rc.errors} errors`);

  console.log('[indexer] Done.');
}

if (process.argv[1]?.includes('indexer')) {
  indexAll()
    .catch(console.error)
    .finally(() => prisma.$disconnect());
}
