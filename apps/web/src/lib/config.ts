/** Resolved app URL — set NEXT_PUBLIC_APP_URL in Railway env for each environment. */
export const APP_URL =
  process.env.NEXT_PUBLIC_APP_URL ?? "https://regbite-production.up.railway.app";
