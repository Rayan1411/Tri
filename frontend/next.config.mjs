// All /api/* calls are proxied to the FastAPI backend, so the browser only talks
// to one origin (cookies just work, no CORS).
const backend =
  process.env.BACKEND_URL ||
  (process.env.BACKEND_HOSTPORT ? `https://stocks-api-hdr9.onrender.com` : "http://127.0.0.1:8000");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: { proxyTimeout: 120000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
