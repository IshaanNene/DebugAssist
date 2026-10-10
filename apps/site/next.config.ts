import type { NextConfig } from "next";

// Static export for GitHub Pages. SITE_BASE_PATH is "/DebugAssist" when served from
// https://<user>.github.io/DebugAssist; empty for local preview or a custom domain.
const basePath = process.env.SITE_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  output: "export",
  basePath,
  trailingSlash: true,
  images: { unoptimized: true },
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
};

export default nextConfig;
