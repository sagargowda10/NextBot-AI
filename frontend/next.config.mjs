/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  // Same-origin API proxy: the browser calls /api/... on the frontend's own address, and Next.js forwards it to the
  // backend. Works from a phone, another laptop or a public URL without hard-coding hosts or touching CORS.
  // Enabled unless NEXT_PUBLIC_API_URL is set. Backend = BACKEND_INTERNAL_URL (Docker: http://backend:8000),
  // or http://localhost:8000 for `npm run dev` on the host.
  async rewrites() {
    if (process.env.NEXT_PUBLIC_API_URL) return [];
    const backend = process.env.BACKEND_INTERNAL_URL || "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/health/:path*", destination: `${backend}/health/:path*` },
    ];
  },
  async headers() {
    return [{
      source: "/(.*)",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      ],
    }];
  },
};

export default nextConfig;
