/** @type {import('next').NextConfig} */
const path = require('path')

const nextConfig = {
  output: 'standalone',
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
  webpack(config) {
    config.resolve.alias = { ...config.resolve.alias, '@': path.join(__dirname, 'src') }
    return config
  },
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '**.autoscout24.**' },
      { protocol: 'https', hostname: '**.mobile.de' },
      { protocol: 'https', hostname: '**.leboncoin.fr' },
      { protocol: 'https', hostname: '**.marktplaats.nl' },
      { protocol: 'https', hostname: '**.coches.net' },
      { protocol: 'https', hostname: 'cdn.cardex.eu' },
    ],
  },
  experimental: {
    serverComponentsExternalPackages: ['meilisearch'],
  },
  async rewrites() {
    // API_URL is the internal Docker hostname (server-side proxy).
    // Falls back to NEXT_PUBLIC_API_URL for local development without Docker.
    const apiDest = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'
    return [
      {
        source: '/api/:path*',
        destination: `${apiDest}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
