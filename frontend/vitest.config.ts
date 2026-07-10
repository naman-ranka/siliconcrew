import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

// Tier-1 verification: component/store tests in jsdom — no browser required.
// Run: npm run test
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./test/setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules", ".next", "e2e"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
      // Headless digitaljs engine — same alias as next.config.mjs (the root
      // export's browser condition would pull the jointjs view bundle).
      digitaljs: path.resolve(__dirname, "node_modules/digitaljs/lib/circuit.js"),
    },
  },
});
