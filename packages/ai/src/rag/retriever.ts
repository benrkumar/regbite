/**
 * RAG retriever — pgvector cosine similarity search
 *
 * Embeds the query text and performs a nearest-neighbor search across
 * FDA regulatory documents stored in the database.
 */

import { prisma } from '@regbite/database';
import { embed } from '../embeddings.js';

export interface RetrievedDocument {
  id: string;
  title: string;
  content: string;
  source: string;
  sourceUrl: string | null;
  similarity: number;
  type: 'warning_letter' | 'ndi' | 'regulatory_change' | 'ingredient';
}

/** Search FDA Warning Letters by semantic similarity */
export async function retrieveWarningLetters(
  query: string,
  topK = 5,
): Promise<RetrievedDocument[]> {
  const queryVec = await embed(query);
  const vecStr = `[${queryVec.join(',')}]`;

  const results = await prisma.$queryRaw<
    Array<{ id: string; subject: string | null; company_name: string; letter_url: string; raw_text: string | null; similarity: number }>
  >`
    SELECT
      id,
      subject,
      company_name,
      letter_url,
      raw_text,
      1 - (embedding <=> ${vecStr}::vector) AS similarity
    FROM "FDAWarningLetter"
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> ${vecStr}::vector
    LIMIT ${topK}
  `;

  type WLRow = { id: string; subject: string | null; company_name: string; letter_url: string; raw_text: string | null; similarity: number };
  return results.map((r: WLRow) => ({
    id: r.id,
    title: r.subject ?? `Warning Letter — ${r.company_name}`,
    content: r.raw_text ?? r.subject ?? '',
    source: 'FDA_WARNING_LETTERS',
    sourceUrl: r.letter_url,
    similarity: r.similarity,
    type: 'warning_letter' as const,
  }));
}

/** Search NDI Notifications by semantic similarity */
export async function retrieveNDINotifications(
  query: string,
  topK = 5,
): Promise<RetrievedDocument[]> {
  const queryVec = await embed(query);
  const vecStr = `[${queryVec.join(',')}]`;

  const results = await prisma.$queryRaw<
    Array<{ id: string; ingredient_name: string; fda_response: string | null; raw_text: string | null; similarity: number }>
  >`
    SELECT
      id,
      ingredient_name,
      fda_response,
      raw_text,
      1 - (embedding <=> ${vecStr}::vector) AS similarity
    FROM "NDINotification"
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> ${vecStr}::vector
    LIMIT ${topK}
  `;

  type NDIRow = { id: string; ingredient_name: string; fda_response: string | null; raw_text: string | null; similarity: number };
  return results.map((r: NDIRow) => ({
    id: r.id,
    title: `NDI Notification — ${r.ingredient_name}`,
    content: r.raw_text ?? r.fda_response ?? '',
    source: 'FDA_NDI',
    sourceUrl: null,
    similarity: r.similarity,
    type: 'ndi' as const,
  }));
}

/** Search Regulatory Changes by semantic similarity */
export async function retrieveRegulatoryChanges(
  query: string,
  topK = 5,
): Promise<RetrievedDocument[]> {
  const queryVec = await embed(query);
  const vecStr = `[${queryVec.join(',')}]`;

  const results = await prisma.$queryRaw<
    Array<{ id: string; document_title: string; summary: string | null; source_url: string | null; source: string; similarity: number }>
  >`
    SELECT
      id,
      document_title,
      summary,
      source_url,
      source,
      1 - (embedding <=> ${vecStr}::vector) AS similarity
    FROM "RegulatoryChange"
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> ${vecStr}::vector
    LIMIT ${topK}
  `;

  type RegRow = { id: string; document_title: string; summary: string | null; source_url: string | null; source: string; similarity: number };
  return results.map((r: RegRow) => ({
    id: r.id,
    title: r.document_title,
    content: r.summary ?? '',
    source: r.source,
    sourceUrl: r.source_url,
    similarity: r.similarity,
    type: 'regulatory_change' as const,
  }));
}

/** Retrieve from all sources and return merged top-K results */
export async function retrieve(query: string, topK = 8): Promise<RetrievedDocument[]> {
  const perSource = Math.ceil(topK / 3);

  const [wls, ndis, regs] = await Promise.allSettled([
    retrieveWarningLetters(query, perSource),
    retrieveNDINotifications(query, perSource),
    retrieveRegulatoryChanges(query, perSource),
  ]);

  const allDocs: RetrievedDocument[] = [
    ...(wls.status === 'fulfilled' ? wls.value : []),
    ...(ndis.status === 'fulfilled' ? ndis.value : []),
    ...(regs.status === 'fulfilled' ? regs.value : []),
  ];

  return allDocs.sort((a, b) => b.similarity - a.similarity).slice(0, topK);
}
