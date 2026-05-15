'use client';

import { useEffect } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
    if (!key || typeof window === 'undefined') return;

    const capture = (window as { posthog?: { capture: (event: string, props?: Record<string, unknown>) => void } }).posthog;
    if (capture) {
      const url = pathname + (searchParams.toString() ? `?${searchParams.toString()}` : '');
      capture.capture('$pageview', { '$current_url': url });
    }
  }, [pathname, searchParams]);

  useEffect(() => {
    const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
    if (!key || typeof window === 'undefined') return;

    (async () => {
      try {
        const posthog = await import('posthog-js').then((m) => m.default);
        if (!posthog.__loaded) {
          posthog.init(key, {
            api_host: 'https://app.posthog.com',
            capture_pageview: false,
            persistence: 'localStorage',
          });
        }
      } catch {
        // PostHog not available in this environment
      }
    })();
  }, []);

  return <>{children}</>;
}
