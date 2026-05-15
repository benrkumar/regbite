import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
    "../../packages/ui/src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          600: '#0D4F3C',
          700: '#0A3D2E',
        },
        accent: '#22C55E',
        negative: '#EF4444',
        surface: '#F8FAFB',
      },
    },
  },
  plugins: [],
};

export default config;
