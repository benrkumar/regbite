import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  experimental: {
    // Ensures workspace packages are included in the standalone bundle
    outputFileTracingRoot: path.join(__dirname, "../../"),
  },
  transpilePackages: [
    "@regbite/database",
    "@regbite/compliance-engine",
    "@regbite/ui",
    "@regbite/config",
    "@regbite/ai",
  ],
};

// Wrap with Sentry if DSN is configured in production
let finalConfig = nextConfig;
try {
  if (process.env.NEXT_PUBLIC_SENTRY_DSN && process.env.NODE_ENV === 'production') {
    const { withSentryConfig } = await import('@sentry/nextjs');
    finalConfig = withSentryConfig(nextConfig, {
      silent: true,
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      widenClientFileUpload: true,
      hideSourceMaps: true,
      disableLogger: true,
    });
  }
} catch {
  // Sentry not installed — skip
}

export default finalConfig;
