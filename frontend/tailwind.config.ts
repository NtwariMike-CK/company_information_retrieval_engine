import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#04060b", 900: "#070b14", 850: "#0a101c", 800: "#0e1626", 700: "#16223a", 600: "#22304f", 500: "#334468" },
        brand: { 300: "#93c5fd", 400: "#60a5fa", 500: "#3b82f6", 600: "#2563eb", 700: "#1d4ed8" },
      },
      fontFamily: { sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"], mono: ["var(--font-geist-mono)", "monospace"] },
      boxShadow: { glow: "0 0 0 1px rgba(59,130,246,.35), 0 8px 30px -8px rgba(37,99,235,.45)" },
    },
  },
  plugins: [],
};
export default config;
