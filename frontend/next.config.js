/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // /api/* is proxied by app/api/[...path]/route.ts so upstream 404s
  // (cross-tenant contract GET) are forwarded instead of becoming 500s.
}

module.exports = nextConfig
