/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        paper: {
          DEFAULT: "var(--bg)",
          50: "var(--surface)",
          100: "var(--surface-2)",
          200: "var(--surface-3)",
          300: "var(--surface-3)",
        },
        ink: { DEFAULT: "var(--ink)", dim: "var(--ink-dim)", faint: "var(--ink-faint)" },
        ochre: { DEFAULT: "#e8a33d", dim: "#b07d2b" },
        critical: "var(--critical)",
        high: "var(--high)",
        info: "var(--info)",
        low: "var(--low)",
        medium: "var(--medium)",
        "risk-low": "var(--low)",
        "risk-medium": "var(--medium)",
        "risk-high": "var(--high)",
        "risk-critical": "var(--critical)",
        "severity-info": "var(--info)",
        "severity-low": "var(--low)",
        "severity-medium": "var(--medium)",
        "severity-high": "var(--high)",
        "severity-critical": "var(--critical)",
      },
      fontFamily: {
        sans: ["ui-monospace", "Cascadia Code", "JetBrains Mono", "Menlo", "Consolas", "monospace"],
        mono: ["ui-monospace", "Cascadia Code", "JetBrains Mono", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
