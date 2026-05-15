export interface FDAScraperResult {
  source: string;
  url: string;
  scrapedAt: Date;
  records: Record<string, unknown>[];
  errors: string[];
}

export interface ScraperConfig {
  name: string;
  schedule: string;
  enabled: boolean;
}
