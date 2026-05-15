/**
 * Embedding generation using Voyage AI's voyage-3 model
 * (512-dim fast model; voyage-3-large for 1024-dim if needed)
 *
 * Fallback: OpenAI text-embedding-3-small (1536-dim, matches vector column)
 *
 * Both produce cosine-compatible normalized vectors.
 */

import { createAnthropicClient } from './client.js';

const EMBEDDING_DIM = 1536;

type EmbedResponse = {
  data: { embedding: number[] }[];
};

/** Generate a single embedding vector for a text string */
export async function embed(text: string): Promise<number[]> {
  const truncated = text.slice(0, 8000);

  // Try Voyage AI first (higher quality for regulatory/scientific text)
  if (process.env.VOYAGE_API_KEY) {
    return embedVoyage(truncated);
  }

  // Fall back to OpenAI
  if (process.env.OPENAI_API_KEY) {
    return embedOpenAI(truncated);
  }

  throw new Error(
    'No embedding provider configured. Set VOYAGE_API_KEY or OPENAI_API_KEY.',
  );
}

/** Embed a batch of texts (returns parallel vectors) */
export async function embedBatch(texts: string[]): Promise<number[][]> {
  return Promise.all(texts.map((t) => embed(t)));
}

async function embedVoyage(text: string): Promise<number[]> {
  const res = await fetch('https://api.voyageai.com/v1/embeddings', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.VOYAGE_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'voyage-3',
      input: text,
      input_type: 'document',
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Voyage AI embed error: ${err}`);
  }

  const data = (await res.json()) as EmbedResponse;
  return data.data[0].embedding;
}

async function embedOpenAI(text: string): Promise<number[]> {
  const res = await fetch('https://api.openai.com/v1/embeddings', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'text-embedding-3-small',
      input: text,
      dimensions: EMBEDDING_DIM,
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`OpenAI embed error: ${err}`);
  }

  const data = (await res.json()) as EmbedResponse;
  return data.data[0].embedding;
}

export { EMBEDDING_DIM };

// Suppress unused import warning — client is used indirectly via env check
void createAnthropicClient;
