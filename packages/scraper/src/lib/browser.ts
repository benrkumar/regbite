import { chromium, Browser, BrowserContext, Page } from 'playwright';

const SCRAPER_UA =
  'Mozilla/5.0 (compatible; RegBite-Scraper/1.0; +https://regbite.com/scraper)';

let browser: Browser | null = null;

async function getBrowser(): Promise<Browser> {
  if (!browser?.isConnected()) {
    browser = await chromium.launch({ headless: true });
  }
  return browser;
}

export async function newPage(): Promise<Page> {
  const b = await getBrowser();
  const ctx: BrowserContext = await b.newContext({
    userAgent: SCRAPER_UA,
    extraHTTPHeaders: {
      Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'Accept-Language': 'en-US,en;q=0.9',
    },
  });
  return ctx.newPage();
}

export async function closeBrowser(): Promise<void> {
  if (browser) {
    await browser.close();
    browser = null;
  }
}
