import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: "#0a0a10",
          secondary: "#13131f",
          tertiary: "#1a1a2e",
          card: "#16162a",
          hover: "#1e1e35",
        },
        border: {
          DEFAULT: "#2a2a45",
          light: "#3a3a5c",
        },
        accent: {
          DEFAULT: "#6366f1",
          hover: "#4f46e5",
          light: "#818cf8",
          dim: "#312e81",
        },
        text: {
          primary: "#e2e8f0",
          secondary: "#94a3b8",
          muted: "#64748b",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      animation: {
        "spin-slow": "spin 2s linear infinite",
        "fade-in": "fadeIn 0.2s ease-out",
        "slide-up": "slideUp 0.3s ease-out",
        blink: "blink 1s step-end infinite",
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        slideUp: {
          from: { transform: "translateY(8px)", opacity: "0" },
          to: { transform: "translateY(0)", opacity: "1" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
      },
      typography: {
        DEFAULT: {
          css: {
            color: "#e2e8f0",
            a: { color: "#818cf8" },
            code: {
              color: "#c4b5fd",
              backgroundColor: "#1e1e35",
              padding: "2px 4px",
              borderRadius: "4px",
              fontWeight: "normal",
            },
            "code::before": { content: '""' },
            "code::after": { content: '""' },
            blockquote: {
              color: "#94a3b8",
              borderLeftColor: "#6366f1",
            },
            h1: { color: "#f1f5f9" },
            h2: { color: "#f1f5f9" },
            h3: { color: "#f1f5f9" },
            strong: { color: "#f1f5f9" },
          },
        },
      },
    },
  },
  plugins: [],
};

export default config;
