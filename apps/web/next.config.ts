import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    const rawInternal = process.env.INTERNAL_API_URL;
    const backendUrl =
      (rawInternal && rawInternal.startsWith("http") && rawInternal) ||
      (process.env.NODE_ENV === "production"
        ? "http://api:8000"
        : "http://127.0.0.1:8000");

    const base = backendUrl.replace(/\/$/, "");

    return [
      // Match /api/py with no trailing path (e.g. /api/py?foo=bar)
      {
        source: "/api/py",
        destination: `${base}/`,
      },
      // Match /api/py/ and /api/py/anything/...
      {
        source: "/api/py/:path*",
        destination: `${base}/:path*`,
      },
    ];
  },
};

export default nextConfig;
