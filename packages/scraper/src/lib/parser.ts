import * as cheerio from 'cheerio';
import { rateLimit } from './rate-limiter.js';

const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (compatible; RegBite-Scraper/1.0; +https://regbite.com/scraper)',
  Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language': 'en-US,en;q=0.9',
};

export async function fetchHtml(url: string): Promise<{ $: cheerio.CheerioAPI; raw: string }> {
  const { hostname } = new URL(url);
  await rateLimit(hostname);

  const res = await fetch(url, { headers: HEADERS });
  if (!res.ok) throw new Error(`HTTP ${res.status} — ${url}`);
  const raw = await res.text();
  return { $: cheerio.load(raw), raw };
}

export async function fetchJson<T = unknown>(url: string): Promise<T> {
  const { hostname } = new URL(url);
  await rateLimit(hostname);

  const res = await fetch(url, {
    headers: { ...HEADERS, Accept: 'application/json' },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} — ${url}`);
  return res.json() as Promise<T>;
}

export async function fetchBuffer(url: string): Promise<Buffer> {
  const { hostname } = new URL(url);
  await rateLimit(hostname);

  const res = await fetch(url, { headers: HEADERS });
  if (!res.ok) throw new Error(`HTTP ${res.status} — ${url}`);
  return Buffer.from(await res.arrayBuffer());
}

export function cleanText(text: string | null | undefined): string {
  return (text ?? '').replace(/\s+/g, ' ').trim();
}
