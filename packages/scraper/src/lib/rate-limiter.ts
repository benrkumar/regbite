const lastRequestMs = new Map<string, number>();

export async function rateLimit(domain: string, intervalMs = 1200): Promise<void> {
  const last = lastRequestMs.get(domain) ?? 0;
  const wait = intervalMs - (Date.now() - last);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  lastRequestMs.set(domain, Date.now());
}
