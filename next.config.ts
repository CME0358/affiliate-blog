import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    outputFileTracingIncludes: {
      "/sitemap.xml": ["./content/posts/**/*"],
    },
  },
};

export default nextConfig;
