import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Extended color palette
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        // Secondary brand accent (Claude blue) — links, info, "viewing X" banner.
        info: {
          DEFAULT: "hsl(var(--info))",
          foreground: "hsl(var(--info-foreground))",
        },
        // Run/status semantics — meaning, never decoration.
        status: {
          pass: "hsl(var(--status-pass))",
          fail: "hsl(var(--status-fail))",
          warn: "hsl(var(--status-warn))",
          running: "hsl(var(--status-running))",
        },
        // Surface hierarchy
        surface: {
          0: "hsl(var(--surface-0))",
          1: "hsl(var(--surface-1))",
          2: "hsl(var(--surface-2))",
          3: "hsl(var(--surface-3))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "monospace"],
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "0.875rem" }],
      },
      spacing: {
        "18": "4.5rem",
        "88": "22rem",
      },
      transitionTimingFunction: {
        // One easing language across the app (calm, slightly springy out-curve).
        swift: "cubic-bezier(0.22, 1, 0.36, 1)",
        "swift-in": "cubic-bezier(0.4, 0, 0.2, 1)",
      },
      transitionDuration: {
        fast: "120ms",
        base: "180ms",
        slow: "280ms",
      },
      animation: {
        "fade-in": "fadeIn 0.18s cubic-bezier(0.22,1,0.36,1)",
        "fade-in-up": "fadeInUp 0.22s cubic-bezier(0.22,1,0.36,1)",
        "scale-in": "scaleIn 0.14s cubic-bezier(0.22,1,0.36,1)",
        "slide-in-right": "slideInRight 0.28s cubic-bezier(0.22,1,0.36,1)",
        "slide-in-left": "slideInLeft 0.28s cubic-bezier(0.22,1,0.36,1)",
        "pulse-subtle": "pulseSubtle 2s ease-in-out infinite",
        shimmer: "shimmer 1.4s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        fadeInUp: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.96)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        slideInRight: {
          "0%": { transform: "translateX(12px)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
        slideInLeft: {
          "0%": { transform: "translateX(-12px)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
        pulseSubtle: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.55" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      boxShadow: {
        // Warm-tinted elevation scale (not cold/black) — calm depth.
        e1: "0 1px 2px hsl(30 12% 4% / 0.30), 0 1px 1px hsl(30 12% 4% / 0.22)",
        e2: "0 2px 6px hsl(30 12% 4% / 0.34), 0 1px 2px hsl(30 12% 4% / 0.24)",
        e3: "0 8px 24px hsl(30 12% 4% / 0.40), 0 2px 6px hsl(30 12% 4% / 0.28)",
        glow: "0 0 0 1px hsl(var(--primary) / 0.35), 0 0 18px hsl(var(--primary) / 0.18)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
