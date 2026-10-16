import type { Config } from "tailwindcss";

/**
 * Enterprise console theme.
 *
 * One tinted neutral ramp, one iris accent, and three semantic colours reserved
 * for the risk bands so that colour in this product always means something.
 * Status colour is never decorative.
 *
 * The small end of the type scale is deliberately larger than Tailwind's
 * default: this console is dense, but 11px body text was not legible enough for
 * all-day use, so `2xs`/`xs` are re-stepped to 12px/13px and every existing
 * `text-xs` in the product moves up with them.
 */
const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "1.5rem", screens: { "2xl": "1560px" } },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        surface: "hsl(var(--surface))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        popover: { DEFAULT: "hsl(var(--popover))", foreground: "hsl(var(--popover-foreground))" },
        sidebar: {
          DEFAULT: "hsl(var(--sidebar))",
          foreground: "hsl(var(--sidebar-foreground))",
          muted: "hsl(var(--sidebar-muted))",
          active: "hsl(var(--sidebar-active))",
        },
        risk: {
          low: "hsl(var(--risk-low))",
          review: "hsl(var(--risk-review))",
          high: "hsl(var(--risk-high))",
        },
      },
      spacing: {
        /* Header height and the mobile nav drawer width: both sit between
           Tailwind's default steps. */
        15: "3.75rem",
        68: "17rem",
      },
      borderRadius: {
        "2xl": "calc(var(--radius) + 6px)",
        xl: "var(--radius)",
        lg: "calc(var(--radius) - 2px)",
        md: "calc(var(--radius) - 4px)",
        sm: "calc(var(--radius) - 6px)",
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "2xs": ["0.75rem", { lineHeight: "1.0625rem", letterSpacing: "0.002em" }],
        xs: ["0.8125rem", { lineHeight: "1.1875rem" }],
        sm: ["0.875rem", { lineHeight: "1.3125rem" }],
        base: ["0.9375rem", { lineHeight: "1.4375rem" }],
        lg: ["1.0625rem", { lineHeight: "1.5rem", letterSpacing: "-0.011em" }],
        xl: ["1.25rem", { lineHeight: "1.6875rem", letterSpacing: "-0.015em" }],
        "2xl": ["1.5rem", { lineHeight: "1.9375rem", letterSpacing: "-0.019em" }],
        "3xl": ["1.875rem", { lineHeight: "2.25rem", letterSpacing: "-0.021em" }],
      },
      boxShadow: {
        /* Two-layer shadows: a tight contact edge plus a soft lift, both tinted
           with the neutral ramp's hue so cards never look grey-on-colour. */
        card: "0 1px 2px -1px hsl(var(--shadow-color) / 0.10), 0 1px 3px 0 hsl(var(--shadow-color) / 0.06)",
        raised:
          "0 1px 2px -1px hsl(var(--shadow-color) / 0.12), 0 4px 12px -2px hsl(var(--shadow-color) / 0.10)",
        overlay:
          "0 2px 4px -2px hsl(var(--shadow-color) / 0.16), 0 16px 40px -8px hsl(var(--shadow-color) / 0.22)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "fade-in": "fade-in 0.18s ease-out",
        "slide-up": "slide-up 0.2s ease-out",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
