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
};

export default nextConfig;
