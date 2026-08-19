import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    const rawInternal = process.env.INTERNAL_API_URL;
    const rawPublic = process.env.NEXT_PUBLIC_API_URL;
    const backendUrl =
      (rawInternal && rawInternal.startsWith("http") && rawInternal) ||
      (rawPublic && rawPublic.startsWith("http") && rawPublic) ||
      (process.env.NODE_ENV === "production" ? "http://api:8000" : "http://127.0.0.1:8000");

    return [
      {
        source: "/api/py/:path*",
        destination: `${backendUrl.replace(/\/$/, "")}/:path*`,
      },
    ];
  },
};

export default nextConfig;
