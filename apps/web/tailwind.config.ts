import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#070b12",
        panel: "#0f1623",
        panel2: "#131c2c",
        line: "#223047",
        mut: "#8aa0bd",
        acc: "#6aa6ff",
        ok: "#39d98a",
        warn: "#ffcc66",
        bad: "#ff6b6b",
      },
      fontFamily: { mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"] },
    },
  },
  plugins: [],
};
export default config;
