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
    alias: [
      { find: "@", replacement: path.resolve(__dirname, ".") },
      // Headless digitaljs engine — mirrors next.config.mjs's exact-match
      // `digitaljs$` alias. Regex-exact so `digitaljs/<subpath>` imports are
      // NOT rewritten (a bare-string alias is a prefix match in vite).
      { find: /^digitaljs$/, replacement: path.resolve(__dirname, "node_modules/digitaljs/lib/circuit.js") },
    ],
  },
});
