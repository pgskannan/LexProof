/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL
    return apiUrl
      ? [{ source: '/api/:path*', destination: `${apiUrl}/api/:path*` }]
      : []
  },
}

module.exports = nextConfig
