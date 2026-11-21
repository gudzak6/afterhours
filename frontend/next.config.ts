import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const backend = process.env.BACKEND_URL?.replace(/\/$/, "");
    // On Netlify, a rewrite to the local coaching server runs at the edge and
    // returns 500 before the app can answer. Leave those paths to the app routes.
    if (!backend && process.env.NETLIFY) return [];
    return [
      {
        source: "/backend/:path*",
        destination: `${backend || "http://127.0.0.1:8000"}/:path*`,
      },
    ];
  },
};

export default nextConfig;
