import { fileURLToPath } from 'url';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  // Allow an isolated build dir (e.g. for a spare dev server on another port)
  // so it never collides with the primary dev server's `.next`.
  ...(process.env.NEXT_DIST_DIR ? { distDir: process.env.NEXT_DIST_DIR } : {}),
  // No build-time API rewrites: the browser talks to the backend directly using
  // URLs injected at runtime (see lib/runtime-config.ts + app/layout.tsx), which
  // keeps the image environment-agnostic — build once, run anywhere.
  webpack: (config) => {
    // digitaljs' root export routes browsers to its full view bundle (jointjs
    // SVG rendering, jquery). The interactive web-sim only needs the headless
    // engine, and the package's exports map doesn't expose it as a subpath —
    // alias the bare specifier to the headless entry (same alias in
    // vitest.config.mts).
    config.resolve.alias = {
      ...config.resolve.alias,
      digitaljs$: fileURLToPath(new URL('./node_modules/digitaljs/lib/circuit.js', import.meta.url)),
    };
    return config;
  },
};

export default nextConfig;
